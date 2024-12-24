from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import statistics

# Cassandra connection details
cassandra_host = 'localhost'  # Use the Docker service name or localhost if running on local machine
cassandra_port = 9042         # Default port for Cassandra CQL
cassandra_keyspace = 'default_keyspace'
cassandra_table = 'trades'

# Connect to Cassandra
cluster = Cluster([cassandra_host], port=cassandra_port)
session = cluster.connect(cassandra_keyspace)

# Query to filter and calculate SUM(sell_asset_amount) for buy_asset_symbol = 'BTC' and status = 'success'
query = """
    SELECT sell_asset_amount 
    FROM {table}
    WHERE buy_asset_symbol = 'BTC' AND status = 'success' 
    ALLOW FILTERING
""".format(table=cassandra_table)

# Prepare and execute the query
statement = SimpleStatement(query)
rows = session.execute(statement)

# Extract sell_asset_amount values
sell_asset_amounts = [row.sell_asset_amount for row in rows]

# Perform calculation: SUM(sell_asset_amount)
total_sell_asset_amount = sum(sell_asset_amounts)

# Calculate population mean and population standard deviation
population_mean = statistics.mean(sell_asset_amounts) if sell_asset_amounts else 0
population_standard_deviation = statistics.stdev(sell_asset_amounts) if len(sell_asset_amounts) > 1 else 0

# Print results
print(f"Total Sell Asset Amount (SUM): {total_sell_asset_amount}")
print(f"Population Mean: {population_mean}")
print(f"Population Standard Deviation: {population_standard_deviation}")

# Close the session and cluster connection
session.shutdown()
cluster.shutdown()