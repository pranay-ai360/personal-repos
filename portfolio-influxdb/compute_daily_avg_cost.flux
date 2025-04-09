option task = {name: "compute_daily_avg_cost", every: 1m}

trades = from(bucket: "home")
  |> range(start: -2d)
  |> filter(fn: (r) => r["_measurement"] == "trades" and r["trade_type"] == "buy")
  |> filter(fn: (r) => r["_field"] == "cost" or r["_field"] == "quantity")
  // Pivot so that each record has both "cost" and "quantity"
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])

cumul = trades
  // Compute cumulative sums for cost and quantity
  |> cumulativeSum(columns: ["cost", "quantity"])
  // Aggregate per day; this gets the last cumulative value for each day
  |> aggregateWindow(every: 1d, fn: last, createEmpty: true)
  // If any day is missing a new value, fill with previous values
  |> fill(column: "cost", usePrevious: true)
  |> fill(column: "quantity", usePrevious: true)

avgCost = cumul
  |> map(fn: (r) => ({
       _time: r._time,
       avgCost: r.cost / r.quantity,
       asset: r.asset
  }))

avgCost
  |> to(
    bucket: "home",
    org: "docs",
    measurement: "daily_avg_cost"
  )