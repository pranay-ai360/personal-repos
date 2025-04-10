import http from 'k6/http';
import { sleep, check } from 'k6';

// Helper function to convert UTC to PHT (UTC+8)
function addPHTDateTime(utcDatetime) {
  const utcDate = new Date(utcDatetime);
  // Add 8 hours to get PHT
  const phtDate = new Date(utcDate.getTime() + (8 * 60 * 60 * 1000));
  return phtDate.toISOString().slice(0, 19);
}

const prices = [
  { datetime_utc: "2025-02-01T00:00:00", pair: "AAPL/USD", price: 100 },
  { datetime_utc: "2025-02-02T00:00:00", pair: "AAPL/USD", price: 105 },
  { datetime_utc: "2025-02-03T00:00:00", pair: "AAPL/USD", price: 102 },
  { datetime_utc: "2025-02-04T00:00:00", pair: "AAPL/USD", price: 107 },
  { datetime_utc: "2025-02-05T00:00:00", pair: "AAPL/USD", price: 104 },
  { datetime_utc: "2025-02-06T00:00:00", pair: "AAPL/USD", price: 109 },
  { datetime_utc: "2025-02-07T00:00:00", pair: "AAPL/USD", price: 106 },
  { datetime_utc: "2025-02-08T00:00:00", pair: "AAPL/USD", price: 111 },
  { datetime_utc: "2025-02-09T00:00:00", pair: "AAPL/USD", price: 108 },
  { datetime_utc: "2025-02-10T00:00:00", pair: "AAPL/USD", price: 113 },
  { datetime_utc: "2025-02-11T00:00:00", pair: "AAPL/USD", price: 110 },
  { datetime_utc: "2025-02-12T00:00:00", pair: "AAPL/USD", price: 115 },
  { datetime_utc: "2025-02-13T00:00:00", pair: "AAPL/USD", price: 112 },
  { datetime_utc: "2025-02-14T00:00:00", pair: "AAPL/USD", price: 117 },
  { datetime_utc: "2025-02-15T00:00:00", pair: "AAPL/USD", price: 114 },
  { datetime_utc: "2025-02-16T00:00:00", pair: "AAPL/USD", price: 119 },
  { datetime_utc: "2025-02-01T00:00:00", pair: "MSFT/USD", price: 50 },
  { datetime_utc: "2025-02-02T00:00:00", pair: "MSFT/USD", price: 55 },
  { datetime_utc: "2025-02-03T00:00:00", pair: "MSFT/USD", price: 52 },
  { datetime_utc: "2025-02-04T00:00:00", pair: "MSFT/USD", price: 57 },
  { datetime_utc: "2025-02-05T00:00:00", pair: "MSFT/USD", price: 54 },
  { datetime_utc: "2025-02-06T00:00:00", pair: "MSFT/USD", price: 59 },
  { datetime_utc: "2025-02-07T00:00:00", pair: "MSFT/USD", price: 56 },
  { datetime_utc: "2025-02-08T00:00:00", pair: "MSFT/USD", price: 61 },
  { datetime_utc: "2025-02-09T00:00:00", pair: "MSFT/USD", price: 58 },
  { datetime_utc: "2025-02-10T00:00:00", pair: "MSFT/USD", price: 63 },
  { datetime_utc: "2025-02-11T00:00:00", pair: "MSFT/USD", price: 60 },
  { datetime_utc: "2025-02-12T00:00:00", pair: "MSFT/USD", price: 65 },
  { datetime_utc: "2025-02-13T00:00:00", pair: "MSFT/USD", price: 62 },
  { datetime_utc: "2025-02-14T00:00:00", pair: "MSFT/USD", price: 67 },
  { datetime_utc: "2025-02-15T00:00:00", pair: "MSFT/USD", price: 64 },
  { datetime_utc: "2025-02-16T00:00:00", pair: "MSFT/USD", price: 69 }
];

// Add datetime_pht to each price object
const enrichedPrices = prices.map(price => ({
  ...price,
  datetime_pht: addPHTDateTime(price.datetime_utc)
}));

export default function () {
  const url = 'http://0.0.0.0:8005/price';
  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  // Iterate through each price data object and post it.
  enrichedPrices.forEach((data) => {
    const payload = JSON.stringify(data);
    const res = http.post(url, payload, params);

    // Check that the request succeeded.
    check(res, {
      'status was 200': (r) => r.status === 200,
    });

    // Add a small delay between requests.
    sleep(1);
  });
}