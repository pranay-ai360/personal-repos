# influx_utils.py
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
import traceback

# Type hinting imports/classes
from influxdb_client.client.write_api import WriteApi
from influxdb_client.client.query_api import QueryApi
from influxdb_client.client.delete_api import DeleteApi
from influxdb_client import InfluxDBClient, Point, WritePrecision, BucketsApi, DeleteApi
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from fastapi import HTTPException # For raising HTTP errors from utils if needed

from config import settings
# Import necessary Pydantic models for type hints and timezone
from models import PriceData, EventData, PHT # Import PHT timezone

# --- InfluxDB Client Initialization ---
client: Optional[InfluxDBClient] = None
write_api: Optional[WriteApi] = None
query_api: Optional[QueryApi] = None
delete_api: Optional[DeleteApi] = None
try:
    client = InfluxDBClient( url=settings.influxdb_url, token=settings.influxdb_token, org=settings.influxdb_org, timeout=60_000)
    if not client.ping(): client = None; print("!!! Initial InfluxDB ping failed.")
    else:
        write_api = client.write_api(write_options=SYNCHRONOUS); query_api = client.query_api(); delete_api = client.delete_api()
        print(f"InfluxDB client initialized for org '{settings.influxdb_org}', bucket '{settings.influxdb_bucket}'")
        try: # Bucket check
            buckets_api = BucketsApi(client);
            if not buckets_api.find_bucket_by_name(settings.influxdb_bucket): print(f"Warning: Bucket '{settings.influxdb_bucket}' not found.")
        except Exception as e: print(f"Error checking bucket: {e}")
except Exception as e: client = None; print(f"!!! Failed to initialize InfluxDB client: {e}")

# --- Price and Event Write Functions (InfluxDB) ---

def write_price(data: PriceData):
    """Writes price data to InfluxDB, storing derived UTC and PHT ISO strings as fields."""
    if not write_api: raise HTTPException(status_code=503, detail="InfluxDB write API not available.")
    utc_dt = data.datetime_utc_derived
    pht_dt = data.datetime_pht_derived
    if not utc_dt or not pht_dt: raise ValueError("Internal Error: Missing derived datetime in PriceData.")
    point = Point(settings.market_measurement).tag("pair", data.pair).field("price", float(data.price)).field("datetime_utc_iso", utc_dt.isoformat()).field("datetime_pht_iso", pht_dt.isoformat()).time(utc_dt, WritePrecision.NS)
    try: write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point)
    except Exception as e: print(f"Error writing price data: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to write price data to InfluxDB.")

def write_event(data: EventData):
    """Writes portfolio event data to InfluxDB, storing derived UTC and PHT ISO strings as fields."""
    if not write_api: raise HTTPException(status_code=503, detail="InfluxDB write API not available.")
    utc_dt = data.datetime_utc_derived
    pht_dt = data.datetime_pht_derived
    if not utc_dt or not pht_dt: raise ValueError("Internal Error: Missing derived datetime in EventData.")
    point = Point(settings.portfolio_events_measurement).tag("assetPortfolioID", data.assetPortfolioID).tag("pair", data.pair).field("event", data.event.value).field("quantity", float(data.quantity)).field("value", float(data.value)).field("datetime_utc_iso", utc_dt.isoformat()).field("datetime_pht_iso", pht_dt.isoformat()).time(utc_dt, WritePrecision.NS)
    if data.orderID: point.tag("orderID", data.orderID)
    try: write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point); print(f"Written Event: Portfolio={data.assetPortfolioID}, Pair={data.pair}, Event={data.event.value}, Qty={data.quantity}, Val={data.value}, Time={utc_dt}")
    except Exception as e: print(f"Error writing event data for {data.assetPortfolioID}: {e}"); traceback.print_exc(); raise HTTPException(status_code=500, detail="Failed to write event data to InfluxDB.")


# --- Raw Data Fetch for Calculation (InfluxDB) ---

def query_raw_data_for_calc(assetPortfolioID: str, pair: str, end_dt_utc: datetime, query_api: QueryApi) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetches market data and portfolio events. Parses datetime_pht_iso and sets it as a PHT-aware index."""
    if not query_api: raise ConnectionError("InfluxDB query API not initialized.") # Raise non-HTTP error for background task
    end_dt_str = (end_dt_utc + pd.Timedelta(microseconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%fZ') # Correct format

    flux_query_market = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: 0, stop: time(v: "{end_dt_str}"))
      |> filter(fn: (r) => r["_measurement"] == "{settings.market_measurement}")
      |> filter(fn: (r) => r["pair"] == "{pair}")
      |> filter(fn: (r) => r["_field"] == "price" or r["_field"] == "datetime_pht_iso")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "price", "datetime_pht_iso"])
      |> sort(columns: ["_time"])
    '''
    flux_query_events = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: 0, stop: time(v: "{end_dt_str}"))
      |> filter(fn: (r) => r["_measurement"] == "{settings.portfolio_events_measurement}")
      |> filter(fn: (r) => r["assetPortfolioID"] == "{assetPortfolioID}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "datetime_pht_iso", "event", "quantity", "value", "orderID"])
      |> sort(columns: ["_time"])
    '''
    try:
        # Process Market Data
        market_df_result = query_api.query_data_frame(query=flux_query_market)
        market_df = market_df_result if isinstance(market_df_result, pd.DataFrame) else pd.DataFrame()
        if not market_df.empty and 'datetime_pht_iso' in market_df.columns:
            market_df['datetime_pht'] = pd.to_datetime(market_df['datetime_pht_iso'], errors='coerce', utc=True) # Assume stored ISO is UTC or has offset
            market_df['datetime_pht'] = market_df['datetime_pht'].dt.tz_convert(PHT)
            market_df = market_df.dropna(subset=['datetime_pht'])
            if not market_df.empty:
                market_df['_time_utc'] = pd.to_datetime(market_df['_time'], utc=True)
                market_df = market_df.set_index('datetime_pht', drop=False)
                market_df.index.name = 'pht_time_index'
                market_df['price'] = pd.to_numeric(market_df['price'], errors='coerce')
            else: market_df = pd.DataFrame(columns=['price', 'datetime_pht', '_time_utc']); market_df.index.name = 'pht_time_index'
        else: market_df = pd.DataFrame(columns=['price', 'datetime_pht', '_time_utc']); market_df.index.name = 'pht_time_index'

        # Process Events Data
        events_df_result = query_api.query_data_frame(query=flux_query_events)
        events_df = events_df_result if isinstance(events_df_result, pd.DataFrame) else pd.DataFrame()
        if not events_df.empty and 'datetime_pht_iso' in events_df.columns:
            events_df['datetime_pht'] = pd.to_datetime(events_df['datetime_pht_iso'], errors='coerce', utc=True) # Assume stored ISO is UTC or has offset
            events_df['datetime_pht'] = events_df['datetime_pht'].dt.tz_convert(PHT)
            events_df = events_df.dropna(subset=['datetime_pht'])
            if not events_df.empty:
                events_df['_time_utc'] = pd.to_datetime(events_df['_time'], utc=True)
                events_df = events_df.set_index('datetime_pht', drop=False)
                events_df.index.name = 'pht_time_index'
                events_df['quantity'] = pd.to_numeric(events_df['quantity'], errors='coerce')
                events_df['value'] = pd.to_numeric(events_df['value'], errors='coerce')
            else: events_df = pd.DataFrame(columns=['event', 'quantity', 'value', 'orderID', 'datetime_pht', '_time_utc']); events_df.index.name = 'pht_time_index'
        else: events_df = pd.DataFrame(columns=['event', 'quantity', 'value', 'orderID', 'datetime_pht', '_time_utc']); events_df.index.name = 'pht_time_index'

        market_df = market_df.drop(columns=['datetime_pht_iso', '_time'], errors='ignore')
        events_df = events_df.drop(columns=['datetime_pht_iso', '_time'], errors='ignore')

        return market_df, events_df
    except Exception as e: print(f"Error fetching/processing raw data for {assetPortfolioID}/{pair}: {e}"); traceback.print_exc(); raise

# --- Query Pre-calculated Summary (InfluxDB) ---
def query_portfolio_summary(assetPortfolioID: str, start_dt_utc_req: datetime, end_dt_utc_req: datetime, query_api: QueryApi) -> pd.DataFrame:
    if not query_api: raise ConnectionError("InfluxDB query API not initialized.") # Raise non-HTTP error for background task
    # Calculate UTC range based on PHT day boundaries
    start_dt_pht_req = start_dt_utc_req.astimezone(PHT); end_dt_pht_req = end_dt_utc_req.astimezone(PHT)
    flux_range_start_pht = start_dt_pht_req.replace(hour=0, minute=0, second=0, microsecond=0)
    flux_range_stop_pht = (end_dt_pht_req + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    flux_range_start_utc = flux_range_start_pht.astimezone(timezone.utc); flux_range_stop_utc = flux_range_stop_pht.astimezone(timezone.utc)
    start_str = flux_range_start_utc.strftime('%Y-%m-%dT%H:%M:%SZ'); end_str = flux_range_stop_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    flux_query = f'''
    from(bucket: "{settings.influxdb_bucket}")
      |> range(start: time(v: "{start_str}"), stop: time(v: "{end_str}"))
      |> filter(fn: (r) => r["_measurement"] == "{settings.portfolio_summary_measurement}")
      |> filter(fn: (r) => r["assetPortfolioID"] == "{assetPortfolioID}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "AUM", "AVG_cost", "Unrealised_Value", "Realised_Value"])
      |> sort(columns: ["_time"])
    '''
    try:
        summary_result = query_api.query_data_frame(query=flux_query)
        if isinstance(summary_result, pd.DataFrame): return summary_result
        else: return pd.DataFrame()
    except Exception as e: print(f"Error querying summary data for {assetPortfolioID}: {e}"); traceback.print_exc(); raise # Re-raise for query endpoint

# --- Close Client ---
def close_influx_client():
    if client: client.close(); print("InfluxDB client closed.")