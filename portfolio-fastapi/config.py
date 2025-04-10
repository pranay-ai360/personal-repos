# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Settings:
    # --- Database URLs ---
    # PostgreSQL for metadata
    database_url: str = os.getenv("DATABASE_URL", "postgresql://myuser:mypassword@postgres/mydatabase") # Default for docker-compose

    # InfluxDB for time-series
    influxdb_url: str = os.getenv("INFLUXDB_URL", "http://influxdb2:8086")
    influxdb_token: str = os.getenv("INFLUXDB_TOKEN", "YOUR_DEFAULT_TOKEN")
    influxdb_org: str = os.getenv("INFLUXDB_ORG", "docs")
    influxdb_bucket: str = os.getenv("INFLUXDB_BUCKET", "home")
    # --- End Database URLs ---

    # FastAPI Configuration
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8005"))

    # --- Measurement Names (InfluxDB) ---
    market_measurement: str = "market_data"
    portfolio_events_measurement: str = "portfolio_events"
    portfolio_summary_measurement: str = "portfolio_summary_daily"
    # --- End Measurement Names ---

settings = Settings()

# Basic validation
if settings.influxdb_token == "YOUR_DEFAULT_TOKEN" or not settings.influxdb_token:
    print("Warning: INFLUXDB_TOKEN is not set. InfluxDB operations may fail.")
if "username:password@postgres" in settings.database_url and "TESTING" not in os.environ: # Avoid warning in tests if default is used
     print("Warning: DATABASE_URL might be using default credentials. Update environment variable for production.")