#!/usr/bin/env python3

import redis
import sys
import json

target_php = 9850  # Target amount in PHP (e.g., 2800 PHP)
user_intent = 'buy'  # 'buy' or 'sell'
request_type = 'php'  # 'php' or 'coin'

# Function to format the decimal values
def format_decimal(value, decimal_places=4):
    """
    Formats a decimal value to the specified number of decimal places.

    Args:
        value (float): The value to format.
        decimal_places (int): The number of decimal places to round to.

    Returns:
        str: The formatted value as a string.
    """
    if value is None:
        return None
    return f"{value:.{decimal_places}f}"

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
    Generates a quote by summing up 'quantity' until the target PHP value is reached.
    This version correctly calculates the price in USD based on the target PHP.
    """
    try:
        orders = redis_client.zrange(sorted_set_key, 0, 20)
        print(f"Orders: {orders}")
    except redis.exceptions.ResponseError as e:
        print(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None

    if not orders:
        print(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None

    # Initialize accumulators
    cumulative_php = 0.0
    total_order_value_PHP = 0.0
    total_order_value_USD = 0.0  # New variable for USD calculation
    last_price_per_base_asset_USD = None  # Track last price for USD
    total_quantity_coins = 0.0  # Track total quantity of coins accumulated

    # Separate orders into bids and asks
    bids = []
    asks = []

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"{order_uuid}"

        # Retrieve 'quantity', 'price_per_base_asset_PHP', and 'price_per_base_asset_USD' from the order hash
        quantity_bytes = redis_client.hget(order_key, 'quantity')
        price_per_base_asset_PHP = redis_client.hget(order_key, 'price_per_base_asset_PHP')
        price_per_base_asset_USD = redis_client.hget(order_key, 'price_per_base_asset_USD')

        if quantity_bytes is None or price_per_base_asset_PHP is None:
            print(f"Order '{order_uuid}' does not have 'quantity' or 'price_per_base_asset_PHP' field.")
            continue

        try:
            quantity = float(quantity_bytes.decode('utf-8'))
            price_per_base_asset_PHP = float(price_per_base_asset_PHP.decode('utf-8'))
            price_per_base_asset_USD = float(price_per_base_asset_USD.decode('utf-8')) if price_per_base_asset_USD else None
        except ValueError:
            print(f"Invalid 'quantity' or 'price_per_base_asset_PHP' for order '{order_uuid}'. Skipping.")
            continue

        # Append to either bids or asks based on the order type
        if user_intent == 'sell':  # Process bids for selling
            bids.append({
                'quantity': quantity,
                'price_per_base_asset_PHP': price_per_base_asset_PHP,
                'price_per_base_asset_USD': price_per_base_asset_USD
            })
        elif user_intent == 'buy':  # Process asks for buying
            asks.append({
                'quantity': quantity,
                'price_per_base_asset_PHP': price_per_base_asset_PHP,
                'price_per_base_asset_USD': price_per_base_asset_USD
            })

    # Sort bids (descending order by price) and asks (ascending order by price)
    if user_intent == 'sell':
        sorted_orders = sorted(bids, key=lambda x: x['price_per_base_asset_USD'], reverse=True)
    else:
        sorted_orders = sorted(asks, key=lambda x: x['price_per_base_asset_USD'])

    # Calculate total price for the target PHP
    previous_target = 0
    index = 0

    while previous_target < target_php and index < len(sorted_orders):
        order = sorted_orders[index]
        quantity = order["quantity"]
        price_per_base_asset_PHP = order["price_per_base_asset_PHP"]
        price_per_base_asset_USD = order["price_per_base_asset_USD"]

        print(f"Processing order {index+1}: Quantity = {quantity}, Price (USD) = {price_per_base_asset_USD}, Price (PHP) = {price_per_base_asset_PHP}")

        # Check if we can accumulate the full value from the current order
        if previous_target + (quantity * price_per_base_asset_PHP) <= target_php:
            total_order_value_PHP += quantity * price_per_base_asset_PHP
            total_order_value_USD += quantity * price_per_base_asset_USD
            total_quantity_coins += quantity
            previous_target += quantity * price_per_base_asset_PHP
            last_price_per_base_asset_USD = price_per_base_asset_USD  # Update last price when order contributes
        else:
            # If we exceed the target with the current order, calculate the remaining price
            remaining_target_php = target_php - previous_target
            total_order_value_PHP += remaining_target_php
            total_order_value_USD += remaining_target_php * (price_per_base_asset_USD / price_per_base_asset_PHP)  # Calculate remaining USD value
            total_quantity_coins += remaining_target_php / price_per_base_asset_PHP  # Add the partial quantity
            last_price_per_base_asset_USD = price_per_base_asset_USD  # Ensure last price is updated on partial contribution
            break

        index += 1

    # Check if the order can be filled
    if total_order_value_PHP < target_php:
        return {
            "message": "Order cannot be filled",
            "total_order_value_PHP": format_decimal(total_order_value_PHP),
            "total_order_value_USD": format_decimal(total_order_value_USD)
        }

    # Format the values before returning
    return {
        "total_order_value_PHP": format_decimal(total_order_value_PHP),
        "total_order_value_USD": format_decimal(total_order_value_USD),
        "lastValue_price_per_base_asset_USD": format_decimal(last_price_per_base_asset_USD) if last_price_per_base_asset_USD else "N/A",
        "total_quantity_coins": format_decimal(total_quantity_coins)  # Include total quantity of coins
    }

def main():
    # Configure Redis connection parameters
    REDIS_HOST = 'redis'  # Ensure this matches your Redis server configuration
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
            "total_order_value_PHP": None,
            "message": f"Failed to connect to Redis: {e}"
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    # Generate the quote based on request type
    if request_type == 'php':
        quote_result = generate_quote_php(redis_client, sorted_set_key, target_php)
        if quote_result:
            # Safely access keys with a check for their existence
            result = {
                "sorted_set_key": sorted_set_key,
                "target_php": target_php,
                "lastValue_price_per_base_asset_USD": quote_result.get("lastValue_price_per_base_asset_USD", "N/A"),
                "total_order_value_PHP": quote_result.get("total_order_value_PHP", "N/A"),
                "total_order_value_USD": quote_result.get("total_order_value_USD", "N/A"),
                "total_quantity_coins": quote_result.get("total_quantity_coins", "N/A")
            }
        else:
            result = {
                "sorted_set_key": sorted_set_key,
                "target_php": target_php,
                "total_order_value_PHP": None,
                "total_order_value_USD": None,
                "message": "No orders found where cumulative value meets the target."
            }
    else:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php,
            "total_order_value_PHP": None,
            "total_order_value_USD": None,
            "message": "Error: Invalid request type. Must be 'php' or 'coin'."
        }

    print(json.dumps(result, indent=4))


if __name__ == '__main__':
    main()