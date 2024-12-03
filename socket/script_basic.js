const WebSocket = require('ws');
const crypto = require('crypto');
const redis = require('redis');

// Add Redis URL constant
const REDIS_URL = '127.0.0.1:6379'; // Redis URL for your Redis instance

// Redis client setup
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

// Assign proper values to the constants
const CB_ACCESS_PASSPHRASE = 'akmwnltyfgb'; // Correct passphrase as a string
const CB_ACCESS_SECRET = 'P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=='; // Correct secret as a string
const CB_ACCESS_KEY = '24ab46f784d1b20db435b852086e3250'; // Correct key as a string
const WS_URL = 'wss://ws-direct.sandbox.exchange.coinbase.com'; // WebSocket URL for Coinbase Pro
const product_ids = ["BTC-USD", "ETH-USD", "ETH-EUR"]; // Product IDs to subscribe
const channels = ["level2"]; // Channels to subscribe

function getSignature(timestamp, method, requestPath, body, secret) {
    const prehash = `${timestamp}${method}${requestPath}${body}`;
    const key = Buffer.from(secret, 'base64');
    return crypto.createHmac('sha256', key).update(prehash).digest('base64');
}

async function createIndexesIfNotExists(productId) {
    try {
        // Check if the index exists by listing all indexes in Redis
        const indexes = await client.ft._list();

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

            console.log(`Bid index and Ask index for ${productId} created successfully.`);
            return true;
        }
    } catch (err) {
        console.error('Error creating or checking indexes:', err);
        return false;
    }
}

async function validateSearchQuery() {
    try {
        // Run the FT.SEARCH query to validate it works
        const result = await client.ft.search('product:BTC-USD:ask:index', '@price:[0 1000000000] @quantity:[1 10000000]');
        console.log('FT.SEARCH query successful:', result);
    } catch (err) {
        console.error('Error executing FT.SEARCH query:', err);
    }
}



async function connect() {
    const ws = new WebSocket(WS_URL);

    ws.on('open', async () => {
        console.log('WebSocket connection established.');

        const timestamp = Math.floor(Date.now() / 1000).toString();
        const method = 'GET';
        const requestPath = '/users/self/verify';
        const body = '';

        const signature = getSignature(timestamp, method, requestPath, body, CB_ACCESS_SECRET);

        const authMessage = {
            type: 'subscribe',
            signature: signature,
            key: CB_ACCESS_KEY,
            passphrase: CB_ACCESS_PASSPHRASE,
            timestamp: timestamp,
            product_ids: product_ids,
            channels: channels
        };

        // Send the subscription message after authentication
        ws.send(JSON.stringify(authMessage));
    });

    ws.on('message', async (message) => {
        // Convert Buffer to string
        const messageString = message.toString();
        const parsedMessage = JSON.parse(messageString);
        console.log('Message from server:', parsedMessage);

        // Handle the snapshot message and store asks in Redis
        if (parsedMessage.type === 'snapshot' && parsedMessage.product_id && parsedMessage.asks) {
            const productId = parsedMessage.product_id;
            const asks = parsedMessage.asks;

            // Create indexes if they don't exist
            const indexExists = await createIndexesIfNotExists(productId);
            if (!indexExists) {
                console.log(`Skipping as index creation failed for product: ${productId}`);
                return;
            }

            asks.forEach(async (ask) => {
                const formattedMessage = {
                    product_id: productId,
                    side: 'ask',  // For snapshot data, side is 'ask'
                    price: ask[0],  // price is the first element in the array
                    quantity: ask[1]  // quantity is the second element in the array
                };

                // Log the formatted message
                console.log(JSON.stringify(formattedMessage, null, 2));

                // Store in Redis under "asks" category, storing raw JSON objects directly
                const key = `${productId}:ask:${ask[0]}`;

                // Add the key to the ask index set
                const askIndexKey = `product:${productId}:ask:index`;
                client.sAdd(askIndexKey, key)
                    .then(() => {
                        console.log(`Added ${key} to ask index ${askIndexKey}`);
                    })
                    .catch(err => {
                        console.error('Error adding to ask index:', err);
                    });

                client.hSet(key, formattedMessage)
                    .then(() => {
                        console.log(`Stored in Redis with key: ${key}`);
                        // Run validations after storing data in Redis
                        // validateSearchQuery();
                    })
                    .catch(err => {
                        console.error('Error storing in Redis:', err);
                    });
            });
        }

        // Handle the l2update message and update bids/asks in Redis
        if (parsedMessage.type === 'l2update' && parsedMessage.product_id && parsedMessage.changes) {
            const productId = parsedMessage.product_id;
            const changes = parsedMessage.changes;

            // Create indexes if they don't exist
            const indexExists = await createIndexesIfNotExists(productId);
            if (!indexExists) {
                console.log(`Skipping as index creation failed for product: ${productId}`);
                return;
            }

            changes.forEach(async (change) => {
                const side = change[0]; // 'buy' or 'sell'
                const price = change[1]; // Price
                const quantity = change[2]; // Quantity

                // Assign 'bid' if 'buy' or 'ask' if 'sell'
                const formattedSide = side === 'buy' ? 'bid' : (side === 'sell' ? 'ask' : side);

                // Only update if quantity is non-zero
                if (parseFloat(quantity) > 0) {
                    const key = `${productId}:${formattedSide}:${price}:`;

                    // Prepare the data to store (with the updated quantity)
                    const formattedMessage = {
                        product_id: productId,
                        side: formattedSide,  // Updated side to 'bid' or 'ask'
                        price: price,
                        quantity: quantity
                    };

                    // Check if the key already exists in Redis
                    client.exists(key)
                        .then(async (exists) => {
                            if (exists) {
                                // Update the quantity if the key exists
                                console.log(`Updating Redis key: ${key}`);
                                client.hSet(key, formattedMessage)
                                    .then(() => {
                                        console.log(`Updated quantity for ${key}`);
                                        // Run validations after updating data in Redis
                                        // validateSearchQuery();
                                                    })
                                    .catch(err => {
                                        console.error('Error updating Redis:', err);
                                    });
                            } else {
                                // Create a new key-value pair if it doesn't exist
                                console.log(`Creating Redis key: ${key}`);
                                client.hSet(key, formattedMessage)
                                    .then(() => {
                                        console.log(`Created new key for ${key}`);
                                        // Run validations after creating data in Redis
                                        //validateSearchQuery();
                                                    })
                                    .catch(err => {
                                        console.error('Error creating Redis key:', err);
                                    });
                            }

                            // Add the updated key to the appropriate index set
                            const indexKey = `product:${productId}:${formattedSide}:index`;
                            client.sAdd(indexKey, key)
                                .then(() => {
                                    console.log(`Added ${key} to ${formattedSide} index ${indexKey}`);
                                })
                                .catch(err => {
                                    console.error('Error adding to index:', err);
                                });
                        })
                        .catch(err => {
                            console.error('Error checking Redis key existence:', err);
                        });
                } else {
                    console.log(`Skipping update for ${formattedSide} at ${price} with quantity ${quantity}`);
                }
            });
        }
    });

    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });

    ws.on('close', (code, reason) => {
        console.log(`WebSocket connection closed: ${code} - ${reason}`);
    });
}

connect();