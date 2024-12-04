const { connectToWebSocket } = require('./cb_connection');
const RedisHandler = require('./redis_handler'); // Import the RedisHandler class

const redisHandler = new RedisHandler(); // Instantiate RedisHandler

// Handle the WebSocket message
async function handleMessage(parsedMessage) {
    if (parsedMessage.type === 'snapshot' && parsedMessage.product_id && parsedMessage.asks) {
        await redisHandler.storeWebSocketMessage(parsedMessage);
    }

    if (parsedMessage.type === 'l2update' && parsedMessage.product_id && parsedMessage.changes) {
        await redisHandler.handleL2Update(parsedMessage);
    }
}

// Start the WebSocket connection
connectToWebSocket();