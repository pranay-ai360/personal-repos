#!/usr/bin/env python3
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import datetime

# Configuration – update these with your actual settings.
token = "MyInitialAdminToken0=="     # Replace with your InfluxDB API token
org = "docs"                         # Must match DOCKER_INFLUXDB_INIT_ORG
bucket = "home"                      # Must match DOCKER_INFLUXDB_INIT_BUCKET
url = "http://influxdb2:8086"

# Initialize the InfluxDB client.
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

def parse_date(date_str):
    """
    Parse a date string in the format 'd/m/yyyy' into a datetime object.
    Assumes the provided dates follow the day/month/year format.
    """
    return datetime.datetime.strptime(date_str, '%d/%m/%Y')

# MARKET DATA entries.
market_data = [
    {'date': '1/2/2025', 'pair': 'AAPL/USD', 'price': 100},
    {'date': '2/2/2025', 'pair': 'AAPL/USD', 'price': 105},
    {'date': '3/2/2025', 'pair': 'AAPL/USD', 'price': 102},
    {'date': '4/2/2025', 'pair': 'AAPL/USD', 'price': 107},
    {'date': '5/2/2025', 'pair': 'AAPL/USD', 'price': 104},
    {'date': '6/2/2025', 'pair': 'AAPL/USD', 'price': 109},
    {'date': '7/2/2025', 'pair': 'AAPL/USD', 'price': 106},
    {'date': '8/2/2025', 'pair': 'AAPL/USD', 'price': 111},
    {'date': '9/2/2025', 'pair': 'AAPL/USD', 'price': 108},
    {'date': '10/2/2025', 'pair': 'AAPL/USD', 'price': 113},
    {'date': '11/2/2025', 'pair': 'AAPL/USD', 'price': 110},
    {'date': '12/2/2025', 'pair': 'AAPL/USD', 'price': 115},
    {'date': '13/2/2025', 'pair': 'AAPL/USD', 'price': 112},
    {'date': '14/2/2025', 'pair': 'AAPL/USD', 'price': 117},
    {'date': '15/2/2025', 'pair': 'AAPL/USD', 'price': 114},
    {'date': '16/2/2025', 'pair': 'AAPL/USD', 'price': 119},
]

# TRADES data for USERID:111A.
trades_data = [
    {'date': '1/2/2025',  'trade': 'Buy',  'quantity': 1, 'total_value': 100},
    {'date': '2/2/2025',  'trade': 'Buy',  'quantity': 2, 'total_value': 210},
    {'date': '3/2/2025',  'trade': 'Buy',  'quantity': 3, 'total_value': 306},
    {'date': '4/2/2025',  'trade': 'Buy',  'quantity': 2, 'total_value': 214},
    {'date': '5/2/2025',  'trade': 'Buy',  'quantity': 1, 'total_value': 104},
    {'date': '6/2/2025',  'trade': 'Sell', 'quantity': 1, 'total_value': 109},
    {'date': '7/2/2025',  'trade': 'Sell', 'quantity': 2, 'total_value': 212},
    {'date': '8/2/2025',  'trade': 'Sell', 'quantity': 1, 'total_value': 111},
    # Skipping the empty rows for 9/2, 10/2, and 11/2.
    {'date': '12/2/2025', 'trade': 'Buy',  'quantity': 2, 'total_value': 230},
    {'date': '13/2/2025', 'trade': 'Buy',  'quantity': 2, 'total_value': 224},
    {'date': '14/2/2025', 'trade': 'Sell', 'quantity': 1, 'total_value': 117},
    {'date': '15/2/2025', 'trade': 'Sell', 'quantity': 2, 'total_value': 228},
    {'date': '16/2/2025', 'trade': 'Sell', 'quantity': 1, 'total_value': 119},
]

# Write MARKET DATA to InfluxDB.
for entry in market_data:
    point = Point("market_data") \
        .tag("pair", entry["pair"]) \
        .field("price", entry["price"]) \
        .time(parse_date(entry["date"]), WritePrecision.S)
    write_api.write(bucket=bucket, org=org, record=point)
    print(f"Inserted market data: {entry}")

# Write TRADES data to InfluxDB.
for trade in trades_data:
    point = Point("trades") \
        .tag("userid", "111A") \
        .field("trade", trade["trade"]) \
        .field("quantity", trade["quantity"]) \
        .field("total_value", trade["total_value"]) \
        .time(parse_date(trade["date"]), WritePrecision.S)
    write_api.write(bucket=bucket, org=org, record=point)
    print(f"Inserted trade data: {trade}")

# Close the InfluxDB client.
client.close()