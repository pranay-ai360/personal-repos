import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

// --- Configuration ---
const API_BASE_URL = 'http://localhost:8000'; // CHANGE if your API runs elsewhere
const CSV_FILE_PATH = './price_data.csv';

// --- Load CSV Data ---
const priceData = new SharedArray('priceData', function () {
    const fileContent = open(CSV_FILE_PATH);
    const lines = fileContent.split('\n').filter(line => line.trim() !== '');
    const dataLines = lines.slice(1);
    const data = dataLines.map(line => {
        const parts = line.split(',');
        if (parts.length === 3) {
            return {
                dateTimeStr: parts[0].trim(),
                tickerId: parts[1].trim(),
                priceStr: parts[2].trim(),
            };
        } else {
            // Use console.error in init context for setup issues
            console.error(`[Init Context] Skipping malformed line: ${line}`);
            return null;
        }
    }).filter(item => item !== null);

    if (data.length === 0) {
        throw new Error(`[Init Context] No valid data loaded from ${CSV_FILE_PATH}. Check the file format and content.`);
    }
    // Use console.info for setup info
    console.info(`[Init Context] Loaded ${data.length} data points from CSV.`);
    return data;
});

// --- k6 Options ---
export const options = {
    stages: [
        { duration: '10s', target: 2 },  // Keep target low for debugging logs
        { duration: '20s', target: 2 },
        { duration: '5s', target: 0 },
    ],
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500'],
    },
};

// --- Helper Function: Convert DD/MM/YYYY HH:MM:SS to ISO 8601 UTC ---
function convertToISO(dateTimeStr, vu, iter) { // Pass VU/Iter for context in logs
    try {
        const parts = dateTimeStr.split(' ');
        if (parts.length !== 2) throw new Error('Invalid format - missing space');
        const datePart = parts[0];
        const timePart = parts[1];
        const dateComponents = datePart.split('/');
        if (dateComponents.length !== 3) throw new Error('Invalid date format');
        const day = dateComponents[0].padStart(2, '0');
        const month = dateComponents[1].padStart(2, '0');
        const year = dateComponents[2];
        const timeComponents = timePart.split(':');
        if (timeComponents.length !== 3) throw new Error('Invalid time format');
        const hour = timeComponents[0].padStart(2, '0');
        const minute = timeComponents[1].padStart(2, '0');
        const second = timeComponents[2].padStart(2, '0');
        const isoString = `${year}-${month}-${day}T${hour}:${minute}:${second}Z`;
        if (isNaN(Date.parse(isoString))) {
             throw new Error(`Generated invalid date: ${isoString}`);
        }
        return isoString;
    } catch (e) {
        // Log errors occurring within a VU's execution context
        console.error(`VU ${vu} Iter ${iter}: Error converting date string "${dateTimeStr}": ${e.message}`);
        return null;
    }
}


// --- Main k6 Virtual User Function ---
export default function () {
    // Get VU and iteration context for logs
    const vu = __VU;
    const iter = __ITER;

    // Pick a random data entry
    const randomIndex = Math.floor(Math.random() * priceData.length);
    const record = priceData[randomIndex];

    // Convert the date/time string
    const isoDateTime = convertToISO(record.dateTimeStr, vu, iter); // Pass context

    // Skip iteration if date conversion failed
    if (!isoDateTime) {
        console.warn(`VU ${vu} Iter ${iter}: Skipping iteration due to failed date conversion for: ${record.dateTimeStr}`);
        sleep(0.1);
        return;
    }

    // Prepare the JSON payload
    const payloadObject = { // Create object first for potential logging/manipulation
        DateTime_UTC: isoDateTime,
        TICKER_ID: record.tickerId,
        PRICE: parseFloat(record.priceStr),
    };
    const payload = JSON.stringify(payloadObject); // Stringify for request

    // Set headers
    const params = {
        headers: {
            'Content-Type': 'application/json',
        },
         // Add tags to metrics for better filtering in results
        tags: {
            name: 'WriteTickerRequest', // Add a tag to the request metrics
            tickerId: record.tickerId,
        }
    };

    // --- LOG REQUEST ---
    // Log request details before sending
    console.log(`VU ${vu} Iter ${iter}: Sending Request to /write_ticker for ${record.tickerId}`);
    console.log(`VU ${vu} Iter ${iter}: Request Payload: ${payload}`);
    // ---------------

    // Send the POST request
    const res = http.post(`${API_BASE_URL}/write_ticker`, payload, params);

    // --- LOG RESPONSE ---
    // Log response details after receiving
    console.log(`VU ${vu} Iter ${iter}: Received Response for /write_ticker (${record.tickerId}) - Status: ${res.status}`);
    if (res && res.body) {
         // Log the raw response body string
        console.log(`VU ${vu} Iter ${iter}: Response Body: ${res.body}`);
    } else {
        console.warn(`VU ${vu} Iter ${iter}: Response for /write_ticker (${record.tickerId}) had no body or request failed.`);
    }
    // ---------------

    // Check the response
    check(res, {
        'status is 200': (r) => r.status === 200,
        'response body contains success': (r) => {
             // Add more robust check for JSON parsing
             let body;
             try {
                 body = r.json(); // Attempt to parse JSON
             } catch (e) {
                 console.error(`VU ${vu} Iter ${iter}: Failed to parse JSON response for ${record.tickerId}: ${r.body}`);
                 return false; // Failed check if JSON is invalid
             }
             return body && body.status === 'success' && body.message && body.message.includes(record.tickerId);
        }
    }, { // Add tags to the check results as well
       checkTickerId: record.tickerId // Tag checks by tickerId
    });

    // Add a small delay between requests per VU
    sleep(1);
}