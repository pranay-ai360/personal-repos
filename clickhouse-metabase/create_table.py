import csv
from clickhouse_driver import Client

# Configuration
csv_file_path = './import/Fireblocks_vault_balances_f12c_2024-04-07T222339.csv'
clickhouse_host = '127.0.0.1'
database_name = 'default'
table_name = 'example_table_4'

# Function to explicitly define ClickHouse data types
def infer_clickhouse_type(header):
    if header in ['Account ID']:
        return 'Int64'
    elif header in ['Total Balance']:
        return 'Float64'  # Adjusting for timestamp columns
    elif header == 'Total Balance - Last Update':
        return 'DateTime'  # Adjusting for timestamp columns
    else:
        return 'String'

# Connect to ClickHouse
client = Client(host=clickhouse_host)

# Load the CSV file and read the headers
with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.reader(csvfile)
    headers = next(reader)  # Get the first row which contains the headers

    # Define column types based on headers
    column_definitions = [(header, infer_clickhouse_type(header)) for header in headers]

# Generate the CREATE TABLE statement
create_table_statement = f"CREATE TABLE IF NOT EXISTS {database_name}.{table_name} (\n"
create_table_statement += ",\n".join([f"`{header}` {data_type}" for header, data_type in column_definitions])
create_table_statement += "\n) ENGINE = MergeTree() ORDER BY (`Account ID`);"

# Execute the CREATE TABLE statement
client.execute(f'USE {database_name}')
client.execute(create_table_statement)

print(f"Table `{table_name}` created successfully.")
