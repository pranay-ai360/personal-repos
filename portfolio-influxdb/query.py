#!/usr/bin/env python3
from influxdb_client import InfluxDBClient
import pandas as pd

# Configuration – update these with your actual settings.
token = "MyInitialAdminToken0=="  # Your InfluxDB API token
org = "docs"                      # Must match DOCKER_INFLUXDB_INIT_ORG in docker-compose.yml
bucket = "home"                   # Must match DOCKER_INFLUXDB_INIT_BUCKET in docker-compose.yml
url = "http://influxdb2:8086"       # Use the service name from docker-compose

# Initialize the InfluxDB client.
client = InfluxDBClient(url=url, token=token, org=org)
query_api = client.query_api()

# Note the doubling of curly braces in the map() and rename() functions.
flux_query = f'''
trades = from(bucket:"{bucket}")
  |> range(start: 2025-04-01T00:00:00Z, stop: 2025-04-11T00:00:00Z)
  |> filter(fn: (r) => r["_measurement"] == "trades")
  |> filter(fn: (r) => r["_field"] == "quantity")
  |> cumulativeSum()
  |> aggregateWindow(every: 1d, fn: last, createEmpty: true)
  |> fill(column: "_value", usePrevious: true)
  |> rename(columns: {{_value: "holdings"}})

prices = from(bucket:"{bucket}")
  |> range(start: 2025-04-01T00:00:00Z, stop: 2025-04-11T00:00:00Z)
  |> filter(fn: (r) => r["_measurement"] == "portfolio")
  |> filter(fn: (r) => r["_field"] == "price")
  |> aggregateWindow(every: 1d, fn: last, createEmpty: false)

join(
  tables: {{p: prices, h: trades}},
  on: ["_time"],
  method: "inner"
)
|> map(fn: (r) => ({{ 
    _time: r._time,
    price: r._value, 
    holdings: r.holdings,
    portfolio_value: r._value * r.holdings
}}))
'''

try:
    # Execute the query and load the result into a Pandas DataFrame.
    result_df = query_api.query_data_frame(flux_query)
    
    # If multiple tables are returned, concatenate them.
    if isinstance(result_df, list):
        result_df = pd.concat(result_df)
    
    if not result_df.empty:
        display_columns = ["_time", "price", "holdings", "portfolio_value"]
        print("Daily Portfolio Value:")
        print(result_df[display_columns].to_string(index=False))
    else:
        print("No data found for the specified query.")
finally:
    client.close()