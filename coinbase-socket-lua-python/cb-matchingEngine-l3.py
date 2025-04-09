import asyncio
import base64
import hashlib
import hmac
import json
import time
import websockets
import uuid  # For generating unique order identifiers
import aiohttp  # For sending HTTP requests
from decimal import Decimal, getcontext, InvalidOperation

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

# =========================
# Decimal Configuration
# =========================

getcontext().prec = 28

# Global variable to store Level3 schema once received
level3_schema = None

# In-memory store for open orders; keys are Coinbase order_id (which becomes orderUUID)
open_orders = {}

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

def generate_uuid():
    # Generates a unique hexadecimal UUID string for orderUUID if needed elsewhere.
    return uuid.uuid4().hex

def map_order_side(side):
    # Map Coinbase side ("buy"/"sell") to order payload side ("BID"/"ASK")
    if side.lower() == "buy":
        return "BID"
    elif side.lower() == "sell":
        return "ASK"
    return side.upper()

# =========================
# Level3 Message Processors
# =========================

def process_level3_open(message):
    """
    Processes a level3 'open' message.
    Coinbase schema: ["open", "product_id", "sequence", "order_id", "side", "price", "size", "time"]

    Mapping:
      - product_id  --> symbol (hard-coded as "BTC-USD")
      - order_id    --> orderUUID
      - price       --> price
      - size        --> size 
      - side        --> mapped to BID (if "buy") or ASK (if "sell")
      - sequence    --> ignored
      - time        --> logged

    New handling:
      - If size is less than or equal to 0, send a cancellation payload immediately.
    """
    try:
        _, product_id, sequence, order_id, side, price_str, size_str, time_str = message
        price = Decimal(price_str)
        size = Decimal(size_str)
        # Debug log the raw and parsed size
        print(f"Processing open message: raw size='{size_str}', parsed size={size}")
    except Exception as e:
        print(f"Error processing level3 open message: {e}")
        return

    # If size is less than or equal to zero, send a cancellation order immediately.
    if size <= Decimal('0'):
        print("Received open message with size <= 0. Sending cancellation order immediately.")
        cancel_payload = {
            "command": "CANCEL_ORDER",
            "orderType": "GTC",
            "userId": 1,
            "userType": "MM",      # Must include this field
            "orderUUID": order_id,  # Mapping Coinbase order_id to orderUUID
            "symbol": "BTC-USD",    # Hard-coded symbol from product_id
            "side": map_order_side(side),
            "price": float(price),
            "size": float(size)
        }
        asyncio.create_task(cancel_order(cancel_payload))
        return

    # Build the order payload if size > 0
    order_payload = {
        "command": "PLACE_ORDER",
        "orderType": "GTC",
        "userId": 1,
        "userType": "MM",      # Must include this field
        "orderUUID": order_id,  # Mapping Coinbase order_id to orderUUID
        "symbol": "BTC-USD",    # Hard-coded symbol from product_id
        "side": map_order_side(side),
        "price": float(price),
        "size": float(size)
    }
    # Store the order in our in-memory open orders using orderUUID as key
    open_orders[order_id] = order_payload

    # Log the timestamp from the Coinbase message (if needed)
    print(f"Order time from Coinbase: {time_str}")
    print("Level3 Open Order Payload:", json.dumps(order_payload, indent=4))
    asyncio.create_task(send_order(order_payload))

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
    
    update_data = {
        'total_price_USD': format_decimal(price * new_size, 20),
        'quantity': format_decimal(new_size, 20),
        'sequence': sequence,
        'time': time_str
    }
    print(f"Level3 Change updated order {order_id} with data: {json.dumps(update_data, indent=4)}")
    # Optionally, update the order in open_orders if needed.

def process_level3_done(message):
    """
    Processes a level3 'done' message.
    Schema: ["done", "product_id", "sequence", "order_id", "time"]
    
    When a done message is received, if the order exists in our open_orders store,
    we construct a cancellation payload and send it.
    """
    try:
        _, product_id, sequence, order_id, time_str = message
    except Exception as e:
        print(f"Error processing level3 done message: {e}")
        return
    
    if order_id in open_orders:
        # Retrieve and remove the order from the store
        order_payload = open_orders.pop(order_id)
        # Build cancellation payload using the stored order details
        cancel_payload = order_payload.copy()
        cancel_payload["command"] = "CANCEL_ORDER"
        print(f"Level3 Done: Cancelling order {order_id} at time {time_str}")
        asyncio.create_task(cancel_order(cancel_payload))
    else:
        print(f"Level3 Done: Order {order_id} not found for cancellation.")

def process_level3_match(message):
    """
    Processes a level3 'match' message.
    Schema: ["match", "product_id", "sequence", "maker_order_id", "taker_order_id", "price", "size", "time"]
    """
    print("Level3 match received.")

def process_level3_noop(message):
    """
    Processes a level3 'noop' message.
    Schema: ["noop", "product_id", "sequence", "time"]
    """
    print("Level3 Noop received.")

def process_level3_message(message):
    """
    Processes a level3 message based on its type.
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
        'channels': [CHANNEL],
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
# Order Processing Functions
# =========================

async def send_order(payload):
    """
    Sends an HTTP POST to the orders endpoint with the given payload.
    """
    url = "http://java-service:7001/orders"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                resp_text = await response.text()
                print(f"Sent order: {payload}\nResponse: {resp_text}")
    except Exception as e:
        print(f"Error sending order: {e}")

async def cancel_order(payload):
    """
    Sends an HTTP POST to cancel an order using the provided cancellation payload.
    The payload format is:
    {
      "command": "CANCEL_ORDER",
      "orderType": "GTC",
      "userId": 1,
      "userType": "MM",      # <-- Must include this
      "orderUUID": <original order_id>,
      "symbol": "BTC-USD",
      "side": "BID" or "ASK",
      "price": <price>,
      "size": <size>
    }
    """
    url = "http://java-service:7001/orders"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                resp_text = await response.text()
                print(f"Cancelled order: {payload}\nResponse: {resp_text}")
    except Exception as e:
        print(f"Error cancelling order: {e}")

# =========================
# Main Execution
# =========================

if __name__ == '__main__':
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("Exiting WebSocket..")