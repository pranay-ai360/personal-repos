import http from 'k6/http';
import { sleep, check } from 'k6';

// --- Configuration ---
const BASE_URL = 'http://localhost:8005';
const EVENT_API_ENDPOINT = `${BASE_URL}/events`;
const HEADERS = { 'Content-Type': 'application/json' };

// List of users (cpmIDs) to process
const testCPMIDs = [
  "b204387b-d3f4-48f5-b00d-971d8888624a", // UserID 1
  "95a990af-a85b-45e2-ab23-ae204dc885e3"  // UserID 2
];

// --- Raw Event Data (Combined for Both Users) ---
const rawEvents = [
  // --- Events for first user ---
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-01T00:00:00", trade: "Buy",  quantity: 1, totalValue: 100 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-02T00:00:00", trade: "Buy",  quantity: 2, totalValue: 210 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-03T00:00:00", trade: "Buy",  quantity: 3, totalValue: 306 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-04T00:00:00", trade: "Buy",  quantity: 2, totalValue: 214 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-05T00:00:00", trade: "Buy",  quantity: 1, totalValue: 104 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-06T00:00:00", trade: "Sell", quantity: 1, totalValue: 109 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-07T00:00:00", trade: "Sell", quantity: 2, totalValue: 212 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-08T00:00:00", trade: "Sell", quantity: 1, totalValue: 111 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-12T00:00:00", trade: "Buy",  quantity: 2, totalValue: 230 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-13T00:00:00", trade: "Buy",  quantity: 2, totalValue: 224 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-14T00:00:00", trade: "Sell", quantity: 1, totalValue: 117 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-15T00:00:00", trade: "Sell", quantity: 2, totalValue: 228 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "AAPL/USD", datetime_pht: "2025-02-16T00:00:00", trade: "Sell", quantity: 1, totalValue: 119 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-01T00:00:00", trade: "Buy",  quantity: 1, totalValue: 50 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-02T00:00:00", trade: "Buy",  quantity: 2, totalValue: 110 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-03T00:00:00", trade: "Buy",  quantity: 3, totalValue: 156 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-04T00:00:00", trade: "Buy",  quantity: 2, totalValue: 114 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-05T00:00:00", trade: "Buy",  quantity: 1, totalValue: 54 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-06T00:00:00", trade: "Sell", quantity: 1, totalValue: 59 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-07T00:00:00", trade: "Sell", quantity: 2, totalValue: 112 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-08T00:00:00", trade: "Sell", quantity: 1, totalValue: 61 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-12T00:00:00", trade: "Buy",  quantity: 2, totalValue: 130 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-13T00:00:00", trade: "Buy",  quantity: 2, totalValue: 124 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-14T00:00:00", trade: "Sell", quantity: 1, totalValue: 67 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-15T00:00:00", trade: "Sell", quantity: 2, totalValue: 128 },
  { cpmID: "b204387b-d3f4-48f5-b00d-971d8888624a", pair: "MSFT/USD", datetime_pht: "2025-02-16T00:00:00", trade: "Sell", quantity: 1, totalValue: 69 },

  // --- Events for second user ---
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-01T00:00:00", trade: "Buy",  quantity: 1, totalValue: 100 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-02T00:00:00", trade: "Buy",  quantity: 2, totalValue: 210 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-03T00:00:00", trade: "Buy",  quantity: 3, totalValue: 306 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-04T00:00:00", trade: "Buy",  quantity: 2, totalValue: 214 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-05T00:00:00", trade: "Buy",  quantity: 1, totalValue: 104 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-06T00:00:00", trade: "Sell", quantity: 1, totalValue: 109 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-07T00:00:00", trade: "Sell", quantity: 2, totalValue: 212 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-08T00:00:00", trade: "Sell", quantity: 1, totalValue: 111 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-12T00:00:00", trade: "Buy",  quantity: 2, totalValue: 230 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-13T00:00:00", trade: "Buy",  quantity: 2, totalValue: 224 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-14T00:00:00", trade: "Sell", quantity: 1, totalValue: 117 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-15T00:00:00", trade: "Sell", quantity: 2, totalValue: 228 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "AAPL/USD", datetime_pht: "2025-02-16T00:00:00", trade: "Sell", quantity: 1, totalValue: 119 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-01T00:00:00", trade: "Buy",  quantity: 1, totalValue: 50 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-02T00:00:00", trade: "Buy",  quantity: 2, totalValue: 110 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-03T00:00:00", trade: "Buy",  quantity: 3, totalValue: 156 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-04T00:00:00", trade: "Buy",  quantity: 2, totalValue: 114 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-05T00:00:00", trade: "Buy",  quantity: 1, totalValue: 54 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-06T00:00:00", trade: "Sell", quantity: 1, totalValue: 59 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-07T00:00:00", trade: "Sell", quantity: 2, totalValue: 112 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-08T00:00:00", trade: "Sell", quantity: 1, totalValue: 61 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-12T00:00:00", trade: "Buy",  quantity: 2, totalValue: 130 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-13T00:00:00", trade: "Buy",  quantity: 2, totalValue: 124 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-14T00:00:00", trade: "Sell", quantity: 1, totalValue: 67 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-15T00:00:00", trade: "Sell", quantity: 2, totalValue: 128 },
  { cpmID: "95a990af-a85b-45e2-ab23-ae204dc885e3", pair: "MSFT/USD", datetime_pht: "2025-02-16T00:00:00", trade: "Sell", quantity: 1, totalValue: 69 }
];

// --- Main Execution Logic ---
export default function () {
  let portfolioIdMap = {};

  // --- Process Each User to Get Their Portfolio Mapping ---
  testCPMIDs.forEach((cpmID) => {
    // Step 1: Get the combinedPortfolioId
    const combinedPayload = JSON.stringify({ cpmID: cpmID });
    const combinedRes = http.post(`${BASE_URL}/portfolios/combined`, combinedPayload, { headers: HEADERS });
    check(combinedRes, {
      [`Combined portfolio for ${cpmID} status is 200`]: (r) => r.status === 200,
      [`Combined response for ${cpmID} has combinedPortfolioId`]: (r) => !!r.json().combinedPortfolioId,
    });

    const combinedPortfolioId = combinedRes.json().combinedPortfolioId;
    console.log(`For cpmID ${cpmID} (UserID ${cpmID === testCPMIDs[0] ? 1 : 2}): Combined Portfolio ID = ${combinedPortfolioId}`);

    // Step 2: Get Asset Portfolio Mapping for the requested pairs
    const assetPayload = JSON.stringify({
      cpmID: cpmID,
      combinedPortfolioId: combinedPortfolioId,
      assetPortfolio: [ "AAPL/USD", "MSFT/USD" ]
    });
    const assetRes = http.post(`${BASE_URL}/portfolios/asset`, assetPayload, { headers: HEADERS });
    check(assetRes, {
      [`Asset portfolio for ${cpmID} status is 200`]: (r) => r.status === 200,
    });

    const assetData = assetRes.json().assetPortfolio;
    portfolioIdMap[cpmID] = portfolioIdMap[cpmID] || {};
    for (const pair in assetData) {
      if (assetData[pair].length > 0) {
        portfolioIdMap[cpmID][pair] = assetData[pair][0].id;
      }
    }
    console.log(`For cpmID ${cpmID} (UserID ${cpmID === testCPMIDs[0] ? 1 : 2}): Asset Portfolio ID = ${JSON.stringify(portfolioIdMap[cpmID])}`);

    // --- Print Events for the Current User ---
    const userEvents = rawEvents.filter(event => event.cpmID === cpmID);
    console.log(`For cpmID ${cpmID} (UserID ${cpmID === testCPMIDs[0] ? 1 : 2}): Processing Events`);
    userEvents.forEach((event, index) => {
      console.log(`Event ${index + 1}: cpmID = ${event.cpmID}, Pair = ${event.pair}, Trade = ${event.trade}, Quantity = ${event.quantity}, Total Value = ${event.totalValue}`);
    });
  });

  // --- Generate Portfolio Data for Each cpmID ---
  testCPMIDs.forEach((cpmID) => {
    const portfolioIDs = [
      portfolioIdMap[cpmID]["AAPL/USD"], 
      portfolioIdMap[cpmID]["MSFT/USD"]
    ];

    const generatePayload = JSON.stringify({
      assetPortfolioID: portfolioIDs.filter(id => id !== undefined)
    });

    const generateRes = http.post(`${BASE_URL}/generate-portfolio-data`, generatePayload, { headers: HEADERS });
    check(generateRes, {
      [`Generate portfolio data for ${cpmID} status is 200`]: (r) => r.status === 200,
    });

    console.log(`Portfolio Data Generation for ${cpmID} Completed`);

    // --- Query Portfolio Data After Generation ---
    const queryPayload = JSON.stringify({
      cpmID: cpmID,
      assetPortfolioID: portfolioIDs.filter(id => id !== undefined),
      start_datetime_pht: "2025-02-01T00:00:00",
      end_datetime_pht: "2025-02-16T23:59:59"
    });

    const queryRes = http.post(`${BASE_URL}/query-portfolio`, queryPayload, { headers: HEADERS });
    check(queryRes, {
      [`Query portfolio data for ${cpmID} status is 200`]: (r) => r.status === 200,
    });

    console.log(`Portfolio Query for ${cpmID} Completed`);
    sleep(0.05); // 50ms delay between requests
  });
}