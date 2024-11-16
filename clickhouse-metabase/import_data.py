import csv
from clickhouse_driver import Client

def chunked(iterable, size):
    """Yield successive size chunks from iterable."""
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk

csv_file_path = './import/Fireblocks_vault_balances_f12c_2024-04-07T222339.csv'
clickhouse_host = '127.0.0.1'
database_name = 'default'
table_name = 'example_table_11'

client = Client(host=clickhouse_host)

create_table_statement = f"""
CREATE TABLE IF NOT EXISTS {database_name}.{table_name} (
    `Account Name` String,
    `Account ID` Int64,
    `Asset` String,
    `Asset Name` String,
    `Total Balance` Float64
) ENGINE = MergeTree()
ORDER BY (`Account Name`, `Asset`);
"""
client.execute(create_table_statement)

def convert_row(row):
    return (
        row['Account Name'],
        int(row['Account ID']),
        row['Asset'],
        row['Asset Name'],
        float(row['Total Balance'])
    )

with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    inserted_combinations = set()
    for batch in chunked(reader, 1000):  
        filtered_batch = []
        for row in batch:
            combo = (row['Account Name'], row['Asset'])
            if combo not in inserted_combinations:
                filtered_batch.append(convert_row(row))
                inserted_combinations.add(combo)
        if filtered_batch:
            client.execute(f'INSERT INTO {database_name}.{table_name} VALUES', filtered_batch)

print("CSV data imported successfully.")
