#!/usr/bin/env python3
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import time

# Configuration – update these with your actual settings.
token = "MyInitialAdminToken0=="     # Replace with your InfluxDB API token
org = "docs"         # Must match DOCKER_INFLUXDB_INIT_ORG
bucket = "home"   # Must match DOCKER_INFLUXDB_INIT_BUCKET
url = "http://influxdb2:8086"

# Initialize the InfluxDB client.
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

# === Trades Payload (for first 4 days) ===
trades_payload = [
    {
        "measurement": "trades",
        "tags": {"asset": "AAPL", "trade_type": "buy", "account": "my_portfolio"},
        "fields": {"price": 10, "quantity": 1, "cost": 10},
        "time": "2025-04-01T16:00:00Z"
    },
    {
        "measurement": "trades",
        "tags": {"asset": "AAPL", "trade_type": "buy", "account": "my_portfolio"},
        "fields": {"price": 11, "quantity": 1, "cost": 11},
        "time": "2025-04-02T16:00:00Z"
    },
    {
        "measurement": "trades",
        "tags": {"asset": "AAPL", "trade_type": "buy", "account": "my_portfolio"},
        "fields": {"price": 12, "quantity": 1, "cost": 12},
        "time": "2025-04-03T16:00:00Z"
    },
    {
        "measurement": "trades",
        "tags": {"asset": "AAPL", "trade_type": "buy", "account": "my_portfolio"},
        "fields": {"price": 13, "quantity": 1, "cost": 13},
        "time": "2025-04-04T16:00:00Z"
    }
]

# === Portfolio Price Payload (for 10 days) ===
portfolio_payload = [
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 10},
        "time": "2025-04-01T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 11},
        "time": "2025-04-02T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 12},
        "time": "2025-04-03T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 13},
        "time": "2025-04-04T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 14},
        "time": "2025-04-05T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 15},
        "time": "2025-04-06T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 16},
        "time": "2025-04-07T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 17},
        "time": "2025-04-08T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 18},
        "time": "2025-04-09T16:00:00Z"
    },
    {
        "measurement": "portfolio",
        "tags": {"asset": "AAPL"},
        "fields": {"price": 19},
        "time": "2025-04-10T16:00:00Z"
    }
]

def write_points(payload):
    for point in payload:
        # Build the point using InfluxDBClient's Point builder.
        p = (
            Point(point["measurement"])
            .tag("asset", point["tags"].get("asset"))
            # Add any additional tags
            .tag("trade_type", point["tags"].get("trade_type", ""))
            .tag("account", point["tags"].get("account", ""))
            # Add fields
            .field("price", point["fields"].get("price"))
            .field("quantity", point["fields"].get("quantity", 0))
            .field("cost", point["fields"].get("cost", 0))
            # Set the time (you can use WritePrecision.NS if nanosecond precision is desired)
            .time(point["time"], WritePrecision.NS)
        )
        write_api.write(bucket=bucket, org=org, record=p)
        print(f"Wrote point to measurement {point['measurement']} at time {point['time']}")
        # Optional small sleep to avoid flooding the write API.
        time.sleep(0.1)

if __name__ == "__main__":
    print("Writing trade points...")
    write_points(trades_payload)
    print("Writing portfolio price points...")
    write_points(portfolio_payload)
    print("Data load complete.")