#!/usr/bin/env python3
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import websockets
import uuid
from decimal import Decimal, getcontext, InvalidOperation, DivisionByZero
import aiohttp

# =========================
# Configuration Parameters
# =========================

API_KEY = '24ab46f784d1b20db435b852086e3250'
PASSPHRASE = 'akmwnltyfgb'
SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='

URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'
CHANNEL = 'level2'
PRODUCT_IDS = 'BTC-USD'

# We ignore PHP conversion; use USD values directly.
SMALLEST_UNIT = '0.0000001'  # Still used for calculations if needed

# =========================
# Decimal Configuration
# =========================

# Set precision high enough for financial calculations
getcontext().prec = 28

# =========================
# Global Order Counter
# =========================

ORDER_ID_COUNTER = 1000

def get_next_order_id():
    global ORDER_ID_COUNTER
    ORDER_ID_COUNTER += 1
    return ORDER_ID_COUNTER

# =========================
# Helper Functions
# =========================

def pad_base64(s):
    """Pad Base64 string with '=' to make its length a multiple of 4."""
    return s + '=' * (-len(s) % 4)

def format_decimal(value, decimal_places=20):
    """
    Formats a Decimal value to a string with up to 'decimal_places' decimal places,
    removing trailing zeros.
    """
    format_str = f'{{0:.{decimal_places}f}}'
    formatted = format_str.format(value)
    return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

async def generate_signature():
    """
    Generates a signature for authenticating with the Coinbase WebSocket API.
    Returns:
        tuple: (signature_b64, timestamp)
    """
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

# =========================
# Order Processing Functions
# =========================

async def process_snapshot(message):
    """
    Processes snapshot messages. For every order (BID/ASK), send an HTTP POST request
    to the orders endpoint.
    """
    product_id = message.get('product_id', 'N/A')
    
    # Process both asks and bids
    for side in ['asks', 'bids']:
        entries = message.get(side, [])
        for entry in entries:
            try:
                # Convert order data to Decimal for precision
                price_per_base_asset_USD = Decimal(entry[0])
                quantity = Decimal(entry[1])
            except (InvalidOperation, TypeError) as e:
                print(f"Invalid entry data: {e}. Skipping entry.")
                continue

            try:
                total_price_USD = price_per_base_asset_USD * quantity
                smallest_unit_decimal = Decimal(SMALLEST_UNIT)
                price_per_smallest_unit = price_per_base_asset_USD * smallest_unit_decimal
            except (InvalidOperation, DivisionByZero) as e:
                print(f"Error in calculations: {e}. Skipping entry.")
                continue

            # Generate a unique numeric order ID
            order_id = get_next_order_id()

            # Determine HTTP payload side: for 'bids' use "BID", for 'asks' use "ASK"
            http_side = "BID" if side == 'bids' else "ASK"

            # Build payload for HTTP POST (using USD values)
            payload = {
                "command": "PLACE_ORDER",
                "orderType": "GTC",
                "userId": 1,
                "userType": "MM",
                "orderId": order_id,
                "symbol": "SOL-USD",
                "side": http_side,
                "price": float(price_per_base_asset_USD),
                "size": float(quantity)
            }
            
            # Send the order via HTTP POST
            await send_order(payload)

            # Optionally print the order details
            order_data = {
                "pair": product_id,
                "side": http_side,
                "smallest_unit": SMALLEST_UNIT,
                "price_per_base_asset_USD": format_decimal(price_per_base_asset_USD, 20),
                "quantity": format_decimal(quantity, 20),
                "total_price_USD": format_decimal(total_price_USD, 20),
                "price_per_smallest_unit": format_decimal(price_per_smallest_unit, 20)
            }
            print(json.dumps(order_data, indent=4))

async def process_l2update(message):
    """
    Processes l2update messages. Currently, this function only prints the update.
    """
    print("l2update message received:")
    print(json.dumps(message, indent=4))

# =========================
# WebSocket Listener
# =========================

async def websocket_listener():
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
                    try:
                        json_response = json.loads(response)
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}. Skipping message.")
                        continue

                    msg_type = json_response.get('type')
                    if msg_type == 'snapshot':
                        await process_snapshot(json_response)
                    elif msg_type == 'l2update':
                        await process_l2update(json_response)
                    else:
                        print(f"Unhandled message type: {msg_type}")

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK) as e:
            print(f"Connection closed: {e}. Retrying in 1 second...")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Unexpected error: {e}. Retrying in 1 second...")
            await asyncio.sleep(1)

# =========================
# Main Execution
# =========================

if __name__ == '__main__':
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("Exiting WebSocket..")