const express = require('express');
const bodyParser = require('body-parser');
const path = require('path');
const { processAssets } = require('./token-sweepJob-inprogress.cjs');

const app = express();
const port = 3000;

app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static('public'));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.post('/submit', (req, res) => {
    const { AssetID, FeeAssetID, threshold, anyvaultAbove } = req.body;
    const assetsPayload = [{
        AssetID,
        FeeAssetID,
        AssetType: "cryptoToken",
        threshold,
        anyvaultAbove,
    }];

    // Assuming processAssets returns a Promise
    processAssets(assetsPayload)
        .then(() => {
            res.send('Process initiated successfully.');
        })
        .catch((error) => {
            console.error(error);
            res.status(500).send('An error occurred.');
        });
});

app.listen(port, () => {
    console.log(`Server listening at http://localhost:${port}`);
});
