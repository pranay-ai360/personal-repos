import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

// --- Configuration ---
const API_BASE_URL = 'http://localhost:8000'; // CHANGE if your API runs elsewhere (e.g., Docker IP)
const CSV_FILE_PATH = './price_data.csv';

// --- Load CSV Data ---
// Use SharedArray to load the CSV data only once and share it among VUs.
// Note: This simple parsing assumes no commas within fields and standard line endings.
// For more robust CSV parsing (handling quotes, commas in fields), consider bundling papaparse.
const priceData = new SharedArray('priceData', function () {
    // Load the CSV file content
    const fileContent = open(CSV_FILE_PATH);
    // Split into lines, remove potential empty lines
    const lines = fileContent.split('\n').filter(line => line.trim() !== '');
    // Remove header line
    const dataLines = lines.slice(1);

    // Process each line into an object
    const data = dataLines.map(line => {
        const parts = line.split(',');
        if (parts.length === 3) {
            return {
                dateTimeStr: parts[0].trim(),
                tickerId: parts[1].trim(),
                priceStr: parts[2].trim(),
            };
        } else {
            console.error(`Skipping malformed line: ${line}`);
            return null; // Mark as invalid
        }
    }).filter(item => item !== null); // Filter out invalid lines

    if (data.length === 0) {
        throw new Error(`No valid data loaded from ${CSV_FILE_PATH}. Check the file format and content.`);
    }
    console.log(`Loaded ${data.length} data points from CSV.`);
    return data; // The setup function must return the data
});

// --- k6 Options ---
export const options = {
    stages: [
        { duration: '10s', target: 5 },  // Ramp up to 5 Virtual Users over 10 seconds
        { duration: '30s', target: 5 },  // Stay at 5 VUs for 30 seconds
        { duration: '5s', target: 0 },   // Ramp down to 0 VUs over 5 seconds
    ],
    thresholds: {
        http_req_failed: ['rate<0.01'], // http errors should be less than 1%
        http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
    },
};

// --- Helper Function: Convert DD/MM/YYYY HH:MM:SS to ISO 8601 UTC ---
function convertToISO(dateTimeStr) {
    try {
        // 1. Split date and time parts
        const parts = dateTimeStr.split(' ');
        if (parts.length !== 2) throw new Error('Invalid format - missing space');

        const datePart = parts[0];
        const timePart = parts[1];

        // 2. Split date into DD, MM, YYYY
        const dateComponents = datePart.split('/');
        if (dateComponents.length !== 3) throw new Error('Invalid date format');
        const day = dateComponents[0].padStart(2, '0');
        const month = dateComponents[1].padStart(2, '0');
        const year = dateComponents[2];

        // 3. Split time into HH, MM, SS
        const timeComponents = timePart.split(':');
        if (timeComponents.length !== 3) throw new Error('Invalid time format');
        const hour = timeComponents[0].padStart(2, '0');
        const minute = timeComponents[1].padStart(2, '0');
        const second = timeComponents[2].padStart(2, '0');

        // 4. Assemble into ISO format string YYYY-MM-DDTHH:MM:SSZ
        // We assume the input time is already UTC as per the column name 'DateTime_UTC'
        const isoString = `${year}-${month}-${day}T${hour}:${minute}:${second}Z`;

        // 5. Optional: Validate the created date string (basic check)
        if (isNaN(Date.parse(isoString))) {
             throw new Error(`Generated invalid date: ${isoString}`);
        }

        return isoString;

    } catch (e) {
        console.error(`Error converting date string "${dateTimeStr}": ${e.message}`);
        return null; // Return null if conversion fails
    }
}


// --- Main k6 Virtual User Function ---
export default function (data) {
    // Pick a random data entry from the shared array for each iteration
    const randomIndex = Math.floor(Math.random() * priceData.length);
    const record = priceData[randomIndex];

    // Convert the date/time string from the CSV to the required ISO format
    const isoDateTime = convertToISO(record.dateTimeStr);

    // Skip iteration if date conversion failed
    if (!isoDateTime) {
        console.warn(`Skipping iteration due to failed date conversion for: ${record.dateTimeStr}`);
        sleep(0.1); // Avoid tight loop on errors
        return;
    }

    // Prepare the JSON payload
    const payload = JSON.stringify({
        DateTime_UTC: isoDateTime,
        TICKER_ID: record.tickerId,
        PRICE: parseFloat(record.priceStr), // Ensure price is a number
    });

    // Set headers
    const params = {
        headers: {
            'Content-Type': 'application/json',
        },
    };

    // Send the POST request
    const res = http.post(`${API_BASE_URL}/write_ticker`, payload, params);

    // Check the response
    check(res, {
        'status is 200': (r) => r.status === 200,
        'response body contains success': (r) => {
             try {
                 const body = r.json(); // Safely parse JSON
                 return body && body.status === 'success' && body.message.includes(record.tickerId);
             } catch (e) {
                 console.error(`Failed to parse JSON response for ${record.tickerId}: ${r.body}`);
                 return false;
             }
        }
    });

    // Add a small delay between requests per VU
    sleep(1); // Sleep for 1 second
}