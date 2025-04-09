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

API_KEY = '24ab46f784d1b20db435b852086e3250'
PASSPHRASE = 'akmwnltyfgb'
SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

# Use Level3 channel
CHANNEL = 'level3'
PRODUCT_IDS = 'BTC-USD'

SMALLEST_UNIT = '0.0000001'
PHPUSD_rate = 58.001

# =========================
# Redis Configuration
# =========================

REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_CONNECT_TIMEOUT = 1000000

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        socket_timeout=REDIS_CONNECT_TIMEOUT
    )
    redis_client.ping()
    print("Connected to Redis successfully.")
except redis.exceptions.ConnectionError as e:
    print(f"Failed to connect to Redis: {e}")
    exit(1)

# =========================
# Decimal Configuration
# =========================

getcontext().prec = 28

# Global variable to store Level3 schema once received
level3_schema = None

# =========================
# Helper Functions
# =========================

def pad_base64(s):
    return s + '=' * (-len(s) % 4)

def format_decimal(value, decimal_places=20):
    format_str = f'{{0:.{decimal_places}f}}'
    return format_str.format(value).rstrip('0').rstrip('.') if '.' in format_str.format(value) else format_str.format(value)

async def generate_signature():
    timestamp = str(time.time())
    message = f'{timestamp}GET{SIGNATURE_PATH}'
    
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
    return f'order:{uuid.uuid4()}'

def generate_uuid():
    return uuid.uuid4().hex

def map_side(side):
    mapping = {
        'BID': 'buy',
        'ASK': 'sell',
        'buy': 'buy',
        'sell': 'sell'
    }
    return mapping.get(side.lower(), side.lower())

def prepare_redis_score(decimal_value):
    try:
        return float(decimal_value)
    except (InvalidOperation, TypeError) as e:
        print(f"Error converting Decimal to float: {e}")
        return 0.0

# =========================
# Level3 Message Processors
# =========================

def process_level3_open(message):
    """
    Processes a level3 'open' message.
    Schema: ["open", "product_id", "sequence", "order_id", "side", "price", "size", "time"]
    """
    try:
        _, product_id, sequence, order_id, side, price_str, size_str, time_str = message
        price = Decimal(price_str)
        size = Decimal(size_str)
    except Exception as e:
        print(f"Error processing level3 open message: {e}")
        return
    
    total_price = price * size
    smallest_unit_decimal = Decimal(SMALLEST_UNIT)
    price_per_smallest_unit = price * smallest_unit_decimal
    price_per_base_asset_PHP = price * Decimal(PHPUSD_rate)
    total_price_PHP = total_price * Decimal(PHPUSD_rate)
    
    order_data = {
        "pair": product_id,
        "side": map_side(side).capitalize(),
        "smallest_unit": SMALLEST_UNIT,
        "price_per_base_asset_USD": format_decimal(price, 20),
        "quantity": format_decimal(size, 20),
        "total_price_USD": format_decimal(total_price, 20),
        "price_per_smallest_unit": format_decimal(price_per_smallest_unit, 20),
        "price_per_base_asset_PHP": format_decimal(price_per_base_asset_PHP, 20),
        "total_price_PHP": format_decimal(total_price_PHP, 20),
        "sequence": sequence,
        "time": time_str
    }
    print("Level3 Open:", json.dumps(order_data, indent=4))
    
    # Store in Redis
    sorted_set_key = f"{product_id}_{map_side(side)}"
    try:
        redis_client.zadd(sorted_set_key, {order_id: prepare_redis_score(price)})
        redis_client.hset(order_id, mapping=order_data)
    except redis.exceptions.RedisError as e:
        print(f"Redis error while storing order {order_id}: {e}")

def process_level3_change(message):
    """
    Processes a level3 'change' message.
    Schema: ["change", "product_id", "sequence", "order_id", "price", "size", "time"]
    """
    try:
        _, product_id, sequence, order_id, price_str, new_size_str, time_str = message
        price = Decimal(price_str)
        new_size = Decimal(new_size_str)
    except Exception as e:
        print(f"Error processing level3 change message: {e}")
        return
    
    try:
        # Retrieve existing order to get side
        existing_order = redis_client.hgetall(order_id)
        if not existing_order:
            print(f"Order {order_id} not found for change message.")
            return
        side = existing_order.get(b'side', b'').decode() or 'buy'
        sorted_set_key = f"{product_id}_{map_side(side)}"
        
        total_price = price * new_size
        price_per_smallest_unit = price * Decimal(SMALLEST_UNIT)
        price_per_base_asset_PHP = price * Decimal(PHPUSD_rate)
        total_price_PHP = total_price * Decimal(PHPUSD_rate)
        
        update_data = {
            'quantity': format_decimal(new_size, 20),
            'total_price_USD': format_decimal(total_price, 20),
            'price_per_smallest_unit': format_decimal(price_per_smallest_unit, 20),
            'price_per_base_asset_PHP': format_decimal(price_per_base_asset_PHP, 20),
            'total_price_PHP': format_decimal(total_price_PHP, 20),
            'sequence': sequence,
            'time': time_str
        }
        redis_client.hset(order_id, mapping=update_data)
        redis_client.zadd(sorted_set_key, {order_id: prepare_redis_score(price)})
        print(f"Level3 Change updated order {order_id}.")
    except redis.exceptions.RedisError as e:
        print(f"Redis error while processing change for order {order_id}: {e}")

def process_level3_done(message):
    """
    Processes a level3 'done' message.
    Schema: ["done", "product_id", "sequence", "order_id", "time"]
    """
    try:
        _, product_id, sequence, order_id, time_str = message
    except Exception as e:
        print(f"Error processing level3 done message: {e}")
        return
    
    try:
        existing_order = redis_client.hgetall(order_id)
        if existing_order:
            side = existing_order.get(b'side', b'').decode() or 'buy'
            sorted_set_key = f"{product_id}_{map_side(side)}"
            redis_client.zrem(sorted_set_key, order_id)
            redis_client.delete(order_id)
            print(f"Level3 Done removed order {order_id}.")
        else:
            print(f"Order {order_id} not found for done message.")
    except redis.exceptions.RedisError as e:
        print(f"Redis error while processing done for order {order_id}: {e}")

def process_level3_match(message):
    """
    Processes a level3 'match' message.
    Schema: ["match", "product_id", "sequence", "maker_order_id", "taker_order_id", "price", "size", "time"]
    """
    try:
        _, product_id, sequence, maker_order_id, taker_order_id, price_str, size_str, time_str = message
        match_price = Decimal(price_str)
        match_size = Decimal(size_str)
    except Exception as e:
        print(f"Error processing level3 match message: {e}")
        return
    
    try:
        existing_order = redis_client.hgetall(maker_order_id)
        if not existing_order:
            print(f"Maker order {maker_order_id} not found for match message.")
            return
        current_size = Decimal(existing_order.get(b'quantity', b'0').decode())
        new_size = current_size - match_size
        if new_size <= 0:
            side = existing_order.get(b'side', b'').decode() or 'buy'
            sorted_set_key = f"{product_id}_{map_side(side)}"
            redis_client.zrem(sorted_set_key, maker_order_id)
            redis_client.delete(maker_order_id)
            print(f"Level3 Match removed maker order {maker_order_id} due to full match.")
        else:
            new_total_price = match_price * new_size
            price_per_smallest_unit = match_price * Decimal(SMALLEST_UNIT)
            price_per_base_asset_PHP = match_price * Decimal(PHPUSD_rate)
            total_price_PHP = new_total_price * Decimal(PHPUSD_rate)
            update_data = {
                'quantity': format_decimal(new_size, 20),
                'total_price_USD': format_decimal(new_total_price, 20),
                'price_per_smallest_unit': format_decimal(price_per_smallest_unit, 20),
                'price_per_base_asset_PHP': format_decimal(price_per_base_asset_PHP, 20),
                'total_price_PHP': format_decimal(total_price_PHP, 20),
                'sequence': sequence,
                'time': time_str
            }
            redis_client.hset(maker_order_id, mapping=update_data)
            print(f"Level3 Match updated maker order {maker_order_id} with reduced size.")
    except redis.exceptions.RedisError as e:
        print(f"Redis error while processing match for order {maker_order_id}: {e}")

def process_level3_noop(message):
    """
    Processes a level3 'noop' message.
    Schema: ["noop", "product_id", "sequence", "time"]
    """
    print("Level3 Noop received.")

def process_level3_message(message):
    """
    Processes a level3 message based on its type.
    If the message is an array, the first element indicates the type.
    """
    if not isinstance(message, list) or len(message) == 0:
        print("Invalid level3 message format.")
        return
    msg_type = message[0]
    if msg_type == 'open':
        process_level3_open(message)
    elif msg_type == 'change':
        process_level3_change(message)
    elif msg_type == 'done':
        process_level3_done(message)
    elif msg_type == 'match':
        process_level3_match(message)
    elif msg_type == 'noop':
        process_level3_noop(message)
    else:
        print(f"Unhandled level3 message type: {msg_type}")

# =========================
# WebSocket Listener
# =========================

async def websocket_listener():
    global level3_schema
    signature_b64, timestamp = await generate_signature()
    subscribe_message = json.dumps({
        'type': 'subscribe',
        'channels': ["level3"],
        'product_ids': [PRODUCT_IDS],
        'signature': signature_b64,
        'key': API_KEY,
        'passphrase': PASSPHRASE,
        'timestamp': timestamp
    })

    while True:
        try:
            async with websockets.connect(URI, ping_interval=None) as websocket:
                await websocket.send(subscribe_message)
                print("Subscribed to Level3 WebSocket channel.")

                while True:
                    response = await websocket.recv()
                    try:
                        json_response = json.loads(response)
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}. Skipping message.")
                        continue

                    # If the message is a dict with a Level3 schema, store it.
                    if isinstance(json_response, dict) and json_response.get('type') == 'level3' and 'schema' in json_response:
                        level3_schema = json_response['schema']
                        print("Received Level3 schema:")
                        print(json.dumps(level3_schema, indent=4))
                        continue
                    
                    # If the message is a list, process it as a Level3 message.
                    if isinstance(json_response, list):
                        process_level3_message(json_response)
                    else:
                        print(f"Unhandled message format: {json_response}")

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