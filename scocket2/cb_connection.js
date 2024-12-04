const WebSocket = require('ws');
const { getSignature } = require('./redis_connection'); // Import getSignature from redis_connection.js
const RedisHandler = require('./redis_handler'); // Import the RedisHandler class

const product_ids = ["BTC-USD", "ETH-USD", "ETH-EUR"];
const channels = ["level2"]; // Channels to subscribe

const redisHandler = new RedisHandler(); // Instantiate RedisHandler

// Function to connect to WebSocket and subscribe to Coinbase channels
function connectToWebSocket() {
    const ws = new WebSocket('wss://ws-direct.sandbox.exchange.coinbase.com');

    ws.on('open', () => {
        console.log('WebSocket connection established.');

        const timestamp = Math.floor(Date.now() / 1000).toString();
        const method = 'GET';
        const requestPath = '/users/self/verify';
        const body = '';
        const signature = getSignature(timestamp, method, requestPath, body, 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw==');

        const authMessage = {
            type: 'subscribe',
            signature: signature,
            key: '24ab46f784d1b20db435b852086e3250',
            passphrase: 'akmwnltyfgb',
            timestamp: timestamp,
            product_ids: product_ids,
            channels: channels
        };

        // Send the subscription message after authentication
        ws.send(JSON.stringify(authMessage));
    });

    ws.on('message', (message) => {
        const parsedMessage = JSON.parse(message.toString());
        console.log('Received message:', parsedMessage);

        // Call the message handling function
        handleMessage(parsedMessage).catch(err => {
            console.error('Error handling message:', err);
        });
    });

    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });

    ws.on('close', (code, reason) => {
        console.log(`WebSocket connection closed: ${code} - ${reason}`);
    });
}

// Handle the WebSocket message
async function handleMessage(parsedMessage) {
    if (parsedMessage.type === 'snapshot' && parsedMessage.product_id) {
        await redisHandler.storeWebSocketMessage(parsedMessage);
    }

    if (parsedMessage.type === 'l2update' && parsedMessage.product_id && parsedMessage.changes) {
        await redisHandler.handleL2Update(parsedMessage);
    }
}

// Export the connectToWebSocket function
module.exports = {
    connectToWebSocket
};