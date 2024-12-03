const WebSocket = require('ws');
const crypto = require('crypto');
const redis = require('redis');

// Add REDIS_URL constant
const REDIS_URL = '127.0.0.1:6379'; // Redis URL for your Redis instance

// Create a Redis client
const client = redis.createClient({
  url: `redis://${REDIS_URL}`
});

// Connect to Redis
client.connect()
  .then(() => {
    console.log('Connected to Redis');
  })
  .catch(err => {
    console.error('Error connecting to Redis:', err);
  });

// Assign proper values to the constants
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
            channels: channels // Fixed the structure here
        };

        // Send the subscription message after authentication
        ws.send(JSON.stringify(authMessage));
    });

    ws.on('message', (message) => {
        // Convert Buffer to string
        const messageString = message.toString();
        const parsedMessage = JSON.parse(messageString);
        console.log('Message from server:', parsedMessage);

        // Handle the 'l2update' message and update the corresponding bid or ask in Redis
        if (parsedMessage.type === 'l2update' && parsedMessage.product_id && parsedMessage.changes) {
            const productId = parsedMessage.product_id;
            const changes = parsedMessage.changes;
            const timestamp = parsedMessage.time;

            changes.forEach(change => {
                const side = change[0]; // 'buy' or 'sell'
                const price = change[1]; // Price
                const quantity = change[2]; // Quantity

                // Assign 'bid' if 'buy' or 'ask' if 'sell'
                const formattedSide = side === 'buy' ? 'bid' : (side === 'sell' ? 'ask' : side);

                // Only update if quantity is non-zero
                if (parseFloat(quantity) > 0) {
                    // Construct the Redis key based on product_id and timestamp (e.g., BTC-USD:2024-12-03T08:27:22.665495Z)
                    const key = `${productId}:${side}:${price}`;

                    // Prepare the data to store (with the updated quantity)
                    const formattedMessage = {
                        product_id: productId,
                        side: formattedSide,  // Updated side to 'bid' or 'ask'
                        price: price,
                        quantity: quantity
                    };

                    // Check if the key already exists
                    client.exists(key)
                        .then((exists) => {
                            if (exists) {
                                // Update the quantity if the key exists
                                console.log(`Updating Redis key: ${key}`);
                                client.hSet(key, formattedMessage)
                                    .then(() => {
                                        console.log(`Updated quantity for ${key}`);
                                    })
                                    .catch(err => {
                                        console.error('Error updating Redis:', err);
                                    });
                            } else {
                                // Create a new key-value pair if it doesn't exist
                                console.log(`Creating Redis key: ${key}`);
                                client.hSet(key, formattedMessage)
                                    .then(() => {
                                        console.log(`Created new key for ${key}`);
                                    })
                                    .catch(err => {
                                        console.error('Error creating Redis key:', err);
                                    });
                            }
                        })
                        .catch(err => {
                            console.error('Error checking Redis key existence:', err);
                        });
                } else {
                    console.log(`Skipping update for ${side} at ${price} with quantity ${quantity}`);
                }
            });
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