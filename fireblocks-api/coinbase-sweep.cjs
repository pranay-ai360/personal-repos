const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { sign } = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');
const csvParser = require('csv-parser');

// API Credentials and Initialization
const apiSecretPath = "./fb.key";
const apiSecret = fs.readFileSync(path.resolve(apiSecretPath), "utf8");
const apiKey = "68937138-8c6a-826d-88d7-f843d981927a";
const baseUrl = "https://api.fireblocks.io";

const omniBusVaultID = 3;
const coinbaseExchangeID = '8a19f86c-25b9-f2d7-924a-dd6667d3b0e2';

class FireblocksRequestHandler {
    constructor(apiSecret, apiKey, baseUrl = "https://api.fireblocks.io") {
        this.baseUrl = baseUrl;
        this.apiSecret = apiSecret;
        this.apiKey = apiKey;
    }

    jwtSign(path, data = '') {
        const token = sign({
            uri: path,
            nonce: uuid(),
            iat: Math.floor(Date.now() / 1000),
            exp: Math.floor(Date.now() / 1000) + 55,
            sub: this.apiKey,
            bodyHash: crypto.createHash("sha256").update(JSON.stringify(data)).digest().toString("hex")
        }, this.apiSecret, { algorithm: "RS256" });
        console.log("Generated JWT:", token);
        return token;
    }

    async req(jwt, path, data, method) {
        const config = {
            url: `${this.baseUrl}${path}`,
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-API-Key': this.apiKey,
                'Authorization': `Bearer ${jwt}`
            },
            data: data
        };

        try {
            const response = await axios(config);
            console.log(`${method} Response:`, JSON.stringify(response.data, null, 2));
            return response.data;
        } catch (error) {
            console.error(`Error in ${method}:`, error.response ? error.response.data : error);
            throw error;
        }
    }

    async fetchExchangeAccountBalances(exchangeAccountId) {
        const path = `/v1/exchange_accounts/${exchangeAccountId}`;
        return this.req(this.jwtSign(path), path, undefined, 'GET');
    }

    async transferFundsToExchangeAccount(assetId, amount, sourceVaultAccountId, destinationExchangeAccountId) {
        const path = "/v1/transactions";
        const data = {
            operation: "TRANSFER",
            assetId: assetId,
            amount: amount.toString(),
            source: { type: "VAULT_ACCOUNT", id: sourceVaultAccountId.toString() },
            destination: { type: "EXCHANGE_ACCOUNT", id: destinationExchangeAccountId }
        };
        return this.req(this.jwtSign(path, data), path, data, "POST");
    }
}

// Function to read assets from CSV file
async function readAssetsFromCSV(filePath) {
    return new Promise((resolve, reject) => {
        const results = [];
        fs.createReadStream(filePath)
            .pipe(csvParser())
            .on('data', (data) => results.push(data))
            .on('end', () => resolve(results.map(asset => ({
                AssetID: asset.assetID,
                AssetType: asset.assetType,
                FeeAssetID: asset.feeAssetID,
                fireblocksOmnibusThreshold: asset.fireblocksOmnibusThreshold,
                anyVautAbove: asset.anyVautAbove,
                coinbaseOmnibusThreshold: asset.coinbaseOmnibusThreshold,
                lowfeeSweepVaults: asset.lowfeeSweepVaults,
                lowfeeSweepEnabled: asset.lowfeeSweepEnabled === "TRUE"
            }))))
            .on('error', reject);
    });
}

// Function to sweep funds to Coinbase
async function sweepFundsToCoinbase(handler, assets) {
    const exchangeBalances = await handler.fetchExchangeAccountBalances(coinbaseExchangeID);
    for (const asset of assets) {
        const assetBalance = exchangeBalances.assets.find(exBalance => exBalance.id === asset.AssetID);
        if (assetBalance && parseFloat(assetBalance.balance) < parseFloat(asset.coinbaseOmnibusThreshold)) {
            const amountToTransfer = parseFloat(asset.coinbaseOmnibusThreshold) - parseFloat(assetBalance.balance);
            console.log(`Transferring ${amountToTransfer} of ${asset.AssetID} to Coinbase...`);
            await handler.transferFundsToExchangeAccount(asset.AssetID, amountToTransfer, omniBusVaultID, coinbaseExchangeID);
        }
    }
}

(async () => {
    try {
        const handler = new FireblocksRequestHandler(apiSecret, apiKey, baseUrl);
        const assets = await readAssetsFromCSV('./sweep-testnet.csv');
        await sweepFundsToCoinbase(handler, assets);
    } catch (error) {
        console.error(`Unhandled error:`, error);
        process.exit(-1);
    }
})();
