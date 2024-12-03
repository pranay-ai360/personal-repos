const Redis = require('ioredis');
const redis = new Redis({
  host: '127.0.0.1',  // Ensure this matches your Redis server configuration
  port: 6379,
  connectTimeout: 10000, // Adjust timeout value if necessary
});

redis.on('connect', () => {
  console.log('Connected to Redis server');
});

redis.on('close', () => {
  console.log('Redis connection closed');
});

redis.on('error', (err) => {
  console.error('Redis error:', err);
});

const pair = 'BTC-USD';  // The trading pair
const side = 'ask';      // Side is 'ask'
const totalQuantity = 0.005;  // The target total quantity

// Aggregation using FT.AGGREGATE for BTC-USD ask orders
const aggregateData = async () => {
  try {
    // Perform aggregation query
    const result = await redis.call('FT.AGGREGATE', 'product:BTC-USD:ask:index', // 'idx' is your index name
      'GROUPBY', '1', '@side',    // Group by the 'side' field
      'REDUCE', 'SUM', '2', '@quantity', // Sum the 'quantity' field
      'REDUCE', 'AVG', '1', '@price' // Calculate the average 'price' field
    );

    // Process the result
    console.log('Aggregated Data:', result);
    
    // Calculate total price and quantity
    let accumulatedQuantity = 0;
    let accumulatedPrice = 0;
    
    // Loop through the result and calculate accumulated values
    result.forEach((row) => {
      const quantity = parseFloat(row['SUM(@quantity)']);
      const price = parseFloat(row['AVG(@price)']);
      accumulatedQuantity += quantity;
      accumulatedPrice += price * quantity;
    });

    // Response object
    const responsePrice = accumulatedPrice;
    console.log({
      requestPair: pair,
      requestSide: side,
      requestTotalQuantity: totalQuantity,
      responsePrice: responsePrice,
    });

  } catch (error) {
    console.error('Error performing aggregation:', error);
  }
};

// Run the aggregation
aggregateData().finally(() => {
  // Close the Redis connection after the operation is complete
  redis.disconnect();
});