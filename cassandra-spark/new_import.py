import mysql.connector
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from decimal import Decimal
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
cassandra_session = cluster.connect(cassandra_keyspace)

# MySQL query to fetch the row data (with LIMIT 10 for batching)
mysql_query = f"""
SELECT serial_id, trade_id, quote_id, buy_asset_symbol, sell_asset_symbol, 
       sell_asset_amount, buy_asset_amount, price, message, status, instrument_id, 
       rfq_trade_id, rfq_trade_amount, rfq_trade_message, rfq_trade_took_ms, 
       rfq_trade_direction, rfq_trade_status, user_id, created_at, updated_at, 
       pm_create_deposit_txid, pm_create_deposit_asset_symbol, updated_at_ts
FROM {mysql_table}
LIMIT 10;
"""

# Prepare the Cassandra insert query
insert_query = f"""
INSERT INTO {cassandra_table} (
    serial_id, trade_id, quote_id, buy_asset_symbol, sell_asset_symbol, 
    sell_asset_amount, buy_asset_amount, price, message, status, instrument_id, 
    rfq_trade_id, rfq_trade_amount, rfq_trade_message, rfq_trade_took_ms, 
    rfq_trade_direction, rfq_trade_status, user_id, created_at, updated_at, 
    pm_create_deposit_txid, pm_create_deposit_asset_symbol, updated_at_ts
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
    %s, %s, %s
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
            row[0],                                    # serial_id
            uuid.UUID(row[1]),                         # trade_id
            uuid.UUID(row[2]),                         # quote_id
            row[3],                                    # buy_asset_symbol
            row[4],                                    # sell_asset_symbol
            row[5] if row[5] is not None else None,     # sell_asset_amount
            row[6] if row[6] is not None else None,     # buy_asset_amount
            row[7] if row[7] is not None else None,     # price
            row[8],                                    # message
            row[9],                                    # status
            row[10],                                   # instrument_id
            uuid.UUID(row[11]) if row[11] is not None else None, # rfq_trade_id
            row[12] if row[12] is not None else None,   # rfq_trade_amount
            row[13],                                   # rfq_trade_message
            row[14],                                   # rfq_trade_took_ms
            row[15],                                   # rfq_trade_direction
            row[16],                                   # rfq_trade_status
            uuid.UUID(row[17]),                        # user_id
            row[18],                                   # created_at
            row[19],                                   # updated_at
            uuid.UUID(row[20]) if row[20] is not None else None, # pm_create_deposit_txid
            row[21],                                   # pm_create_deposit_asset_symbol
            row[22] if row[22] is not None else None    # updated_at_ts
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