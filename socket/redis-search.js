const Redis = require('ioredis');
const redis = new Redis('redis://127.0.0.1:6379'); // Connecting to Redis server

// Set some key-value pairs
redis.set('user:1', JSON.stringify({ name: 'Alice', age: 30 }));
redis.set('user:2', JSON.stringify({ name: 'Bob', age: 25 }));

// Get a value by key
redis.get('user:1').then((result) => {
  console.log('User 1:', JSON.parse(result)); // Output the parsed result
});

// Searching for keys
redis.keys('user:*').then((keys) => {
  console.log('User keys:', keys);
  keys.forEach(async (key) => {
    const user = await redis.get(key);
    console.log(`User ${key}:`, JSON.parse(user));
  });
});

// Close the connection
redis.quit();