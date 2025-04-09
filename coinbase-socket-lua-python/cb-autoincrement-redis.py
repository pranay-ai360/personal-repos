import asyncio
import base64
import hashlib
import hmac
import json
import time
import websockets
import redis
import uuid

# =========================
# Coinbase API Configuration
# =========================

API_KEY = '24ab46f784d1b20db435b852086e3250'
PASSPHRASE = 'akmwnltyfgb'
SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

# Use Level3 channel
CHANNEL = 'level3'
PRODUCT_IDS = 'BTC-USD'

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
# Helper Functions
# =========================

def pad_base64(s):
    return s + '=' * (-len(s) % 4)

async def generate_signature():
    timestamp = str(time.time())
    message = f'{timestamp}GET{SIGNATURE_PATH}'
    padded_secret_key = pad_base64(SECRET_KEY)
    try:
        hmac_key = base64.b64decode(padded_secret_key)
    except Exception as e:
        print(f"Error decoding SECRET_KEY: {e}")
        exit(1)
    signature = hmac.new(
        hmac_key,
        message.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode().rstrip('\n')
    return signature_b64, timestamp

# =========================
# Redis Order Counter Function
# =========================

def get_or_create_order_counter(order_id):
    """
    Looks up the given order_id (from Coinbase) in Redis.
    If found, returns the associated counter number.
    If not found, increments a global counter, stores the new number,
    and returns it.
    """
    mapping_key = "uuid_to_number"
    counter_value = redis_client.hget(mapping_key, order_id)
    if counter_value is not None:
        print(f"Order {order_id} found with counter: {int(counter_value)}")
        return int(counter_value)
    else:
        new_counter = redis_client.incr("global:counter")
        redis_client.hset(mapping_key, order_id, new_counter)
        print(f"Order {order_id} inserted with new counter: {new_counter}")
        return new_counter

# =========================
# Process Coinbase Level3 Messages
# =========================

def process_level3_message(message):
    """
    Processes a Level3 message from Coinbase.
    For messages that include order IDs, it retrieves (or creates) a counter.
    
    Schemas:
      open:  ["open", "product_id", "sequence", "order_id", "side", "price", "size", "time"]
      change: ["change", "product_id", "sequence", "order_id", "price", "size", "time"]
      done:  ["done", "product_id", "sequence", "order_id", "time"]
      match: ["match", "product_id", "sequence", "maker_order_id", "taker_order_id", "price", "size", "time"]
      noop:  ["noop", "product_id", "sequence", "time"]
    """
    if not isinstance(message, list) or len(message) == 0:
        return
    msg_type = message[0]
    if msg_type == 'open':
        order_id = message[3]
        counter = get_or_create_order_counter(order_id)
        print(f"Open message: order_id: {order_id}, counter: {counter}")
    elif msg_type == 'change':
        order_id = message[3]
        counter = get_or_create_order_counter(order_id)
        print(f"Change message: order_id: {order_id}, counter: {counter}")
    elif msg_type == 'done':
        order_id = message[3]
        counter = get_or_create_order_counter(order_id)
        print(f"Done message: order_id: {order_id}, counter: {counter}")
    # elif msg_type == 'match':
    #     maker_order_id = message[3]
    #     taker_order_id = message[4]
    #     maker_counter = get_or_create_order_counter(maker_order_id)
    #     taker_counter = get_or_create_order_counter(taker_order_id)
    #     print(f"Match message: maker_order_id: {maker_order_id}, counter: {maker_counter}; "
    #           f"taker_order_id: {taker_order_id}, counter: {taker_counter}")
    # elif msg_type == 'noop':
    #     print("Noop message received.")
    else:
        print(f"Unhandled message type: {msg_type}")

# =========================
# Coinbase Level3 WebSocket Listener
# =========================

async def websocket_listener():
    signature_b64, timestamp = await generate_signature()
    subscribe_message = json.dumps({
        'type': 'subscribe',
        'channels': [CHANNEL],
        'product_ids': [PRODUCT_IDS],
        'signature': signature_b64,
        'key': API_KEY,
        'passphrase': PASSPHRASE,
        'timestamp': timestamp
    })

    async with websockets.connect(URI, ping_interval=None) as websocket:
        await websocket.send(subscribe_message)
        print("Subscribed to Coinbase Level3 WebSocket channel.")
        while True:
            response = await websocket.recv()
            try:
                json_response = json.loads(response)
            except Exception as e:
                print(f"Error decoding message: {e}")
                continue

            # Handle the schema message
            if isinstance(json_response, dict) and json_response.get('type') == 'level3' and 'schema' in json_response:
                print("Received Level3 schema:")
                print(json.dumps(json_response['schema'], indent=4))
                continue

            # Process level3 messages (which are expected as lists)
            if isinstance(json_response, list):
                print(f"Received Level3 message: {json_response}")
                process_level3_message(json_response)
            else:
                print(f"Unhandled message format: {json_response}")

# =========================
# Main Execution
# =========================

if __name__ == '__main__':
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("Exiting WebSocket...")