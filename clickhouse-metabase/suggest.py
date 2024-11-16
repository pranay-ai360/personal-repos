import csv
from collections import defaultdict

def infer_data_type(value, current_type):
    """
    Attempts to refine the guessed data type for a column based on a new value.
    """
    # Default to String if it's not been set yet
    if current_type is None:
        current_type = "String"
        
    # Skip type inference if the value is empty
    if value == "":
        return current_type

    # If we've already identified the column as String, no need to continue checking
    if current_type == "String":
        return "String"

    try:
        # Attempt to parse the value as an integer
        int_val = int(value)
        if current_type in ["Int32", "Int64"]:
            return current_type
        return "Int32" if -2147483648 <= int_val <= 2147483647 else "Int64"
    except ValueError:
        pass

    try:
        # Attempt to parse the value as a float
        float(value)
        return "Float32" if current_type not in ["Float64"] else "Float64"
    except ValueError:
        pass

    # Further type checks (e.g., for DateTime, UUID) should be implemented here

    # Default to String for any value that doesn't fit the above categories
    return "String"

def read_csv_and_infer_types(csv_file_path, max_rows=10000):
    """
    Reads the CSV file and infers the data types of its columns based on up to max_rows rows.
    """
    data_types = defaultdict(lambda: None)
    with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            for column, value in row.items():
                current_type = data_types[column]
                data_types[column] = infer_data_type(value, current_type)
    return data_types

def generate_create_table_statement(data_types, table_name="default.my_table"):
    """
    Generates a CREATE TABLE statement for ClickHouse using inferred data types.
    """
    columns_definitions = ",\n".join([f"    `{col}` {dtype}" for col, dtype in data_types.items()])
    return f"CREATE TABLE {table_name}\n(\n{columns_definitions}\n) ENGINE = MergeTree() ORDER BY tuple();"

# Specify the path to your CSV file and the desired table name
csv_file_path = './import/Fireblocks_vault_balances_f12c_2024-04-07T222339.csv'
table_name = "default.my_first_table"

# Infer data types from the CSV
data_types = read_csv_and_infer_types(csv_file_path)

# Generate the CREATE TABLE statement
create_table_statement = generate_create_table_statement(data_types, table_name)

# Print the statement
print(create_table_statement)
