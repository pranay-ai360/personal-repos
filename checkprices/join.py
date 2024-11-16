import mysql.connector
from mysql.connector import Error
import http.client
import hmac
import hashlib
import base64
import json
import urllib.parse
import time as time_module

# Define the CoinSymbol
CoinSymbol = 'BTC'

# API credentials
api_key = '24ab46f784d1b20db435b852086e3250'
api_secret = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='
passphrase = 'akmwnltyfgb'

# Variables for conversion
usdphprate = 57.25
margin = 0.025  # 2.5%

def connect_to_mysql(host, port, database, user, password):
    try:
        # Establish a connection to the MySQL database
        connection = mysql.connector.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )

        if connection.is_connected():
            print(f"Connected to MySQL Server")
            # Return the connection object
            return connection

    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None

def run_query(connection, CoinSymbol):
    try:
        # Create a cursor object using the connection
        cursor = connection.cursor()

        # SQL query for "buy" trade with the CoinSymbol variable injected
        buy_query = f"""
        SELECT
            trade_id, price, rfq_trade_direction, created_at
        FROM
            trades
        WHERE
            instrument_id = '{CoinSymbol}PHP'
            AND status = 'success'
            AND rfq_trade_direction = 'buy'
        ORDER BY
            created_at DESC
        LIMIT 1;
        """

        # Execute the "buy" query
        cursor.execute(buy_query)

        # Fetch the result for "buy"
        buy_result = cursor.fetchone()

        # Print the result for "buy"
        if buy_result:
            print("Latest 'buy' trade details:")
            print(f"Trade ID: {buy_result[0]}")
            print(f"Price: {buy_result[1]}")
            print(f"RFQ Trade Direction: {buy_result[2]}")
            print(f"Created At: {buy_result[3]}")
        else:
            print("No 'buy' trade found for the given criteria.")

        # SQL query for "sell" trade with the CoinSymbol variable injected
        sell_query = f"""
        SELECT
            trade_id, price, rfq_trade_direction, created_at
        FROM
            trades
        WHERE
            instrument_id = '{CoinSymbol}PHP'
            AND status = 'success'
            AND rfq_trade_direction = 'sell'
        ORDER BY
            created_at DESC
        LIMIT 1;
        """

        # Execute the "sell" query
        cursor.execute(sell_query)

        # Fetch the result for "sell"
        sell_result = cursor.fetchone()

        # Print the result for "sell"
        if sell_result:
            print("\nLatest 'sell' trade details:")
            print(f"Trade ID: {sell_result[0]}")
            print(f"Price: {sell_result[1]}")
            print(f"RFQ Trade Direction: {sell_result[2]}")
            print(f"Created At: {sell_result[3]}")
        else:
            print("No 'sell' trade found for the given criteria.")

        return buy_result, sell_result

    except Error as e:
        print(f"Error while executing query: {e}")

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("MySQL connection is closed")

def make_coinbase_request(timestamp, start_time, end_time):
    method = 'GET'
    granularity = 60  # 1 minute

    # URL encode the start and end time
    query_params = urllib.parse.urlencode({
        'granularity': granularity,
        'start': start_time,
        'end': end_time
    })

    request_path = f'/products/{CoinSymbol}-USD/candles?{query_params}'
    body = ''  # Empty for GET requests

    # Create the prehash string
    message = timestamp + method + request_path + body

    # Create HMAC signature
    key = base64.b64decode(api_secret)
    signature = hmac.new(key, message.encode('utf-8'), hashlib.sha256)
    signature_b64 = base64.b64encode(signature.digest())

    # Establish connection
    conn = http.client.HTTPSConnection("api.exchange.coinbase.com")

    # Set headers
    headers = {
        'CB-ACCESS-KEY': api_key,
        'CB-ACCESS-SIGN': signature_b64.decode('utf-8'),
        'CB-ACCESS-TIMESTAMP': timestamp,
        'CB-ACCESS-PASSPHRASE': passphrase,
        'Content-Type': 'application/json',
        'User-Agent': 'YourAppName/1.0'  # Add a User-Agent header
    }

    # Send GET request
    conn.request("GET", request_path, body, headers)

    # Get and process the response
    res = conn.getresponse()
    data = res.read()

    # Parse the JSON data
    response_data = json.loads(data.decode("utf-8"))

    # Function to convert Unix timestamp to readable time
    def convert_timestamp(unix_timestamp):
        return time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.gmtime(unix_timestamp))

    # Process the response and print date, close price, buy price, and sell price
    print("Date, Close Price(USD), Buy Price(PHP), Sell Price(PHP):")
    for row in response_data:
        time_bucket_start = convert_timestamp(row[0])  # Convert timestamp to readable format
        close_price = row[4]  # Get the close price

        # Calculate buy and sell prices
        buy_price = close_price * usdphprate * (1 + margin)
        sell_price = close_price * usdphprate * (1 - margin)

        # Print results
        print(f"Date: {time_bucket_start}, ClosePrice(USD): {close_price:.2f}, Buy(PHP): {buy_price:.2f}, Sell(PHP): {sell_price:.2f}")

# Replace with your MySQL server details
host = '13.215.135.190'
port = 20000  # Replace with your MySQL port
database = 'paymaya_api'
user = 'admin'
password = 'Sr!35_JGDR'

# Connect to MySQL
connection = connect_to_mysql(host, port, database, user, password)

# Run the queries if connection was successful
if connection:
    buy_result, sell_result = run_query(connection, CoinSymbol)

    if buy_result and sell_result:
        # Set request details for Coinbase API
        timestamp = str(time_module.time())
        
        # Convert MySQL timestamp (buy_result[3] and sell_result[3]) to string format for API request
        start_time_buy = str(buy_result[3])  # buy timestamp
        end_time_buy = str(buy_result[3])  # For 1 minute granularity

        start_time_sell = str(sell_result[3])  # sell timestamp
        end_time_sell = str(sell_result[3])  # For 1 minute granularity

        # Make API request for buy
        print("\nMaking Coinbase request for 'buy' trade timestamp:")
        make_coinbase_request(timestamp, start_time_buy, end_time_buy)

        # Make API request for sell
        print("\nMaking Coinbase request for 'sell' trade timestamp:")
        make_coinbase_request(timestamp, start_time_sell, end_time_sell)