#!/usr/bin/env python3

import redis
import sys
import json

target_php = 1000.1
target_coins = 1
user_intent = 'sell'  # 'buy' or 'sell'
request_type = 'coin'  # 'php' or 'coin'

# Determine sorted set key based on user intent
if user_intent == 'buy':
    sorted_set_key = 'BTC-USD_asks'
elif user_intent == 'sell':
    sorted_set_key = 'BTC-USD_bids'
else:
    print(json.dumps({"message": "Invalid user intent. Must be 'buy' or 'sell'."}, indent=4))
    sys.exit(1)

def generate_quote_php(redis_client, sorted_set_key, target_php):
    """
    Generates a quote by iterating through the sorted set and summing up
    'total_price_PHP' until the target PHP value is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set.
        target_php (float): Target cumulative value in PHP.

    Returns:
        float or None: Total price in USD once the target PHP is met, or None if not found.
    """
    try:
        orders = redis_client.zrange(sorted_set_key, 0, -1)
        print(orders)
    except redis.exceptions.ResponseError as e:
        print(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None

    if not orders:
        print(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None

    cumulative = 0.0

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"{order_uuid}"

        # Retrieve 'total_price_PHP' from the order hash
        how_much_bytes = redis_client.hget(order_key, 'total_price_PHP')
        if how_much_bytes is None:
            print(f"Order '{order_uuid}' does not have 'total_price_PHP' field.")
            continue

        try:
            how_much = float(how_much_bytes.decode('utf-8'))
        except ValueError:
            print(f"Invalid 'total_price_PHP' for order '{order_uuid}'. Skipping.")
            continue

        cumulative += how_much

        if cumulative >= target_php:
            # Retrieve 'total_price_USD' from the order hash
            total_price_bytes = redis_client.hget(order_key, 'total_price_USD')
            if total_price_bytes is None:
                print(f"Order '{order_uuid}' does not have 'total_price_USD' field.")
                return None

            try:
                total_price_USD = float(total_price_bytes.decode('utf-8'))
            except ValueError:
                print(f"Invalid 'total_price_USD' for order '{order_uuid}'.")
                return None

            return total_price_USD

    return None

def generate_quote_coin(redis_client, sorted_set_key, target_coins):
    """
    Generates a quote by summing up 'quantity' until the target coins value is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set.
        target_coins (float): Target cumulative quantity in coins.

    Returns:
        float or None: Total price in USD once the target coin quantity is met, or None if not found.
    """
    try:
        orders = redis_client.zrange(sorted_set_key, 0, -1)
        print(orders)
    except redis.exceptions.ResponseError as e:
        print(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None

    if not orders:
        print(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None

    cumulative = 0.0

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"{order_uuid}"

        # Retrieve 'quantity' from the order hash
        quantity_bytes = redis_client.hget(order_key, 'quantity')
        if quantity_bytes is None:
            print(f"Order '{order_uuid}' does not have 'quantity' field.")
            continue

        try:
            quantity = float(quantity_bytes.decode('utf-8'))
        except ValueError:
            print(f"Invalid 'quantity' for order '{order_uuid}'. Skipping.")
            continue

        cumulative += quantity

        if cumulative >= target_coins:
            # Retrieve 'total_price_USD' from the order hash
            total_price_bytes = redis_client.hget(order_key, 'total_price_USD')
            if total_price_bytes is None:
                print(f"Order '{order_uuid}' does not have 'total_price_USD' field.")
                return None

            try:
                total_price_USD = float(total_price_bytes.decode('utf-8'))
            except ValueError:
                print(f"Invalid 'total_price_USD' for order '{order_uuid}'.")
                return None

            return total_price_USD

    return None

def main():
    # Configure Redis connection parameters
    REDIS_HOST = '127.0.0.1'  # Ensure this matches your Redis server configuration
    REDIS_PORT = 6379
    REDIS_DB = 0  # Default Redis database
    REDIS_CONNECT_TIMEOUT = 5  # Adjust timeout value if necessary (in seconds)

    try:
        # Initialize Redis client
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=REDIS_CONNECT_TIMEOUT
        )
        # Test the connection
        redis_client.ping()
    except redis.exceptions.ConnectionError as e:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php,
            "total_price_USD": None,
            "message": f"Failed to connect to Redis: {e}"
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    # Generate the quote based on request type
    if request_type == 'php':
        total_price_USD = generate_quote_php(redis_client, sorted_set_key, target_php)
    elif request_type == 'coin':
        total_price_USD = generate_quote_coin(redis_client, sorted_set_key, target_coins)
    else:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php,
            "total_price_USD": None,
            "message": "Error: Invalid request type. Must be 'php' or 'coin'."
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    if total_price_USD is not None:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php if request_type == 'php' else target_coins,
            "total_price_USD": total_price_USD
        }
        print(json.dumps(result, indent=4))
    else:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php if request_type == 'php' else target_coins,
            "total_price_USD": None,
            "message": "No orders found where cumulative value meets the target."
        }
        print(json.dumps(result, indent=4))

if __name__ == '__main__':
    main()