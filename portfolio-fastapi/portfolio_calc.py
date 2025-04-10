# portfolio_calc.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import pytz

# Bring PHT timezone here as well, or import from models
PHT = pytz.timezone('Asia/Manila')

def calculate_portfolio_history(
    market_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    start_dt_pht: datetime,
    end_dt_pht: datetime) -> list[dict]:
    """
    Calculates daily portfolio history using Average Cost method based on provided DataFrames.
    Realised Value = Total Proceeds from Sales on that day.
    Filters results between start_dt_pht and end_dt_pht.

    Args:
        market_df: DataFrame with market prices, indexed by UTC datetime.
        trades_df: DataFrame with trades, indexed by UTC datetime.
        start_dt_pht: The requested start datetime (PHT timezone).
        end_dt_pht: The requested end datetime (PHT timezone).

    Returns:
        A list of dictionaries, each representing a day's portfolio state
        within the requested date range (inclusive).
    """
    portfolio_history = []

    # Ensure inputs are timezone-aware (should be UTC from influx_utils)
    if not market_df.empty and market_df.index.tz is None: market_df.index = market_df.index.tz_localize(timezone.utc)
    if not trades_df.empty and trades_df.index.tz is None: trades_df.index = trades_df.index.tz_localize(timezone.utc)

    # Determine the date range for calculation based on available data
    # Concatenate index only if DataFrames are not empty
    all_times_list = []
    if not market_df.empty:
        all_times_list.append(market_df.index.to_series())
    if not trades_df.empty:
        all_times_list.append(trades_df.index.to_series())

    if not all_times_list:
        print("No market or trade data available for calculation.")
        return [] # No data to calculate

    all_times = pd.concat(all_times_list)

    # Use floor('D') on the Pandas Timestamps from the data
    min_calc_date_utc = all_times.min().floor('D')
    max_calc_date_utc_from_data = all_times.max().floor('D') # Use floor here

    # Convert requested end date to UTC standard datetime
    end_dt_utc = end_dt_pht.astimezone(timezone.utc)

    # --- FIX: Use datetime methods to get start of day for end_dt_utc ---
    # Get the start of the day (midnight) for the requested end date in UTC
    end_dt_utc_start_of_day = end_dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Determine the overall maximum calculation date (latest of data or requested end date)
    max_calc_date_utc = max(max_calc_date_utc_from_data, end_dt_utc_start_of_day)
    # --- END FIX ---

    # Create a full date range (daily) in UTC for iteration
    # Ensure the max calculation date is included
    all_calc_dates_utc = pd.date_range(start=min_calc_date_utc, end=max_calc_date_utc, freq='D', tz=timezone.utc)

    current_aum = 0.0 # Use float for potential fractional shares
    total_cost_basis = 0.0
    current_avg_cost = 0.0
    last_market_price = np.nan

    print(f"Calculating portfolio from {min_calc_date_utc.date()} to {max_calc_date_utc.date()} UTC...")

    # --- Loop through each DAY in the calculation range ---
    for current_day_utc_start in all_calc_dates_utc:
        # Define end of day precisely (start of next day minus one nanosecond)
        current_day_utc_end = current_day_utc_start + timedelta(days=1) - timedelta(nanoseconds=1)

        # Get market price for the *end* of the current day
        # Use asof for the latest price ON or BEFORE the end of the day timestamp
        if not market_df.empty:
             market_price_today = market_df.price.asof(current_day_utc_end)
        else:
             market_price_today = np.nan


        if pd.isna(market_price_today):
            market_price_today = last_market_price # Use previous day's price if current is missing
        else:
            last_market_price = market_price_today # Update last known price

        # Get trades that occurred *on* this specific day (Index is UTC)
        trades_today = trades_df[
            (trades_df.index >= current_day_utc_start) &
            (trades_df.index <= current_day_utc_end) # Inclusive end of day
        ]

        daily_realised_value_proceeds = 0.0

        # Process trades chronologically within the day
        if not trades_today.empty:
            for trade_time, trade in trades_today.sort_index().iterrows():
                if trade['trade'] == 'Buy':
                    buy_quantity = float(trade['quantity'])
                    buy_total_value = float(trade['total_value'])
                    total_cost_basis += buy_total_value
                    current_aum += buy_quantity
                    current_avg_cost = (total_cost_basis / current_aum) if current_aum > 1e-9 else 0.0 # Avoid division by zero/small numbers

                elif trade['trade'] == 'Sell':
                    sell_quantity = float(trade['quantity'])
                    sell_proceeds = float(trade['total_value'])
                    daily_realised_value_proceeds += sell_proceeds

                    # Update AUM and Cost Basis
                    if current_aum < 1e-9:
                        print(f"Warning on {current_day_utc_start.date()}: Sell trade when AUM near zero.")
                        continue

                    sell_quantity_adjusted = min(sell_quantity, current_aum) # Don't sell more than held
                    if sell_quantity > current_aum + 1e-9: # Add tolerance
                         print(f"Warning on {current_day_utc_start.date()}: Attempted sell {sell_quantity} > AUM {current_aum}. Selling {sell_quantity_adjusted}.")


                    cost_of_sold_units = sell_quantity_adjusted * current_avg_cost
                    current_aum -= sell_quantity_adjusted
                    total_cost_basis -= cost_of_sold_units

                    if current_aum < 1e-9:
                        current_aum = 0.0
                        total_cost_basis = 0.0
                        current_avg_cost = 0.0


        # --- Calculate end-of-day metrics ---
        report_avg_cost = current_avg_cost
        unrealised_value = (current_aum * market_price_today) if not pd.isna(market_price_today) and current_aum > 0 else 0.0
        if pd.isna(unrealised_value):
            unrealised_value = None # Explicitly None if calculation failed

        # Store results with the UTC timestamp representing the start of the day
        portfolio_history.append({
            'datetime': current_day_utc_start, # Store day's timestamp (UTC start)
            'AUM': current_aum,
            'avg_cost': report_avg_cost if current_aum > 0 else 0.0,
            'unrealised_value': unrealised_value,
            'realised_value': daily_realised_value_proceeds, # Use accumulated proceeds
        })

    # --- Filter results to the requested PHT range ---
    # Convert request start/end PHT to UTC start of day for comparison
    start_dt_utc_sod = start_dt_pht.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # end_dt_utc_sod was already calculated above
    end_dt_utc_sod = end_dt_utc_start_of_day

    filtered_history = [
        record for record in portfolio_history
        if record['datetime'] >= start_dt_utc_sod and record['datetime'] <= end_dt_utc_sod
    ]

    # Convert the filtered UTC datetimes back to PHT for the response
    for record in filtered_history:
        record['datetime'] = record['datetime'].astimezone(PHT)

    print(f"Calculation complete. Returning {len(filtered_history)} records for the requested range.")
    return filtered_history