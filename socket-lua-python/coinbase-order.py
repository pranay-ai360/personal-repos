API_KEY = '24ab46f784d1b20db435b852086e3250'
PASSPHRASE = 'akmwnltyfgb'
SECRET_KEY = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='


# Copyright 2023-present Coinbase Global, Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json, hmac, hashlib, time, requests, base64, os, sys, uuid
from urllib.parse import urlparse

# w

#url = 'https://api.exchange.coinbase.com/orders'

url = 'https://api-public.sandbox.exchange.coinbase.com/orders'

timestamp = str(int(time.time()))
idempotency_key = str(uuid.uuid4())
method = 'POST'

url_path = urlparse(url).path

payload = {
   'type': 'limit',
   'side': 'buy',
   'product_id': 'BTC-USD',
   'client_oid': idempotency_key,
   'size': '0.001',
   'time_in_force': 'GTC',
   'price': '2000'
}

message = timestamp + method + url_path + json.dumps(payload)
hmac_key = base64.b64decode(SECRET_KEY)
signature = hmac.digest(hmac_key, message.encode('utf-8'), hashlib.sha256)
signature_b64 = base64.b64encode(signature)

headers = {
   'CB-ACCESS-SIGN': signature_b64,
   'CB-ACCESS-TIMESTAMP': timestamp,
   'CB-ACCESS-KEY': API_KEY,
   'CB-ACCESS-PASSPHRASE': PASSPHRASE,
   'Accept': 'application/json',
   'content-type': 'application/json'
}

response = requests.post(url, json=payload, headers=headers)
print(response.status_code)
parse = json.loads(response.text)
cb_order = json.loads(response.text)
print(json.dumps(parse, indent=3))
cb_id = cb_order["id"]


url = f'https://api-public.sandbox.exchange.coinbase.com/orders/{cb_id}'

timestamp = str(int(time.time()))
method = 'GET'

url_path = f'{urlparse(url).path}{urlparse(url).query}'

message = timestamp + method + url_path
hmac_key = base64.b64decode(SECRET_KEY)
signature = hmac.digest(hmac_key, message.encode('utf-8'), hashlib.sha256)
signature_b64 = base64.b64encode(signature)

headers = {
   'CB-ACCESS-SIGN': signature_b64,
   'CB-ACCESS-TIMESTAMP': timestamp,
   'CB-ACCESS-KEY': API_KEY,
   'CB-ACCESS-PASSPHRASE': PASSPHRASE,
   'Accept': 'application/json'
}

response = requests.get(url, headers=headers)
print(response.status_code)
parse = json.loads(response.text)
print(json.dumps(parse, indent=3))


