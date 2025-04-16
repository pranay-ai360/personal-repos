# main.py
import uvicorn
from fastapi import (
    FastAPI, HTTPException, Query, Path, Request, Response, Body, BackgroundTasks
)
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel, Field, field_validator, model_validator
)
# Ensure 'time' is included in the import from datetime
from datetime import date, datetime, timezone, timedelta, time
from typing import List, Dict, Tuple, Literal, Any, Optional
import bisect
import logging
# Use an alias for the standard 'time' module if needed for other things
import time as system_time
import json
import pandas as pd
import pytz

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api_logger")

# --- Constants ---
DEFAULT_TIMEZONE = "UTC"
try:
    VALID_TIMEZONES = pytz.all_timezones_set
except AttributeError:
    logger.warning("Could not get timezones from pytz. Timezone validation might be limited.")
    VALID_TIMEZONES = {"UTC", "Asia/Manila", "America/New_York", "Europe/London"}

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

# Candle Models
class StoredCandle(BaseModel):
    open: float; high: float; low: float; close: float
    openDateTimeUtc: datetime; closeDateTimeUtc: datetime

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
    closeDateTime_UTC: str = Field(..., example="2024-11-23T15:59:59Z")

class GetCandlesResponse(BaseModel):
    candles: List[CandleResponseItem]
    startDatetime_UTC_Interpreted: str = Field(..., example="2024-11-21T16:00:00Z")
    endDatetime_UTC_Interpreted: str = Field(..., example="2024-11-25T15:59:59Z")
    TICKER_ID: str
    timezone: str

class CalculateCandlesResponse(BaseModel):
    status: str; message: str; ticker_id: str; interval: str; timezone: str
    candles_calculated: Optional[int] = None


# --- In-Memory Data Storage ---
ticker_storage: Dict[str, List[Tuple[datetime, float]]] = {}
candle_storage: Dict[str, Dict[str, List[StoredCandle]]] = {}


# --- FastAPI Application ---
app = FastAPI(
    title="Ticker Data API",
    description="API to write/read ticker data and calculate/read timezone-aware OHLC candles based on date ranges.",
    version="1.2.6", # Incremented version
)

# --- Middleware for Logging Request and Response ---
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

            return Response(content=res_body_bytes, status_code=response.status_code,
                            headers=dict(response.headers), media_type=response.media_type)
        else:
             status_code = 500
             logger.warning(f"rid={request_id} Non-standard response object received from endpoint.")
             logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
             return response

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
def get_pandas_interval(interval_str: str) -> str:
    mapping = { "1m": "min", "5m": "5min", "15m": "15min", "1h": "h", "4h": "4h", "1d": "D", }
    if interval_str not in mapping:
        raise ValueError(f"Unsupported interval: {interval_str}. Supported: {list(mapping.keys())}")
    return mapping[interval_str]

def validate_timezone_str(tz_str: str) -> str:
    if tz_str not in VALID_TIMEZONES:
        similar = sorted([z for z in VALID_TIMEZONES if tz_str.lower() in z.lower() or z.lower() in tz_str.lower()], key=len)[:5]
        raise ValueError(f"Invalid timezone '{tz_str}'. Must be a valid IANA timezone. Similar: {similar}")
    return tz_str

# --- Candle Calculation Function ---
def perform_candle_calculation(ticker_id: str, interval: str, calc_timezone_str: str):
    storage_key = f"{interval}_{calc_timezone_str}"; task_id = f"{ticker_id}_{storage_key}_{system_time.time():.6f}"
    logger.info(f"Task {task_id}: Starting candle calculation for {ticker_id}, key '{storage_key}'")
    if ticker_id not in ticker_storage or not ticker_storage[ticker_id]: logger.warning(f"Task {task_id}: No raw data for {ticker_id}. Skipped."); return 0
    raw_data = ticker_storage[ticker_id];
    if not raw_data: logger.warning(f"Task {task_id}: Raw data list empty for {ticker_id}. Skipped."); return 0
    try:
        df = pd.DataFrame(raw_data, columns=['Timestamp', 'Price'])
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True); df = df.set_index('Timestamp')
        if df.empty: logger.warning(f"Task {task_id}: DataFrame empty after loading {ticker_id}. Skipped."); return 0
        df = df[~df.index.duplicated(keep='first')]; df.sort_index(inplace=True)
    except Exception as e: logger.error(f"Task {task_id}: Failed DataFrame creation for {ticker_id}: {e}", exc_info=True); return 0
    try: calc_tz = pytz.timezone(calc_timezone_str); df_local = df.tz_convert(calc_tz)
    except Exception as e: logger.error(f"Task {task_id}: Failed index conversion to '{calc_timezone_str}' for {ticker_id}: {e}", exc_info=True); return 0
    try:
        pd_interval = get_pandas_interval(interval); ohlc = df_local['Price'].resample(pd_interval, label='left', closed='left').ohlc()
        ohlc = ohlc.dropna(how='all')
        if ohlc.empty: logger.info(f"Task {task_id}: No candles generated for key '{storage_key}'."); candle_storage.setdefault(ticker_id, {})[storage_key] = []; return 0
    except ValueError as e: logger.error(f"Task {task_id}: Invalid interval/resampling error for '{interval}': {e}", exc_info=True); return 0
    except Exception as e: logger.error(f"Task {task_id}: Failed during resampling/OHLC for key '{storage_key}': {e}", exc_info=True); return 0
    calculated_candles: List[StoredCandle] = [];
    try:
        freq = pd.tseries.frequencies.to_offset(pd_interval)
        for index_ts_local, row in ohlc.iterrows():
            if pd.isna(row['open']) or pd.isna(row['high']) or pd.isna(row['low']) or pd.isna(row['close']): logger.warning(f"Task {task_id}: Skipping candle at {index_ts_local} due to NaN OHLC."); continue
            open_dt_local = index_ts_local.to_pydatetime()
            if freq: close_dt_local = open_dt_local + freq - timedelta(microseconds=1)
            else: logger.warning(f"Task {task_id}: Could not determine freq offset for '{pd_interval}'. Close time inaccurate."); close_dt_local = open_dt_local
            open_dt_utc = open_dt_local.astimezone(timezone.utc); close_dt_utc = close_dt_local.astimezone(timezone.utc)
            calculated_candles.append(StoredCandle(open=float(row['open']), high=float(row['high']), low=float(row['low']), close=float(row['close']), openDateTimeUtc=open_dt_utc, closeDateTimeUtc=close_dt_utc))
    except Exception as e: logger.error(f"Task {task_id}: Error processing OHLC rows for key '{storage_key}': {e}", exc_info=True); return 0
    candle_storage.setdefault(ticker_id, {})[storage_key] = calculated_candles; num_calculated = len(calculated_candles)
    logger.info(f"Task {task_id}: Successfully calculated/stored {num_calculated} candles for key '{storage_key}'"); return num_calculated

# --- API Endpoints ---
@app.post("/write_ticker", response_model=WriteResponse, summary="Write Ticker Data", tags=["Ticker Data"])
async def write_ticker_data(request: TickerWriteRequest):
    ticker_id = request.TICKER_ID; timestamp = request.DateTime_UTC
    if timestamp.tzinfo is None: logger.warning(f"Naive dt received for {ticker_id}. Assuming UTC: {timestamp}"); timestamp = timestamp.replace(tzinfo=timezone.utc)
    elif timestamp.tzinfo != timezone.utc: timestamp = timestamp.astimezone(timezone.utc)
    price = request.PRICE; new_item = (timestamp, price); ticker_list = ticker_storage.setdefault(ticker_id, [])
    bisect.insort_left(ticker_list, new_item); timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f"Inserted data for {ticker_id} at {timestamp_str}"); return WriteResponse(message=f"Inserted data for {ticker_id} at {timestamp_str}")

@app.get("/ticker_data/{ticker_id}", response_model=TickerDataResponse, summary="Get Raw Ticker Data", tags=["Ticker Data"])
async def get_ticker_data(ticker_id: str = Path(..., example="SOL-PHP"), start_utc: datetime = Query(..., example="2024-11-21T00:00:00Z"), end_utc: datetime = Query(..., example="2024-11-23T23:59:59Z"), limit: int = Query(100, ge=1), sort: Literal['asc', 'desc'] = Query("desc")):
    if ticker_id not in ticker_storage: logger.warning(f"Ticker GET: ID '{ticker_id}' not found."); raise HTTPException(status_code=404, detail=f"ID '{ticker_id}' not found.")
    if start_utc.tzinfo is None: start_utc = start_utc.replace(tzinfo=timezone.utc)
    elif start_utc.tzinfo != timezone.utc: start_utc = start_utc.astimezone(timezone.utc)
    if end_utc.tzinfo is None: end_utc = end_utc.replace(tzinfo=timezone.utc)
    elif end_utc.tzinfo != timezone.utc: end_utc = end_utc.astimezone(timezone.utc)
    all_data_points = ticker_storage.get(ticker_id, []); filtered_data = [dp for dp in all_data_points if start_utc <= dp[0] <= end_utc]
    if sort == "desc": filtered_data.reverse();
    limited_data = filtered_data[:limit] # Apply limit *after* sorting/reversing if applicable
    response_data = [TickerDataPointResponse( timestamp_utc=dt.strftime('%Y-%m-%dT%H:%M:%SZ'), price=price ) for dt, price in limited_data ]
    logger.info(f"Ticker GET: Retrieved {len(response_data)} raw points for {ticker_id}"); return TickerDataResponse(data=response_data, ticker_id=ticker_id, count=len(response_data))

@app.post("/calculate_candles/{ticker_id}", response_model=CalculateCandlesResponse, status_code=202, summary="Trigger Timezone-Aware OHLC Candle Calculation", tags=["Candles"])
async def trigger_candle_calculation(background_tasks: BackgroundTasks, ticker_id: str = Path(..., example="SOL-PHP"), interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Query(..., example="1d"), timezone: str = Query(DEFAULT_TIMEZONE, example="Asia/Manila")):
    try: calc_timezone_str = validate_timezone_str(timezone)
    except ValueError as e: logger.error(f"Calc Trigger Error: Invalid TZ '{timezone}'. {e}"); raise HTTPException(status_code=400, detail=str(e))
    if ticker_id not in ticker_storage or not ticker_storage[ticker_id]: logger.warning(f"Calc Trigger: No raw data for {ticker_id}. Not scheduled."); raise HTTPException(status_code=404, detail=f"No raw data for ID '{ticker_id}'")
    background_tasks.add_task(perform_candle_calculation, ticker_id, interval, calc_timezone_str); storage_key = f"{interval}_{calc_timezone_str}"
    logger.info(f"Calc Trigger: Accepted request for ticker '{ticker_id}', storage key '{storage_key}'"); return CalculateCandlesResponse(status="accepted", message=f"Candle calculation scheduled for {ticker_id} interval {interval} based on {calc_timezone_str} timezone.", ticker_id=ticker_id, interval=interval, timezone=calc_timezone_str)

@app.post("/get_candles/{ticker_id}", response_model=GetCandlesResponse, summary="Get Calculated OHLC Candles (from Date Range, UTC Output)", tags=["Candles"])
async def get_candles(request: GetCandlesRequest, ticker_id: str = Path(..., example="SOL-PHP")):
    interval = request.interval; calc_timezone_str = request.timezone
    start_date_req = request.startDate; end_date_req = request.endDate
    try:
        filter_tz = pytz.timezone(calc_timezone_str)
        # *** Ensure correct usage of datetime.time.min/max ***
        start_dt_naive = datetime.combine(start_date_req, time.min) # Use time.min directly
        start_dt_filter = filter_tz.localize(start_dt_naive)
        end_dt_naive = datetime.combine(end_date_req, time.max)   # Use time.max directly
        end_dt_filter = filter_tz.localize(end_dt_naive)
    except Exception as e:
         logger.error(f"Error constructing filter datetime range from dates/timezone: {e}", exc_info=True)
         raise HTTPException(status_code=400, detail=f"Error processing date/timezone: {e}")
    storage_key = f"{interval}_{calc_timezone_str}"; start_utc_interpreted = start_dt_filter.astimezone(timezone.utc); end_utc_interpreted = end_dt_filter.astimezone(timezone.utc)
    logger.info(f"Candle GET: Request for ticker '{ticker_id}', storage key '{storage_key}'. Interpreted date range [{start_date_req} to {end_date_req}] in TZ '{calc_timezone_str}' as UTC range [{start_utc_interpreted.strftime('%Y-%m-%dT%H:%M:%SZ')} to {end_utc_interpreted.strftime('%Y-%m-%dT%H:%M:%SZ')}]. Outputting candle times in UTC.")
    if ticker_id not in candle_storage or storage_key not in candle_storage[ticker_id]:
        logger.warning(f"Candle GET: No pre-calculated candles found for key '{storage_key}'. Trigger calculation."); available_keys = list(candle_storage.get(ticker_id, {}).keys())
        detail_msg = f"No pre-calculated candles found for ID '{ticker_id}' with interval '{interval}' based on calc TZ '{calc_timezone_str}'. Use '/calculate_candles' first."
        if available_keys: detail_msg += f" Available keys: {available_keys}"
        raise HTTPException(status_code=404, detail=detail_msg)
    stored_candles: List[StoredCandle] = candle_storage[ticker_id][storage_key]
    # Filter based on OVERLAP between candle interval (UTC) and constructed filter interval (UTC)
    filtered_candles: List[StoredCandle] = [ c for c in stored_candles if c.openDateTimeUtc < end_dt_filter and c.closeDateTimeUtc >= start_dt_filter ]
    response_candles: List[CandleResponseItem] = []; price_format = ".2f"
    for candle in filtered_candles:
        try:
            response_candles.append(CandleResponseItem( open=f"{candle.open:{price_format}}", high=f"{candle.high:{price_format}}", low=f"{candle.low:{price_format}}", close=f"{candle.close:{price_format}}", openDateTime_UTC=candle.openDateTimeUtc.strftime('%Y-%m-%dT%H:%M:%SZ'), closeDateTime_UTC=candle.closeDateTimeUtc.strftime('%Y-%m-%dT%H:%M:%SZ')))
        except Exception as e: logger.error(f"Candle GET: Error formatting candle open={candle.openDateTimeUtc}: {e}", exc_info=True); continue
    logger.info(f"Candle GET: Returning {len(response_candles)} candles for ticker '{ticker_id}', key '{storage_key}'"); return GetCandlesResponse( candles=response_candles, startDatetime_UTC_Interpreted=start_utc_interpreted.strftime('%Y-%m-%dT%H:%M:%SZ'), endDatetime_UTC_Interpreted=end_utc_interpreted.strftime('%Y-%m-%dT%H:%M:%SZ'), TICKER_ID=ticker_id, timezone=calc_timezone_str )

# --- Run the Application ---
if __name__ == "__main__":
    logger.info("Starting FastAPI server...")
    logger.info(f"Default calculation timezone: {DEFAULT_TIMEZONE}")
    logger.info(f"Loaded {len(VALID_TIMEZONES)} valid timezones.")
    logger.info("Access API documentation at http://0.0.0.0:8000/docs")
    logger.info("Access ReDoc documentation at http://0.0.0.0:8000/redoc")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)