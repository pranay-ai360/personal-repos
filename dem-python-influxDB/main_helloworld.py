# main.py
import os
import logging
from fastapi import FastAPI, HTTPException
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
import uvicorn # Required for running directly (though usually run via uvicorn command)

# --- Configuration (Best practice: use environment variables) ---
INFLUXDB_URL = os.getenv("INFLUXDB_V2_URL", "http://influxdb:8086") # Service name in Docker network
INFLUXDB_TOKEN = os.getenv("INFLUXDB_V2_TOKEN", "my-super-secret-auth-token") # Use the token you set up
INFLUXDB_ORG = os.getenv("INFLUXDB_V2_ORG", "my-org") # Use the org you set up
INFLUXDB_BUCKET = os.getenv("INFLUXDB_V2_BUCKET", "my-bucket") # Use the bucket you set up

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI(title="FastAPI InfluxDB Demo")

# --- InfluxDB Client Setup ---
# It's often better to create the client once if possible,
# but for simplicity in this demo, we'll create it in the endpoint.
# For production, consider FastAPI dependencies for managing the client lifecycle.

@app.get("/")
async def read_root():
    """Basic Hello World endpoint."""
    logger.info("Root endpoint '/' accessed")
    return {"message": "Hello World from FastAPI"}

@app.get("/write-test")
async def write_influxdb_test_point():
    """Connects to InfluxDB and writes a test data point."""
    logger.info("'/write-test' endpoint accessed. Attempting to connect to InfluxDB.")
    logger.info(f"Using InfluxDB Config: URL={INFLUXDB_URL}, Org={INFLUXDB_ORG}, Bucket={INFLUXDB_BUCKET}")

    try:
        # Use a context manager for the client to ensure resources are cleaned up
        with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=10_000) as client:
            # Check server accessibility (optional but good practice)
            if not client.ping():
                 logger.error("InfluxDB ping failed.")
                 raise HTTPException(status_code=503, detail="Cannot connect to InfluxDB (ping failed)")

            logger.info("Successfully connected to InfluxDB.")

            # Use SYNCHRONOUS write for immediate feedback/errors in this demo
            write_api = client.write_api(write_options=SYNCHRONOUS)

            # Create a data point
            point = Point("system_metrics") \
                .tag("host", "fastapi_server_demo") \
                .field("cpu_load", 0.64) \
                .field("memory_usage", 80.0) \
                .time(WritePrecision.NS) # Use nanosecond precision

            logger.info(f"Attempting to write point to bucket '{INFLUXDB_BUCKET}': {point.to_line_protocol()}")

            # Write the point
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            logger.info(f"Successfully wrote test point to InfluxDB bucket '{INFLUXDB_BUCKET}'.")
            return {"status": "success", "message": f"Test point written to InfluxDB bucket '{INFLUXDB_BUCKET}'"}

    except ApiException as e:
        logger.error(f"InfluxDB API Error: {e.status} - {e.reason} - {e.body}")
        raise HTTPException(status_code=500, detail=f"InfluxDB API error: {e.reason} {e.body}")
    except Exception as e:
        logger.error(f"An unexpected error occurred connecting to or writing to InfluxDB: {e}", exc_info=True)
        # Provide a generic error message externally, log the detail
        raise HTTPException(status_code=500, detail=f"Failed to write to InfluxDB due to an internal error: {type(e).__name__}")


# --- For running locally without Docker (uvicorn main:app --reload) ---
# Not strictly needed for Docker setup but useful for local dev
if __name__ == "__main__":
     # Note: For Docker, the CMD in Dockerfile.python handles this.
     # The host '0.0.0.0' is important for Docker accessibility.
     uvicorn.run(app, host="0.0.0.0", port=8000)