import os
import json
import boto3
import asyncio
import traceback
import pandas as pd
from elliptic import AML
from fastapi import FastAPI
from sqlalchemy import create_engine, Table, Column, MetaData, Integer, Float, String, Boolean, text, inspect, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.pool import QueuePool

app = FastAPI()

# Create engine with connection pooling
engine = create_engine(
    os.getenv('postgres_url'),
    future=True,
    poolclass=QueuePool,
    pool_size=int(os.getenv('postgres_max_connections', 2)),
    max_overflow=0  # Don't allow more connections than pool_size
)

# Event listener to ensure connections are returned to the pool
@event.listens_for(engine, 'checkout')
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    print("Connection checked out from pool")

@event.listens_for(engine, 'checkin')
def receive_checkin(dbapi_connection, connection_record):
    print("Connection returned to pool")

def poll_sqs_messages(queue_url: str, queue_type: str):
    """Poll all available messages from SQS queue"""
    try:
        print(f"Starting to poll messages from SQS queue: {queue_url}")
        print("SQS client configuration:", {
            "region": sqs.meta.region_name,
            "endpoint_url": sqs.meta.endpoint_url
        })
        
        all_messages = []
        while True:  # Keep polling until no more messages
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,  # Max allowed by AWS
                WaitTimeSeconds=10,
                AttributeNames=['All'],
                MessageAttributeNames=['All']
            )
            print(f"Receive message response: {response}")
            
            if 'Messages' not in response:
                print("No more messages found in queue")
                break
                
            print(f"Received {len(response['Messages'])} messages")
            for message in response['Messages']:
                all_messages.append(message['Body'])
                # Delete the message after reading
                try:
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    print(f"Successfully deleted message: {message['Body']}")
                except Exception as delete_error:
                    print(f"Error deleting message: {str(delete_error)}")
                    print(f"Delete error traceback: {traceback.format_exc()}")
            
            # If we received less than 10 messages, there are no more to fetch
            if len(response['Messages']) < 10:
                break
                
        print(f"Total messages received: {len(all_messages)}")
        return all_messages
    except Exception as e:
        print(f"Error polling SQS: {str(e)}")
        print(f"Error type: {type(e)}")
        print(f"Error traceback: {traceback.format_exc()}")
        return []

# Initialize AWS SQS client
try:
    sqs = boto3.client(
        'sqs',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-west-2')
    )
    print("Successfully initialized SQS client")
except Exception as e:
    print(f"Error initializing SQS client: {str(e)}")
    print(f"Error traceback: {traceback.format_exc()}")
    raise

SQS_queue_url_transaction = os.getenv('SQS_queue_url_transaction')
SQS_queue_url_wallet = os.getenv('SQS_queue_url_wallet')
print(f"Using Transaction SQS queue URL: {SQS_queue_url_transaction}")
print(f"Using Wallet SQS queue URL: {SQS_queue_url_wallet}")

# Retrieve your Elliptic API credentials from environment variables
api_key = os.getenv("elliptic_api_key")
api_secret = os.getenv("elliptic_api_secret")

# Initialize the AML client with your API key and secret
aml = AML(key=api_key, secret=api_secret)

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
            
            # Store certain fields as JSON without flattening to reduce row width
            if (key in ("matched_elements", "matched_behaviors", "behaviors", "elements", 
                       "risk_indicators", "customer_reference", "scores",
                       "wallet_provider", "contributions", "cluster", "cluster_entities",
                       "blockchain_info", "triggered_rules") or
                isinstance(value, (list, dict)) and len(str(value)) > 500):  # Keep large nested structures as JSON
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

def write_to_database(data, table_name: str):
    """
    Writes the provided data to the PostgreSQL database.
    Creates or updates the table schema as needed and handles data type mapping.
    """
    try:
        # Flatten the JSON and create a DataFrame (a single row)
        flat_data = flatten_json(data, sep="__")
        df = pd.DataFrame([flat_data])

        metadata = MetaData()

        # Function to map Python types to SQL types
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

        # Check if table exists and handle schema
        inspector = inspect(engine)

        if table_name not in inspector.get_table_names():
            # Create new table with id as primary key
            columns = [Column('id', String, primary_key=True)]
            for col in df.columns:
                if col != 'id':  # Skip id as it's already added
                    sample_value = df[col].iloc[0] if not df[col].empty else None
                    sql_type_str, sa_type = map_python_type(sample_value)
                    columns.append(Column(col, sa_type))
            elliptic_table = Table(table_name, metadata, *columns)
            metadata.create_all(engine)
        else:
            # Update existing table if needed
            metadata.reflect(engine, only=[table_name])
            elliptic_table = metadata.tables[table_name]

            # Prepare data
            row_data = df.iloc[0].to_dict()

            # Check if record exists and handle new columns in a single transaction
            with engine.begin() as conn:
                result = conn.execute(
                    text(f'SELECT id FROM {table_name} WHERE id = :id'),
                    {'id': row_data.get('id')}
                ).fetchone()

                # Filter out columns that don't exist in the table
                existing_columns = set(elliptic_table.c.keys())
                filtered_data = {k: v for k, v in row_data.items() if k in existing_columns}

                # Execute insert or update with filtered data
                if result:
                    # Update existing record
                    conn.execute(
                        elliptic_table.update()
                        .where(elliptic_table.c.id == filtered_data['id'])
                        .values(**filtered_data)
                    )
                else:
                    # Insert new record
                    conn.execute(elliptic_table.insert().values(**filtered_data))
                
                print(f"Successfully wrote data to database table: {table_name}")
                return True
    except Exception as e:
        print(f"Error writing to database: {str(e)}")
        print(f"Error traceback: {traceback.format_exc()}")
        return False

def get_analysis(mc_analysis_id: str, analysis_type: str = "transaction"):
    """
    Retrieves details for a single analysis given its mc_analysis_id.
    """
    print(f"Fetching {analysis_type} analysis details for ID: {mc_analysis_id}")
    
    # Different endpoints for transaction and wallet analyses
    endpoint = f"/v2/wallet/{mc_analysis_id}" if analysis_type == "wallet" else f"/v2/analyses/{mc_analysis_id}"
    response = aml.client.get(endpoint)
    data = response.json()
    
    # Write the data to appropriate database table
    table_name = "transactions" if analysis_type == "transaction" else "wallets"
    write_to_database(data, table_name)
    
    return data

def list_analyses_for_date(date_str: str, subject_type: str = "transaction"):
    """
    Retrieves all analyses that were analysed on a specific date using pagination.

    Constructs ISO8601 timestamps for the start and end of the day.
    For example, for date_str "2025-03-03", it will use:
      - analysed_at_after: "2025-03-03T00:00:00Z"
      - analysed_at_before: "2025-03-03T23:59:59Z"
    
    :param date_str: A string representing the date in YYYY-MM-DD format.
    :param subject_type: Type of analysis ("transaction" or "address")
    :return: The combined API response with all items.
    """
    start_of_day = f"{date_str}T00:00:00Z"
    end_of_day = f"{date_str}T23:59:59Z"
    
    all_items = []
    page = 1
    per_page = 100
    
    while True:
        params = {
            "expand": "customer_reference",
            "sort": "created_at",
            "page": page,
            "per_page": per_page,
            "subject": {
                "type": subject_type,
                "asset": "holistic",
                "blockchain": "holistic"
            } if subject_type == "address" else {"type": subject_type},
            "analysed_at_after": start_of_day,
            "analysed_at_before": end_of_day
        }
        response = aml.client.get("/v2/analyses", params=params)
        data = response.json()
        
        if 'items' in data and data['items']:
            all_items.extend(data['items'])
            # Check if we've received less than per_page items
            if len(data['items']) < per_page:
                break
            page += 1
        else:
            break
    
    # Return in the same format as the original API response
    return {
        'items': all_items,
        'total': len(all_items)
    }

@app.get("/analyses/{date_str}")
async def get_analyses(date_str: str):
    """
    FastAPI endpoint to retrieve transaction analyses for a given date.
    """
    result = list_analyses_for_date(date_str, "transaction")
    sent_messages = []
    
    # Extract and send IDs to SQS
    if 'items' in result:
        print(f"Found {len(result['items'])} analyses to process")
        for analysis in result['items']:
            if 'id' in analysis:
                try:
                    # Send analysis ID value directly to SQS
                    message_body = analysis['id']
                    print(f"Attempting to send message to SQS. Queue URL: {SQS_queue_url_transaction}")
                    print(f"Message body: {message_body}")
                    
                    response = sqs.send_message(
                        QueueUrl=SQS_queue_url_transaction,
                        MessageBody=message_body
                    )
                    sent_messages.append(message_body)
                    print(f"Successfully sent message to SQS. MessageId: {response.get('MessageId')}")
                    print(f"Full SQS response: {response}")
                except Exception as e:
                    print(f"Error sending message to SQS: {str(e)}")
                    print(f"Error type: {type(e)}")
                    print(f"Error traceback: {traceback.format_exc()}")
    
    print(f"Total messages sent to SQS: {len(sent_messages)}")
    print(f"Sent message IDs: {sent_messages}")
    
    # Wait for messages to be processed by SQS
    print("Waiting 5 seconds before polling messages...")
    await asyncio.sleep(5)
    
    # Poll messages to verify they were sent
    received_messages = poll_sqs_messages(SQS_queue_url_transaction, "transaction")
    print(f"Received messages from SQS: {received_messages}")
    
    # Fetch details for each received message ID
    analysis_details = []
    for message_id in received_messages:
        try:
            details = get_analysis(message_id, "transaction")
            analysis_details.append(details)
            print(f"Successfully fetched details for ID: {message_id}")
        except Exception as e:
            print(f"Error fetching details for ID {message_id}: {str(e)}")
            print(f"Error traceback: {traceback.format_exc()}")
    
    return {
        "analyses": result,
        "sqs_messages_received": received_messages,
        "analysis_details": analysis_details
    }

@app.get("/wallet-analyses/{date_str}")
async def get_wallet_analyses(date_str: str):
    """
    FastAPI endpoint to retrieve wallet analyses for a given date.
    """
    result = list_analyses_for_date(date_str, "address")
    sent_messages = []
    
    # Extract and send IDs to SQS
    if 'items' in result:
        print(f"Found {len(result['items'])} wallet analyses to process")
        for analysis in result['items']:
            if 'id' in analysis:
                try:
                    # Send analysis ID value directly to SQS
                    message_body = analysis['id']
                    print(f"Attempting to send message to SQS. Queue URL: {SQS_queue_url_wallet}")
                    print(f"Message body: {message_body}")
                    
                    response = sqs.send_message(
                        QueueUrl=SQS_queue_url_wallet,
                        MessageBody=message_body
                    )
                    sent_messages.append(message_body)
                    print(f"Successfully sent message to SQS. MessageId: {response.get('MessageId')}")
                    print(f"Full SQS response: {response}")
                except Exception as e:
                    print(f"Error sending message to SQS: {str(e)}")
                    print(f"Error type: {type(e)}")
                    print(f"Error traceback: {traceback.format_exc()}")
    
    print(f"Total messages sent to SQS: {len(sent_messages)}")
    print(f"Sent message IDs: {sent_messages}")
    
    # Wait for messages to be processed by SQS
    print("Waiting 5 seconds before polling messages...")
    await asyncio.sleep(5)
    
    # Poll messages to verify they were sent
    received_messages = poll_sqs_messages(SQS_queue_url_wallet, "wallet")
    print(f"Received messages from SQS: {received_messages}")
    
    # Fetch details for each received message ID
    analysis_details = []
    for message_id in received_messages:
        try:
            details = get_analysis(message_id, "wallet")
            analysis_details.append(details)
            print(f"Successfully fetched details for ID: {message_id}")
        except Exception as e:
            print(f"Error fetching details for ID {message_id}: {str(e)}")
            print(f"Error traceback: {traceback.format_exc()}")
    
    return {
        "analyses": result,
        "sqs_messages_received": received_messages,
        "analysis_details": analysis_details
    }
