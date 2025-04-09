#!/usr/bin/env python3
from influxdb_client import InfluxDBClient

# Configuration – update these with your actual settings.
token = "MyInitialAdminToken0=="  # Your InfluxDB API token
org = "docs"                      # Must match DOCKER_INFLUXDB_INIT_ORG in docker-compose.yml
bucket = "home"                   # Must match DOCKER_INFLUXDB_INIT_BUCKET in docker-compose.yml
url = "http://influxdb2:8086"       # Use the service name from docker-compose

# Initialize the InfluxDB client.
client = InfluxDBClient(url=url, token=token, org=org)
query_api = client.query_api()

# Flux query to compute the cumulative cost and quantity from "buy" trades over the last two days,
# calculate the daily average cost, and write the result to the bucket.
flux_query = f'''
trades = from(bucket: "{bucket}")
  |> range(start: -2d)
  |> filter(fn: (r) => r["_measurement"] == "trades" and r["trade_type"] == "buy")
  |> filter(fn: (r) => r["_field"] == "cost" or r["_field"] == "quantity")
  // Pivot so that each record has both "cost" and "quantity"
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])

cumul = trades
  // Compute cumulative sums for cost and quantity
  |> cumulativeSum(columns: ["cost", "quantity"])
  // Aggregate per day; this gets the last cumulative value for each day
  |> aggregateWindow(every: 1d, fn: last, createEmpty: true)
  // If any day is missing a new value, fill with previous values.
  |> fill(column: "cost", usePrevious: true)
  |> fill(column: "quantity", usePrevious: true)

avgCost = cumul
  |> map(fn: (r) => ({{ 
       _time: r._time,
       _measurement: "daily_avg_cost", 
       avgCost: r.cost / r.quantity,
       asset: r.asset
  }}))

avgCost
  |> to(
    bucket: "{bucket}",
    org: "{org}"
  )
'''

try:
    query_api.query(flux_query)
    print("Flux query executed successfully. Daily average cost data has been written to the bucket.")
finally:
    client.close()