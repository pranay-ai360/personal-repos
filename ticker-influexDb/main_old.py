import os
from datetime import datetime, timezone, timedelta
import re
import uvicorn
# Added Query for query parameters, Optional for optional parameters
from fastapi import FastAPI, HTTPException, status, Body, Query, Path
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import List, Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision, QueryApi
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
# Removed FluxStructureEncoder, using direct processing
import json # For error body parsing

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# 1) -------- ENVIRONMENT VARIABLES FOR INFLUXDB --------
INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "my-super-secret-token")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "my-bucket")

# Define the target ticker globally or make it configurable
TARGET_TICKER_ID = "SOL-PHP" # Used by /get_candles, can be overridden in /ticker_data

# Define PHT timezone (UTC+8)
PHT = timezone(timedelta(hours=8), 'PHT')

# --- Helper Function for Interval Parsing ---
def parse_influx_interval(interval_str: str) -> timedelta:
    """Parses InfluxDB duration string into Python timedelta. Handles s, m, h, d, w."""
    match = re.match(r"(\d+)([smhdw])", interval_str)
    if not match:
        raise ValueError(f"Invalid interval format: '{interval_str}'. Use Ns, Nm, Nh, Nd, Nw.")

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 's': return timedelta(seconds=value)
    elif unit == 'm': return timedelta(minutes=value)
    elif unit == 'h': return timedelta(hours=value)
    elif unit == 'd': return timedelta(days=value)
    elif unit == 'w': return timedelta(weeks=value)
    else: raise ValueError(f"Unsupported interval unit: '{unit}'")

# --- Pydantic Models ---

# Model for writing individual ticker data
class TickerDataWrite(BaseModel):
    DateTime_UTC: datetime = Field(...)
    TICKER_ID: str
    PRICE: float

    @field_validator('DateTime_UTC')
    @classmethod
    def dt_must_be_utc(cls, v):
        if v.tzinfo is None or v.tzinfo.utcoffset(v) != timezone.utc.utcoffset(None):
             if v.tzinfo is None:
                 print(f"Warning: Received naive datetime {v}, assuming UTC.")
                 return v.replace(tzinfo=timezone.utc)
             raise ValueError('DateTime_UTC must be timezone-aware and UTC (use Z suffix or +00:00)')
        return v

# Model for the /get_candles request body
class CandleRequest(BaseModel):
    start_utc: datetime
    end_utc: datetime
    interval: str = Field(..., pattern=r"^\d+[smhdw]$")

    @field_validator('start_utc', 'end_utc')
    @classmethod
    def dt_must_be_utc_candle(cls, v: datetime, info: ValidationInfo): # Renamed validator
        if v.tzinfo is None or v.tzinfo.utcoffset(v) != timezone.utc.utcoffset(None):
            if v.tzinfo is None:
                print(f"Warning: Received naive {info.field_name} {v}, assuming UTC.")
                return v.replace(tzinfo=timezone.utc)
            raise ValueError(f'{info.field_name} must be timezone-aware and UTC')
        return v

    @field_validator('interval')
    @classmethod
    def validate_interval_parseable(cls, v):
        try: parse_influx_interval(v)
        except ValueError as e: raise ValueError(f"Invalid interval: {e}")
        return v

# Model for a single candle in the /get_candles response
class Candle(BaseModel):
    open: str
    close: str
    high: str
    low: str
    opentime_pht: datetime
    closetime_pht: datetime

# Model for the /get_candles response body
class CandleResponse(BaseModel):
    candles: List[Candle]

# --- NEW Models for /ticker_data ---
# Model for a single raw data point in the response
class TickerDataPoint(BaseModel):
    timestamp_utc: datetime
    price: float

# Model for the /ticker_data response body
class AllTickerDataResponse(BaseModel):
    data: List[TickerDataPoint]
    ticker_id: str
    count: int

# --- FastAPI Application ---
app = FastAPI(
    title="InfluxDB Ticker API",
    description="API to write and query ticker data in InfluxDB",
    version="1.2.0", # Incremented version
)

# --- API Endpoints ---

@app.post(
    "/write_ticker",
    summary="Write Ticker Data",
    # ... (rest of decorator and function as before) ...
    tags=["Write"],
)
async def write_ticker_data(data: TickerDataWrite):
    """Writes a single price point."""
    print(f"Received data for writing: {data.dict()}")
    point = (
        Point("ticker_price")
        .tag("ticker_id", data.TICKER_ID)
        .field("price", data.PRICE)
        .time(data.DateTime_UTC, WritePrecision.NS)
    )
    print(f"Prepared InfluxDB Point: {point.to_line_protocol()}")
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            try:
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                print(f"Successfully wrote point to bucket '{INFLUX_BUCKET}'.")
                timestamp_aware = data.DateTime_UTC.astimezone(timezone.utc)
                timestamp_str = timestamp_aware.isoformat(timespec='seconds').replace('+00:00', 'Z')
                success_message = f"Inserted data for {data.TICKER_ID} at {timestamp_str}"
                return {"status": "success", "message": success_message}
            except ApiException as e:
                print(f"InfluxDB API Error writing: Status={e.status}, Body={e.body}")
                error_detail = f"Error writing to InfluxDB bucket '{INFLUX_BUCKET}': {e.reason} ({e.status})"
                if e.status == 401: error_detail = "InfluxDB authentication failed. Check INFLUX_TOKEN."
                elif e.status == 404: error_detail = f"InfluxDB bucket '{INFLUX_BUCKET}' or org '{INFLUX_ORG}' not found or token lacks permission."
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
            except Exception as e:
                print(f"Generic error during write: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error writing: {e}")
    except Exception as e:
        print(f"Error connecting to InfluxDB for write: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not connect to InfluxDB: {e}")


@app.post(
    "/get_candles",
    summary="Get OHLC Candle Data",
    description=f"Retrieves aggregated OHLC candle data for the specific ticker **{TARGET_TICKER_ID}**.",
    response_model=CandleResponse,
    tags=["Query"],
)
async def get_candle_data(request: CandleRequest = Body(...)):
    """Calculates and returns OHLC candles for the default ticker."""
    print(f"Received candle request: {request.dict()}")
    if request.start_utc >= request.end_utc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_utc must be before end_utc")
    try: interval_delta = parse_influx_interval(request.interval)
    except ValueError as e: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Use the query with chained joins from the previous correction
    flux_query = """
        import "strings"
        windowIntervalDuration = duration(v: windowInterval)
        base = from(bucket: bucket)
          |> range(start: timeRangeStart, stop: timeRangeStop)
          |> filter(fn: (r) => r._measurement == "ticker_price")
          |> filter(fn: (r) => r.ticker_id == tickerID)
          |> filter(fn: (r) => r._field == "price")
        opens = base |> aggregateWindow(every: windowIntervalDuration, fn: first, createEmpty: false) |> map(fn: (r) => ({ _time: r._time, open: r._value }))
        highs = base |> aggregateWindow(every: windowIntervalDuration, fn: max, createEmpty: false) |> map(fn: (r) => ({ _time: r._time, high: r._value }))
        lows = base |> aggregateWindow(every: windowIntervalDuration, fn: min, createEmpty: false) |> map(fn: (r) => ({ _time: r._time, low: r._value }))
        closes = base |> aggregateWindow(every: windowIntervalDuration, fn: last, createEmpty: false) |> map(fn: (r) => ({ _time: r._time, close: r._value }))
        join1 = join(tables: {left: opens, right: highs}, on: ["_time"], method: "inner")
        join2 = join(tables: {left: join1, right: lows}, on: ["_time"], method: "inner")
        join3 = join(tables: {left: join2, right: closes}, on: ["_time"], method: "inner")
        join3
          |> map(fn: (r) => ({ _time: r._time, open: r.open, high: r.high, low: r.low, close: r.close }))
          |> sort(columns: ["_time"])
          |> yield(name: "ohlc_candles")
    """
    query_params = {
        "bucket": INFLUX_BUCKET,
        "timeRangeStart": request.start_utc,
        "timeRangeStop": request.end_utc,
        "windowInterval": request.interval,
        "tickerID": TARGET_TICKER_ID # Hardcoded for this endpoint
    }
    candles_list: List[Candle] = []
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            query_api = client.query_api()
            print(f"Executing Flux query for candles with params: { {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in query_params.items()} }")
            result = query_api.query(query=flux_query, params=query_params)
            print(f"InfluxDB candle query executed. Processing results...")
            for table in result:
                for record in table.records:
                    opentime_utc = record.get_time()
                    if opentime_utc.tzinfo is None: opentime_utc = opentime_utc.replace(tzinfo=timezone.utc)
                    else: opentime_utc = opentime_utc.astimezone(timezone.utc)
                    closetime_utc = opentime_utc + interval_delta
                    opentime_pht = opentime_utc.astimezone(PHT)
                    closetime_pht = closetime_utc.astimezone(PHT)
                    o, h, l, c = record.values.get('open'), record.values.get('high'), record.values.get('low'), record.values.get('close')
                    if None in [o, h, l, c]:
                        print(f"Warning: Skipping candle record at {opentime_utc} due to missing OHLC values.")
                        continue
                    try:
                        candle = Candle(open=f"{o:.2f}", high=f"{h:.2f}", low=f"{l:.2f}", close=f"{c:.2f}", opentime_pht=opentime_pht, closetime_pht=closetime_pht)
                        candles_list.append(candle)
                    except (TypeError, ValueError) as format_err:
                        print(f"Warning: Skipping candle record at {opentime_utc} due to formatting error: {format_err}.")
                        continue
            print(f"Processed {len(candles_list)} candle records.")
            return CandleResponse(candles=candles_list)
    except ApiException as e:
        # ... (rest of error handling as before) ...
        print(f"InfluxDB API Error querying candles: Status={e.status}, Body={e.body}, Headers={e.headers}")
        error_detail = f"Error querying InfluxDB candles: {e.reason} ({e.status})"
        if e.status == 400:
             try: error_detail = f"InfluxDB Bad Request (400): {json.loads(e.body).get('message', e.reason)}"
             except: pass
        elif e.status == 401: error_detail = "InfluxDB authentication failed. Check INFLUX_TOKEN."
        elif e.status == 404: error_detail = f"InfluxDB Not Found (404). Check org '{INFLUX_ORG}' or bucket '{INFLUX_BUCKET}'."
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    except Exception as e:
        print(f"Generic error during candle query/processing: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during candle query: {e}")


# --- NEW ENDPOINT ---
@app.get(
    "/ticker_data/{ticker_id}",
    summary="Get Raw Ticker Data",
    description="Retrieves raw price data points for a specified ticker ID within an optional time range.",
    response_model=AllTickerDataResponse, # Specify the response structure
    tags=["Query"],
)
async def get_all_ticker_data(
    ticker_id: str = Path(..., description="The Ticker ID to query (e.g., SOL-PHP)", example="SOL-PHP"),
    start_utc: Optional[datetime] = Query(None, description="Optional start timestamp (ISO 8601 format, UTC recommended). Defaults to -7d if not provided.", example="2024-02-01T00:00:00Z"),
    end_utc: Optional[datetime] = Query(None, description="Optional end timestamp (ISO 8601 format, UTC recommended). Defaults to now() if not provided.", example="2024-02-02T00:00:00Z"),
    limit: int = Query(1000, description="Maximum number of data points to return.", gt=0, le=10000) # Default limit, with bounds
):
    """
    Retrieves raw timestamp and price data points for the specified ticker.
    Provides optional time range filtering and limits the number of results.
    """
    print(f"Received raw data request for {ticker_id}: start={start_utc}, end={end_utc}, limit={limit}")

    # Basic validation for timestamps if both provided
    if start_utc and end_utc and start_utc >= end_utc:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_utc must be before end_utc if both are provided"
        )

    # Ensure timestamps are UTC if provided
    query_params = { "bucket": INFLUX_BUCKET, "tickerID": ticker_id }
    range_start_flux = "-7d" # Default range start if not provided
    range_stop_flux = "now()" # Default range stop if not provided

    if start_utc:
        if start_utc.tzinfo is None or start_utc.tzinfo.utcoffset(start_utc) != timezone.utc.utcoffset(None):
             start_utc = start_utc.replace(tzinfo=timezone.utc) # Assume UTC if naive
        query_params["timeRangeStart"] = start_utc
        range_start_flux = "timeRangeStart" # Use parameter name in query

    if end_utc:
        if end_utc.tzinfo is None or end_utc.tzinfo.utcoffset(end_utc) != timezone.utc.utcoffset(None):
             end_utc = end_utc.replace(tzinfo=timezone.utc) # Assume UTC if naive
        query_params["timeRangeStop"] = end_utc
        range_stop_flux = "timeRangeStop" # Use parameter name in query

    query_params["limitParam"] = limit

    # Define the Flux Query
    flux_query = f"""
        from(bucket: bucket)
          |> range(start: {range_start_flux}, stop: {range_stop_flux})
          |> filter(fn: (r) => r._measurement == "ticker_price")
          |> filter(fn: (r) => r.ticker_id == tickerID)
          |> filter(fn: (r) => r._field == "price")
          |> keep(columns: ["_time", "_value"]) // Only keep time and price value
          |> sort(columns: ["_time"], desc: false) // Sort ascending
          |> limit(n: limitParam) // Apply limit
          |> yield(name: "raw_data")
    """

    data_points_list: List[TickerDataPoint] = []

    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            query_api = client.query_api()
            # Log carefully - avoid logging sensitive tokens if they were in params
            log_params = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in query_params.items()}
            print(f"Executing Flux query for raw data with params: {log_params}")
            print(f"Flux Query:\n{flux_query}") # Log the generated query

            result = query_api.query(query=flux_query, params=query_params)

            print(f"InfluxDB raw data query executed. Processing results...")

            # Process the results
            for table in result:
                for record in table.records:
                    ts_utc = record.get_time()
                    if ts_utc.tzinfo is None: ts_utc = ts_utc.replace(tzinfo=timezone.utc)
                    else: ts_utc = ts_utc.astimezone(timezone.utc)

                    price = record.get_value()

                    if price is None: # Should not happen with _field filter, but check
                        print(f"Warning: Skipping raw data record at {ts_utc} due to missing price value.")
                        continue

                    try:
                        # Ensure price is float
                        price_float = float(price)
                        data_points_list.append(
                            TickerDataPoint(timestamp_utc=ts_utc, price=price_float)
                        )
                    except (TypeError, ValueError) as format_err:
                         print(f"Warning: Skipping raw data record at {ts_utc} due to price formatting error: {format_err}. Value: {price}")
                         continue


            print(f"Processed {len(data_points_list)} raw data points.")
            return AllTickerDataResponse(
                data=data_points_list,
                ticker_id=ticker_id,
                count=len(data_points_list)
            )

    except ApiException as e:
        # ... (rest of error handling similar to get_candles) ...
        print(f"InfluxDB API Error querying raw data: Status={e.status}, Body={e.body}, Headers={e.headers}")
        error_detail = f"Error querying InfluxDB raw data: {e.reason} ({e.status})"
        if e.status == 400:
             try: error_detail = f"InfluxDB Bad Request (400): {json.loads(e.body).get('message', e.reason)}"
             except: pass
        elif e.status == 401: error_detail = "InfluxDB authentication failed. Check INFLUX_TOKEN."
        elif e.status == 404: error_detail = f"InfluxDB Not Found (404). Check org '{INFLUX_ORG}' or bucket '{INFLUX_BUCKET}'."
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    except Exception as e:
        print(f"Generic error during raw data query/processing: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during raw data query: {e}")


# --- Root Endpoint (For basic status check) ---
@app.get("/", tags=["Status"])
async def read_root():
    """Provides basic status information."""
    return {
        "message": "FastAPI InfluxDB Ticker API is running.",
        "influx_url": INFLUX_URL,
        "influx_org": INFLUX_ORG,
        "influx_bucket": INFLUX_BUCKET,
        "docs": "/docs",
        "endpoints": {
            "write": "/write_ticker (POST)",
            "candles": f"/get_candles (POST, for {TARGET_TICKER_ID})", # Clarify ticker
            "raw_data": "/ticker_data/{ticker_id} (GET)" # Added new endpoint
        }
    }

# --- Run the Application ---
if __name__ == "__main__":
    print("--- InfluxDB Configuration ---")
    print(f"URL:    {INFLUX_URL}")
    print(f"Org:    {INFLUX_ORG}")
    print(f"Bucket: {INFLUX_BUCKET}")
    print(f"Token:  {'*' * len(INFLUX_TOKEN) if INFLUX_TOKEN else 'Not Set!'}")
    # Removed Target Ticker printout as it's specific to one endpoint now
    print("------------------------------")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)