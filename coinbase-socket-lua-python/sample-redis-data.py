import uuid
import redis
from decimal import Decimal

# Example dataset from your provided data object
orders_data = [
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 300, "price_per_base_asset_PHP": 17400, "quantity": 0.005, "total_price_USD": 1.5, "total_price_PHP": 87},
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 200, "price_per_base_asset_PHP": 11600, "quantity": 2.5, "total_price_USD": 500, "total_price_PHP": 29000},
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 100, "price_per_base_asset_PHP": 5800, "quantity": 0.5, "total_price_USD": 50, "total_price_PHP": 2900},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 99, "price_per_base_asset_PHP": 5742, "quantity": 3, "total_price_USD": 297, "total_price_PHP": 17226},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 97, "price_per_base_asset_PHP": 5626, "quantity": 1, "total_price_USD": 97, "total_price_PHP": 5626},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 5, "price_per_base_asset_PHP": 290, "quantity": 2.5, "total_price_USD": 12.5, "total_price_PHP": 725}
]

# Connect to Redis
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

# Function to generate a unique UUID for the order
def generate_uuid():
    return str(uuid.uuid4())

# Function to format the decimal values with the given precision
def format_decimal(value, precision):
    """Formats a decimal number with specified precision."""
    return f"{Decimal(value):.{precision}f}"

# Function to prepare score for the sorted set based on price
def prepare_redis_score(price_per_base_asset_USD):
    """Prepares a score for the sorted set based on the price."""
    return float(price_per_base_asset_USD)

# Function to generate order ID with prefix
def generate_order_id():
    return f"order:{uuid.uuid4()}"

# Function to generate UUID and store order details in Redis
def load_order_to_redis(redis_client, product_id, side, price_per_base_asset_USD, quantity, total_price_USD,
                        price_per_smallest_unit, price_per_base_asset_PHP, total_price_PHP):
    """Loads an order into Redis with order details and adds it to a sorted set."""
    
    # Generate unique UUID for the order
    order_uuid = generate_uuid()
    order_id = generate_order_id()
    
    # Define the sorted set key based on the product_id and side (buy or sell)
    sorted_set_key = f"{product_id}_{'bids' if side.lower() == 'bids' else 'asks'}"  # e.g., 'BTC-USD_buy' or 'BTC-USD_sell'
    
    try:
        # Create a hash for the order with detailed information
        redis_client.hset(order_id, mapping={
            'pair': product_id,
            'side': 'Buy' if side.lower() == 'bids' else 'Sell',  # 'Buy' or 'Sell'
            'price_per_base_asset_USD': format_decimal(price_per_base_asset_USD, 20),  # Updated
            'quantity': format_decimal(quantity, 20),
            'total_price_USD': format_decimal(total_price_USD, 20),  # Updated
            'price_per_smallest_unit': format_decimal(price_per_smallest_unit, 20),
            'price_per_base_asset_PHP': format_decimal(price_per_base_asset_PHP, 20),  # Added
            'total_price_PHP': format_decimal(total_price_PHP, 20)  # Added
        })
        
        # Insert order into the specific sorted set '{product-id}_{side}'
        redis_client.zadd(sorted_set_key, {order_id: prepare_redis_score(price_per_base_asset_USD)})
        print(f"Order {order_id} added to Redis under sorted set {sorted_set_key}.")
    
    except Exception as e:
        print(f"Error inserting order {order_id} into Redis: {e}")


# Load all orders into Redis
if __name__ == "__main__":
    for order in orders_data:
        load_order_to_redis(
            redis_client, 
            order['pair'],
            order['side'],
            order['price_per_base_asset_USD'],
            order['quantity'],
            order['total_price_USD'],
            order['price_per_base_asset_USD'],  # Assuming price_per_smallest_unit is same as price_per_base_asset_USD
            order['price_per_base_asset_PHP'],
            order['total_price_PHP']
        )