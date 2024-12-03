const Redis = require('ioredis');
const redis = new Redis('redis://127.0.0.1:6379'); // Connecting to Redis server

const pair = 'BTC-USD';  // The trading pair
const side = 'ask';      // Side is 'ask'
const totalQuantity = 0.005;  // The target total quantity

// Searching for keys with the pair and side 'ask'
redis.keys(`${pair}:${side}:*`).then((keys) => {
  // Fetch all ask orders and store them
  const askDataPromises = keys.map(async (key) => {
    const result = await redis.get(key);
    const parsedResult = JSON.parse(result);
    parsedResult.key = key;  // Include the key for debugging/logging purposes
    return parsedResult;
  });

  // Once all data is fetched, sort by price (lowest to highest)
  Promise.all(askDataPromises).then((askData) => {
    const sortedAskData = askData.sort((a, b) => parseFloat(a.price) - parseFloat(b.price));

    let accumulatedQuantity = 0;
    let accumulatedPrice = 0;
    let responsePrice = 0;

    // Accumulate until totalQuantity is met or exceeded
    sortedAskData.forEach((order) => {
      if (accumulatedQuantity < totalQuantity) {
        const availableQuantity = parseFloat(order.quantity);
        accumulatedQuantity += availableQuantity;
        accumulatedPrice += availableQuantity * parseFloat(order.unitPrice);
        responsePrice = accumulatedPrice;
      }
    });

    // Log the response object
    console.log({
      requestPair: pair,
      requestSide: side,
      requestTotalQuantity: totalQuantity,
      responsePrice: responsePrice
    });
  });
});

// Close the connection
redis.quit();