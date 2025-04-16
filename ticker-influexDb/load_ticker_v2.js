import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Trend } from 'k6/metrics'; // Import Trend for custom timing

// --- Configuration ---
const API_URL = 'http://0.0.0.0:8000/write_ticker'; // Your API endpoint
const CSV_FILE_PATH = './price_data_hourly.csv'; // Relative path to your CSV file

// Custom metric to track processing time per row
const processingTime = new Trend('processing_time_per_row', true);

// --- Load CSV Data ---
// Use SharedArray for efficiency: the file is read only once and shared between VUs.
const csvData = new SharedArray('tickerData', function () {
    try {
        // Use open() to read the file content
        let fileContent = open(CSV_FILE_PATH);
        if (!fileContent) {
            throw new Error(`Failed to open CSV file at path: ${CSV_FILE_PATH}`);
        }

        // Basic CSV parsing (split by newline, then by comma)
        // Assumes no commas within fields and uses standard line endings (\n or \r\n)
        let lines = fileContent.replace(/\r\n/g, '\n').trim().split('\n');

        // Check if the first line is the header and remove it
        if (lines.length > 0 && lines[0].toLowerCase().startsWith('datetime_utc')) {
            lines = lines.slice(1); // Remove header row
            console.log(`CSV Header removed. ${lines.length} data rows found.`);
        } else if (lines.length > 0) {
            console.warn("CSV file does not seem to have the expected 'DateTime_UTC' header. Processing all lines.");
        } else {
            console.warn("CSV file appears to be empty after trimming.");
            return []; // Return empty array if no lines
        }

        // Map lines to arrays of columns
        let parsedData = lines.map((line, idx) => {
            const columns = line.split(',');
            // Basic validation: ensure we have exactly 3 columns after trimming
            if (columns.length === 3) {
                return columns.map(col => col.trim()); // Trim each column
            }
            console.error(`Skipping malformed line (line ${idx + 2} in original file): ${line} - Expected 3 columns, found ${columns.length}`);
            return null; // Mark line as invalid
        }).filter(row => row !== null); // Filter out any invalid lines

        console.log(`Successfully parsed ${parsedData.length} valid data rows from CSV.`);
        if (parsedData.length === 0) {
             throw new Error(`CSV file loaded, but resulted in zero valid data rows after parsing.`);
        }
        return parsedData;

    } catch (e) {
        // K6 doesn't have console.fatal, use error and throw to stop execution
        console.error(`Error reading or parsing CSV file: ${e.message}`);
        // Throwing here will stop the test initialization if the data can't be loaded
        throw new Error(`Critical error loading CSV data: ${e.message}`);
    }
});


// --- k6 Options ---
export const options = {
    scenarios: {
        // Define a scenario where each VU executes the default function exactly once
        send_all_data_once_per_vu: {
            executor: 'per-vu-iterations', // Each VU runs a fixed number of iterations
            vus: 20,                       // Number of parallel virtual users (jobs)
            iterations: 1,                 // Each VU runs exactly 1 iteration
            maxDuration: '5m',             // Maximum time allowed for the VUs to complete their single iteration (adjust as needed)
        }
    },
    thresholds: {
        http_req_failed: ['rate<0.01'],      // Less than 1% failed requests overall
        http_req_duration: ['p(95)<1000'],   // 95% of individual requests should be below 1000ms (adjust as needed)
        processing_time_per_row: ['p(95)<1100'], // 95% of row processing (incl. req) below 1100ms
        checks: ['rate>0.99'],             // Over 99% of checks should pass
    },
    // Ensure setup function ran without critical errors if data loading is essential
    setupTimeout: '30s', // Allow time for CSV loading/parsing
};

// --- Helper function to convert CSV datetime to ISO 8601 UTC ---
function formatTimestamp(csvDateTime) {
    // Input format: DD/MM/YYYY HH:MM:SS
    const parts = csvDateTime.trim().split(' ');
    if (parts.length !== 2) {
        // console.error(`Invalid timestamp format (expected 'DD/MM/YYYY HH:MM:SS'): ${csvDateTime}`); // Reduce log noise
        return null; // Invalid format
    }

    const dateParts = parts[0].split('/');
    if (dateParts.length !== 3 || dateParts[0].length !== 2 || dateParts[1].length !== 2 || dateParts[2].length !== 4) {
        // console.error(`Invalid date part in timestamp: ${parts[0]}`);
        return null; // Invalid date part
    }

    const timePart = parts[1];
    if (!/^\d{1,2}:\d{2}:\d{2}$/.test(timePart)) { // Allow single digit hour
        // console.error(`Invalid time part in timestamp: ${timePart}`);
         return null; // Invalid time part
    }
     // Pad single-digit hour if necessary
    const timeParts = timePart.split(':');
    const hour = timeParts[0].padStart(2, '0');
    const minute = timeParts[1];
    const second = timeParts[2];
    const formattedTimePart = `${hour}:${minute}:${second}`;


    // Rearrange to YYYY-MM-DD
    const isoDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}`;

    // Combine and add Z for UTC (assuming CSV times are already UTC)
    return `${isoDate}T${formattedTimePart}Z`;
}


// --- Main k6 Test Logic (Executed once per VU) ---
export default function () {
    // Check if data loaded correctly and is not empty - critical check
    if (!csvData || csvData.length === 0) {
        console.error(`VU ${__VU}: No data available from CSV. Aborting VU execution.`);
        // In 'per-vu-iterations' executor, returning effectively stops this VU's only iteration
        return;
    }

    console.log(`VU ${__VU}: Starting to process ${csvData.length} records.`);
    let successCount = 0;
    let errorCount = 0;

    // Iterate through ALL records in the CSV data for this VU
    for (let i = 0; i < csvData.length; i++) {
        const record = csvData[i]; // Access the record using the loop index 'i'
        const startTime = Date.now(); // Start timer for this row

        // Check if the record itself is valid
        if (!record || record.length !== 3) {
            console.error(`VU ${__VU}: Skipping invalid record structure at index ${i}: ${record}`);
            errorCount++;
            continue; // Move to the next record in the loop
        }

        // Extract data from the record
        const dateTimeStr = record[0];
        const tickerId = record[1];
        const priceStr = record[2];

        // Format the timestamp
        const isoDateTime = formatTimestamp(dateTimeStr);
        if (!isoDateTime) {
            console.error(`VU ${__VU}: Skipping record due to timestamp parsing error (Index: ${i}). Timestamp value: '${dateTimeStr}'`);
            errorCount++;
            continue; // Move to the next record
        }

        // Convert price to float
        const price = parseFloat(priceStr);
        if (isNaN(price)) {
            console.error(`VU ${__VU}: Could not parse price: '${priceStr}'. Skipping record (Index: ${i}).`);
            errorCount++;
            continue; // Move to the next record
        }

        // Construct the JSON payload
        const payload = JSON.stringify({
            DateTime_UTC: isoDateTime,
            TICKER_ID: tickerId,
            PRICE: price,
        });

        // Define request parameters (headers)
        const params = {
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            tags: {
                name: 'WriteTickerData', // Tag for easier filtering of results
                ticker: tickerId,
                vu: __VU,               // Tag with VU ID
            },
        };

        // Send the POST request
        const res = http.post(API_URL, payload, params);

        // Check the response status and log errors
        const checkOutput = check(res, {
            [`VU ${__VU} - Row ${i} - status is 200`]: (r) => r.status === 200,
            // Optional: Add check for successful response body content if applicable
            // [`VU ${__VU} - Row ${i} - response body indicates success`]: (r) => r.json('status') === 'success',
        }, { vu: __VU, rowIndex: i }); // Add tags to the check itself

        if (!checkOutput) {
            errorCount++;
            console.error(`VU ${__VU} Request failed! Index: ${i}, Status: ${res.status}, URL: ${API_URL}, Body: ${res.body}, Payload: ${payload}`);
        } else {
            successCount++;
        }

        // Record the processing time for this row
        processingTime.add(Date.now() - startTime);

        // NO SLEEP INSIDE THE LOOP - process all rows as fast as possible for this VU
    }

    console.log(`VU ${__VU}: Finished processing. Success: ${successCount}, Errors: ${errorCount}`);
    // No sleep after the loop needed because the iteration ends here.
}