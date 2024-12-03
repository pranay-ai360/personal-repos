const redis = require('redis');

// Redis client setup
const client = redis.createClient({
    url: 'redis://127.0.0.1:6379'
});

// Connect to Redis
client.connect()
    .then(() => {
        console.log('Connected to Redis');
    })
    .catch(err => {
        console.error('Error connecting to Redis:', err);
    });

/**
 * Function to create Redis schema and indexes for bid/ask
 * @param {string} productId - The product ID for the market.
 * @param {string} formattedSide - The order side ('bid' or 'ask').
 * @param {number} price - The price of the order.
 * @param {number} quantity - The quantity of the order.
 * @param {array} indexes - List of existing indexes to check.
 */
async function creditRedisSchema(productId, formattedSide, price, quantity, indexes) {
    const key = `${productId}:${formattedSide}:${price}:`;

    // Prepare the data to store (with the updated quantity)
    const formattedMessage = {
        product_id: productId,
        side: formattedSide, // Updated side to 'bid' or 'ask'
        price: price,
        quantity: quantity
    };

    // Add the message to the Redis store (could be a hash or a string)
    await client.set(key, JSON.stringify(formattedMessage));

    // Define the index keys for bid and ask
    const bidIndexKey = `${productId}:bid`;
    const askIndexKey = `${productId}:ask`;

    if (indexes.includes(bidIndexKey) && indexes.includes(askIndexKey)) {
        console.log(`Bid index and Ask index for ${productId} already exist.`);
        return true;
    } else {
        console.log(`One or both indexes for ${productId} do not exist. Creating new indexes...`);

        // Create bid index
        await client.ft.create(bidIndexKey, {
            product_id: { type: 'TEXT' },
            side: { type: 'TEXT' },
            price: { type: 'NUMERIC', sortable: true }, // Add 'sortable' to price field
            quantity: { type: 'NUMERIC', sortable: true } // Add 'sortable' to quantity field
        });

        // Create ask index
        await client.ft.create(askIndexKey, {
            product_id: { type: 'TEXT' },
            side: { type: 'TEXT' },
            price: { type: 'NUMERIC', sortable: true }, // Add 'sortable' to price field
            quantity: { type: 'NUMERIC', sortable: true } // Add 'sortable' to quantity field
        });

        console.log('Indexes created successfully for bid and ask.');
    }
}

// Export the Redis client and creditRedisSchema function for use in other files
module.exports = {
    client,
    creditRedisSchema
};