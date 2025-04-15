# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Path, Request, Response, Body, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Literal, Any, Optional
import bisect
import logging
import time
import json
import pandas as pd # Import pandas

# --- Logging Setup (remains the same) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api_logger")

# --- Pydantic Models ---

# --- Ticker Write Models (remain the same) ---
class TickerWriteRequest(BaseModel):
    DateTime_UTC: datetime = Field(..., example="2024-02-21T01:00:00Z")
    TICKER_ID: str = Field(..., example="SOL-PHP")
    PRICE: float = Field(..., example=100.0)

class WriteResponse(BaseModel):
    status: str = "success"
    message: str

# --- Ticker Data Retrieval Models (remain the same) ---
class TickerDataPointResponse(BaseModel):
    timestamp_utc: str
    price: float

class TickerDataResponse(BaseModel):
    data: List[TickerDataPointResponse]
    ticker_id: str
    count: int

# --- Candle Calculation & Retrieval Models ---

# Internal representation for stored candles (using native types)
class StoredCandle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    openDateTimeUtc: datetime # Start of the candle interval (always UTC)
    closeDateTimeUtc: datetime # End of the candle interval (always UTC)

# Request model for fetching candles
class GetCandlesRequest(BaseModel):
    startDatetime: datetime # FastAPI automatically parses ISO strings with timezone
    endDatetime: datetime
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] # Define allowed intervals

    # Ensure end datetime is after start datetime
    @validator('endDatetime')
    def end_must_be_after_start(cls, end_dt, values):
        if 'startDatetime' in values and values['startDatetime'] and end_dt <= values['startDatetime']:
            raise ValueError('endDatetime must be after startDatetime')
        return end_dt

# Response model item for a single candle (formatting applied)
class CandleResponseItem(BaseModel):
    open: str
    close: str
    high: str
    low: str
    openDateTime: str # Formatted string with original request's timezone offset
    closeDateTime: str # Formatted string with original request's timezone offset

# Response model for the get_candles endpoint
class GetCandlesResponse(BaseModel):
    candles: List[CandleResponseItem]
    startDatetime: str # Echoing input, formatted
    endDatetime: str # Echoing input, formatted
    TICKER_ID: str # Using TICKER_ID for consistency with write endpoint

# Response model for the calculation trigger
class CalculateCandlesResponse(BaseModel):
    status: str
    message: str
    ticker_id: str
    interval: str
    candles_calculated: Optional[int] = None


# --- In-Memory Data Storage ---
# Raw ticker data (remains the same)
# Structure: {"TICKER_ID": [(datetime_obj_utc, price), ...]} sorted by datetime
ticker_storage: Dict[str, List[Tuple[datetime, float]]] = {}

# Calculated candle data
# Structure: {"TICKER_ID": {"INTERVAL": [StoredCandle, StoredCandle, ...]}}
# Candles within the list should be sorted by openDateTimeUtc
candle_storage: Dict[str, Dict[str, List[StoredCandle]]] = {}


# --- FastAPI Application (remains the same) ---
app = FastAPI(
    title="Ticker Data API",
    description="API to write/read ticker data and calculate/read OHLC candles.",
    version="1.1.0", # Increment version
)

# --- Middleware (remains the same) ---
@app.middleware("http")
async def log_requests_responses(request: Request, call_next):
    request_id = str(request.client.host) + "_" + str(request.client.port) + "_" + str(time.time())
    logger.info(f"rid={request_id} START Request: {request.method} {request.url.path}")
    if request.query_params:
         logger.info(f"rid={request_id} Request Query Params: {request.query_params}")

    req_body_bytes = await request.body()
    log_body_str = "[Binary or Decode Error]"
    if req_body_bytes:
        try:
            log_body_str = req_body_bytes.decode('utf-8')
        except UnicodeDecodeError:
             pass # Keep default error string
        # Avoid logging excessively large bodies
        log_body_preview = log_body_str[:500] + ('...' if len(log_body_str) > 500 else '')
        logger.info(f"rid={request_id} Request Body: {log_body_preview}")
    else:
        logger.info(f"rid={request_id} Request Body: [Empty]")

    start_time = time.time()
    response = None # Initialize response
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time) # Add process time header

        res_body_bytes = b""
        async for chunk in response.body_iterator:
            res_body_bytes += chunk

        log_res_body_str = "[Binary or Decode Error]"
        if res_body_bytes:
             try:
                 log_res_body_str = res_body_bytes.decode('utf-8')
             except UnicodeDecodeError:
                 pass
        log_res_preview = log_res_body_str[:500] + ('...' if len(log_res_body_str) > 500 else '')

        logger.info(f"rid={request_id} END Request: Status={response.status_code}, Process Time={process_time:.4f}s")
        logger.info(f"rid={request_id} Response Body: {log_res_preview}")

        # Re-create the response with the consumed body bytes
        return Response(content=res_body_bytes, status_code=response.status_code,
                        headers=dict(response.headers), media_type=response.media_type)

    except Exception as e:
        process_time = time.time() - start_time
        status_code = 500
        detail = "Internal Server Error"
        if isinstance(e, HTTPException): # Preserve status code from HTTPExceptions
             status_code = e.status_code
             detail = e.detail

        logger.error(f"rid={request_id} Request failed after {process_time:.4f}s: {e}", exc_info=True)
        # Ensure response object exists for logging even if call_next failed early
        if response is None:
             logger.info(f"rid={request_id} END Request: Status={status_code}, Process Time={process_time:.4f}s")
             logger.info(f"rid={request_id} Response Body: {json.dumps({'detail': detail})}")

        # Return a JSON response for the exception
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail}
        )


# --- Helper Functions ---
# --- Helper Functions ---
def get_pandas_interval(interval_str: str) -> str:
    """Maps user-friendly interval strings to Pandas offset aliases."""
    # Use lowercase where recommended by Pandas for future compatibility
    mapping = {
        "1m": "min", # Use 'min' instead of 'T'
        "5m": "5min",# Use 'min'
        "15m": "15min",# Use 'min'
        "1h": "h",   # Use 'h' instead of 'H'
        "4h": "4h",  # Use 'h'
        "1d": "D",   # 'D' is standard for day
    }
    if interval_str not in mapping:
        raise ValueError(f"Unsupported interval: {interval_str}. Supported: {list(mapping.keys())}")
    return mapping[interval_str]

# --- Candle Calculation Function (can be run in background) ---
def perform_candle_calculation(ticker_id: str, interval: str):
    """
    Calculates OHLC candles for a ticker and interval from raw data
    and stores them in candle_storage.
    """
    task_id = f"{ticker_id}_{interval}_{time.time()}"
    logger.info(f"Task {task_id}: Starting candle calculation for {ticker_id}, interval {interval}")

    # 1. Get Raw Data
    if ticker_id not in ticker_storage or not ticker_storage[ticker_id]:
        logger.warning(f"Task {task_id}: No raw data found for {ticker_id}. Calculation skipped.")
        # Optionally update a task status if using a real job queue
        return

    raw_data = ticker_storage[ticker_id]
    if not raw_data:
        logger.warning(f"Task {task_id}: Raw data list is empty for {ticker_id}. Calculation skipped.")
        return

    # 2. Create Pandas DataFrame
    try:
        df = pd.DataFrame(raw_data, columns=['Timestamp', 'Price'])
        # Ensure Timestamp is datetime and set as index (MUST be UTC)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], utc=True)
        df = df.set_index('Timestamp')
    except Exception as e:
        logger.error(f"Task {task_id}: Failed to create DataFrame for {ticker_id}: {e}", exc_info=True)
        return

    # 3. Resample and Aggregate
    try:
        pd_interval = get_pandas_interval(interval)
        # Resample creates groups based on the interval START time.
        # 'label='left'' uses the interval start time as the label (index).
        # 'closed='left'' means the interval includes the start time but excludes the end time (e.g., 10:00 to 10:59:59.999 for 'H').
        ohlc = df['Price'].resample(pd_interval, label='left', closed='left').ohlc()

        # Drop rows where all OHLC values are NaN (intervals with no trades)
        ohlc = ohlc.dropna(how='all')

        if ohlc.empty:
             logger.info(f"Task {task_id}: No candles generated for {ticker_id}, interval {interval} after resampling (possibly no data in range or only NaN results).")
             # Ensure storage is empty for this combo
             candle_storage.setdefault(ticker_id, {})[interval] = []
             return

    except ValueError as e: # Handle invalid interval from get_pandas_interval
         logger.error(f"Task {task_id}: Invalid interval '{interval}': {e}")
         return
    except Exception as e:
        logger.error(f"Task {task_id}: Failed during resampling/OHLC for {ticker_id}, {interval}: {e}", exc_info=True)
        return

    # 4. Prepare StoredCandle objects
    calculated_candles: List[StoredCandle] = []
    freq = pd.tseries.frequencies.to_offset(pd_interval) # Get timedelta for interval
    for index_ts, row in ohlc.iterrows():
        open_dt_utc = index_ts.to_pydatetime() # Already UTC from resampling UTC index
        # Calculate close datetime (end of the interval)
        close_dt_utc = open_dt_utc + freq - timedelta(microseconds=1) # Go to next interval start and subtract epsilon

        candle = StoredCandle(
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            openDateTimeUtc=open_dt_utc,
            closeDateTimeUtc=close_dt_utc
        )
        calculated_candles.append(candle)

    # 5. Store Candles (overwrite existing for this interval)
    candle_storage.setdefault(ticker_id, {})[interval] = calculated_candles
    logger.info(f"Task {task_id}: Successfully calculated and stored {len(calculated_candles)} candles for {ticker_id}, interval {interval}")


# --- API Endpoints ---

# --- Ticker Write/Read Endpoints (remain mostly the same, just use logger) ---
@app.post("/write_ticker", response_model=WriteResponse, tags=["Ticker Data"])
async def write_ticker_data(request: TickerWriteRequest):
    ticker_id = request.TICKER_ID
    timestamp = request.DateTime_UTC
    if timestamp.tzinfo is None: timestamp = timestamp.replace(tzinfo=timezone.utc)
    elif timestamp.tzinfo != timezone.utc: timestamp = timestamp.astimezone(timezone.utc)

    price = request.PRICE
    new_item = (timestamp, price)
    ticker_list = ticker_storage.setdefault(ticker_id, [])
    bisect.insort_left(ticker_list, new_item)
    timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f"Inserted data for {ticker_id} at {timestamp_str}")
    return WriteResponse(message=f"Inserted data for {ticker_id} at {timestamp_str}")

@app.get("/ticker_data/{ticker_id}", response_model=TickerDataResponse, tags=["Ticker Data"])
async def get_ticker_data(
    ticker_id: str = Path(..., example="SOL-PHP"),
    start_utc: datetime = Query(..., example="2024-02-01T00:00:00Z"),
    end_utc: datetime = Query(..., example="2024-02-28T23:59:59Z"),
    limit: int = Query(100, ge=1),
    sort: Literal['asc', 'desc'] = Query("desc")
):
    if ticker_id not in ticker_storage:
        logger.warning(f"Ticker GET: Ticker ID '{ticker_id}' not found.")
        raise HTTPException(status_code=404, detail=f"Ticker ID '{ticker_id}' not found.")

    # Ensure query datetimes are UTC
    if start_utc.tzinfo is None: start_utc = start_utc.replace(tzinfo=timezone.utc)
    elif start_utc.tzinfo != timezone.utc: start_utc = start_utc.astimezone(timezone.utc)
    if end_utc.tzinfo is None: end_utc = end_utc.replace(tzinfo=timezone.utc)
    elif end_utc.tzinfo != timezone.utc: end_utc = end_utc.astimezone(timezone.utc)

    all_data_points = ticker_storage.get(ticker_id, [])
    filtered_data = [dp for dp in all_data_points if start_utc <= dp[0] <= end_utc]

    if sort == "desc": filtered_data.reverse()
    limited_data = filtered_data[:limit]

    response_data = [
        TickerDataPointResponse(timestamp_utc=dt.strftime('%Y-%m-%dT%H:%M:%SZ'), price=price)
        for dt, price in limited_data
    ]
    logger.info(f"Ticker GET: Retrieved {len(response_data)} raw data points for {ticker_id}")
    return TickerDataResponse(data=response_data, ticker_id=ticker_id, count=len(response_data))


# --- Candle Calculation Endpoint ---
@app.post(
    "/calculate_candles/{ticker_id}",
    response_model=CalculateCandlesResponse,
    status_code=202, # Accepted: Request accepted, processing initiated
    summary="Trigger OHLC Candle Calculation",
    tags=["Candles"]
)
async def trigger_candle_calculation(
    background_tasks: BackgroundTasks,
    ticker_id: str = Path(..., example="SOL-PHP", description="Ticker ID to calculate candles for"),
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Query(..., example="1h", description="Candle interval")
):
    """
    Triggers a background task to calculate OHLC candles for the specified
    ticker and interval based on the currently stored raw ticker data.
    Existing candles for this ticker/interval will be overwritten.
    """
    # Check if raw data exists first (quick check before scheduling)
    if ticker_id not in ticker_storage or not ticker_storage[ticker_id]:
         logger.warning(f"Calculation Trigger: No raw data found for {ticker_id}. Calculation not scheduled.")
         raise HTTPException(status_code=404, detail=f"No raw data found for ticker ID '{ticker_id}' to perform calculation.")

    # Add the calculation function to background tasks
    background_tasks.add_task(perform_candle_calculation, ticker_id, interval)

    logger.info(f"Calculation Trigger: Accepted request to calculate {interval} candles for {ticker_id}")
    return CalculateCandlesResponse(
        status="accepted",
        message=f"Candle calculation for {ticker_id} with interval {interval} has been scheduled.",
        ticker_id=ticker_id,
        interval=interval
    )

# --- Candle Retrieval Endpoint ---
@app.post( # Using POST as per user's curl example with --data
    "/get_candles/{ticker_id}",
    response_model=GetCandlesResponse,
    summary="Get Calculated OHLC Candles",
    tags=["Candles"]
)
async def get_candles(
    request: GetCandlesRequest, # Request body defines params
    ticker_id: str = Path(..., example="SOL-PHP", description="Ticker ID to retrieve candles for")
):
    """
    Retrieves pre-calculated OHLC candles for a specific ticker and interval
    within the requested datetime range.

    Candles must be calculated first using the `/calculate_candles/{ticker_id}` endpoint.
    Timestamps in the response (openDateTime, closeDateTime) will reflect the
    timezone offset provided in the request's startDatetime.
    """
    interval = request.interval
    start_dt_req = request.startDatetime # Already timezone-aware from Pydantic
    end_dt_req = request.endDatetime   # Already timezone-aware from Pydantic
    req_timezone = start_dt_req.tzinfo # Get the timezone from the request

    logger.info(f"Candle GET: Request for {ticker_id}, interval {interval}, range {start_dt_req} to {end_dt_req}")

    # 1. Check if candles for this ticker/interval have been calculated
    if ticker_id not in candle_storage or interval not in candle_storage[ticker_id]:
        logger.warning(f"Candle GET: No pre-calculated candles found for {ticker_id}, interval {interval}. Trigger calculation first.")
        raise HTTPException(status_code=404, detail=f"No pre-calculated '{interval}' candles found for ticker ID '{ticker_id}'. Use '/calculate_candles' first.")

    stored_candles: List[StoredCandle] = candle_storage[ticker_id][interval]

    # 2. Filter stored candles by the requested datetime range
    # Compare the REQUEST range against the candle's UTC open time
    filtered_candles: List[StoredCandle] = [
        c for c in stored_candles
        if c.openDateTimeUtc >= start_dt_req and c.openDateTimeUtc <= end_dt_req
        # Alternative filter logic: include candle if ANY part of it overlaps the request range?
        # Example: if (c.openDateTimeUtc < end_dt_req and c.closeDateTimeUtc > start_dt_req)
        # Let's stick to filtering by open time based on common practice.
    ]

    # 3. Format the response candles
    response_candles: List[CandleResponseItem] = []
    price_format = ".2f" # Example: 2 decimal places for price strings
    for candle in filtered_candles:
        # Format datetimes to ISO string WITH the requested timezone
        open_dt_local = candle.openDateTimeUtc.astimezone(req_timezone)
        close_dt_local = candle.closeDateTimeUtc.astimezone(req_timezone)

        response_candles.append(
            CandleResponseItem(
                # Format floats to strings as per example response
                open=f"{candle.open:{price_format}}",  # Now uses .2f correctly
                high=f"{candle.high:{price_format}}", # Now uses .2f correctly
                low=f"{candle.low:{price_format}}",  # Now uses .2f correctly
                close=f"{candle.close:{price_format}}",# Now uses .2f correctly
                # Format datetime with the request's timezone offset
                openDateTime=open_dt_local.isoformat(),
                closeDateTime=close_dt_local.isoformat()
            )
        )

    # 4. Construct final response
    logger.info(f"Candle GET: Returning {len(response_candles)} candles for {ticker_id}, interval {interval}")
    return GetCandlesResponse(
        candles=response_candles,
        # Echo back input datetimes formatted with their original timezone
        startDatetime=start_dt_req.isoformat(),
        endDatetime=end_dt_req.isoformat(),
        TICKER_ID=ticker_id
    )


# --- Run the Application ---
if __name__ == "__main__":
    logger.info("Starting FastAPI server...")
    logger.info("Access the API documentation at http://0.0.0.0:8000/docs")
    # Add some sample data on startup for testing
    try:
         # Ensure startup data is UTC
         now = datetime.now(timezone.utc)
         sample_data = [
             (now - timedelta(days=2, hours=1), 100.0), (now - timedelta(days=2, hours=0), 102.0), # Day 1
             (now - timedelta(days=1, hours=12), 105.0), (now - timedelta(days=1, hours=10), 110.0), # Day 2 (High)
             (now - timedelta(days=1, hours=5), 99.0), (now - timedelta(days=1, hours=1), 105.0), # Day 2 (Low, Close)
             (now - timedelta(hours=23), 105.0), (now - timedelta(hours=20), 106.0), # Day 3 (Open, High)
             (now - timedelta(hours=15), 102.0), (now - timedelta(hours=10), 103.5) # Day 3 (Low, Close)
         ]
         ticker_storage["SOL-PHP"] = sorted(sample_data)
         logger.info("Loaded sample SOL-PHP data into memory.")
    except Exception as e:
        logger.error(f"Failed to load sample data: {e}")

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)