import mysql.connector
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import uuid
from datetime import datetime

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
mysql_conn = mysql.connector.connect(
    host=mysql_host,
    port=mysql_port,
    user=mysql_user,
    password=mysql_password,
    database=mysql_db
)
mysql_cursor = mysql_conn.cursor()

# Connect to Cassandra
cluster = Cluster([cassandra_host], port=cassandra_port)
cassandra_session = cluster.connect(cassandra_keyspace)  # Connecting to the default_keyspace

# MySQL query to fetch only the required columns (10 rows at a time)
mysql_query = f"""
SELECT trade_id, buy_asset_amount, buy_asset_symbol, created_at, instrument_id, 
       price, sell_asset_amount, sell_asset_symbol, status, updated_at
FROM {mysql_table}
WHERE buy_asset_symbol = 'USDC'
LIMIT 10000;
"""

# Prepare the Cassandra insert query with only the selected columns
insert_query = f"""
INSERT INTO {cassandra_table} (
    trade_id, buy_asset_amount, buy_asset_symbol, created_at, instrument_id, 
    price, sell_asset_amount, sell_asset_symbol, status, updated_at
) VALUES (
    %s, %s, %s, %s, %s, 
    %s, %s, %s, %s, %s
);
"""

# Loop to fetch and process data in batches of 10
while True:
    # Execute the query to fetch 10 rows at a time
    mysql_cursor.execute(mysql_query)
    
    # Fetch the next 10 rows
    rows = mysql_cursor.fetchall()
    
    if not rows:
        break  # Exit the loop if there are no more rows
    
    # Process the fetched rows
    for row in rows:
        data = (
            uuid.UUID(row[0]),                         # trade_id
            row[1] if row[1] is not None else None,     # buy_asset_amount
            row[2],                                    # buy_asset_symbol
            row[3],                                    # created_at
            row[4],                                    # instrument_id
            row[5] if row[5] is not None else None,     # price
            row[6] if row[6] is not None else None,     # sell_asset_amount
            row[7],                                    # sell_asset_symbol
            row[8],                                    # status
            row[9],                                    # updated_at
        )
        
        # Print the data as it's getting processed
        print(f"Processing row: {data}")
        
        # Execute the insert query for Cassandra
        cassandra_session.execute(insert_query, data)

# Close MySQL and Cassandra connections
mysql_cursor.close()
mysql_conn.close()
cluster.shutdown()

print("Data transfer complete!")