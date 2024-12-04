const redis = require('redis');
const crypto = require('crypto');
const { promisify } = require('util');

// Redis client setup
const REDIS_URL = '127.0.0.1:6379'; // Redis URL for your Redis instance
const client = redis.createClient({
    url: `redis://${REDIS_URL}`
});

client.connect()
    .then(() => {
        console.log('Connected to Redis');
    })
    .catch(err => {
        console.error('Error connecting to Redis:', err);
    });

// Promisify Redis commands for better async handling
const hSetAsync = promisify(client.hSet).bind(client);
const existsAsync = promisify(client.exists).bind(client);

// Signature function
function getSignature(timestamp, method, requestPath, body, secret) {
    const prehash = `${timestamp}${method}${requestPath}${body}`;
    const key = Buffer.from(secret, 'base64');
    return crypto.createHmac('sha256', key).update(prehash).digest('base64');
}

// Function to check Redis key existence
async function checkRedisKeyExists(key) {
    try {
        const exists = await existsAsync(key);
        return exists;
    } catch (err) {
        console.error('Error checking Redis key existence:', err);
        return false;
    }
}

// Function to store data in Redis
async function storeInRedis(key, formattedMessage) {
    try {
        // Assuming formattedMessage is an object, store key-value pairs individually
        await hSetAsync(key, 'price', formattedMessage.price, 'quantity', formattedMessage.quantity);
        console.log(`Stored in Redis with key: ${key}`);
    } catch (err) {
        console.error('Error storing in Redis:', err);
    }
}

// Export the client and necessary functions
module.exports = {
    client,       // Export the client itself
    storeInRedis,
    checkRedisKeyExists,
    getSignature
};