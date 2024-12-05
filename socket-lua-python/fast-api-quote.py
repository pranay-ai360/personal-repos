#!/usr/bin/env python3

from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import redis
from redis.exceptions import ResponseError, ConnectionError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more verbosity
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Quote Generator API",
    description="Generate a quote from Redis sorted sets based on target cents.",
    version="1.1.0"
)

# Redis configuration - adjust these as needed or consider using environment variables
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_CONNECT_TIMEOUT = 5  # seconds

class QuoteResponse(BaseModel):
    sorted_set_key: str
    target_cents: float
    total_price: Optional[float] = None
    message: Optional[str] = None

def determine_sort_order(sorted_set_key: str) -> bool:
    """
    Determines the sort order based on the sorted set key.
    Returns True for descending (for bids), False for ascending (for asks).
    """
    if 'bids' in sorted_set_key.lower() or 'buys' in sorted_set_key.lower():
        return True  # Descending
    elif 'asks' in sorted_set_key.lower() or 'sells' in sorted_set_key.lower():
        return False  # Ascending
    else:
        logger.warning(f"Could not determine sort order from key '{sorted_set_key}'. Defaulting to ascending.")
        return False  # Default to ascending

def get_redis_client():
    """
    Dependency to get a Redis client. Raises HTTPException if connection fails.
    """
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=REDIS_CONNECT_TIMEOUT
        )
        client.ping()
        logger.info("Successfully connected to Redis.")
        return client
    except ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to Redis: {e}")

def generate_quote(redis_client: redis.Redis, sorted_set_key: str, target_cents: float, descending: bool):
    """
    Generates a quote by iterating through the sorted set and summing up
    'how_much_value_of_crypto_in_cents' until the target is reached.

    Args:
        redis_client (redis.Redis): Redis client instance.
        sorted_set_key (str): Name of the sorted set.
        target_cents (float): Target cumulative value in cents.
        descending (bool): If True, iterate in descending order; else ascending.

    Returns:
        tuple: (total_price, error_message)
               total_price (float or None): The 'total_price' where target is met.
               error_message (str or None): Error message if any.
    """
    try:
        if descending:
            # Fetch all members of the sorted set in descending order of score
            orders = redis_client.zrevrange(sorted_set_key, 0, -1)
            logger.debug(f"Fetched {len(orders)} orders from sorted set '{sorted_set_key}' in descending order.")
        else:
            # Fetch all members of the sorted set in ascending order of score
            orders = redis_client.zrange(sorted_set_key, 0, -1)
            logger.debug(f"Fetched {len(orders)} orders from sorted set '{sorted_set_key}' in ascending order.")
    except ResponseError as e:
        logger.error(f"Error fetching sorted set '{sorted_set_key}': {e}")
        return None, f"Error fetching sorted set '{sorted_set_key}': {e}"

    if not orders:
        logger.warning(f"Sorted set '{sorted_set_key}' is empty or does not exist.")
        return None, f"Sorted set '{sorted_set_key}' is empty or does not exist."

    cumulative = 0.0

    for order_uuid_bytes in orders:
        order_uuid = order_uuid_bytes.decode('utf-8')
        order_key = f"order:{order_uuid}"
        logger.debug(f"Processing order UUID: {order_uuid}")

        # Retrieve 'how_much_value_of_crypto_in_cents' from the order hash
        how_much_bytes = redis_client.hget(order_key, 'how_much_value_of_crypto_in_cents')
        if how_much_bytes is None:
            logger.warning(f"Order '{order_uuid}' does not have 'how_much_value_of_crypto_in_cents' field. Skipping.")
            continue

        try:
            how_much_str = how_much_bytes.decode('utf-8')
            how_much = float(how_much_str)
            logger.debug(f"Order '{order_uuid}': how_much_value_of_crypto_in_cents = {how_much}")
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid 'how_much_value_of_crypto_in_cents' for order '{order_uuid}': {e}. Skipping.")
            continue

        cumulative += how_much
        logger.debug(f"Cumulative value: {cumulative} cents")

        if cumulative >= target_cents:
            logger.info(f"Target of {target_cents} cents reached with order '{order_uuid}'.")
            # Retrieve 'total_price' from the order hash
            total_price_bytes = redis_client.hget(order_key, 'total_price')
            if total_price_bytes is None:
                logger.error(f"Order '{order_uuid}' does not have 'total_price' field.")
                return None, f"Order '{order_uuid}' does not have 'total_price' field."

            try:
                total_price_str = total_price_bytes.decode('utf-8')
                total_price = float(total_price_str)
                logger.debug(f"Order '{order_uuid}': total_price = {total_price}")
            except (ValueError, AttributeError) as e:
                logger.error(f"Invalid 'total_price' for order '{order_uuid}': {e}.")
                return None, f"Invalid 'total_price' for order '{order_uuid}'."

            return total_price, None

    # If target is not met after processing all orders
    logger.warning(f"No orders found where cumulative value >= {target_cents} cents.")
    return None, f"No orders found where cumulative value >= {target_cents} cents."

@app.get("/generate_quote", response_model=QuoteResponse)
def generate_quote_endpoint(
    sorted_set_key: str,
    target_cents: float,
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """
    Endpoint to generate a quote based on the provided sorted set key and target cents.

    Args:
        sorted_set_key (str): Name of the Redis sorted set.
        target_cents (float): Target cumulative value in cents.
        redis_client (redis.Redis): Redis client instance.

    Returns:
        QuoteResponse: The response containing the quote or an error message.
    """
    logger.info(f"Received request to generate quote for sorted_set_key='{sorted_set_key}' with target_cents={target_cents}")

    # Validate target_cents
    if target_cents <= 0:
        logger.error("Invalid target_cents: must be a positive number.")
        return QuoteResponse(
            sorted_set_key=sorted_set_key,
            target_cents=target_cents,
            total_price=None,
            message="Error: target_cents must be a positive number."
        )

    # Determine sort order based on sorted_set_key
    descending = determine_sort_order(sorted_set_key)
    logger.debug(f"Sort order for '{sorted_set_key}': {'descending' if descending else 'ascending'}")

    # Generate the quote
    total_price, error_message = generate_quote(redis_client, sorted_set_key, target_cents, descending)

    if total_price is not None:
        logger.info(f"Successfully generated quote: total_price={total_price}")
        return QuoteResponse(
            sorted_set_key=sorted_set_key,
            target_cents=target_cents,
            total_price=total_price,
            message=None
        )
    else:
        logger.warning(f"Quote generation failed: {error_message}")
        return QuoteResponse(
            sorted_set_key=sorted_set_key,
            target_cents=target_cents,
            total_price=None,
            message=error_message
        )