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
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import websockets
from tabulate import tabulate
import redis
import uuid  # For generating unique order IDs
from decimal import Decimal, getcontext

# =========================
# Configuration Parameters
# =========================

# Uncomment and set these environment variables securely
# API_KEY = str(os.environ.get('API_KEY'))
# PASSPHRASE = str(os.environ.get('PASSPHRASE'))
# SECRET_KEY = str(os.environ.get('SECRET_KEY'))

# API_KEY = 'your_api_key_here'          # Replace with your actual API key
# PASSPHRASE = 'your_passphrase_here'    # Replace with your actual passphrase
# SECRET_KEY = 'your_secret_key_here'    # Replace with your actual secret key

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

CHANNEL = 'level2'
PRODUCT_IDS = 'BTC-USD'

SMALLEST_UNIT = Decimal('0.0000001')  # Define the smallest unit globally

# Set decimal precision high enough to handle small units
getcontext().prec = 100

# =========================
# Redis Configuration
# =========================

# Configure Redis connection parameters
REDIS_HOST = '127.0.0.1'  # Ensure this matches your Redis server configuration
REDIS_PORT = 6379
REDIS_DB = 0  # Default Redis database
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
# Helper Functions
# =========================

async def generate_signature():
    """
    Generates a signature for authenticating with the Coinbase WebSocket API.
    """
    timestamp = str(time.time())
    message = f'{timestamp}GET{SIGNATURE_PATH}'
    hmac_key = base64.b64decode(SECRET_KEY)
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
    """
    return f'order:{uuid.uuid4()}'

def generate_uuid():
    """
    Generates a unique UUID string.
    """
    return uuid.uuid4().hex  # Generates a 32-character hexadecimal string

def format_decimal(value, decimal_places=8):
    """
    Formats a Decimal value to a fixed number of decimal places without exponential notation.
    """
    quantize_str = '1.' + '0' * decimal_places
    return str(value.quantize(Decimal(quantize_str)))



def map_side(side):
    """
    Maps the side from 'BID'/'ASK' to 'buys'/'sells'.
    """
    mapping = {
        'BID': 'buys',
        'ASK': 'sells'
    }
    return mapping.get(side.upper(), side.lower())


def process_snapshot(message):
    """
    Processes the 'snapshot' type messages, performs calculations,
    displays the data, and stores it in Redis.
    """
    data = []
    product_id = message.get('product_id', 'N/A')

    for side in ['asks', 'bids']:
        entries = message.get(side, [])
        for entry in entries:
            price_per_base_asset = Decimal(entry[0])
            quantity = Decimal(entry[1])
            total_price = price_per_base_asset * quantity
            price_per_smallest_unit = price_per_base_asset * SMALLEST_UNIT
            no_of_units_available_as_per_smallest_unit = quantity / SMALLEST_UNIT
            how_much_value_of_crypto_in_cents = total_price * Decimal('100')

            # Format all Decimal values to avoid exponential notation
            price_per_base_asset_str = format_decimal(price_per_base_asset, 2)
            quantity_str = format_decimal(quantity, 8)
            total_price_str = format_decimal(total_price, 8)
            price_per_smallest_unit_str = format_decimal(price_per_smallest_unit, 8)
            no_of_units_available_str = format_decimal(no_of_units_available_as_per_smallest_unit, 2)
            how_much_value_in_cents_str = format_decimal(how_much_value_of_crypto_in_cents, 2)

            row = [
                product_id,
                side.upper(),
                format_decimal(SMALLEST_UNIT, 7),  # 0.0000001
                price_per_base_asset_str,
                quantity_str,
                total_price_str,
                price_per_smallest_unit_str,
                no_of_units_available_str,
                how_much_value_in_cents_str
            ]
            data.append(row)

            # =========================
            # Redis Storage
            # =========================

            order_uuid = generate_uuid()  # Generate a unique UUID
            sorted_set_key = f"{product_id}_{map_side(side)}"  # e.g., 'BTC-USD_buys'
            order_id = f'order:{order_uuid}'  # Hash key for the order

            try:
                # Insert order into the sorted set with price_per_base_asset as the score
                redis_client.zadd(sorted_set_key, {order_uuid: float(price_per_base_asset)})

                # Create a hash for the order with detailed information
                redis_client.hmset(order_id, {
                    'pair': product_id,
                    'side': side.upper(),
                    'smallest_unit': format_decimal(SMALLEST_UNIT, 7),
                    'price_per_base_asset': price_per_base_asset_str,
                    'quantity': quantity_str,
                    'total_price': total_price_str,
                    'price_per_smallest_unit': price_per_smallest_unit_str,
                    'no_of_units_available_as_per_smallest_unit': no_of_units_available_str,
                    'how_much_value_of_crypto_in_cents': how_much_value_in_cents_str
                })
            except redis.exceptions.RedisError as e:
                print(f"Redis error while storing order {order_id}: {e}")

    # Define headers for the table
    headers = [
        "pair",
        "side",
        "smallest_unit",
        "price_per_base_asset",
        "quantity",
        "total_price",
        "price_per_smallest_unit",
        "no_of_units_available_as_per_smallest_unit",
        "how_much_value_of_crypto_in_cents"
    ]

    # Print the table
    print(tabulate(data, headers=headers, tablefmt="grid"))

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
                    json_response = json.loads(response)

                    # Uncomment the following line to print raw JSON responses (optional)
                    # print(json_response)

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