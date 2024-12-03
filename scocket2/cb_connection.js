const WebSocket = require('ws');
const { getSignature } = require('./redis_connection');  // Import getSignature function from redis_connection.js

const product_ids = ["BTC-USD", "ETH-USD", "ETH-EUR"]; // Product IDs to subscribe
const channels = ["level2"]; // Channels to subscribe

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

        // The actual message handling will now be in script.js
        // You can call the handleMessage function from script.js here
    });

    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });

    ws.on('close', (code, reason) => {
        console.log(`WebSocket connection closed: ${code} - ${reason}`);
    });
}

// Export the connectToWebSocket function
module.exports = {
    connectToWebSocket
};