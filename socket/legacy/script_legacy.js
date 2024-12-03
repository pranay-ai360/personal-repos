const WebSocket = require('ws');
const crypto = require('crypto');
const fetch = require('node-fetch');
const redis = require('redis');
const express = require('express');

// Initialize Express application
const app = express();
const PORT = process.env.PORT || 3000;

// Replace these with your API credentials
const CB_ACCESS_KEY = 'your_api_key';
const CB_ACCESS_SECRET = 'your_api_secret';
const CB_ACCESS_PASSPHRASE = 'your_passphrase';

// Coinbase WebSocket URLs
const ENVIRONMENT = process.env.ENVIRONMENT || 'sandbox'; // Set "sandbox" or "production"
const WEBSOCKET_URL = ENVIRONMENT === 'production' 
  ? 'wss://ws-direct.exchange.coinbase.com' 
  : 'wss://ws-direct.sandbox.exchange.coinbase.com';

// Redis client setup
const REDIS_URL = process.env.REDIS_URL || 'redis://LJenkins:p%40ssw0rd@redis-16379.hosted.com:16379/0';
const redisClient = redis.createClient({ url: REDIS_URL });
redisClient.on('error', (err) => console.error('Redis Client Error', err));
redisClient.connect();

function getAuthHeaders() {
  const timestamp = Math.floor(Date.now() / 1000);
  const requestPath = '/users/self/verify';
  const method = 'GET';
  const message = timestamp + method + requestPath;
  const signature = crypto
    .createHmac('sha256', CB_ACCESS_SECRET)
    .update(message)
    .digest('base64');

  return {
    key: CB_ACCESS_KEY,
    passphrase: CB_ACCESS_PASSPHRASE,
    timestamp: timestamp.toString(),
    signature,
  };
}

const ws = new WebSocket(WEBSOCKET_URL);

ws.on('open', () => {
  console.log(`WebSocket connection opened to ${WEBSOCKET_URL} in ${ENVIRONMENT} environment.`);

  const authHeaders = getAuthHeaders();

  const subscribeMessage = {
    type: 'subscribe',
    channels: ["level2"],
    product_ids: ["ETH-USD", "BTC-USD"],
    signature: authHeaders.signature,
    key: authHeaders.key,
    passphrase: authHeaders.passphrase,
    timestamp: authHeaders.timestamp,
  };

  ws.send(JSON.stringify(subscribeMessage));
});

ws.on('message', async (data) => {
  const message = JSON.parse(data);
  console.log('Received message:', message);

  if (message.type === 'snapshot' || message.type === 'l2update') {
    const key = `orderbook:${message.product_id}`;
    try {
      await redisClient.set(key, JSON.stringify(message));
      console.log(`Stored ${message.type} for ${message.product_id} in Redis.`);
    } catch (err) {
      console.error('Error storing message in Redis:', err);
    }
  }
});

ws.on('error', (error) => {
  console.error('WebSocket error:', error);
});

ws.on('close', (code, reason) => {
  console.log(`WebSocket closed: Code = ${code}, Reason = ${reason}`);
});

// Express routes
app.get('/', (req, res) => {
  res.send('Welcome to the Coinbase WebSocket Service!');
});

app.get('/status', async (req, res) => {
  try {
    const keys = await redisClient.keys('orderbook:*');
    const data = {};

    for (const key of keys) {
      data[key] = JSON.parse(await redisClient.get(key));
    }

    res.json({
      status: 'success',
      environment: ENVIRONMENT,
      orderbook: data,
    });
  } catch (err) {
    console.error('Error fetching data from Redis:', err);
    res.status(500).json({ status: 'error', message: 'Internal Server Error' });
  }
});

app.listen(PORT, () => {
  console.log(`Express server running on port ${PORT}`);
});

// PM2 Process Monitoring
if (require.main === module) {
  console.log("Script is running under PM2 monitoring.");
}

module.exports = { app, ws, redisClient };
