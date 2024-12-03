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

const channels = ["level2"]; // Fixed channel subscription

// Define the minimum unit quantity for BTC-USD
const UNIT_QUANTITY = 0.0000001; // Minimum BTC-USD quantity
const MAX_SEQUENCE = 1000000000000; // Just an arbitrary limit for the number of sequences

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
                const price = parseFloat(change[1]); // Price
                let quantity = parseFloat(change[2]); // Quantity

                // Assign 'bid' if 'buy' or 'ask' if 'sell'
                const formattedSide = side === 'buy' ? 'bid' : (side === 'sell' ? 'ask' : side);

                // Only process if quantity is greater than or equal to the minimum unit
                if (quantity >= UNIT_QUANTITY) {
                    // Construct the Redis key based on product_id, side, price, and timestamp
                    let sequence = 1;
                    let remainingQuantity = quantity;

                    // Process by breaking the quantity into unit quantities and updating Redis
                    while (remainingQuantity >= UNIT_QUANTITY) {
                        const key = `${productId}:${formattedSide}:${price}:${sequence}`;

                        // Calculate unitPrice as (price / quantity) * UNIT_QUANTITY
                        const unitPrice = ((price / quantity) * UNIT_QUANTITY).toFixed(7);

                        const formattedMessage = {
                            product_id: productId,
                            side: formattedSide,  // 'bid' or 'ask'
                            quantity: UNIT_QUANTITY.toFixed(7),
                            price: price.toFixed(2),
                            unitQuantity: UNIT_QUANTITY.toFixed(7),  // Minimum quantity used for each entry
                            unitPrice: unitPrice  // Unit price calculation
                        };

                        // Store in Redis under "productId:side:price:sequence"
                        client.hSet(key, formattedMessage)
                            .then(() => {
                                console.log(`Stored in Redis with key: ${key}`);
                            })
                            .catch(err => {
                                console.error('Error storing in Redis:', err);
                            });

                        // Update remaining quantity and increment sequence
                        remainingQuantity -= UNIT_QUANTITY;
                        sequence += 1;

                        // Limit sequence to avoid infinite loops (use appropriate logic based on your needs)
                        if (sequence > MAX_SEQUENCE) {
                            console.log('Reached max sequence, stopping.');
                            break;
                        }
                    }
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