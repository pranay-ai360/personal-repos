API_KEY = '24ab46f784d1b20db435b852086e3250'
PASSPHRASE = 'akmwnltyfgb'
SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='

# Copyright 2023-present Coinbase Global, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#!/usr/bin/env python3

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import websockets
import redis
import uuid  # For generating unique order IDs
from decimal import Decimal, getcontext, InvalidOperation, DivisionByZero

# =========================
# Configuration Parameters
# =========================

# It's highly recommended to set these as environment variables for security.
# Uncomment and set these environment variables securely in your environment.
# API_KEY = os.getenv('API_KEY')
# PASSPHRASE = os.getenv('PASSPHRASE')
# SECRET_KEY = os.getenv('SECRET_KEY')

# API_KEY = 'your_api_key_here'          # Replace with your actual API key
# PASSPHRASE = 'your_passphrase_here'    # Replace with your actual passphrase
# SECRET_KEY = 'your_secret_key_here'    # Replace with your actual secret key

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

CHANNEL = 'level2'
PRODUCT_IDS = 'BTC-USD'

SMALLEST_UNIT = '0.0000001'  # Define the smallest unit globally as a string to maintain precision

# =========================
# Redis Configuration
# =========================

# Configure Redis connection parameters
REDIS_HOST = '127.0.0.1'  # Ensure this matches your Redis server configuration
REDIS_PORT = 6379
REDIS_DB = 0               # Default Redis database
REDIS_CONNECT_TIMEOUT = 1000000  # Adjust timeout value if necessary

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        socket_timeout=REDIS_CONNECT_TIMEOUT
    )
    # Test the connection
    redis_client.ping()
    print("Connected to Redis successfully.")
except redis.exceptions.ConnectionError as e:
    print(f"Failed to connect to Redis: {e}")
    exit(1)

# =========================
# Decimal Configuration
# =========================

# Set the precision high enough to handle financial calculations
getcontext().prec = 28  # You can adjust this as needed

# =========================
# Helper Functions
# =========================

def pad_base64(s):
    """Pad Base64 string with '=' to make its length a multiple of 4."""
    return s + '=' * (-len(s) % 4)

async def generate_signature():
    """
    Generates a signature for authenticating with the Coinbase WebSocket API.
    
    Returns:
        tuple: (signature_b64, timestamp)
    """
    timestamp = str(time.time())
    message = f'{timestamp}GET{SIGNATURE_PATH}'
    
    # Pad the SECRET_KEY if necessary
    padded_secret_key = pad_base64(SECRET_KEY)
    
    try:
        hmac_key = base64.b64decode(padded_secret_key)
    except (base64.binascii.Error, TypeError) as e:
        print(f"Error decoding SECRET_KEY: {e}")
        exit(1)
    
    signature = hmac.new(
        hmac_key,
        message.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode().rstrip('\n')
    return signature_b64, timestamp

def generate_order_id():
    """
    Generates a unique order ID using UUID4.
    
    Returns:
        str: A unique order ID string.
    """
    return f'order:{uuid.uuid4()}'

def generate_uuid():
    """
    Generates a unique UUID string.
    
    Returns:
        str: A 32-character hexadecimal UUID string.
    """
    return uuid.uuid4().hex  # Generates a 32-character hexadecimal string

def map_side(side):
    """
    Maps the side from 'BID'/'ASK' to 'buys'/'sells'.
    
    Args:
        side (str): The side of the order ('bids' or 'asks').
    
    Returns:
        str: Mapped side ('buys' or 'sells').
    """
    mapping = {
        'BID': 'buys',
        'ASK': 'sells'
    }
    return mapping.get(side.upper(), side.lower())

def prepare_redis_score(decimal_value):
    """
    Converts a Decimal to float for Redis sorted set scores.
    
    Args:
        decimal_value (Decimal): The Decimal value to convert.
    
    Returns:
        float: The converted float value.
    """
    try:
        return float(decimal_value)
    except (InvalidOperation, TypeError) as e:
        print(f"Error converting Decimal to float: {e}")
        return 0.0  # or handle accordingly

def process_snapshot(message):
    """
    Processes the 'snapshot' type messages, performs calculations,
    stores data in Redis, and prepares JSON output.
    
    Args:
        message (dict): The snapshot message from the WebSocket.
    """
    data = []
    product_id = message.get('product_id', 'N/A')

    for side in ['asks', 'bids']:
        entries = message.get(side, [])
        for entry in entries:
            try:
                # Convert string entries to Decimal for precise arithmetic
                price_per_base_asset = Decimal(entry[0])
                quantity = Decimal(entry[1])
            except (InvalidOperation, TypeError) as e:
                print(f"Invalid entry data: {e}. Skipping entry.")
                continue

            try:
                total_price = price_per_base_asset * quantity
                smallest_unit_decimal = Decimal(SMALLEST_UNIT)
                price_per_smallest_unit = price_per_base_asset * smallest_unit_decimal
                no_of_units_available_as_per_smallest_unit = quantity / smallest_unit_decimal
                how_much_value_of_crypto_in_cents = total_price * Decimal('100')
            except (InvalidOperation, DivisionByZero) as e:
                print(f"Error in calculations: {e}. Skipping entry.")
                continue

            order_data = {
                "pair": product_id,
                "side": map_side(side).capitalize(),  # 'Buys' or 'Sells'
                "smallest_unit": SMALLEST_UNIT,       # "0.0000001"
                "price_per_base_asset": f"{price_per_base_asset:.12f}",
                "quantity": f"{quantity:.12f}",
                "total_price": f"{total_price:.12f}",
                "price_per_smallest_unit": f"{price_per_smallest_unit:.12f}",
                "no_of_units_available_as_per_smallest_unit": f"{no_of_units_available_as_per_smallest_unit:.12f}",
                "how_much_value_of_crypto_in_cents": f"{how_much_value_of_crypto_in_cents:.12f}"
            }
            data.append(order_data)

            # =========================
            # Redis Storage
            # =========================

            order_uuid = generate_uuid()  # Generate a unique UUID
            sorted_set_key = f"{product_id}_{map_side(side)}"  # e.g., 'BTC-USD_buys'
            order_id = generate_order_id()  # e.g., 'order:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

            try:
                # Insert order into the specific sorted set '{product-id}_{side}'
                # Convert Decimal to float for the score
                redis_client.zadd(sorted_set_key, {order_uuid: prepare_redis_score(price_per_base_asset)})

                # Create a hash for the order with detailed information
                redis_client.hset(order_id, mapping={
                    'pair': product_id,
                    'side': map_side(side).capitalize(),  # 'Buys' or 'Sells'
                    'smallest_unit': SMALLEST_UNIT,
                    'price_per_base_asset': f"{price_per_base_asset:.12f}",
                    'quantity': f"{quantity:.12f}",
                    'total_price': f"{total_price:.12f}",
                    'price_per_smallest_unit': f"{price_per_smallest_unit:.12f}",
                    'no_of_units_available_as_per_smallest_unit': f"{no_of_units_available_as_per_smallest_unit:.12f}",
                    'how_much_value_of_crypto_in_cents': f"{how_much_value_of_crypto_in_cents:.12f}"
                })
            except redis.exceptions.RedisError as e:
                print(f"Redis error while storing order {order_id}: {e}")

    # Print the data as JSON
    print(json.dumps(data, indent=4))

async def websocket_listener():
    """
    Connects to the Coinbase WebSocket API, subscribes to the specified channel,
    listens for incoming messages, processes snapshots, and handles reconnections.
    """
    signature_b64, timestamp = await generate_signature()
    subscribe_message = json.dumps({
        'type': 'subscribe',
        'channels': [{'name': CHANNEL, 'product_ids': [PRODUCT_IDS]}],
        'signature': signature_b64,
        'key': API_KEY,
        'passphrase': PASSPHRASE,
        'timestamp': timestamp
    })

    while True:
        try:
            async with websockets.connect(URI, ping_interval=None) as websocket:
                await websocket.send(subscribe_message)
                print("Subscribed to WebSocket channel.")

                while True:
                    response = await websocket.recv()
                    print(response)  # Optionally print raw responses
                    json_response = json.loads(response)

                    if json_response.get('type') == 'snapshot':
                        process_snapshot(json_response)

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK) as e:
            print(f'Connection closed: {e}. Retrying in 1 second...')
            await asyncio.sleep(1)
        except Exception as e:
            print(f'Unexpected error: {e}. Retrying in 1 second...')
            await asyncio.sleep(1)

# =========================
# Main Execution
# =========================

if __name__ == '__main__':
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("Exiting WebSocket..")