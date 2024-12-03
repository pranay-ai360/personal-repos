#!/bin/bash

# Redis server details (default settings)
REDIS_HOST="127.0.0.1"
REDIS_PORT="6379"
REDIS_CLI="redis-cli"

# Index name (updated for BTC_USD_ASKS)
INDEX_NAME=""

# Aggregation query (example: sum of a field 'price')
AGGREGATE_QUERY="FT.AGGREGATE BTC_USD_ASKS '*' GROUPBY 1 @category REDUCE SUM 2 @unit_price"

# Run the aggregation query using redis-cli
result=$($REDIS_CLI -h $REDIS_HOST -p $REDIS_PORT $AGGREGATE_QUERY)

# Output the result
echo "Aggregation result:"
echo "$result"