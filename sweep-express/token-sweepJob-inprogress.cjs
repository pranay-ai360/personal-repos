const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { sign } = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');
const { exit } = require('process');
const { inspect } = require('util');
const csvParser = require('csv-parser');
const { estimateGasFees } = require('./fees-estimate.cjs');

// API Credentials and Initialization
const apiSecretPath = "./fb.key";

const apiSecret = fs.readFileSync(path.resolve(apiSecretPath), "utf8");
const apiKey = "68937138-8c6a-826d-88d7-f843d981927a";
const baseUrl = "https://api.fireblocks.io";

const omniBusVaultID = 3;
const gasStationVaultID = 232613;
const coinbaseExchangeID = '8a19f86c-25b9-f2d7-924a-dd6667d3b0e2';
const assetsPayload = await readAssetsFromCSV('./sweep-testnet.csv'); // Adjusted file path


// Read assets from CSV file
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
                threshold: asset.fireblocksOmnibusThreshold,
                anyvaultAbove: asset.anyVautAbove,
            }))))
            .on('error', reject);
    });
}

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
            console.error(`Error in ${method}:`, inspect(error.response ? error.response.data : error));
            throw error;
        }
    }

    async fetchVaultAccountDetails(vaultAccountId) {
        return this.req(this.jwtSign(`/v1/vault/accounts/${vaultAccountId}`), `/v1/vault/accounts/${vaultAccountId}`, undefined, 'get');
    }

    async fetchVaultAssetWallets(assetDetails) {
        const queryParams = new URLSearchParams({
            totalAmountLargerThan: parseFloat(assetDetails.anyvaultAbove),
            assetId: assetDetails.AssetID,
            orderBy: 'DESC',
            limit: 500
        }).toString();
        return this.req(this.jwtSign(`/v1/vault/asset_wallets?${queryParams}`), `/v1/vault/asset_wallets?${queryParams}`, undefined, 'get');
    }

    async transferFunds(sourceId, destinationId, assetId, amount) {
        const path = "/v1/transactions";
        const data = {
            operation: "TRANSFER",
            source: { type: "VAULT_ACCOUNT", id: sourceId.toString() },
            destination: { type: "VAULT_ACCOUNT", id: destinationId.toString() },
            assetId: assetId,
            amount: amount
        };
        return this.req(this.jwtSign(path, data), path, data, "POST");
    }
    
    async fetchTransactionStatus(transactionId) {
        return this.req(this.jwtSign(`/v1/transactions/${transactionId}`), `/v1/transactions/${transactionId}`, undefined, 'get');
    }

    async waitForTransactionCompletion(transactionId, maxAttempts = 20, interval = 10000) {
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            console.log(`Checking status for transaction ID: ${transactionId}, attempt ${attempt}`);
            const statusResponse = await this.fetchTransactionStatus(transactionId);
            console.log(`Transaction status: ${statusResponse.status}`);
            if (statusResponse.status === 'COMPLETED' || statusResponse.status === 'FAILED') {
                return statusResponse;
            }
            await new Promise(resolve => setTimeout(resolve, interval));
        }
        throw new Error('Transaction status check exceeded maximum attempts without completion.');
    }
}

// Remaining functions and processing logic as previously defined...

(async () => {
    try {
        await processAssets(assetsPayload);
    } catch (error) {
        console.error(`Unhandled error:`, error);
        exit(-1);
    }
})();
