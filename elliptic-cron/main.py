import os
import json
import boto3
import asyncio
import traceback
import pandas as pd
from datetime import datetime
from elliptic import AML
from fastapi import FastAPI
from sqlalchemy import create_engine, Table, Column, MetaData, Integer, Float, String, Boolean, text, inspect, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.pool import QueuePool

# Environment variables
ELLIPTIC_API_KEY = os.getenv('elliptic_api_key')
ELLIPTIC_API_SECRET = os.getenv('elliptic_api_secret')
SQS_QUEUE_URL = os.getenv('SQS_queue_url_wallet')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')
POSTGRES_URL = os.getenv('postgres_url', 'postgresql://doadmin:xxx@postgres-cluster-do-user-12892822-0.c.db.ondigitalocean.com:25060/elliptic')
POSTGRES_MAX_CONNECTIONS = int(os.getenv('postgres_max_connections', 2))

# Initialize AWS SQS client
sqs_client = boto3.client(
    'sqs',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)
print("Successfully initialized SQS client")

# Initialize the AML client
aml = AML(key=ELLIPTIC_API_KEY, secret=ELLIPTIC_API_SECRET)

# Initialize SQLAlchemy engine with connection pooling
engine = create_engine(
    POSTGRES_URL,
    future=True,
    poolclass=QueuePool,
    pool_size=POSTGRES_MAX_CONNECTIONS,
    max_overflow=0  # Don't allow more connections than pool_size
)
metadata = MetaData()

# Event listener to ensure connections are returned to the pool
@event.listens_for(engine, 'checkout')
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    print("Connection checked out from pool")

@event.listens_for(engine, 'checkin')
def receive_checkin(dbapi_connection, connection_record):
    print("Connection returned to pool")

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

def poll_sqs_messages(queue_url: str, queue_type: str):
    """Poll all available messages from SQS queue"""
    try:
        print(f"Starting to poll messages from SQS queue: {queue_url}")
        print("SQS client configuration:", {
            "region": sqs_client.meta.region_name,
            "endpoint_url": sqs_client.meta.endpoint_url
        })
        
        all_messages = []
        while True:  # Keep polling until no more messages
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                WaitTimeSeconds=30,  # Increased wait time
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
                    sqs_client.delete_message(
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

async def get_wallet_transactions(date_str="2024-06-30", subject_type="address"):
    """Get wallet transactions from Elliptic API and process them."""
    try:
        successful_ids = []
        failed_ids = []
        
        # Format timestamps for the full day
        start_of_day = f"{date_str}T00:20:05.529Z"
        end_of_day = f"{date_str}T23:20:05.529Z"
        
        # Get wallet transactions with exact parameters as specified
        params = {
            "analysed_at_before": end_of_day,
            "analysed_at_after": start_of_day,
            "risk_rules": "",
            "sort": "-analysed_at",
            "page": 1,
            "per_page": 20
        }
        
        print(f"\nFetching wallet transactions with params: {json.dumps(params, indent=2)}")
        
        # Make GET request to wallet endpoint with retries
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                response = aml.client.get('/v2/wallet', params=params)
                response.raise_for_status()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                await asyncio.sleep(retry_delay)
        data = response.json()
        transaction_items = data.get('items', [])
        
        if not transaction_items:
            print("No items found in response")
            return {"status": "success", "message": "No transactions found"}
            
        print(f"\nFound {len(transaction_items)} transactions to process:")
        for item in transaction_items:
            print(f"ID: {item['id']}, Type: {item.get('type')}, Status: {item.get('process_status')}")
        
        # Send IDs to SQS
        for item in transaction_items:
            try:
                # Send full item to SQS
                message_body = json.dumps(item)
                response = sqs_client.send_message(
                    QueueUrl=SQS_QUEUE_URL,
                    MessageBody=message_body
                )
                print(f"\nSent to SQS - ID: {item['id']}, MessageId: {response.get('MessageId')}")
            except Exception as e:
                print(f"Failed to send to SQS - ID: {item['id']}, Error: {str(e)}")
        
        # Wait for messages to be processed
        print("\nWaiting 10 seconds before polling messages...")
        await asyncio.sleep(10)  # Increased wait time
        
        # Poll messages using poll_sqs_messages
        received_messages = poll_sqs_messages(SQS_QUEUE_URL, "wallet")
        print(f"\nReceived {len(received_messages)} messages from SQS")
        
        # Process received messages
        for message_body in received_messages:
            try:
                # Parse message body
                try:
                    if isinstance(message_body, str):
                        message_data = json.loads(message_body)
                        tx_id = message_data.get('id')
                        if not tx_id and message_body.strip().startswith('"') and message_body.strip().endswith('"'):
                            # Handle case where the message is just an ID string
                            tx_id = message_body.strip().strip('"')
                        elif not tx_id:
                            print(f"Skipping invalid message format: {message_body}")
                            continue
                    else:
                        print(f"Skipping non-string message: {message_body}")
                        continue
                except json.JSONDecodeError:
                    # Try to handle case where the message is just an ID string
                    if isinstance(message_body, str) and message_body.strip():
                        tx_id = message_body.strip()
                    else:
                        print(f"Failed to parse message body: {message_body}")
                        continue
                
                print(f"\nProcessing transaction: {tx_id}")
                
                # Get transaction details with retries
                for attempt in range(max_retries):
                    try:
                        response = aml.client.get(f'/v2/wallet/{tx_id}')
                        response.raise_for_status()
                        tx_details = response.json()
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            print(f"Failed to get details for {tx_id} after {max_retries} attempts: {str(e)}")
                            failed_ids.append(tx_id)
                            continue
                        print(f"Attempt {attempt + 1} failed for {tx_id}: {str(e)}")
                        await asyncio.sleep(retry_delay)
                
                if tx_details:
                    print(f"Got details for {tx_id}:")
                    print(f"Type: {tx_details.get('type')}")
                    print(f"Status: {tx_details.get('process_status')}")
                    print(f"Error: {tx_details.get('error', {}).get('message', 'None')}")
                    
                    # Write transaction details to database
                    success = write_to_database(tx_details, "wallet")
                    if success:
                        print(f"Successfully wrote transaction {tx_id} to database")
                        successful_ids.append(tx_id)
                    else:
                        print(f"Failed to write transaction {tx_id} to database")
                        failed_ids.append(tx_id)
            except Exception as e:
                print(f"Error processing transaction: {str(e)}")
                print(traceback.format_exc())
                failed_ids.append(tx_id if 'tx_id' in locals() else message_body)
        
        # Remove duplicates from successful and failed IDs
        successful_ids = list(dict.fromkeys(successful_ids))
        failed_ids = list(dict.fromkeys(failed_ids))
        
        # Remove IDs from failed if they're in successful
        failed_ids = [id for id in failed_ids if id not in successful_ids]
        
        # Query database to get actual count and details
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM wallet")).scalar()
            return {
                "status": "success", 
                "message": f"Found {len(transaction_items)} transactions, successfully stored {len(successful_ids)} in database",
                "details": {
                    "total_found": len(transaction_items),
                    "successful": len(successful_ids),
                    "failed": len(failed_ids),
                    "successful_ids": successful_ids,
                    "failed_ids": failed_ids,
                    "total_in_db": result
                }
            }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}

app = FastAPI()

@app.get("/process-wallet-transactions/{date}")
async def process_transactions(date: str, subject_type: str = "address"):
    """API endpoint to trigger wallet transaction processing for a specific date."""
    return await get_wallet_transactions(date, subject_type)
