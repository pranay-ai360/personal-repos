import mysql.connector
from mysql.connector import Error

# Define the CoinSymbol
CoinSymbol = 'BTC'

def connect_to_mysql(host, port, database, user, password):
    try:
        # Establish a connection to the MySQL database
        connection = mysql.connector.connect(
            host='13.215.135.190',
            port=20000,
            database='paymaya_api',
            user='admin',
            password='Sr!35_JGDR'
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

    except Error as e:
        print(f"Error while executing query: {e}")

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("MySQL connection is closed")

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
    run_query(connection, CoinSymbol)