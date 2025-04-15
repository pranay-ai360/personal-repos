# main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Path, Request, Response
from fastapi.responses import JSONResponse # Import Response for potential modification
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Literal, Any
import bisect # Used for efficient insertion into sorted list
import logging # Import the logging library
import time # To measure processing time
import json # To decode/encode json bodies

# --- Logging Setup ---
# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api_logger") # Create a specific logger

# --- Pydantic Models (remain the same) ---
class TickerWriteRequest(BaseModel):
    DateTime_UTC: datetime = Field(
        ...,
        example="2024-02-21T01:00:00Z",
        description="Timestamp in ISO 8601 format (UTC)"
    )
    TICKER_ID: str = Field(..., example="SOL-PHP", description="Identifier for the ticker")
    PRICE: float = Field(..., example=100.0, description="Price at the given timestamp")

class WriteResponse(BaseModel):
    status: str = "success"
    message: str

class TickerDataPointResponse(BaseModel):
    timestamp_utc: str = Field(..., example="2024-02-12T00:00:00Z")
    price: float = Field(..., example=116.9043192)

class TickerDataResponse(BaseModel):
    data: List[TickerDataPointResponse]
    ticker_id: str
    count: int

# --- In-Memory Data Storage (remains the same) ---
ticker_storage: Dict[str, List[Tuple[datetime, float]]] = {}

# --- FastAPI Application ---
app = FastAPI(
    title="Ticker Data API",
    description="API to write and read time-series ticker data.",
    version="1.0.0",
)

# --- Middleware for Logging Request and Response ---
@app.middleware("http")
async def log_requests_responses(request: Request, call_next):
    """
    Middleware to log incoming request details and outgoing response details.
    """
    request_id = str(request.client.host) + "_" + str(request.client.port) + "_" + str(time.time())
    logger.info(f"rid={request_id} START Request: {request.method} {request.url.path}")
    # Log query params if any
    if request.query_params:
         logger.info(f"rid={request_id} Request Query Params: {request.query_params}")

    # Log request headers if needed (can be verbose)
    # logger.info(f"rid={request_id} Request Headers: {dict(request.headers)}")

    # Read and log request body (handle potential errors)
    req_body_bytes = await request.body()
    if req_body_bytes:
        try:
            req_body_str = req_body_bytes.decode('utf-8')
            # Avoid logging excessively large bodies in production if necessary
            log_body = req_body_str[:500] + ('...' if len(req_body_str) > 500 else '')
            logger.info(f"rid={request_id} Request Body: {log_body}")
        except UnicodeDecodeError:
            logger.warning(f"rid={request_id} Request Body: [Non-UTF8 data, length: {len(req_body_bytes)}]")
        except Exception as e:
             logger.error(f"rid={request_id} Error reading request body: {e}")
    else:
        logger.info(f"rid={request_id} Request Body: [Empty]")

    start_time = time.time()

    # IMPORTANT: This calls the actual endpoint function (or next middleware)
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time) # Add process time header

        # Log response status and headers
        logger.info(f"rid={request_id} END Request: Status={response.status_code}, Process Time={process_time:.4f}s")
        # logger.info(f"rid={request_id} Response Headers: {dict(response.headers)}")

        # Read and log response body (THIS IS THE TRICKY PART)
        # We need to read the body stream and then re-create the response
        # so the client still receives the body.
        res_body_bytes = b""
        async for chunk in response.body_iterator:
            res_body_bytes += chunk

        # Log the response body
        if res_body_bytes:
             try:
                 res_body_str = res_body_bytes.decode('utf-8')
                 log_body = res_body_str[:500] + ('...' if len(res_body_str) > 500 else '')
                 logger.info(f"rid={request_id} Response Body: {log_body}")
             except UnicodeDecodeError:
                logger.warning(f"rid={request_id} Response Body: [Non-UTF8 data, length: {len(res_body_bytes)}]")
             except Exception as e:
                logger.error(f"rid={request_id} Error reading response body: {e}")
        else:
             logger.info(f"rid={request_id} Response Body: [Empty]")

        # Re-create the response with the consumed body bytes
        # This is crucial, otherwise the client gets an empty response!
        return Response(content=res_body_bytes, status_code=response.status_code,
                        headers=dict(response.headers), media_type=response.media_type)

    except Exception as e:
        # Log exceptions that occur during request processing
        process_time = time.time() - start_time
        logger.error(f"rid={request_id} Request failed after {process_time:.4f}s: {e}", exc_info=True)
        # Return a generic error response
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"}
        )


# --- API Endpoints (remain the same) ---

@app.post(
    "/write_ticker",
    response_model=WriteResponse,
    summary="Write Ticker Data",
    tags=["Ticker Data"]
)
async def write_ticker_data(request: TickerWriteRequest):
    """
    Receives ticker data (timestamp, ID, price) and stores it.
    Ensures data for each ticker is stored sorted by timestamp.
    """
    ticker_id = request.TICKER_ID
    timestamp = request.DateTime_UTC
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    elif timestamp.tzinfo != timezone.utc:
        timestamp = timestamp.astimezone(timezone.utc)

    price = request.PRICE
    new_item = (timestamp, price)
    ticker_list = ticker_storage.setdefault(ticker_id, [])
    bisect.insort_left(ticker_list, new_item)
    timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Log specific action inside endpoint if needed (optional)
    # logger.info(f"Data inserted for {ticker_id} at {timestamp_str}")

    return WriteResponse(
        message=f"Inserted data for {ticker_id} at {timestamp_str}"
    )

@app.get(
    "/ticker_data/{ticker_id}",
    response_model=TickerDataResponse,
    summary="Get Ticker Data",
    tags=["Ticker Data"]
)
async def get_ticker_data(
    ticker_id: str = Path(..., example="SOL-PHP", description="The Ticker ID to query data for"),
    start_utc: datetime = Query(..., example="2024-02-01T00:00:00Z", description="Start timestamp (inclusive, UTC)"),
    end_utc: datetime = Query(..., example="2024-02-28T23:59:59Z", description="End timestamp (inclusive, UTC)"),
    limit: int = Query(100, ge=1, description="Maximum number of data points to return"),
    sort: Literal['asc', 'desc'] = Query("desc", description="Sort order by timestamp ('asc' or 'desc')")
):
    """
    Retrieves historical data for a given ticker_id within a specified
    time range, with options for limiting results and sorting.
    """
    if ticker_id not in ticker_storage:
        logger.warning(f"Attempted to access non-existent ticker: {ticker_id}")
        raise HTTPException(status_code=404, detail=f"Ticker ID '{ticker_id}' not found.")

    if start_utc.tzinfo is None: start_utc = start_utc.replace(tzinfo=timezone.utc)
    elif start_utc.tzinfo != timezone.utc: start_utc = start_utc.astimezone(timezone.utc)
    if end_utc.tzinfo is None: end_utc = end_utc.replace(tzinfo=timezone.utc)
    elif end_utc.tzinfo != timezone.utc: end_utc = end_utc.astimezone(timezone.utc)

    all_data_points = ticker_storage.get(ticker_id, []) # Use .get for safety

    filtered_data = [dp for dp in all_data_points if start_utc <= dp[0] <= end_utc]

    if sort == "desc":
        filtered_data.reverse()

    limited_data = filtered_data[:limit]

    response_data = [
        TickerDataPointResponse(
            timestamp_utc=dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            price=price
        )
        for dt, price in limited_data
    ]

    response_payload = TickerDataResponse(
        data=response_data,
        ticker_id=ticker_id,
        count=len(response_data)
    )
    # Log specific action inside endpoint if needed (optional)
    # logger.info(f"Retrieved {len(response_data)} data points for {ticker_id}")
    return response_payload

# --- Run the Application (remains the same) ---
if __name__ == "__main__":
    logger.info("Starting FastAPI server...") # Use logger
    logger.info("Access the API documentation at http://0.0.0.0:8000/docs") # Use logger
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Pass app as string for reload