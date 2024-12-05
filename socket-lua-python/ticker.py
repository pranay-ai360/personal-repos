# API_KEY = '24ab46f784d1b20db435b852086e3250'
# PASSPHRASE = 'akmwnltyfgb'
# SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import websockets
import redis

# Provided API credentials (hardcoded)


# API_KEY = os.getenv('COINBASE_API_KEY')
# PASSPHRASE = os.getenv('COINBASE_PASSPHRASE')
# SECRET_KEY = os.getenv('COINBASE_SECRET_KEY')

# WebSocket feed URI and path for signature
URI = 'wss://ws-direct.sandbox.exchange.coinbase.com'
SIGNATURE_PATH = '/users/self/verify'

# PHP to USD exchange rate (fixed value as per your example)
PHPUSD_rate = 58.001

# Channel and product IDs to subscribe to
channel = 'ticker'
product_ids = ['BTC-USD', 'ETH-USD']  # Add more pairs as needed

# Redis connection setup
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Function to generate the signature for WebSocket connection
async def generate_signature():
    timestamp = str(time.time())
    message = f'{timestamp}GET{SIGNATURE_PATH}'
    hmac_key = base64.b64decode(SECRET_KEY)
    signature = hmac.new(
        hmac_key,
        message.encode('utf-8'),
        digestmod=hashlib.sha256).digest()
    signature_b64 = base64.b64encode(signature).decode().rstrip('\n')
    return signature_b64, timestamp

# WebSocket listener function to subscribe and listen to market data
async def websocket_listener():
    signature_b64, timestamp = await generate_signature()
    subscribe_message = json.dumps({
        'type': 'subscribe',
        'channels': [{'name': channel, 'product_ids': product_ids}],
        'signature': signature_b64,
        'key': API_KEY,
        'passphrase': PASSPHRASE,
        'timestamp': timestamp
    })

    while True:
        try:
            # Establish WebSocket connection
            async with websockets.connect(URI, ping_interval=None) as websocket:
                await websocket.send(subscribe_message)
                print(f"Subscribed to {channel} channel for products {product_ids}")
                while True:
                    # Receive and handle messages from the WebSocket feed
                    response = await websocket.recv()
                    json_response = json.loads(response)
                    
                    # Extract relevant data (product, price, etc.)
                    if 'type' in json_response and json_response['type'] == 'ticker':
                        product_id = json_response['product_id']
                        price = json_response['price']
                        
                        # Check if product ends with USD (e.g., BTC-USD, ETH-USD)
                        if product_id.endswith('USD'):
                            # Convert the price to PHP
                            price_php = float(price) * PHPUSD_rate
                            
                            # Create new product ID by replacing USD with PHP
                            maya_product_id = product_id.replace('USD', 'PHP')
                            
                            # Update the ticker data in Redis
                            redis_client.set(f"ticker:{maya_product_id}", price_php)
                            
                            # Publish the updated price to Redis Pub/Sub
                            redis_client.publish(f"{maya_product_id}", price_php)
                            print(f"{maya_product_id}: {price_php}")

        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
            print('Connection closed, retrying..')
            await asyncio.sleep(1)

# Run the WebSocket listener when the script is executed
if __name__ == '__main__':
    try:
        asyncio.run(websocket_listener())
    except KeyboardInterrupt:
        print("Exiting WebSocket..")