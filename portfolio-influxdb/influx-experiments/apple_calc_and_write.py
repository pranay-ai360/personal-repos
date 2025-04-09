#!/usr/bin/env python3
import datetime
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
import numpy as np

# --- Configuration ---
token = "MyInitialAdminToken0=="  # Replace with your InfluxDB API token
org = "docs"                      # Must match DOCKER_INFLUXDB_INIT_ORG
bucket = "home"                   # Must match DOCKER_INFLUXDB_INIT_BUCKET
url = "http://influxdb2:8086"     # Adjust if your InfluxDB is elsewhere
USER_ID = "111A"
ASSET_PAIR = "AAPL/USD"
# Using the same measurement name, assuming we overwrite previous calculation
# Or change this if you want to keep both versions (e.g., portfolio_summary_avg_cost_proceeds)
PORTFOLIO_MEASUREMENT = "portfolio_summary_avg_cost"

# --- InfluxDB Connection ---
client = InfluxDBClient(url=url, token=token, org=org, timeout=30_000)
write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()

def fetch_data(start_date_str="2025-02-01T00:00:00Z", end_date_str="2025-02-17T00:00:00Z"):
    """Fetches market data and trades data from InfluxDB using Flux."""
    print(f"Fetching data between {start_date_str} and {end_date_str}...")

    flux_query_market = f'''
    from(bucket: "{bucket}")
      |> range(start: {start_date_str}, stop: {end_date_str})
      |> filter(fn: (r) => r["_measurement"] == "market_data")
      |> filter(fn: (r) => r["pair"] == "{ASSET_PAIR}")
      |> filter(fn: (r) => r["_field"] == "price")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "price"])
      |> sort(columns: ["_time"])
    '''

    flux_query_trades = f'''
    from(bucket: "{bucket}")
      |> range(start: {start_date_str}, stop: {end_date_str})
      |> filter(fn: (r) => r["_measurement"] == "trades")
      |> filter(fn: (r) => r["userid"] == "{USER_ID}")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "trade", "quantity", "total_value"])
      |> sort(columns: ["_time"])
    '''
    try:
        print("Fetching market data...")
        market_df = query_api.query_data_frame(query=flux_query_market)
        if not market_df.empty:
            market_df['_time'] = pd.to_datetime(market_df['_time']).dt.tz_localize(None)
            market_df.set_index('_time', inplace=True)
            market_df['price'] = pd.to_numeric(market_df['price'], errors='coerce')
            print(f"Fetched {len(market_df)} market data points.")
        else:
             print("Warning: No market data found.")
             return pd.DataFrame(), pd.DataFrame()

        print("Fetching trades data...")
        trades_df = query_api.query_data_frame(query=flux_query_trades)
        if not trades_df.empty:
            trades_df['_time'] = pd.to_datetime(trades_df['_time']).dt.tz_localize(None)
            trades_df.set_index('_time', inplace=True)
            trades_df['quantity'] = pd.to_numeric(trades_df['quantity'], errors='coerce')
            trades_df['total_value'] = pd.to_numeric(trades_df['total_value'], errors='coerce')
            print(f"Fetched {len(trades_df)} trade data points.")
        else:
             print("Warning: No trade data found.")
             if not market_df.empty:
                 trades_df = pd.DataFrame(columns=['trade', 'quantity', 'total_value'])
                 trades_df.index.name = '_time'


        return market_df, trades_df

    except InfluxDBError as e:
        print(f"Error querying InfluxDB: {e}")
        if "Errno 111" in str(e) or "Connection refused" in str(e):
             print(f"Connection refused. Is InfluxDB running and accessible at {url}?")
        elif "timeout" in str(e).lower():
             print("Query timed out. Check InfluxDB performance or increase client timeout.")
        else:
            print(f"An InfluxDB error occurred: {e.message}")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred during data fetching: {e}")
        return pd.DataFrame(), pd.DataFrame()


def calculate_portfolio_avg_cost():
    """
    Calculates daily portfolio metrics using Average Cost method.
    Realised Value = Total Proceeds from Sales on that day.
    """
    start_dt = datetime.datetime(2025, 2, 1)
    end_dt = datetime.datetime(2025, 2, 17) # Go one day past last data point

    start_str = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    market_df, trades_df = fetch_data(start_str, end_str)

    if market_df.empty:
        print("Cannot calculate portfolio without market data.")
        return

    all_dates = pd.date_range(start=start_dt, end=end_dt - datetime.timedelta(days=1), freq='D')
    portfolio_history = []

    current_aum = 0
    total_cost_basis = 0.0
    current_avg_cost = 0.0

    print("\nCalculating daily portfolio values (Avg Cost, Realised=Proceeds)...")
    for current_date in all_dates:
        market_price_today = market_df.loc[market_df.index == current_date, 'price'].iloc[0] if current_date in market_df.index else None
        last_market_price = portfolio_history[-1]['market_price'] if portfolio_history else None

        if market_price_today is None:
             if last_market_price is not None:
                 market_price_today = last_market_price
             else:
                 pass # Will result in None for Unrealised Value

        # --- Reset daily realised value ---
        # This now represents TOTAL PROCEEDS from sales today
        daily_realised_value_proceeds = 0.0

        trades_today = trades_df[trades_df.index == current_date]

        if not trades_today.empty:
            for _, trade in trades_today.iterrows():
                if trade['trade'] == 'Buy':
                    buy_quantity = int(trade['quantity'])
                    buy_total_value = trade['total_value']
                    total_cost_basis += buy_total_value
                    current_aum += buy_quantity
                    current_avg_cost = (total_cost_basis / current_aum) if current_aum > 0 else 0.0

                elif trade['trade'] == 'Sell':
                    sell_quantity = int(trade['quantity'])
                    sell_proceeds = trade['total_value'] # This is the value we want for Realised Value

                    # --- Accumulate Todays Sale Proceeds ---
                    daily_realised_value_proceeds += sell_proceeds

                    # --- Update AUM and Cost Basis (still needed for Avg Cost) ---
                    if current_aum == 0:
                        print(f"Warning on {current_date.strftime('%d/%m/%Y')}: Attempted to sell {sell_quantity} units, but AUM is zero. Skipping cost basis update.")
                        continue
                    if sell_quantity > current_aum:
                         print(f"Warning on {current_date.strftime('%d/%m/%Y')}: Attempted to sell {sell_quantity} units, but only {current_aum} held. Selling available amount for AUM/Cost update.")
                         sell_quantity_adjusted = current_aum # Adjust quantity used for cost basis update
                    else:
                        sell_quantity_adjusted = sell_quantity

                    # Cost basis reduction still uses the average cost
                    cost_of_sold_units = sell_quantity_adjusted * current_avg_cost
                    current_aum -= sell_quantity_adjusted
                    total_cost_basis -= cost_of_sold_units

                    if current_aum <= 1e-9: # Use tolerance for float comparison
                        current_aum = 0
                        total_cost_basis = 0.0
                        current_avg_cost = 0.0
                    # Average cost itself does not change on a sale


        # --- Calculate end-of-day metrics ---
        report_avg_cost = current_avg_cost
        unrealised_value = (current_aum * market_price_today) if market_price_today is not None and current_aum > 0 else 0.0
        if pd.isna(unrealised_value):
            unrealised_value = None

        portfolio_history.append({
            'date': current_date,
            'AUM': current_aum,
            'AVG_cost': report_avg_cost if current_aum > 0 else 0.0,
            'Unrealised_Value': unrealised_value,
            'Realised_Value': daily_realised_value_proceeds, # Use the accumulated proceeds
            'market_price': market_price_today
        })

    return portfolio_history

def write_portfolio_to_influx(portfolio_data):
    """Writes the calculated portfolio summary data to InfluxDB."""
    if not portfolio_data:
        print("No portfolio data to write.")
        return

    points = []
    print(f"\nWriting {len(portfolio_data)} portfolio summary points to measurement '{PORTFOLIO_MEASUREMENT}'...")
    for record in portfolio_data:
        point = Point(PORTFOLIO_MEASUREMENT) \
            .tag("userid", USER_ID) \
            .tag("pair", ASSET_PAIR) \
            .field("AUM", int(record['AUM'])) \
            .time(record['date'], WritePrecision.S)

        if record['AVG_cost'] is not None and not np.isnan(record['AVG_cost']):
             point.field("AVG_cost", float(record['AVG_cost']))
        else:
             point.field("AVG_cost", 0.0)

        if record['Unrealised_Value'] is not None and not np.isnan(record['Unrealised_Value']):
             point.field("Unrealised_Value", float(record['Unrealised_Value']))

        # Realised Value (Proceeds) should always be a number (0.0 if no sales)
        point.field("Realised_Value", float(record['Realised_Value']))

        points.append(point)

    try:
        write_api.write(bucket=bucket, org=org, record=points)
        print(f"Successfully wrote portfolio data to InfluxDB measurement: {PORTFOLIO_MEASUREMENT}.")
    except InfluxDBError as e:
        print(f"Error writing portfolio data to InfluxDB: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during writing: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    calculated_data = calculate_portfolio_avg_cost()

    if calculated_data:
        print("\nCalculated Portfolio History (Avg Cost, Realised=Proceeds):")
        df_results = pd.DataFrame(calculated_data)
        df_results['date'] = df_results['date'].dt.strftime('%d/%m/%Y')
        df_results.set_index('date', inplace=True)
        pd.options.display.float_format = '{:.8f}'.format
        # Display columns relevant to user's original request + corrected Realised Value
        print(df_results[['AUM', 'AVG_cost', 'Unrealised_Value', 'Realised_Value']].to_string())

        write_portfolio_to_influx(calculated_data)

    print("Closing InfluxDB client.")
    client.close()