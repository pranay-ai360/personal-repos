const WebSocket = require('ws');
const crypto = require('crypto');
const redis = require('redis');

// Add REDIS_URL constant
const REDIS_URL = '127.0.0.1:6379'; // Redis URL for your Redis instance

// Redis client setup
const client = redis.createClient({
    url: `redis://${REDIS_URL}`
});

client.connect();

const CB_ACCESS_PASSPHRASE = 'akmwnltyfgb'; // Correct passphrase as a string
const CB_ACCESS_SECRET = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='; // Correct secret as a string
const CB_ACCESS_KEY = '24ab46f784d1b20db435b852086e3250'; // Correct key as a string
const WS_URL = 'wss://ws-direct.sandbox.exchange.coinbase.com'; // Fixed the extra space in the URL

const product_ids = ["BTC-USD", "ETH-USD", "ETH-EUR"]; // Add product IDs to subscribe

const channels = ["level2", "heartbeat"]; // Fixed channel subscription

function getSignature(timestamp, method, requestPath, body, secret) {
    const prehash = `${timestamp}${method}${requestPath}${body}`;
    const key = Buffer.from(secret, 'base64');
    return crypto.createHmac('sha256', key).update(prehash).digest('base64');
}

function connect() {
    const ws = new WebSocket(WS_URL);

    ws.on('open', () => {
        console.log('WebSocket connection established.');

        const timestamp = Math.floor(Date.now() / 1000).toString();
        const method = 'GET';
        const requestPath = '/users/self/verify';
        const body = '';

        const signature = getSignature(timestamp, method, requestPath, body, CB_ACCESS_SECRET);

        const authMessage = {
            type: 'subscribe',
            signature: signature,
            key: CB_ACCESS_KEY,
            passphrase: CB_ACCESS_PASSPHRASE,
            timestamp: timestamp,
            product_ids: product_ids,
            channels: channels
        };

        // Send the subscription message after authentication
        ws.send(JSON.stringify(authMessage));
    });

    ws.on('message', (message) => {
        // Convert Buffer to string
        const messageString = message.toString();

        // Parse the JSON string into an object
        try {
            const parsedMessage = JSON.parse(messageString);
            console.log('Message from server:', parsedMessage);

            // Only handle snapshot type messages
            if (parsedMessage.type === 'snapshot') {
                const { product_id, asks, bids } = parsedMessage;

                // Process "asks"
                asks.forEach(([price, quantity]) => {
                    const askData = {
                        product_id,
                        side: 'asks',
                        price,
                        quantity
                    };
                    // Store in Redis under "asks" category
                    client.hSet(`orderbook:${product_id}:asks`, price, JSON.stringify(askData));
                });

                // Process "bids"
                bids.forEach(([price, quantity]) => {
                    const bidData = {
                        product_id,
                        side: 'bids',
                        price,
                        quantity
                    };
                    // Store in Redis under "bids" category
                    client.hSet(`orderbook:${product_id}:bids`, price, JSON.stringify(bidData));
                });

                console.log('Orderbook data stored in Redis');
            }
        } catch (error) {
            console.error('Error parsing message:', error);
        }
    });

    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });

    ws.on('close', (code, reason) => {
        console.log(`WebSocket connection closed: ${code} - ${reason}`);
    });
}

connect();