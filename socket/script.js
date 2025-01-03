const WebSocket = require('ws');
const crypto = require('crypto');

// Assign proper values to the constants
const CB_ACCESS_PASSPHRASE = 'akmwnltyfgb'; // Correct passphrase as a string
const CB_ACCESS_SECRET = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='; // Correct secret as a string
const CB_ACCESS_KEY = '24ab46f784d1b20db435b852086e3250'; // Correct key as a string
const WS_URL = 'wss://ws-direct.sandbox.exchange.coinbase.com'; // Fixed the extra space in the URL

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
            product_ids: ["BTC-USD"], // Add product IDs to subscribe
            channels: [
                "level2", // Subscribe to level2 channel
                "heartbeat", // Subscribe to heartbeat channel
                {
                    name: "ticker", // Subscribe to ticker channel for specific products
                    product_ids: ["BTC-USD"]
                }
            ]
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
        } catch (error) {
            console.error('Error parsing message:', error);
        }
    });
}

connect();