# background_jobs.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import pytz
from influxdb_client import Point, WritePrecision
# Type hinting imports
from influxdb_client.client.write_api import WriteApi
from influxdb_client.client.query_api import QueryApi
from influxdb_client.client.delete_api import DeleteApi
from influxdb_client.client.exceptions import InfluxDBError
import traceback

from config import settings
# Import the updated raw data fetch function
from influx_utils import query_raw_data_for_calc
from models import EventType, PHT # Import PHT timezone

def calculate_and_store_portfolio(
    cpmID: str, assetPortfolioID: str, pair: str,
    query_api: QueryApi, write_api: WriteApi, delete_api: DeleteApi):
    """
    Calculates and stores daily portfolio summary based on PHT days.
    Fetches raw data from InfluxDB, calculates, deletes old InfluxDB summary, writes new InfluxDB summary.
    """
    try:
        print(f"[BG Job {assetPortfolioID}/{pair}] Starting calculation...")
        end_fetch_date_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # Fetches data, index is now PHT-aware 'pht_time_index'
        market_df, events_df = query_raw_data_for_calc(assetPortfolioID, pair, end_fetch_date_utc, query_api)

        # --- Date Range Determination based on PHT index ---
        all_pht_indices = []
        if not market_df.empty: all_pht_indices.append(market_df.index.to_series())
        if not events_df.empty: all_pht_indices.append(events_df.index.to_series())
        if not all_pht_indices: print(f"[BG Job {assetPortfolioID}/{pair}] No PHT indices found. Skipping."); return
        all_pht_times = pd.concat(all_pht_indices)
        min_calc_date_pht = all_pht_times.min().normalize()
        latest_data_date_pht = all_pht_times.max().normalize()
        today_pht_sod = datetime.now(PHT).replace(hour=0, minute=0, second=0, microsecond=0) # Use replace()
        max_calc_date_pht = max(latest_data_date_pht, today_pht_sod)
        if min_calc_date_pht > max_calc_date_pht: print(f"[BG Job {assetPortfolioID}/{pair}] Min PHT date > Max PHT date. Skipping."); return
        all_calc_dates_pht = pd.date_range(start=min_calc_date_pht, end=max_calc_date_pht, freq='D', tz=PHT)
        # --- End PHT Date Range ---

        portfolio_history_points = []
        current_aum = 0.0; total_cost_basis = 0.0; current_avg_cost = 0.0; last_market_price = np.nan

        print(f"[BG Job {assetPortfolioID}/{pair}] Calculating daily summaries from {min_calc_date_pht.date()} to {max_calc_date_pht.date()} PHT...")

        # --- Ensure market_df index is sorted for .asof ---
        if not market_df.empty and not market_df.index.is_monotonic_increasing:
            print(f"Warning: Market data index for {pair} not sorted. Sorting...")
            market_df = market_df.sort_index()
        # ---

        # --- Calculation Loop (Iterating by PHT Day) ---
        for current_day_pht_start in all_calc_dates_pht:
            next_day_pht_start = current_day_pht_start + timedelta(days=1)

            # --- Get market price using PHT day end on PHT index ---
            market_price_today = np.nan
            if not market_df.empty:
                lookup_time_pht_end_of_day = next_day_pht_start - timedelta(microseconds=1)
                try:
                    # Use .asof on the sorted PHT index
                    market_price_today = market_df['price'].asof(lookup_time_pht_end_of_day)
                except Exception as price_lookup_e:
                    print(f"Warning: Price lookup using 'asof' failed for {current_day_pht_start.date()}. Error: {price_lookup_e}. Using last known price.")
                    market_price_today = last_market_price
            # --- End Price Lookup ---

            if pd.isna(market_price_today): market_price_today = last_market_price
            else: last_market_price = market_price_today

            # Filter events using PHT index within the current PHT day
            events_today = events_df[
                (events_df.index >= current_day_pht_start) &
                (events_df.index < next_day_pht_start) # Exclusive end
            ]

            daily_realised_value_proceeds = 0.0

            # Process events
            if not events_today.empty:
                events_to_process = events_today
                if '_time_utc' in events_today.columns: events_to_process = events_today.sort_values('_time_utc')
                else: events_to_process = events_today.sort_index()

                for _, event in events_to_process.iterrows():
                     event_type = event.get('event', 'unknown'); quantity = float(event.get('quantity', 0.0)); value = float(event.get('value', 0.0))
                     # ... (Event logic remains the same - BUY, SELL, RECEIVE, SEND, etc.) ...
                     if event_type == EventType.BUY.value: current_aum += quantity; total_cost_basis += value
                     elif event_type == EventType.SELL.value:
                         sell_quantity = abs(quantity); daily_realised_value_proceeds += abs(value)
                         if current_aum > 1e-9:
                             sell_quantity_adjusted = min(sell_quantity, current_aum); cost_of_sold_units = sell_quantity_adjusted * current_avg_cost
                             current_aum -= sell_quantity_adjusted; total_cost_basis -= cost_of_sold_units
                     # ... other event types ...
                     if current_aum < 1e-9: current_aum = 0.0; total_cost_basis = 0.0; current_avg_cost = 0.0
                     else: current_avg_cost = (total_cost_basis / current_aum) if current_aum > 1e-9 else 0.0

            # --- Prepare Summary Point ---
            report_avg_cost = current_avg_cost
            unrealised_value = (current_aum * market_price_today) if not pd.isna(market_price_today) and current_aum > 0 else 0.0
            point_time_utc = current_day_pht_start.astimezone(timezone.utc) # Timestamp is UTC equivalent of PHT day start
            point = Point(settings.portfolio_summary_measurement).tag("cpmID", cpmID).tag("assetPortfolioID", assetPortfolioID).tag("pair", pair).field("AUM", float(current_aum)).field("AVG_cost", float(report_avg_cost if current_aum > 0 else 0.0)).field("Realised_Value", float(daily_realised_value_proceeds)).time(point_time_utc, WritePrecision.S)
            if unrealised_value is not None and not np.isnan(unrealised_value): point.field("Unrealised_Value", float(unrealised_value))
            portfolio_history_points.append(point)
        # --- End Calculation Loop ---

        # --- Delete & Write (InfluxDB Summary) ---
        if portfolio_history_points:
            try: # Delete old InfluxDB summary data
                delete_start="1970-01-01T00:00:00Z"
                delete_stop = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') # Use Z format for delete
                predicate=f'_measurement="{settings.portfolio_summary_measurement}" AND assetPortfolioID="{assetPortfolioID}"'
                print(f"[BG Job {assetPortfolioID}/{pair}] Deleting summary: {predicate}");
                if delete_api: delete_api.delete(start=delete_start, stop=delete_stop, predicate=predicate, bucket=settings.influxdb_bucket, org=settings.influxdb_org); print("Deletion attempted.")
                else: print("Delete API NA.")
            except InfluxDBError as del_e_influx: print(f"InfluxDB Error deleting summary: {del_e_influx}"); traceback.print_exc()
            except Exception as del_e: print(f"General Error deleting summary: {del_e}"); traceback.print_exc()

            try: # Write new InfluxDB summary data
                print(f"[BG Job {assetPortfolioID}/{pair}] Writing {len(portfolio_history_points)} points...");
                if write_api: write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=portfolio_history_points); print("Write successful.")
                else: print("Write API NA.")
            except Exception as write_e: print(f"!!! Write Error: {write_e}"); traceback.print_exc()
        else: print(f"[BG Job {assetPortfolioID}/{pair}] No summary points generated.")

    except Exception as e: print(f"!!! [BG Job {assetPortfolioID}/{pair}] CRITICAL ERROR: {e}"); traceback.print_exc()