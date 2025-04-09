const { Kafka } = require('kafkajs');

// Initialize Kafka client
const kafka = new Kafka({
  clientId: 'crypto-consumer-app',
  brokers: ['localhost:9092'] // Adjust if your Kafka broker is located elsewhere
});

// Create a consumer
const consumer = kafka.consumer({ groupId: 'crypto-consumer-group' });

const run = async () => {
  // Connect the consumer
  await consumer.connect();

  // Define the product IDs (topics) to subscribe to
  const productIds = ['BTC-PHP']; // Add more product IDs as needed

  // Subscribe to each product ID topic dynamically
  for (const productId of productIds) {
    await consumer.subscribe({ topic: productId, fromBeginning: true });
    console.log(`Subscribed to ${productId} topic`);
  }

  // Listen for messages on all subscribed topics
  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
      // Log each message received from the topic
      console.log(`Received message from topic ${topic}: ${message.value.toString()}`);
    },
  });
};

run().catch(console.error);