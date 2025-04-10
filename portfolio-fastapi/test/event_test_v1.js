import http from 'k6/http';
import { sleep, check } from 'k6';

const events = [
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-01T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 100
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    assetPortfolioID: "161a624d-e6c4-43b6-9916-4f2974b0dcc8",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-02T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 210
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-03T01:00:00",
    trade: "Buy",
    quantity: 3,
    totalValue: 306
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-04T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 214
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-05T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 104
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-06T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 109
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-07T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 212
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-08T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 111
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-12T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 230
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-13T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 224
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-14T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 117
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-15T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 228
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-16T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 119
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    assetPortfolioID: "b4d3ec49-ace7-43f7-bd3e-f4dfc30e43f2",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-01T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 50
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-02T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 110
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-03T01:00:00",
    trade: "Buy",
    quantity: 3,
    totalValue: 156
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-04T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 114
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-05T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 54
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-06T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 59
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-07T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 112
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-08T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 61
  },
  // There are no events for 9th, 10th, and 11th February as per the provided table.
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-12T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 130
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-13T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 124
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-14T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 67
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-15T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 128
  },
  {
    cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-16T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 69
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    assetPortfolioID: "00750867-bc0a-44f0-bb07-378949e0cea3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-01T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 100
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-02T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 210
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-03T01:00:00",
    trade: "Buy",
    quantity: 3,
    totalValue: 306
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-04T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 214
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-05T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 104
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-06T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 109
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-07T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 212
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-08T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 111
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-12T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 230
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-13T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 224
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-14T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 117
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-15T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 228
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "AAPL/USD",
    datetime_pht: "2025-02-16T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 119
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    assetPortfolioID: "c9eee42e-0e50-4098-8fcc-40d92c5ac335",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-01T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 50
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-02T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 110
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-03T01:00:00",
    trade: "Buy",
    quantity: 3,
    totalValue: 156
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-04T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 114
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-05T01:00:00",
    trade: "Buy",
    quantity: 1,
    totalValue: 54
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-06T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 59
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-07T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 112
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-08T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 61
  },
  // There are no events for 9th, 10th, and 11th February as per the provided table.
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-12T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 130
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-13T01:00:00",
    trade: "Buy",
    quantity: 2,
    totalValue: 124
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-14T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 67
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-15T01:00:00",
    trade: "Sell",
    quantity: 2,
    totalValue: 128
  },
  {
    cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3",
    pair: "MSFT/USD",
    datetime_pht: "2025-02-16T01:00:00",
    trade: "Sell",
    quantity: 1,
    totalValue: 69
  }
];

export default function () {
  const url = 'http://0.0.0.0:8005/events';
  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  events.forEach(eventData => {
    const payload = JSON.stringify(eventData);
    const res = http.post(url, payload, params);

    check(res, {
      'status is 200': (r) => r.status === 200,
    });

    // Optional delay between requests; adjust as needed.
    sleep(1);
  });
}