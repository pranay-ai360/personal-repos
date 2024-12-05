# Sample data (can be expanded)
orders = [
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 300, "price_per_base_asset_PHP": 17400, "quantity": 0.005, "total_price_USD": 1.5, "total_price_PHP": 87},
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 200, "price_per_base_asset_PHP": 11600, "quantity": 2.5, "total_price_USD": 500, "total_price_PHP": 29000},
    {"pair": "BTC-USD", "side": "asks", "price_per_base_asset_USD": 100, "price_per_base_asset_PHP": 5800, "quantity": 0.5, "total_price_USD": 50, "total_price_PHP": 2900},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 99, "price_per_base_asset_PHP": 5742, "quantity": 3, "total_price_USD": 297, "total_price_PHP": 17226},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 97, "price_per_base_asset_PHP": 5626, "quantity": 1, "total_price_USD": 97, "total_price_PHP": 5626},
    {"pair": "BTC-USD", "side": "bids", "price_per_base_asset_USD": 5, "price_per_base_asset_PHP": 290, "quantity": 2.5, "total_price_USD": 12.5, "total_price_PHP": 725}
]

# Sorting the orders based on the side
bids = [order for order in orders if order["side"] == "bids"]
asks = [order for order in orders if order["side"] == "asks"]

# Sort bids from highest to lowest price
bids_sorted = sorted(bids, key=lambda x: x["price_per_base_asset_USD"], reverse=True)

# Sort asks from lowest to highest price
asks_sorted = sorted(asks, key=lambda x: x["price_per_base_asset_USD"])

# Set target quantity to be accumulated
order_type = "sell"  # Change to "buy" if you're looking at asks
target = 3.5
total_price = 0
previous_target = 0
index = 0

# Adjust sorted_orders based on order_type
if order_type == "buy":
    sorted_orders = asks_sorted  # Look at asks for buying
else:
    sorted_orders = bids_sorted  # Look at bids for selling

# Using a while loop to iterate over the sorted orders
while previous_target < target and index < len(sorted_orders):
    order = sorted_orders[index]
    quantity = order["quantity"]
    price_per_base_asset_USD = order["price_per_base_asset_USD"]
    
    # Check if we can accumulate the full quantity from the current order
    if previous_target + quantity <= target:
        total_price += order["total_price_USD"]
        previous_target += quantity
    else:
        # If we exceed the target with the current order, calculate the remaining price
        remaining_target = target - previous_target
        total_price += remaining_target * price_per_base_asset_USD
        break
    
    index += 1

# Output the total price for the target
print("Total price for target:", total_price)