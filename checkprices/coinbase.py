import http.client
import hmac
import hashlib
import time
import base64
import json
import urllib.parse
import time as time_module



# API credentials
api_key = '24ab46f784d1b20db435b852086e3250'
api_secret = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='
passphrase = 'akmwnltyfgb'


# Variables for conversion
usdphprate = 57.25
margin = 0.025  # 2.5%


# Set request details
timestamp = str(time_module.time())
method = 'GET'
start_time = '2024-10-18T17:50:11'
end_time = '2024-10-18T17:54:11'
granularity = 60  # 1 minute

# URL encode the start and end time
query_params = urllib.parse.urlencode({
    'granularity': granularity,
    'start': start_time,
    'end': end_time
})

request_path = f'/products/BTC-USD/candles?{query_params}'
body = ''  # Empty for GET requests

# Create the prehash string
message = timestamp + method + request_path + body

# Create HMAC signature
key = base64.b64decode(api_secret)
signature = hmac.new(key, message.encode('utf-8'), hashlib.sha256)
signature_b64 = base64.b64encode(signature.digest())

# Establish connection
conn = http.client.HTTPSConnection("api.exchange.coinbase.com")

# Set headers
headers = {
    'CB-ACCESS-KEY': api_key,
    'CB-ACCESS-SIGN': signature_b64.decode('utf-8'),
    'CB-ACCESS-TIMESTAMP': timestamp,
    'CB-ACCESS-PASSPHRASE': passphrase,
    'Content-Type': 'application/json',
    'User-Agent': 'YourAppName/1.0'  # Add a User-Agent header
}

# Send GET request
conn.request("GET", request_path, body, headers)

# Get and process the response
res = conn.getresponse()
data = res.read()

# Parse the JSON data
response_data = json.loads(data.decode("utf-8"))

# Function to convert Unix timestamp to readable time
def convert_timestamp(unix_timestamp):
    return time_module.strftime('%Y-%m-%d %H:%M:%S', time_module.gmtime(unix_timestamp))

# Process the response and print date, close price, buy price, and sell price
print("Date, Close Price(USD), Buy Price(PHP), Sell Price(PHP):")
for row in response_data:
    time_bucket_start = convert_timestamp(row[0])  # Convert timestamp to readable format
    close_price = row[4]  # Get the close price
    
    # Calculate buy and sell prices
    buy_price = close_price * usdphprate * (1 + margin)
    sell_price = close_price * usdphprate * (1 - margin)
    
    # Print results
    print(f"Date: {time_bucket_start}, ClosePrice(USD): {close_price:.2f}, Buy(PHP): {buy_price:.2f}, Sell(PHP): {sell_price:.2f}")