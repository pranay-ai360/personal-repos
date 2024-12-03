#!/bin/bash

# Redis CLI connection details
REDIS_HOST="localhost"
REDIS_PORT="6379"

# Minimum quantity for calculation
minimumQuantity=0.0000001

# Create Index for BTC-USD:bids, including the unit_price field in the schema
redis-cli -h $REDIS_HOST -p $REDIS_PORT FT.CREATE BTC_USD_BIDS SCHEMA price NUMERIC quantity NUMERIC side TAG product_id TAG unit_price NUMERIC

# Create Index for BTC-USD:asks, including the unit_price field in the schema
redis-cli -h $REDIS_HOST -p $REDIS_PORT FT.CREATE BTC_USD_ASKS SCHEMA price NUMERIC quantity NUMERIC side TAG product_id TAG unit_price NUMERIC

# Bids data
for i in {100..109}
do
  # Calculate the unit price
  price=$i
  quantity=1
  unitprice=$(echo "scale=8; ($price / $quantity) * $minimumQuantity" | bc)

  # Create JSON with the calculated unit price and set the data in Redis using HSET
  redis-cli -h $REDIS_HOST -p $REDIS_PORT HSET "BTC-USD:bids:$i" price "$price" quantity "$quantity" side "bids" product_id "BTC-USD" unit_price "$unitprice"
done

# Asks data
for i in {200..209}
do
  # Calculate the unit price
  price=$i
  quantity=1
  unitprice=$(echo "scale=8; ($price / $quantity) * $minimumQuantity" | bc)

  # Create JSON with the calculated unit price and set the data in Redis using HSET
  redis-cli -h $REDIS_HOST -p $REDIS_PORT HSET "BTC-USD:asks:$i" price "$price" quantity "$quantity" side "asks" product_id "BTC-USD" unit_price "$unitprice"
done

echo "Data has been loaded into Redis successfully with unit price, and indexes have been created using HSET."