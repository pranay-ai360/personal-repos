import redis

r = redis.Redis(host='localhost', port=6379, db=0)
cursor = 0
sorted_sets = []

while True:
    cursor, keys = r.scan(cursor=cursor, match='*', _type='zset', count=100)
    sorted_sets.extend(keys)
    if cursor == 0:
        break

print("Sorted Sets:", sorted_sets)