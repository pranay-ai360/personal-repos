const { connectToWebSocket } = require('./cb_connection');

// Handle the WebSocket message
async function handleMessage(parsedMessage) {
    // Implement the logic for handling snapshot and l2update messages
    if (parsedMessage.type === 'snapshot' && parsedMessage.product_id && parsedMessage.asks) {
        const productId = parsedMessage.product_id;
        const asks = parsedMessage.asks;

        // Add your Redis logic here to handle snapshot data
        // For example: storeInRedis(productId, 'ask', ask[0], ask[1]);
    }

    if (parsedMessage.type === 'l2update' && parsedMessage.product_id && parsedMessage.changes) {
        const productId = parsedMessage.product_id;
        const changes = parsedMessage.changes;

        // Add your Redis logic here to handle l2update data
        // For example: storeInRedis(productId, 'ask', price, quantity);
    }
}

// Start the WebSocket connection
connectToWebSocket();