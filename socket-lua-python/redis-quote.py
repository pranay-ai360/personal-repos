#!/usr/bin/env python3

import redis
import sys
import json

# Predefined variables
sorted_set_key = 'BTC-USD_asks'
target_cents = 700

def generate_quote(redis_client, sorted_set_key, target_cents):
    """
    Generates a quote by iterating through the sorted set and summing up
    'how_much_value_of_crypto_in_cents' until the target is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set (e.g., 'BTC-USD_buys' or 'BTC-USD_sells').
        target_cents (float): Target cumulative value in cents.

    Returns:
        float or None: 'total_price' of the order where the target is met, or None if not found.
    """
    try:
        # Fetch all members of the sorted set in ascending order of score
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

        # Retrieve 'how_much_value_of_crypto_in_cents' from the order hash
        how_much_bytes = redis_client.hget(order_key, 'how_much_value_of_crypto_in_cents')
        if how_much_bytes is None:
            print(f"Order '{order_uuid}' does not have 'how_much_value_of_crypto_in_cents' field.")
            continue

        try:
            how_much = float(how_much_bytes.decode('utf-8'))
        except ValueError:
            print(f"Invalid 'how_much_value_of_crypto_in_cents' for order '{order_uuid}'. Skipping.")
            continue

        cumulative += how_much

        if cumulative >= target_cents:
            # Retrieve 'total_price' from the order hash
            total_price_bytes = redis_client.hget(order_key, 'total_price')
            if total_price_bytes is None:
                print(f"Order '{order_uuid}' does not have 'total_price' field.")
                return None

            try:
                total_price = float(total_price_bytes.decode('utf-8'))
            except ValueError:
                print(f"Invalid 'total_price' for order '{order_uuid}'.")
                return None

            return total_price

    # If target is not met after processing all orders
    return None

def main():
    # Use the predefined variables
    global sorted_set_key, target_cents

    # Validate target_cents
    if target_cents <= 0:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_cents": target_cents,
            "total_price": None,
            "message": "Error: target_cents must be a positive number."
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    # Configure Redis connection parameters
    REDIS_HOST = '127.0.0.1'          # Ensure this matches your Redis server configuration
    REDIS_PORT = 6379
    REDIS_DB = 0                      # Default Redis database
    REDIS_CONNECT_TIMEOUT = 5         # Adjust timeout value if necessary (in seconds)

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
            "target_cents": target_cents,
            "total_price": None,
            "message": f"Failed to connect to Redis: {e}"
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    # Generate the quote
    total_price = generate_quote(redis_client, sorted_set_key, target_cents)

    if total_price is not None:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_cents": target_cents,
            "total_price": total_price
        }
        print(json.dumps(result, indent=4))
    else:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_cents": target_cents,
            "total_price": None,
            "message": f"No orders found where cumulative value >= {target_cents}."
        }
        print(json.dumps(result, indent=4))

if __name__ == '__main__':
    main()