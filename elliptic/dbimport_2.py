import pandas as pd
from sqlalchemy import create_engine, Table, Column, MetaData, Integer, Float, String, Boolean, text, inspect
from sqlalchemy.dialects.postgresql import JSONB

def flatten_json(y, parent_key='', sep='__'):
    """
    Recursively flattens a nested JSON/dictionary.
    If the value is a list of dictionaries, each dictionary is flattened with its index in the key.
    Exception: if a key is 'matched_elements' or 'matched_behaviors', its value is stored as is (as JSON) without further flattening.
    """
    items = {}
    if isinstance(y, dict):
        for key, value in y.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            
            # Exception: store 'matched_elements' or 'matched_behaviors' as JSON without flattening
            if key in ("matched_elements", "matched_behaviors"):
                items[new_key] = value
                continue

            if isinstance(value, dict):
                items.update(flatten_json(value, new_key, sep=sep))
            elif isinstance(value, list):
                # If list items are all dictionaries, flatten each item with its index
                if value and all(isinstance(i, dict) for i in value):
                    for idx, item in enumerate(value):
                        items.update(flatten_json(item, f"{new_key}{sep}{idx}", sep=sep))
                else:
                    items[new_key] = value
            else:
                items[new_key] = value
    else:
        items[parent_key] = y
    return items

# Your sample JSON data
data = {
    "id": "b7535048-76f8-4f60-bdd3-9d659298f9e20",
    "type": "wallet_exposure",
    "type4": "wallet_exposure",
    "type8": "wallet_exposure",
    "subject": {
        "asset": "ETH",
        "type": "address",
        "hash": "1MdYC22Gmjp2ejVPCxyYjFyWbQCYTGhGq8"
    },
    "customer": {
        "id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
        "reference": "foobar"
    },
    "blockchain_info": {
        "cluster": {
            "inflow_value": {
                "usd": 38383838
            },
            "outflow_value": {
                "usd": 0
            }
        }
    },
    "created_at": "2015-05-13T10:36:21.000Z",
    "updated_at": "2015-05-13T10:36:21.000Z",
    "analysed_at": "2015-05-13T10:36:21.000Z",
    "analysed_by": {
        "id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
        "type": "api_key"
    },
    "asset_tier": "full",
    "cluster_entities": [
        {
            "name": "Mt.Gox",
            "category": "Exchange",
            "is_primary_entity": True,
            "is_vasp": True
        }
    ],
    "team_id": "e333694b-c7c7-4a36-bf35-ed2615865242",
    "risk_score": 9.038007,
    "risk_score_detail": {
        "source": 6,
        "destination": 6
    },
    "error": {
        "message": "something went wrong"
    },
    "evaluation_detail": {
        "source": [
            {
                "rule_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "rule_name": "Illict",
                "risk_score": 9.038007,
                "matched_elements": [
                    {
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "contribution_percentage": 0,
                        "contribution_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "counterparty_percentage": 0,
                        "counterparty_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "indirect_percentage": 0,
                        "indirect_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "contributions": [
                            {
                                "contribution_percentage": 0,
                                "counterparty_percentage": 0,
                                "indirect_percentage": 0,
                                "entity": "AlphaBay",
                                "risk_triggers": {
                                    "name": "Binance",
                                    "category": "Dark Markets",
                                    "is_sanctioned": True,
                                    "country": [
                                        "MM"
                                    ]
                                },
                                "contribution_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "counterparty_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "indirect_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "is_screened_address": False,
                                "min_number_of_hops": 1
                            }
                        ]
                    }
                ],
                "matched_behaviors": [
                    {
                        "behavior_type": "Peeling Chain",
                        "length": 7,
                        "usd_value": 10500
                    }
                ],
                "rule_history_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "mc_analysis_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7"
            }
        ],
        "destination": [
            {
                "rule_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "rule_name": "Illict",
                "risk_score": 9.038007,
                "matched_elements": [
                    {
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "contribution_percentage": 0,
                        "contribution_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "counterparty_percentage": 0,
                        "counterparty_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "indirect_percentage": 0,
                        "indirect_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "contributions": [
                            {
                                "contribution_percentage": 0,
                                "counterparty_percentage": 0,
                                "indirect_percentage": 0,
                                "entity": "AlphaBay",
                                "risk_triggers": {
                                    "name": "Binance",
                                    "category": "Dark Markets",
                                    "is_sanctioned": True,
                                    "country": [
                                        "MM"
                                    ]
                                },
                                "contribution_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "counterparty_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "indirect_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "is_screened_address": False,
                                "min_number_of_hops": 1
                            }
                        ]
                    }
                ],
                "matched_behaviors": [
                    {
                        "behavior_type": "Peeling Chain",
                        "length": 7,
                        "usd_value": 10500
                    }
                ],
                "rule_history_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "mc_analysis_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7"
            }
        ]
    },
    "contributions": {
        "source": [
            {
                "entities": [
                    {
                        "name": "Alphabay",
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "entity_id": "1a93efdd-6063-4118-9748-d0a18a35fb70",
                        "is_primary_entity": True,
                        "is_vasp": True
                    }
                ],
                "contribution_percentage": 95,
                "contribution_value": {
                    "native": 0.07414304,
                    "native_major": 0.07414304,
                    "usd": 0.07414304
                },
                "counterparty_percentage": 50,
                "counterparty_value": {
                    "native": 0.04414304,
                    "native_major": 0.04414304,
                    "usd": 0.04414304
                },
                "indirect_percentage": 45,
                "indirect_value": {
                    "native": 0.03,
                    "native_major": 0.03,
                    "usd": 0.03
                },
                "is_screened_address": False,
                "min_number_of_hops": 1
            }
        ],
        "destination": [
            {
                "entities": [
                    {
                        "name": "Alphabay",
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "entity_id": "1a93efdd-6063-4118-9748-d0a18a35fb70",
                        "is_primary_entity": True,
                        "is_vasp": True
                    }
                ],
                "contribution_percentage": 95,
                "contribution_value": {
                    "native": 0.07414304,
                    "native_major": 0.07414304,
                    "usd": 0.07414304
                },
                "counterparty_percentage": 50,
                "counterparty_value": {
                    "native": 0.04414304,
                    "native_major": 0.04414304,
                    "usd": 0.04414304
                },
                "indirect_percentage": 45,
                "indirect_value": {
                    "native": 0.03,
                    "native_major": 0.03,
                    "usd": 0.03
                },
                "is_screened_address": False,
                "min_number_of_hops": 1
            }
        ]
    },
    "detected_behaviors": [
        {
            "behavior_type": "Peeling Chain",
            "length": 7,
            "usd_value": 10500
        }
    ],
    "changes": {
        "risk_score_change": 0.1
    },
    "workflow_status": "active",
    "workflow_status_id": 1,
    "process_status": "running",
    "process_status_id": 2,
    "triggered_rules": [],
    "screening_source": "sync",
    "type2": "new_value"  # New key added
}

# Flatten the JSON and create a DataFrame (a single row)
flat_data = flatten_json(data, sep="__")
df = pd.DataFrame([flat_data])

# Create the SQLAlchemy engine (using SQLAlchemy 2.0 style)
connection_url = "postgresql://doadmin:xxxxx@postgres-cluster-do-user-12892822-0.c.db.ondigitalocean.com:25060/elliptic"
engine = create_engine(connection_url, future=True)
metadata = MetaData()

# Function to map a Python value to an SQL type (as a string and as a SQLAlchemy type)
def map_python_type(val):
    if val is None:
        return "TEXT", String
    elif isinstance(val, bool):
        return "BOOLEAN", Boolean
    elif isinstance(val, int):
        return "INTEGER", Integer
    elif isinstance(val, float):
        return "DOUBLE PRECISION", Float
    elif isinstance(val, (list, dict)):
        return "JSONB", JSONB
    else:
        return "TEXT", String

# Check if the table does not exist, create it, else update it
table_name = "elliptic"
inspector = inspect(engine)

# If the table does not exist, create it with columns based on the DataFrame headers.
if table_name not in inspector.get_table_names():
    columns = []
    for col in df.columns:
        sample_value = df[col].iloc[0] if not df[col].empty else None
        sql_type_str, sa_type = map_python_type(sample_value)
        columns.append(Column(col, sa_type))
    elliptic_table = Table(table_name, metadata, *columns)
    metadata.create_all(engine)
else:
    # Reflect the existing table.
    metadata.reflect(engine, only=[table_name])
    elliptic_table = metadata.tables[table_name]

    # Check for any missing columns in the table compared to the DataFrame.
    existing_columns = set(elliptic_table.c.keys())
    missing_columns = []
    for col in df.columns:
        if col not in existing_columns:
            sample_value = df[col].iloc[0] if not df[col].empty else None
            sql_type_str, _ = map_python_type(sample_value)
            missing_columns.append((col, sql_type_str))
    
    # If there are missing columns, update the table schema.
    if missing_columns:
        with engine.begin() as conn:
            for col_name, sql_type_str in missing_columns:
                # Use SQLAlchemy's DDL commands to add the new columns to the table
                alter_stmt = text(f'ALTER TABLE {table_name} ADD COLUMN "{col_name}" {sql_type_str}')
                conn.execute(alter_stmt)

        # Re-reflect the table to include the new columns.
        metadata.reflect(engine, only=[table_name])
        elliptic_table = metadata.tables[table_name]

# Insert the flattened data into the table.
row_data = df.iloc[0].to_dict()
with engine.begin() as conn:
    conn.execute(elliptic_table.insert().values(**row_data))