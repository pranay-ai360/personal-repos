import pymysql
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import subprocess

# MySQL connection details
mysql_host = '13.215.135.190'
mysql_port = 20000
mysql_user = 'admin'
mysql_password = 'Sr!35_JGDR'
mysql_db = 'paymaya_api'
mysql_table = 'trades'

# Cassandra connection details
cassandra_host = 'localhost'  # Use the Docker service name or localhost if running on local machine
cassandra_port = 9042         # Default port for Cassandra CQL
cassandra_keyspace = 'default_keyspace'
cassandra_table = 'trades'


# Connect to MySQL
mysql_conn = pymysql.connect(host=mysql_host, port=mysql_port, user=mysql_user, password=mysql_password, database=mysql_db)
mysql_cursor = mysql_conn.cursor()

# Connect to Cassandra
cluster = Cluster([cassandra_host], port=cassandra_port)
session = cluster.connect()


# # Create keyspace if it doesn't exist
# def create_keyspace():
#     # Running cqlsh command to create the keyspace if it doesn't exist
#     cql_query = "CREATE KEYSPACE IF NOT EXISTS default WITH REPLICATION = {'class' : 'SimpleStrategy', 'replication_factor' : 1};"
#     subprocess.run(["cqlsh", cassandra_host, "-e", cql_query])

# # Create keyspace
# create_keyspace()

# Function to copy data in batches of 100 rows

# Function to copy data in batches of 100 rows
# Function to copy data in batches of 100 rows
def copy_data_batch():
    offset = 0
    batch_size = 100
    expected_columns = 49  # Set the number of expected columns as per the Cassandra schema

    while True:
        # Fetch 100 rows from MySQL
        mysql_cursor.execute(f"SELECT * FROM {mysql_table} LIMIT {batch_size} OFFSET {offset}")
        rows = mysql_cursor.fetchall()

        if not rows:
            break  # Exit loop if no more rows to fetch

        # Prepare insert statement for Cassandra
        query = f"""
        INSERT INTO {cassandra_table} (
            serial_id, trade_id, quote_id, buy_asset_symbol, sell_asset_symbol, 
            sell_asset_amount, buy_asset_amount, price, message, status, instrument_id, 
            rfq_trade_id, rfq_trade_amount, rfq_trade_message, rfq_trade_took_ms, 
            rfq_trade_direction, rfq_trade_status, user_id, 
            created_at, updated_at, pm_create_deposit_txid, pm_create_deposit_asset_symbol, updated_at_ts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Process each row dynamically
        for row in rows:
            print(f"Processing row with {len(row)} columns: {row}")  # Debugging: Print row length and content

            # Adjust row length by either truncating or filling with default values
            if len(row) < expected_columns:
                # Fill missing columns with default values (None, empty string, etc.)
                row = list(row) + [None] * (expected_columns - len(row))  # Fill missing columns with None
            elif len(row) > expected_columns:
                # Trim extra columns if the row has more than the expected number
                row = row[:expected_columns]  # Trim to expected number of columns

            # Ensure UUID columns are in UUID format
            try:
                # Convert to UUID (if needed) for relevant columns
                row[1] = uuid.UUID(row[1]) if isinstance(row[1], str) else row[1]  # trade_id
                row[2] = uuid.UUID(row[2]) if isinstance(row[2], str) else row[2]  # quote_id
                row[11] = uuid.UUID(row[11]) if isinstance(row[11], str) else row[11]  # rfq_trade_id
                row[20] = uuid.UUID(row[20]) if isinstance(row[20], str) else row[20]  # pm_create_deposit_txid
                row[17] = uuid.UUID(row[17]) if isinstance(row[17], str) else row[17]  # user_id

                # Insert the row into Cassandra
                session.execute(query, row)
            except Exception as e:
                print(f"Error processing row: {e} | Row data: {row}")
                continue

        # Increment offset to get the next batch
        offset += batch_size

    print("Data transfer complete!")


# Execute the data transfer
copy_data_batch()

# Close connections
mysql_cursor.close()
mysql_conn.close()
session.shutdown()