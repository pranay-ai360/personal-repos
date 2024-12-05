#!/usr/bin/env python3

import redis
import sys
import json

target_php = 31900
target_coins = 5  # Target amount of coins (for example, 2.5 BTC)
user_intent = 'sell'  # 'buy' or 'sell'
request_type = 'coin'  # 'php' or 'coin'

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
    Generates a quote by summing up 'total_price_PHP' until the target PHP value is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set.
        target_php (float): Target cumulative price in PHP.

    Returns:
        dict or None: A dictionary containing the total quantity in coins and total price in PHP,
                      or None if not found.
    """
    try:
        orders = redis_client.zrange(sorted_set_key, 0, -1)
        print(f"Orders: {orders}")
    except redis.exceptions.ResponseError as e:
        print(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None

    if not orders:
        print(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None

    # Initialize accumulators
    cumulative_php = 0.0
    total_quantity_coins = 0.0

    # Separate orders into bids and asks
    bids = []
    asks = []

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"{order_uuid}"

        # Retrieve 'quantity' and 'total_price_PHP' from the order hash
        quantity_bytes = redis_client.hget(order_key, 'quantity')
        total_price_php_bytes = redis_client.hget(order_key, 'total_price_PHP')
        price_per_base_asset_USD = redis_client.hget(order_key, 'price_per_base_asset_USD')

        if quantity_bytes is None or total_price_php_bytes is None:
            print(f"Order '{order_uuid}' does not have 'quantity' or 'total_price_PHP' field.")
            continue

        try:
            quantity = float(quantity_bytes.decode('utf-8'))
            total_price_php = float(total_price_php_bytes.decode('utf-8'))
            price_per_base_asset_USD = float(price_per_base_asset_USD.decode('utf-8'))
        except ValueError:
            print(f"Invalid 'quantity' or 'total_price_PHP' for order '{order_uuid}'. Skipping.")
            continue

        # Append to either bids or asks based on the order type
        if user_intent == 'sell':  # Process bids for selling
            bids.append({
                'price_per_base_asset_USD': price_per_base_asset_USD,
                'quantity': quantity,
                'total_price_PHP': total_price_php
            })
        elif user_intent == 'buy':  # Process asks for buying
            asks.append({
                'price_per_base_asset_USD': price_per_base_asset_USD,
                'quantity': quantity,
                'total_price_PHP': total_price_php
            })

    # Sort bids (descending order by price) and asks (ascending order by price)
    if user_intent == 'sell':
        sorted_orders = sorted(bids, key=lambda x: x['price_per_base_asset_USD'], reverse=True)
    else:
        sorted_orders = sorted(asks, key=lambda x: x['price_per_base_asset_USD'])

    # Apply logic only for 'buy' intent and 'php' request_type
    if user_intent == 'buy' and request_type == 'php':
        accumulated_php = 0
        total_quantity = 0
        index = 0

        while accumulated_php < target_php and index < len(sorted_orders):
            order = sorted_orders[index]
            quantity = order["quantity"]
            total_price_php = order["total_price_PHP"]

            print(f"Processing order {index+1}: Quantity = {quantity}, Total Price (PHP) = {total_price_php}")

            # Check if we can accumulate the full value from the current order
            if accumulated_php + total_price_php <= target_php:
                accumulated_php += total_price_php
                total_quantity += quantity
            else:
                # If we exceed the target with the current order, calculate the remaining value
                remaining_php = target_php - accumulated_php
                total_quantity += (remaining_php / total_price_php) * quantity
                accumulated_php = target_php  # This will break the loop
                break

            index += 1

        # Get the latest price per base asset USD (the price of the last order processed)
        last_value_price_per_base_asset_USD = sorted_orders[index-1]["price_per_base_asset_USD"]

        # Format the values before returning
        return {
            "sorted_set_key": sorted_set_key,
            "target_php": format_decimal(target_php),
            "lastValue_price_per_base_asset_USD": format_decimal(last_value_price_per_base_asset_USD),
            "total_quantity_coins": format_decimal(total_quantity)
        }

    # Apply logic for 'sell' intent and 'php' request_type
    elif user_intent == 'sell' and request_type == 'php':
        accumulated_php = 0
        total_quantity = 0
        index = 0

        while accumulated_php < target_php and index < len(sorted_orders):
            order = sorted_orders[index]
            quantity = order["quantity"]
            total_price_php = order["total_price_PHP"]

            print(f"Processing order {index+1}: Quantity = {quantity}, Total Price (PHP) = {total_price_php}")

            # Check if we can accumulate the full value from the current order
            if accumulated_php + total_price_php <= target_php:
                accumulated_php += total_price_php
                total_quantity += quantity
            else:
                # If we exceed the target with the current order, calculate the remaining value
                remaining_php = target_php - accumulated_php
                total_quantity += (remaining_php / total_price_php) * quantity
                accumulated_php = target_php  # This will break the loop
                break

            index += 1

        # Get the latest price per base asset USD (the price of the last order processed)
        last_value_price_per_base_asset_USD = sorted_orders[index-1]["price_per_base_asset_USD"]

        # Format the values before returning
        return {
            "sorted_set_key": sorted_set_key,
            "target_php": format_decimal(target_php),
            "lastValue_price_per_base_asset_USD": format_decimal(last_value_price_per_base_asset_USD),
            "total_quantity_coins": format_decimal(total_quantity)
        }

def generate_quote_coin(redis_client, sorted_set_key, target_coins):
    """
    Generates a quote by summing up 'quantity' until the target coins value is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set.
        target_coins (float): Target cumulative quantity in coins.

    Returns:
        dict or None: A dictionary containing the total price in PHP and total order value (PHP),
                      or None if not found.
    """
    try:
        orders = redis_client.zrange(sorted_set_key, 0, -1)
        print(f"Orders: {orders}")
    except redis.exceptions.ResponseError as e:
        print(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None

    if not orders:
        print(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None

    # Initialize accumulators
    cumulative_quantity = 0.0
    total_order_value_PHP = 0.0

    # Separate orders into bids and asks
    bids = []
    asks = []

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"{order_uuid}"

        # Retrieve 'quantity' and 'price_per_base_asset_PHP' from the order hash
        quantity_bytes = redis_client.hget(order_key, 'quantity')
        price_per_base_asset_PHP = redis_client.hget(order_key, 'price_per_base_asset_PHP')

        if quantity_bytes is None or price_per_base_asset_PHP is None:
            print(f"Order '{order_uuid}' does not have 'quantity' or 'price_per_base_asset_PHP' field.")
            continue

        try:
            quantity = float(quantity_bytes.decode('utf-8'))
            price_per_base_asset_PHP = float(price_per_base_asset_PHP.decode('utf-8'))
        except ValueError:
            print(f"Invalid 'quantity' or 'price_per_base_asset_PHP' for order '{order_uuid}'. Skipping.")
            continue

        # Append to either bids or asks based on the order type
        if user_intent == 'sell':  # Process bids for selling
            bids.append({
                'quantity': quantity,
                'price_per_base_asset_PHP': price_per_base_asset_PHP
            })
        elif user_intent == 'buy':  # Process asks for buying
            asks.append({
                'quantity': quantity,
                'price_per_base_asset_PHP': price_per_base_asset_PHP
            })

    # Sort bids (descending order by price) and asks (ascending order by price)
    if user_intent == 'sell':
        sorted_orders = sorted(bids, key=lambda x: x['price_per_base_asset_PHP'], reverse=True)
    else:
        sorted_orders = sorted(asks, key=lambda x: x['price_per_base_asset_PHP'])

    # Calculate total price for the target quantity
    total_price_PHP = 0
    previous_target = 0
    index = 0

    while previous_target < target_coins and index < len(sorted_orders):
        order = sorted_orders[index]
        quantity = order["quantity"]
        price_per_base_asset_PHP = order["price_per_base_asset_PHP"]

        print(f"Processing order {index+1}: Quantity = {quantity}, Price (PHP) = {price_per_base_asset_PHP}")

        # Check if we can accumulate the full quantity from the current order
        if previous_target + quantity <= target_coins:
            total_price_PHP += quantity * price_per_base_asset_PHP
            previous_target += quantity
        else:
            # If we exceed the target with the current order, calculate the remaining price
            remaining_target = target_coins - previous_target
            total_price_PHP += remaining_target * price_per_base_asset_PHP
            break

        index += 1

    # Adjust to provide correct total order value
    total_order_value_PHP = total_price_PHP

    # Get the latest price per base asset PHP (the price of the last order processed)
    last_value_price_per_base_asset_PHP = sorted_orders[index-1]["price_per_base_asset_PHP"]

    # Format the values before returning
    return {
        "total_order_value_PHP": format_decimal(total_order_value_PHP),
        "lastValue_price_per_base_asset_PHP": format_decimal(last_value_price_per_base_asset_PHP)
    }

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
            "total_order_value_PHP": None,
            "message": f"Failed to connect to Redis: {e}"
        }
        print(json.dumps(result, indent=4))
        sys.exit(1)

    # Generate the quote based on request type
    if request_type == 'php':
        quote_result = generate_quote_php(redis_client, sorted_set_key, target_php)
        if quote_result:
            result = {
                "sorted_set_key": sorted_set_key,
                "target_php": target_php,
                "lastValue_price_per_base_asset_USD": quote_result["lastValue_price_per_base_asset_USD"],
                "total_quantity_coins": quote_result["total_quantity_coins"]
            }
        else:
            result = {
                "sorted_set_key": sorted_set_key,
                "target_php": target_php,
                "total_quantity_coins": None,
                "message": "No orders found where cumulative value meets the target."
            }
    elif request_type == 'coin':
        quote_result = generate_quote_coin(redis_client, sorted_set_key, target_coins)
        if quote_result:
            result = {
                "sorted_set_key": sorted_set_key,
                "target_coins": target_coins,
                "lastValue_price_per_base_asset_PHP": quote_result["lastValue_price_per_base_asset_PHP"],
                "total_order_value_PHP": quote_result["total_order_value_PHP"]
            }
        else:
            result = {
                "sorted_set_key": sorted_set_key,
                "target_coins": target_coins,
                "total_order_value_PHP": None,
                "message": "No orders found where cumulative value meets the target."
            }
    else:
        result = {
            "sorted_set_key": sorted_set_key,
            "target_php": target_php,
            "total_order_value_PHP": None,
            "message": "Error: Invalid request type. Must be 'php' or 'coin'."
        }

    print(json.dumps(result, indent=4))


if __name__ == '__main__':
    main()