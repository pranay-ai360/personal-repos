from kafka import KafkaConsumer
from influxdb_client import InfluxDBClient, Point
import json

# Kafka configuration
kafka_broker = 'localhost:9092'
kafka_group_id = 'crypto-consumer-group'
product_ids = ['BTC-PHP']  # Add more product IDs as necessary

# InfluxDB configuration (with authentication)
influxdb_url = "http://localhost:8086"
influxdb_token = "un:pass"  # Token is a combination of username and password
influxdb_org = "demo"
influxdb_bucket = "demo"

# Initialize Kafka consumer
consumer = KafkaConsumer(
    *product_ids,  # Dynamically subscribe to product_id topics
    group_id=kafka_group_id,
    bootstrap_servers=kafka_broker,
    auto_offset_reset='earliest',  # Start reading at the earliest message
    enable_auto_commit=True,
)

# Initialize InfluxDB client
client = InfluxDBClient(url=influxdb_url, token=influxdb_token)

# Function to write data to InfluxDB
def write_to_influxdb(product_id, price_php):
    point = Point("crypto_price") \
        .tag("product_id", product_id) \
        .field("price_php", price_php)

    write_api = client.write_api()
    write_api.write(bucket=influxdb_bucket, org=influxdb_org, record=point)
    print(f"Written data to InfluxDB for {product_id}: {price_php} PHP")

# Consume messages from Kafka and write to InfluxDB
for message in consumer:
    try:
        # Parse the message value (price_php)
        price_php = float(message.value.decode('utf-8'))
        product_id = message.topic  # The topic name is the product ID (e.g., BTC-PHP)

        # Write data to InfluxDB
        write_to_influxdb(product_id, price_php)
    
    except Exception as e:
        print(f"Error processing message: {e}")