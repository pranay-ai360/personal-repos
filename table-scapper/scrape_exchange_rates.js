const puppeteer = require('puppeteer');
const fs = require('fs');
const csvWriter = require('csv-writer').createObjectCsvWriter;

(async () => {
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    await page.goto('https://www.bsp.gov.ph/SitePages/Statistics/exchangerate.aspx', { waitUntil: 'networkidle2' });

    const dateText = await page.evaluate(() => {
        const dateElement = document.querySelector('#date');
        return dateElement ? dateElement.innerText.trim() : '';
    });

    // Parse the date and format it as YYYYMMDD
    const date = new Date(dateText);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const formattedDate = `${year}${month}${day}`;

    const data = await page.evaluate(() => {
        const rows = Array.from(document.querySelectorAll('#ExRate tbody tr'));
        const tableData = [];

        rows.forEach(row => {
            const columns = Array.from(row.querySelectorAll('td'));
            if (columns.length === 6) {
                const country = columns[0].innerText.trim().replace(/^\d+\s*/, ''); // Remove leading numbers
                tableData.push({
                    country: country,
                    unit: columns[1].innerText.trim(),
                    symbol: columns[2].innerText.trim(),
                    euroEquivalent: columns[3].innerText.trim(),
                    usdEquivalent: columns[4].innerText.trim(),
                    phpEquivalent: columns[5].innerText.trim()
                });
            }
        });

        return tableData;
    });

    await browser.close();

    const headers = [
        { id: 'country', title: 'Country' },
        { id: 'unit', title: 'Unit' },
        { id: 'symbol', title: 'Symbol' },
        { id: 'euroEquivalent', title: 'Euro Equivalent' },
        { id: 'usdEquivalent', title: 'USD Equivalent' },
        { id: 'phpEquivalent', title: 'PHP Equivalent' }
    ];

    const writer = csvWriter({
        path: `exchange_rates_${formattedDate}.csv`,
        header: headers
    });

    writer.writeRecords(data)
        .then(() => console.log('CSV file written successfully'));
})();
