const { client } = require('./redis_connection');

// Function to create Redis indexes for bids and asks
async function createIndexesIfNotExists(productId) {
    try {
        // Fetch the list of existing indexes
        const indexes = await client.ft._list();
        const bidIndexKey = `${productId}:bid`;
        const askIndexKey = `${productId}:ask`;

        // Log the current indexes to debug
        console.log('Current indexes:', indexes);

        // Check if the indexes for the product already exist
        if (indexes.includes(bidIndexKey) && indexes.includes(askIndexKey)) {
            console.log(`Bid index and Ask index for ${productId} already exist.`);
            return true;
        } else {
            console.log(`One or both indexes for ${productId} do not exist. Creating new indexes...`);

            // Create bid index
            await client.ft.create(bidIndexKey, {
                product_id: { type: 'TEXT' },
                side: { type: 'TEXT' },
                price: { type: 'NUMERIC', sortable: true },
                quantity: { type: 'NUMERIC', sortable: true }
            });

            // Create ask index
            await client.ft.create(askIndexKey, {
                product_id: { type: 'TEXT' },
                side: { type: 'TEXT' },
                price: { type: 'NUMERIC', sortable: true },
                quantity: { type: 'NUMERIC', sortable: true }
            });

            console.log(`Indexes for ${productId} created successfully.`);

            // After creating indexes, validate if they have been created
            const updatedIndexes = await client.ft._list();
            console.log('Updated indexes:', updatedIndexes);
            if (updatedIndexes.includes(bidIndexKey) && updatedIndexes.includes(askIndexKey)) {
                console.log('Successfully validated the creation of both bid and ask indexes.');
                return true;
            } else {
                console.error('Error: Failed to create the required indexes.');
                return false;
            }
        }
    } catch (err) {
        console.error('Error creating or validating indexes:', err);
        return false;
    }
}

// Export the function to create indexes
module.exports = {
    createIndexesIfNotExists
};