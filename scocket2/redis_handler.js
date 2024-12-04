const { client } = require('./redis_connection'); // Ensure correct import of client

class RedisHandler {
    constructor() {
        if (!client) {
            throw new Error("Redis client is not initialized correctly.");
        }
        this.client = client;
    }

    // Store data in Redis
    async storeInRedis(key, formattedMessage) {
        try {
            await this.client.hSet(key, formattedMessage);
            console.log(`Stored in Redis with key: ${key}`);
        } catch (err) {
            console.error('Error storing in Redis:', err);
        }
    }

    // Check if key exists in Redis
    async checkRedisKeyExists(key) {
        try {
            const exists = await this.client.exists(key);
            return exists;
        } catch (err) {
            console.error('Error checking Redis key existence:', err);
            return false;
        }
    }

    // Store WebSocket message in Redis
    async storeWebSocketMessage(parsedMessage) {
        const productId = parsedMessage.product_id;
        const asks = parsedMessage.asks;
        const bids = parsedMessage.bids;

        // Process and store asks
        for (let ask of asks) {
            const price = ask[0];
            const quantity = ask[1];
            const key = `${productId}:asks:${price}`;

            const formattedMessage = {
                price: price,
                quantity: quantity
            };

            await this.storeInRedis(key, formattedMessage);
            console.log(`Stored ask for ${productId} at price ${price}`);
        }

        // Process and store bids
        for (let bid of bids) {
            const price = bid[0];
            const quantity = bid[1];
            const key = `${productId}:bids:${price}`;

            const formattedMessage = {
                price: price,
                quantity: quantity
            };

            await this.storeInRedis(key, formattedMessage);
            console.log(`Stored bid for ${productId} at price ${price}`);
        }
    }

    // Handle 'l2update' type WebSocket message
    async handleL2Update(parsedMessage) {
        const productId = parsedMessage.product_id;
        const changes = parsedMessage.changes;

        // Process each change (either 'buy' or 'sell')
        for (let change of changes) {
            const side = change[0]; // 'buy' or 'sell'
            const price = change[1]; // Price
            const quantity = change[2]; // Quantity

            const sideFormatted = side === 'buy' ? 'bids' : 'asks';
            const key = `${productId}:${sideFormatted}:${price}`;

            const formattedMessage = {
                price: price,
                quantity: quantity
            };

            const exists = await this.checkRedisKeyExists(key);
            if (exists) {
                console.log(`Updating ${sideFormatted} for ${productId} at price ${price}`);
            } else {
                console.log(`Creating ${sideFormatted} for ${productId} at price ${price}`);
            }

            // Store or update the Redis key
            await this.storeInRedis(key, formattedMessage);
        }
    }
}

module.exports = RedisHandler;