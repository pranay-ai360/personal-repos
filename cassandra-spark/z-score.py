from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import statistics
from decimal import Decimal

# Cassandra connection details
cassandra_host = 'localhost'  # Use the Docker service name or localhost if running on local machine
cassandra_port = 9042         # Default port for Cassandra CQL
cassandra_keyspace = 'default_keyspace'
cassandra_table = 'trades'

# Connect to Cassandra
cluster = Cluster([cassandra_host], port=cassandra_port)
session = cluster.connect(cassandra_keyspace)

# Query to filter and calculate SUM(sell_asset_amount) for buy_asset_symbol = 'USDC' and status = 'success'
# Adding GROUP BY based on created_at
query = """
    SELECT created_at, sell_asset_amount 
    FROM {table}
    WHERE buy_asset_symbol = 'USDC' AND status = 'success' 
    GROUP BY created_at
    ALLOW FILTERING
""".format(table=cassandra_table)

# Prepare and execute the query
statement = SimpleStatement(query)
rows = session.execute(statement)

# Extract sell_asset_amount values
sell_asset_amounts = [Decimal(row.sell_asset_amount) for row in rows]

# Perform calculation: SUM(sell_asset_amount)
total_sell_asset_amount = sum(sell_asset_amounts)

# Calculate population mean and population standard deviation
population_mean = float(statistics.mean(sell_asset_amounts)) if sell_asset_amounts else 0
population_standard_deviation = float(statistics.stdev(sell_asset_amounts)) if len(sell_asset_amounts) > 1 else 0

# Calculate Z-score for a given X value (31150.07761 in this case)
X = Decimal('31150.07761')
z_score = (X - population_mean) / population_standard_deviation if population_standard_deviation else 0

# Print results
print(f"Total Sell Asset Amount (SUM): {total_sell_asset_amount}")
print(f"Population Mean: {population_mean}")
print(f"Population Standard Deviation: {population_standard_deviation}")
print(f"Z-score for X={X}: {z_score}")

# Close the session and cluster connection
session.shutdown()
cluster.shutdown()