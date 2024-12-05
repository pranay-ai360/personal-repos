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

# **IMPORTANT:** Remove hardcoded credentials and use environment variables instead.
# Example:
# API_KEY = os.getenv('COINBASE_API_KEY')
# PASSPHRASE = os.getenv('COINBASE_PASSPHRASE')
# SECRET_KEY = os.getenv('COINBASE_SECRET_KEY')

# API_KEY = 'your_api_key_here'          # Replace with your actual API key
# PASSPHRASE = 'your_passphrase_here'    # Replace with your actual passphrase
# SECRET_KEY = 'your_secret_key_here'    # Replace with your actual secret key

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

CHANNEL = 'level2'
PRODUCT_IDS = 'BTC-USD'

SMALLEST_UNIT = '0.0000001'  # Define the smallest unit globally as a string to maintain precision

PHPUSD_rate = 58.001

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

def format_decimal(value, decimal_places=20):
    """
    Formats a Decimal value to a string with up to 'decimal_places' decimal places,
    removing any trailing zeros.

    Args:
        value (Decimal): The Decimal value to format.
        decimal_places (int): Maximum number of decimal places.

    Returns:
        str: Formatted decimal as string.
    """
    format_str = f'{{0:.{decimal_places}f}}'
    return format_str.format(value).rstrip('0').rstrip('.') if '.' in format_str.format(value) else format_str.format(value)

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
    Maps the side from 'BID'/'ASK' to 'buy'/'sell'.
    
    Args:
        side (str): The side of the order ('bid' or 'ask').
    
    Returns:
        str: Mapped side ('buy' or 'sell').
    """
    mapping = {
        'BID': 'buy',
        'ASK': 'sell'
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
                price_per_base_asset_USD = Decimal(entry[0])  # Renamed
                quantity = Decimal(entry[1])
            except (InvalidOperation, TypeError) as e:
                print(f"Invalid entry data: {e}. Skipping entry.")
                continue

            try:
                total_price_USD = price_per_base_asset_USD * quantity  # Renamed
                smallest_unit_decimal = Decimal(SMALLEST_UNIT)
                price_per_smallest_unit = price_per_base_asset_USD * smallest_unit_decimal
                # Removed: no_of_units_available_as_per_smallest_unit
                # Removed: how_much_value_of_crypto_in_cents

                # Added PHP calculations
                price_per_base_asset_PHP = price_per_base_asset_USD * Decimal(PHPUSD_rate)
                total_price_PHP = total_price_USD * Decimal(PHPUSD_rate)
            except (InvalidOperation, DivisionByZero) as e:
                print(f"Error in calculations: {e}. Skipping entry.")
                continue

            order_data = {
                "pair": product_id,
                "side": map_side(side).capitalize(),  # 'Buy' or 'Sell'
                "smallest_unit": SMALLEST_UNIT,       # "0.0000001"
                "price_per_base_asset_USD": format_decimal(price_per_base_asset_USD, 20),
                "quantity": format_decimal(quantity, 20),
                "total_price_USD": format_decimal(total_price_USD, 20),
                "price_per_smallest_unit": format_decimal(price_per_smallest_unit, 20),
                "price_per_base_asset_PHP": format_decimal(price_per_base_asset_PHP, 20),  # Added
                "total_price_PHP": format_decimal(total_price_PHP, 20)                   # Added
            }
            data.append(order_data)

            # =========================
            # Redis Storage
            # =========================

            # PRANAY COMMENT 

            #  mapping = {
            #         'BID': 'buy',
            #         'ASK': 'sell'
            # side should either buy or sell #
            #     }

            order_uuid = generate_uuid()  # Generate a unique UUID
            sorted_set_key = f"{product_id}_{map_side(side)}"  # e.g., 'BTC-USD_buy'
            order_id = generate_order_id()  # e.g., 'order:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

            try:
                # Insert order into the specific sorted set '{product-id}_{side}'
                # Convert Decimal to float for the score

                redis_client.zadd(sorted_set_key, {order_id: prepare_redis_score(price_per_base_asset_USD)})  # Updated variable

                # Create a hash for the order with detailed information
                redis_client.hset(order_id, mapping={
                    'pair': product_id,
                    'side': map_side(side).capitalize(),  # 'Buy' or 'Sell'
                    'smallest_unit': SMALLEST_UNIT,
                    'price_per_base_asset_USD': format_decimal(price_per_base_asset_USD, 20),  # Updated
                    'quantity': format_decimal(quantity, 20),
                    'total_price_USD': format_decimal(total_price_USD, 20),                    # Updated
                    'price_per_smallest_unit': format_decimal(price_per_smallest_unit, 20),
                    'price_per_base_asset_PHP': format_decimal(price_per_base_asset_PHP, 20),  # Added
                    'total_price_PHP': format_decimal(total_price_PHP, 20)                       # Added
                })
            except redis.exceptions.RedisError as e:
                print(f"Redis error while storing order {order_id}: {e}")

    # Print the data as JSON
    print(json.dumps(data, indent=4))

def process_l2update(message):
    """
    Processes the 'l2update' type messages, updates Redis accordingly,
    and prepares JSON output.

    Args:
        message (dict): The l2update message from the WebSocket.
    """
    product_id = message.get('product_id', 'N/A')
    changes = message.get('changes', [])

    for change in changes:
        try:
            side, price_str, new_quantity_str = change
            price = Decimal(price_str)
            new_quantity = Decimal(new_quantity_str)
        except (InvalidOperation, ValueError) as e:
            print(f"Invalid change data: {e}. Skipping change.")
            continue

        mapped_side = map_side(side).capitalize()  # 'Buy' or 'Sell'
        sorted_set_key = f"{product_id}_{map_side(side)}"  # e.g., 'BTC-USD_buy'

        try:
            # Convert price to float for Redis compatibility
            price_float = float(price)

            # Fetch all order_ids with the given price
            order_ids = redis_client.zrangebyscore(sorted_set_key, price_float, price_float)
            
            # Remove all matching orders
            for order_id in order_ids:
                redis_client.zrem(sorted_set_key, order_id)
                redis_client.delete(order_id)
            print(f"Removed orders at price {price} on side {mapped_side}.")

            # Scan again for remaining order_ids at the same price
            order_ids = redis_client.zrangebyscore(sorted_set_key, price_float, price_float)

            # Check for zero quantity after the scan
            if new_quantity <= Decimal('0'):
                print(f"Skipping insertion for zero quantity at price {price} on side {mapped_side}.")
                continue

            # If no existing orders and quantity is non-zero, insert a new one
            if not order_ids:
                mock_snapshot = {
                    "type": "snapshot",
                    "product_id": product_id,
                    "bids": [],
                    "asks": []
                }

                if side.lower() == 'buy':
                    mock_snapshot["bids"].append([str(price), str(new_quantity)])
                elif side.lower() == 'sell':
                    mock_snapshot["asks"].append([str(price), str(new_quantity)])

                process_snapshot(mock_snapshot)
                print(f"Inserted new order at price {price} on side {mapped_side} with quantity {new_quantity}.")
            else:
                # Update the quantity and total prices for existing orders
                for order_id in order_ids:
                    redis_client.hset(order_id, mapping={
                        'quantity': format_decimal(new_quantity, 20),
                        'total_price_USD': format_decimal(price * new_quantity, 20),
                        'total_price_PHP': format_decimal(price * new_quantity * Decimal(PHPUSD_rate), 20)
                    })
                print(f"Updated orders at price {price} on side {mapped_side} with new quantity {new_quantity}.")

        except redis.exceptions.RedisError as e:
            print(f"Redis error while processing l2update: {e}")

    # Optionally, print the update as JSON
    print(json.dumps(message, indent=4))

async def websocket_listener():
    """
    Connects to the Coinbase WebSocket API, subscribes to the specified channel,
    listens for incoming messages, processes snapshots and l2updates, and handles reconnections.
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
                    # print(response)  # Optionally print raw responses

                    try:
                        json_response = json.loads(response)
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}. Skipping message.")
                        continue

                    msg_type = json_response.get('type')

                    if msg_type == 'snapshot':
                        process_snapshot(json_response)
                    elif msg_type == 'l2update':
                        process_l2update(json_response)
                    else:
                        print(f"Unhandled message type: {msg_type}")

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