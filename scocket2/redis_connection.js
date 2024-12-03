const redis = require('redis');
const crypto = require('crypto');

// Redis URL constant
const REDIS_URL = '127.0.0.1:6379'; // Redis URL for your Redis instance

// Redis client setup
const client = redis.createClient({
    url: `redis://${REDIS_URL}`
});

// Function to check if Redis is reachable
async function checkRedisConnection() {
    try {
        await client.connect();
        console.log('Connected to Redis');
    } catch (err) {
        console.error('Error connecting to Redis:', err);
    }
}

// Signature function
function getSignature(timestamp, method, requestPath, body, secret) {
    const prehash = `${timestamp}${method}${requestPath}${body}`;
    const key = Buffer.from(secret, 'base64');
    return crypto.createHmac('sha256', key).update(prehash).digest('base64');
}

// Create Redis index if not exists
async function createIndexesIfNotExists(productId) {
    try {
        const indexes = await client.ft._list();
        const bidIndexKey = `${productId}:bid`;
        const askIndexKey = `${productId}:ask`;

        if (indexes.includes(bidIndexKey) && indexes.includes(askIndexKey)) {
            console.log(`Bid index and Ask index for ${productId} already exist.`);
            return true;
        } else {
            console.log(`Creating new indexes for ${productId}...`);

            await client.ft.create(bidIndexKey, {
                product_id: { type: 'TEXT' },
                side: { type: 'TEXT' },
                price: { type: 'NUMERIC', sortable: true },
                quantity: { type: 'NUMERIC', sortable: true }
            });

            await client.ft.create(askIndexKey, {
                product_id: { type: 'TEXT' },
                side: { type: 'TEXT' },
                price: { type: 'NUMERIC', sortable: true },
                quantity: { type: 'NUMERIC', sortable: true }
            });

            console.log(`Indexes created for ${productId}`);
            return true;
        }
    } catch (err) {
        console.error('Error creating or checking indexes:', err);
        return false;
    }
}

// Store bid/ask data in Redis
async function storeInRedis(productId, side, price, quantity) {
    const key = `${productId}:${side}:${price}`;
    const formattedMessage = {
        product_id: productId,
        side: side,
        price: price,
        quantity: quantity
    };

    // Store data in Redis hash
    await client.hSet(key, formattedMessage);
    console.log(`Stored ${side} data for ${productId} at price ${price}`);
}

// Export the necessary functions
module.exports = {
    checkRedisConnection,
    storeInRedis,
    createIndexesIfNotExists,
    getSignature
};