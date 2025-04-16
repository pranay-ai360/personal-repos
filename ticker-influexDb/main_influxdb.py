# main_influxdb.py
import uvicorn
from fastapi import (
    FastAPI, HTTPException, Query, Path, Request, Response, Body
)
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel, Field, field_validator, model_validator
)
from datetime import date, datetime, timezone, timedelta, time
from typing import List, Dict, Tuple, Literal, Any, Optional
import logging
import time as system_time
import json
import pytz

# --- InfluxDB Client ---
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.flux_table import FluxStructureEncoder # For better JSON serialization of results

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api_logger_influxdb")

# --- Constants & Configuration ---
DEFAULT_TIMEZONE = "UTC"
try:
    VALID_TIMEZONES = pytz.all_timezones_set
except AttributeError:
    logger.warning("Could not get timezones from pytz. Timezone validation might be limited.")
    VALID_TIMEZONES = {"UTC", "Asia/Manila", "America/New_York", "Europe/London"}

# --- InfluxDB Configuration ---
INFLUXDB_URL = "http://influxdb2:9999" # Use service name if in Docker Compose
INFLUXDB_TOKEN = "MyInitialAdminToken0==" # Replace with your actual token
INFLUXDB_ORG = "docs"
INFLUXDB_BUCKET = "home"
RAW_MEASUREMENT = "raw_ticker_data" # Measurement name for raw prices

# --- Pydantic Models ---

# Ticker Write Models
class TickerWriteRequest(BaseModel):
    DateTime_UTC: datetime = Field(..., example="2024-11-21T16:00:00Z")
    TICKER_ID: str = Field(..., example="SOL-PHP")
    PRICE: float = Field(..., example=115.64)

class WriteResponse(BaseModel):
    status: str = "success"
    message: str

# Ticker Data Retrieval Models
class TickerDataPointResponse(BaseModel):
    timestamp_utc: str
    price: float

class TickerDataResponse(BaseModel):
    data: List[TickerDataPointResponse]
    ticker_id: str
    count: int

# Candle Models (Only request and response needed now)
class GetCandlesRequest(BaseModel):
    startDate: date = Field(..., example="2024-11-22")
    endDate: date = Field(..., example="2024-11-24")
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"]
    timezone: str = Field(DEFAULT_TIMEZONE)

    @field_validator('timezone')
    @classmethod
    def check_timezone(cls, tz_str: str) -> str:
        if tz_str not in VALID_TIMEZONES:
            similar = sorted([z for z in VALID_TIMEZONES if tz_str.lower() in z.lower() or z.lower() in tz_str.lower()], key=len)[:5]
            raise ValueError(f"Invalid timezone '{tz_str}'. Must be a valid IANA timezone. Similar: {similar}")
        return tz_str

    @model_validator(mode='after')
    def check_dates(self) -> 'GetCandlesRequest':
        start_d = self.startDate; end_d = self.endDate
        if start_d and end_d and end_d < start_d:
            raise ValueError('endDate cannot be before startDate')
        return self

class CandleResponseItem(BaseModel):
    open: str = Field(..., example="115.64")
    close: str = Field(..., example="88.48")
    high: str = Field(..., example="129.45")
    low: str = Field(..., example="79.89")
    openDateTime_UTC: str = Field(..., example="2024-11-22T16:00:00Z")
    closeDateTime_UTC: str = Field(..., example="2024-11-23T15:59:59Z") # Note: This needs careful calculation from Flux output

class GetCandlesResponse(BaseModel):
    candles: List[CandleResponseItem]
    startDatetime_UTC_Interpreted: str = Field(..., example="2024-11-21T16:00:00Z")
    endDatetime_UTC_Interpreted: str = Field(..., example="2024-11-25T15:59:59Z")
    TICKER_ID: str
    timezone: str # The requested timezone for calculation

# --- InfluxDB Client Initialization ---
try:
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=30_000) # Increased timeout
    write_api = client.write_api(write_options=SYNCHRONOUS)
    query_api = client.query_api()
    # Check connection
    client.health()
    logger.info(f"Successfully connected to InfluxDB at {INFLUXDB_URL}, org: {INFLUXDB_ORG}, bucket: {INFLUXDB_BUCKET}")
except Exception as e:
    logger.critical(f"Failed to connect to InfluxDB at {INFLUXDB_URL}: {e}", exc_info=True)
    # Depending on requirements, you might want to exit or run in a degraded mode.
    # For now, we'll let it proceed and fail on API calls.
    client = None
    write_api = None
    query_api = None

# --- FastAPI Application ---
app = FastAPI(
    title="Ticker Data API (InfluxDB Backend)",
    description="API to write/read ticker data and read timezone-aware OHLC candles from InfluxDB.",
    version="2.0.0", # Updated version for backend change
)

# --- Middleware (Copied from original, no changes needed) ---
@app.middleware("http")
async def log_requests_responses(request: Request, call_next):
    request_id = f"{request.client.host}:{request.client.port}_{system_time.time():.6f}"
    logger.info(f"rid={request_id} START Request: {request.method} {request.url.path}")
    if request.query_params:
         logger.info(f"rid={request_id} Request Query Params: {request.query_params}")

    req_body_bytes = await request.body()
    log_body_str = "[Binary or Decode Error]"
    if req_body_bytes:
        try:
            log_body_str = req_body_bytes.decode('utf-8')
        except UnicodeDecodeError:
             log_body_str = f"[Non-UTF8 data, length: {len(req_body_bytes)}]"
        log_body_preview = log_body_str[:500] + ('...' if len(log_body_str) > 500 else '')
        logger.info(f"rid={request_id} Request Body: {log_body_preview}")
    else:
        logger.info(f"rid={request_id} Request Body: [Empty]")

    start_process_time = system_time.time()
    response = None
    try:
        # Add check for InfluxDB client readiness
        if client is None or write_api is None or query_api is None:
            logger.error(f"rid={request_id} InfluxDB client not initialized. Cannot process request.")
            raise HTTPException(status_code=503, detail="InfluxDB connection not available")

        response = await call_next(request)
        process_time = system_time.time() - start_process_time

        if isinstance(response, Response):
            response.headers["X-Process-Time"] = str(process_time)
            res_body_bytes = b""
            async for chunk in response.body_iterator:
                 res_body_bytes += chunk

            log_res_body_str = "[Binary or Decode Error]"
            if res_body_bytes:
                try:
                    log_res_body_str = res_body_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    log_res_body_str = f"[Non-UTF8 data, length: {len(res_body_bytes)}]"

            log_res_preview = log_res_body_str[:500] + ('...' if len(log_res_body_str) > 500 else '')
            status_code = response.status_code
            logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
            logger.info(f"rid={request_id} Response Body: {log_res_preview}")

            # Use a custom response class for JSON to handle InfluxDB types if needed
            # For now, standard Response works as long as data is serializable
            return Response(content=res_body_bytes, status_code=response.status_code,
                            headers=dict(response.headers), media_type=response.media_type)
        else:
             status_code = 500
             logger.warning(f"rid={request_id} Non-standard response object received from endpoint.")
             logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
             return response

    except InfluxDBError as e:
        process_time = system_time.time() - start_process_time
        status_code = 503 # Service Unavailable likely
        detail = f"InfluxDB Error: {e}"
        logger.error(f"rid={request_id} InfluxDB Error after {process_time:.4f}s: {e}", exc_info=True)
        if response is None:
             logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
             logger.info(f"rid={request_id} Response Body (InfluxDB Error): {json.dumps({'detail': detail})}")
        return JSONResponse( status_code=status_code, content={"detail": detail} )

    except Exception as e:
        process_time = system_time.time() - start_process_time
        status_code = 500
        detail = "Internal Server Error"
        if isinstance(e, HTTPException):
             status_code = e.status_code
             detail = e.detail

        logger.error(f"rid={request_id} Request failed after {process_time:.4f}s: {e}", exc_info=True)
        if response is None:
             logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
             logger.info(f"rid={request_id} Response Body (Error): {json.dumps({'detail': detail})}")

        return JSONResponse( status_code=status_code, content={"detail": detail} )


# --- Helper Functions ---
def get_flux_interval(interval_str: str) -> str:
    # Maps API interval string to Flux duration literal
    mapping = { "1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", }
    if interval_str not in mapping:
        raise ValueError(f"Unsupported interval: {interval_str}. Supported: {list(mapping.keys())}")
    return mapping[interval_str]

def get_interval_timedelta(interval_str: str) -> timedelta:
    # Crude mapping for calculating close time - assumes standard durations
    mapping = {
        "1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1),
    }
    if interval_str not in mapping:
        raise ValueError(f"Unsupported interval for timedelta calculation: {interval_str}")
    return mapping[interval_str]

def validate_timezone_str(tz_str: str) -> str: # Keep this validation
    if tz_str not in VALID_TIMEZONES:
        similar = sorted([z for z in VALID_TIMEZONES if tz_str.lower() in z.lower() or z.lower() in tz_str.lower()], key=len)[:5]
        raise ValueError(f"Invalid timezone '{tz_str}'. Must be a valid IANA timezone. Similar: {similar}")
    return tz_str

def format_datetime_for_flux(dt: datetime) -> str:
    """Formats datetime object into RFC3339 string for Flux queries."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) # Assume UTC if naive
    elif dt.tzinfo != timezone.utc:
        dt = dt.astimezone(timezone.utc)
    # Ensure nanoseconds are handled correctly if present, format to RFC3339 with Z
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3] + 'Z'

# --- API Endpoints ---
@app.post("/write_ticker", response_model=WriteResponse, summary="Write Ticker Data to InfluxDB", tags=["Ticker Data"])
async def write_ticker_data(request: TickerWriteRequest):
    ticker_id = request.TICKER_ID
    timestamp = request.DateTime_UTC
    if timestamp.tzinfo is None:
        logger.warning(f"Naive datetime received for {ticker_id}. Assuming UTC: {timestamp}")
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    elif timestamp.tzinfo != timezone.utc:
        timestamp = timestamp.astimezone(timezone.utc)

    price = request.PRICE

    point = Point(RAW_MEASUREMENT) \
        .tag("ticker_id", ticker_id) \
        .field("price", price) \
        .time(timestamp, WritePrecision.NS) # Use Nanosecond precision

    try:
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
        logger.info(f"InfluxDB WRITE: Inserted data for {ticker_id} at {timestamp_str}")
        return WriteResponse(message=f"Inserted data for {ticker_id} at {timestamp_str}")
    except InfluxDBError as e:
        logger.error(f"InfluxDB WRITE Error for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Failed to write data to InfluxDB: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during InfluxDB write for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during data write.")


@app.get("/ticker_data/{ticker_id}", response_model=TickerDataResponse, summary="Get Raw Ticker Data from InfluxDB", tags=["Ticker Data"])
async def get_ticker_data(
    ticker_id: str = Path(..., example="SOL-PHP"),
    start_utc: datetime = Query(..., example="2024-11-21T00:00:00Z"),
    end_utc: datetime = Query(..., example="2024-11-23T23:59:59Z"),
    limit: int = Query(100, ge=1),
    sort: Literal['asc', 'desc'] = Query("desc")
):
    # Ensure datetimes are timezone-aware UTC for Flux range
    start_utc_str = format_datetime_for_flux(start_utc)
    end_utc_str = format_datetime_for_flux(end_utc)
    sort_desc = sort == 'desc'

    flux_query = f"""
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: {start_utc_str}, stop: {end_utc_str})
            |> filter(fn: (r) => r["_measurement"] == "{RAW_MEASUREMENT}")
            |> filter(fn: (r) => r["ticker_id"] == "{ticker_id}")
            |> filter(fn: (r) => r["_field"] == "price")
            |> sort(columns: ["_time"], desc: {str(sort_desc).lower()})
            |> limit(n: {limit})
            |> yield(name: "raw_data")
    """
    logger.debug(f"Executing Flux query for raw data:\n{flux_query}")

    try:
        result = query_api.query(query=flux_query, org=INFLUXDB_ORG)
    except InfluxDBError as e:
        logger.error(f"InfluxDB GET Raw Error for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Failed to query raw data from InfluxDB: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during InfluxDB raw query for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during data query.")

    response_data: List[TickerDataPointResponse] = []
    if result:
        for table in result:
            for record in table.records:
                # Ensure _time is datetime and convert to UTC string
                record_time_utc = record.get_time().astimezone(timezone.utc)
                response_data.append(
                    TickerDataPointResponse(
                        timestamp_utc=record_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        price=record.get_value()
                    )
                )

    logger.info(f"InfluxDB GET: Retrieved {len(response_data)} raw points for {ticker_id}")
    return TickerDataResponse(data=response_data, ticker_id=ticker_id, count=len(response_data))


# Endpoint /calculate_candles is REMOVED


@app.post("/get_candles/{ticker_id}", response_model=GetCandlesResponse, summary="Get OHLC Candles Calculated by InfluxDB (from Date Range, UTC Output)", tags=["Candles"])
async def get_candles(
    request: GetCandlesRequest,
    ticker_id: str = Path(..., example="SOL-PHP")
):
    interval_api = request.interval
    calc_timezone_str = request.timezone # Timezone used for defining day boundaries and candle alignment
    start_date_req = request.startDate
    end_date_req = request.endDate

    try:
        flux_interval = get_flux_interval(interval_api)
        interval_delta = get_interval_timedelta(interval_api)
        filter_tz = pytz.timezone(calc_timezone_str)

        # Create timezone-aware start/end datetimes based on the *request timezone*
        # Start: Beginning of the startDate in the requested timezone
        start_dt_naive = datetime.combine(start_date_req, time.min)
        start_dt_filter_local = filter_tz.localize(start_dt_naive)

        # End: End of the endDate in the requested timezone (inclusive)
        end_dt_naive = datetime.combine(end_date_req, time.max)
        end_dt_filter_local = filter_tz.localize(end_dt_naive) # This is end of day

        # Convert filter boundaries to UTC strings for Flux 'range' function
        start_utc_interpreted_str = format_datetime_for_flux(start_dt_filter_local)
        end_utc_interpreted_str = format_datetime_for_flux(end_dt_filter_local)

    except ValueError as e: # Catches issues from get_flux_interval, get_interval_timedelta, pytz.timezone
        logger.error(f"Candle GET Error: Invalid parameter processing: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
         logger.error(f"Error constructing filter datetime range: {e}", exc_info=True)
         raise HTTPException(status_code=400, detail=f"Error processing date/timezone: {e}")

    logger.info(f"Candle GET Request: ticker='{ticker_id}', interval='{interval_api}', timezone='{calc_timezone_str}', dateRange=[{start_date_req} to {end_date_req}]")
    logger.info(f"Interpreted UTC range for query: [{start_utc_interpreted_str} to {end_utc_interpreted_str}]")

    # Construct the timezone-aware Flux query for OHLC
    # We use aggregateWindow with the location option for timezone alignment.
    flux_query = f"""
        import "timezone"

        option location = timezone.location(name: "{calc_timezone_str}")

        data = from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: {start_utc_interpreted_str}, stop: {end_utc_interpreted_str}) // Filter data within the UTC interpretation of the local date range
            |> filter(fn: (r) => r["_measurement"] == "{RAW_MEASUREMENT}")
            |> filter(fn: (r) => r["ticker_id"] == "{ticker_id}")
            |> filter(fn: (r) => r["_field"] == "price")

        // Calculate OHLC using aggregateWindow aligned to the specified timezone
        // createEmpty: false ensures we only get windows with actual data
        ohlc = data
            |> aggregateWindow(every: {flux_interval}, fn: (column, tables) => {{
                // Use reduce to calculate ohlc within each window table
                init = {{
                    open: float(v: tables |> findRecord(fn: (key) => true, idx: 0) |> yield(name: "_value")), // First record's value
                    high: tables |> max(column: "_value"),
                    low: tables |> min(column: "_value"),
                    close: float(v: tables |> findRecord(fn: (key) => true, idx: (tables |> length()) - 1) |> yield(name: "_value")) // Last record's value
                }}
                // This reduce isn't actually needed here as aggregateWindow applies functions directly
                // Keeping the structure for clarity of what aggregateWindow does internally for common funcs
                return init
            }}, createEmpty: false, timeSrc: "_start") // timeSrc ensures _time is the window start
            // The above 'fn' with reduce is complex; simpler way using multiple aggregates:

        open = data |> aggregateWindow(every: {flux_interval}, fn: first, createEmpty: false, timeSrc: "_start") |> map(fn: (r) => ({{ r with _field: "open" }}))
        high = data |> aggregateWindow(every: {flux_interval}, fn: max, createEmpty: false, timeSrc: "_start")   |> map(fn: (r) => ({{ r with _field: "high" }}))
        low = data |> aggregateWindow(every: {flux_interval}, fn: min, createEmpty: false, timeSrc: "_start")    |> map(fn: (r) => ({{ r with _field: "low" }}))
        close = data |> aggregateWindow(every: {flux_interval}, fn: last, createEmpty: false, timeSrc: "_start")  |> map(fn: (r) => ({{ r with _field: "close" }}))

        // Join the aggregated results based on time
        join(tables: {{open: open, high: high, low: low, close: close}}, on: ["_time", "_start", "_stop", "ticker_id"], method: "inner") // Join on common tags/time
             |> drop(columns: ["_start", "_stop", "_measurement", "ticker_id"]) // Clean up intermediate cols
             |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") // Pivot fields into columns
             |> sort(columns: ["_time"])
             |> yield(name: "ohlc_candles")
    """

    logger.debug(f"Executing Flux query for OHLC:\n{flux_query}")
    response_candles: List[CandleResponseItem] = []
    try:
        result = query_api.query(query=flux_query, org=INFLUXDB_ORG)

        if not result:
            logger.warning(f"Candle GET: No OHLC data returned by InfluxDB for ticker '{ticker_id}', interval '{interval_api}', timezone '{calc_timezone_str}'.")
            # Return empty list, not 404, as the query ran but found nothing in the range.
        else:
            # Process the results (expecting one table from the pivot)
            for table in result:
                 if table.records:
                    logger.info(f"Processing {len(table.records)} candle records from table.")
                 for record in table.records:
                    # _time is the start of the window (UTC)
                    open_dt_utc = record.get_time().astimezone(timezone.utc)
                    # Calculate close time: open time + interval duration - 1 nanosecond (smallest unit)
                    close_dt_utc = open_dt_utc + interval_delta - timedelta(nanoseconds=1)

                    # Format prices (handle potential None if aggregation failed, though createEmpty=false helps)
                    o = record.values.get("open")
                    h = record.values.get("high")
                    l = record.values.get("low")
                    c = record.values.get("close")

                    if o is None or h is None or l is None or c is None:
                         logger.warning(f"Skipping candle at {open_dt_utc} due to missing OHLC values.")
                         continue

                    # Format output
                    price_format = ".4f" # Use more precision maybe?
                    response_candles.append(CandleResponseItem(
                        open=f"{o:{price_format}}",
                        high=f"{h:{price_format}}",
                        low=f"{l:{price_format}}",
                        close=f"{c:{price_format}}",
                        openDateTime_UTC=open_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        closeDateTime_UTC=close_dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
                    ))

    except InfluxDBError as e:
        logger.error(f"InfluxDB GET Candles Error for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Failed to query candle data from InfluxDB: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during InfluxDB candle query/processing for {ticker_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during candle data processing.")


    logger.info(f"Candle GET: Returning {len(response_candles)} candles for ticker '{ticker_id}', interval '{interval_api}', timezone '{calc_timezone_str}'")
    return GetCandlesResponse(
        candles=response_candles,
        startDatetime_UTC_Interpreted=start_dt_filter_local.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), # Use the actual boundaries
        endDatetime_UTC_Interpreted=end_dt_filter_local.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        TICKER_ID=ticker_id,
        timezone=calc_timezone_str
    )

# --- Run the Application ---
if __name__ == "__main__":
    logger.info("Starting FastAPI server (InfluxDB Backend)...")
    if client:
        logger.info(f"InfluxDB Config: URL={INFLUXDB_URL}, Org={INFLUXDB_ORG}, Bucket={INFLUXDB_BUCKET}")
    else:
        logger.error("InfluxDB Client FAILED TO INITIALIZE. API calls requiring DB will fail.")
    logger.info(f"Default calculation timezone: {DEFAULT_TIMEZONE}")
    logger.info(f"Loaded {len(VALID_TIMEZONES)} valid timezones.")
    logger.info("Access API documentation at http://0.0.0.0:8000/docs")
    logger.info("Access ReDoc documentation at http://0.0.0.0:8000/redoc")
    uvicorn.run("main_influxdb:app", host="0.0.0.0", port=8000, reload=True) # Adjust module name if needed