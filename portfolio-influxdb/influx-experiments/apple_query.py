#!/usr/bin/env python3
import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError

# --- Configuration ---
token = "MyInitialAdminToken0=="  # Replace with your InfluxDB API token
org = "docs"                      # Must match DOCKER_INFLUXDB_INIT_ORG
bucket = "home"                   # Must match DOCKER_INFLUXDB_INIT_BUCKET
url = "http://influxdb2:8086"     # Adjust if your InfluxDB is elsewhere
USER_ID = "111A"
PORTFOLIO_MEASUREMENT = "portfolio_summary_avg_cost"
# Optional: Define time range for query
# Example: Query data written in the last 30 days
# start_range = "-30d"
# Example: Query specific range matching the calculation script
start_range = "2025-02-01T00:00:00Z"
stop_range = "2025-02-17T00:00:00Z" # Use the day *after* the last expected data point

# --- InfluxDB Connection ---
client = InfluxDBClient(url=url, token=token, org=org, timeout=20_000)
query_api = client.query_api()

def query_portfolio_summary():
    """Queries and displays the portfolio summary data."""
    print(f"Querying measurement '{PORTFOLIO_MEASUREMENT}' for user '{USER_ID}'...")
    print(f"Time range: {start_range} to {stop_range}")

    # Flux query to retrieve the calculated portfolio summary
    # Pivot the fields back into columns for easy DataFrame creation
    flux_query = f'''
    from(bucket: "{bucket}")
      |> range(start: {start_range}, stop: {stop_range})
      |> filter(fn: (r) => r["_measurement"] == "{PORTFOLIO_MEASUREMENT}")
      |> filter(fn: (r) => r["userid"] == "{USER_ID}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      // Select and potentially rename columns for clarity
      |> keep(columns: ["_time", "AUM", "AVG_cost", "Unrealised_Value", "Realised_Value"])
      |> sort(columns: ["_time"])
    '''

    try:
        # Execute the query and get results as a Pandas DataFrame
        df = query_api.query_data_frame(query=flux_query)

        if df.empty:
            print("No portfolio summary data found for the specified user and time range.")
            return

        # --- Data Cleaning and Formatting ---
        # Convert time to a more readable format (optional)
        # Keep timezone info if present, or remove it if desired
        df['_time'] = pd.to_datetime(df['_time']).dt.strftime('%Y-%m-%d') # Just date

        # Set display options for Pandas (optional)
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.float_format', '{:.4f}'.format) # Format floats

        # Rename columns for better readability
        df.rename(columns={
            '_time': 'Date',
            'AVG_cost': 'AVG Cost',
            'Unrealised_Value': 'Unrealised Value',
            'Realised_Value': 'Realised Value'
        }, inplace=True)

        # Reorder columns
        df = df[['Date', 'AUM', 'AVG Cost', 'Unrealised Value', 'Realised Value']]

        # Set Date as index for display (optional)
        df.set_index('Date', inplace=True)


        print("\n--- Portfolio Summary ---")
        print(df.to_string()) # Use to_string() to print the full DataFrame

    except InfluxDBError as e:
        print(f"Error querying InfluxDB: {e}")
        if "Errno 111" in str(e) or "Connection refused" in str(e):
             print(f"Connection refused. Is InfluxDB running and accessible at {url}?")
        elif "timeout" in str(e).lower():
             print("Query timed out. Check InfluxDB performance or increase client timeout.")
        else:
            print(f"An InfluxDB error occurred: {e.message}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    query_portfolio_summary()

    # --- Close Client ---
    print("\nClosing InfluxDB client.")
    client.close()