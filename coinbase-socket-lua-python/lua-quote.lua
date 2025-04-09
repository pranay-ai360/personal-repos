-- Lua Script to Find the Total Price When Cumulative 'how_much_value_of_crypto_in_cents' Reaches Target

-- Usage:
-- EVAL "<script>" 1 <sorted_set_key> <target>

local sorted_set_key = 'BTC-USD_asks'
local target = 2000000

-- Fetch all orders in the sorted set with their scores
local orders = redis.call('ZRANGE', sorted_set_key, 0, -1, 'WITHSCORES')

local cumulative = 0

for i = 1, #orders, 2 do
    local order_uuid = orders[i]
    local how_much_str = redis.call('HGET', 'order:' .. order_uuid, 'how_much_value_of_crypto_in_cents')
    
    if how_much_str then
        local how_much = tonumber(how_much_str)
        if how_much then
            cumulative = cumulative + how_much

            if cumulative >= target then
                -- Return the 'total_price' of the current order
                return redis.call('HGET', 'order:' .. order_uuid, 'total_price')
            end
        end
    end
end

-- If target not reached, return nil
return nil