const redis = require('redis');
const { promisify } = require('util');

// Redis connection details
const REDIS_HOST = 'localhost';
const REDIS_PORT = 6379;

// Minimum quantity for calculation
const minimumQuantity = 0.0000001;

// Create Redis client
const client = redis.createClient({
  host: REDIS_HOST,
  port: REDIS_PORT
});

// Promisify Redis commands for easier async/await usage
const hsetAsync = promisify(client.hset).bind(client);

// Connect to Redis
client.on('connect', function () {
  console.log('Connected to Redis');
});

// Function to calculate unit price
function calculateUnitPrice(price, quantity) {
  return (price / quantity) * minimumQuantity;
}

// Create Index for BTC-USD:bids and BTC-USD:asks using RediSearch commands directly
async function createIndexes() {
  try {
    // Create index for bids using FT.CREATE command
    await new Promise((resolve, reject) => {
      client.send_command('FT.CREATE', [
        'BTC_USD_BIDS',
        'SCHEMA',
        'price', 'NUMERIC',
        'quantity', 'NUMERIC',
        'side', 'TAG',
        'product_id', 'TAG',
        'unit_price', 'NUMERIC'
      ], (err, reply) => {
        if (err) reject(err);
        resolve(reply);
      });
    });

    // Create index for asks using FT.CREATE command
    await new Promise((resolve, reject) => {
      client.send_command('FT.CREATE', [
        'BTC_USD_ASKS',
        'SCHEMA',
        'price', 'NUMERIC',
        'quantity', 'NUMERIC',
        'side', 'TAG',
        'product_id', 'TAG',
        'unit_price', 'NUMERIC'
      ], (err, reply) => {
        if (err) reject(err);
        resolve(reply);
      });
    });

    console.log('Indexes have been created successfully');
  } catch (err) {
    console.error('Error creating indexes:', err);
  }
}

// Insert bid data into Redis
async function insertBids() {
  for (let i = 100; i <= 109; i++) {
    const price = i;
    const quantity = 1;
    const unitPrice = calculateUnitPrice(price, quantity);

    const key = `BTC-USD:bids:${i}`;
    const data = {
      price,
      quantity,
      side: 'bids',
      product_id: 'BTC-USD',
      unit_price: unitPrice
    };

    try {
      await hsetAsync(key, data);
      console.log(`Inserted bid data for price ${price}`);
    } catch (err) {
      console.error('Error inserting bid data:', err);
    }
  }
}

// Insert ask data into Redis
async function insertAsks() {
  for (let i = 200; i <= 209; i++) {
    const price = i;
    const quantity = 1;
    const unitPrice = calculateUnitPrice(price, quantity);

    const key = `BTC-USD:asks:${i}`;
    const data = {
      price,
      quantity,
      side: 'asks',
      product_id: 'BTC-USD',
      unit_price: unitPrice
    };

    try {
      await hsetAsync(key, data);
      console.log(`Inserted ask data for price ${price}`);
    } catch (err) {
      console.error('Error inserting ask data:', err);
    }
  }
}

// Main function to execute the logic
async function main() {
  await createIndexes();
  await insertBids();
  await insertAsks();

  console.log("Data has been loaded into Redis successfully with unit price, and indexes have been created.");
  client.quit();
}

main().catch((err) => {
  console.error("Error occurred:", err);
  client.quit();
});