// fees-estimate.cjs
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { sign } = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');

// API Credentials and Initialization
const apiSecretPath = "./fb.key";
const apiSecret = fs.readFileSync(path.resolve(apiSecretPath), "utf8");
const apiKey = "68937138-8c6a-826d-88d7-f843d981927a";
const baseUrl = "https://api.fireblocks.io";

class FireblocksRequestHandler {
    baseUrl;
    apiSecret;
    apiKey;

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
        return token;
    }

    async estimateGasFee(operation, sourceId, destinationId, assetId) {
        const path = "/v1/transactions/estimate_fee";
        const data = {
            operation: operation,
            source: {
                type: "VAULT_ACCOUNT",
                id: sourceId
            },
            destination: {
                type: "VAULT_ACCOUNT",
                id: destinationId
            },
            amount: "1",
            assetId: assetId
        };
        const jwt = this.jwtSign(path, data);
        const config = {
            method: 'post',
            url: `${this.baseUrl}${path}`,
            headers: { 
                'Accept': 'application/json', 
                'X-API-Key': this.apiKey,
                'Authorization': `Bearer ${jwt}`,
                'Content-Type': 'application/json'
            },
            data: data
        };

        try {
            const response = await axios.request(config);
            return response.data;
        } catch (error) {
            console.error(`Error in estimateGasFee: ${error.response?.data}`);
            throw error;
        }
    }
}

// Function to calculate result as before
function calculateResult(baseFee, priorityFee, gasLimit) {
    const baseFeeNumeric = Number(baseFee);
    const totalFee = baseFeeNumeric + Number(priorityFee);
    const multiplied = totalFee * Number(gasLimit);
    const result = multiplied / 1e9;
    return result;
}

// Exported function
async function estimateGasFees(sourceId, destinationId, assetId) {
    const handler = new FireblocksRequestHandler(apiSecret, apiKey, baseUrl);
    try {
        const gasFeeEstimation = await handler.estimateGasFee("TRANSFER", sourceId, destinationId, assetId);
        const results = {};
        Object.keys(gasFeeEstimation).forEach(level => {
            const info = gasFeeEstimation[level];
            const result = calculateResult(info.baseFee, info.priorityFee, info.gasLimit);
            results[level] = result.toFixed(18);
        });
        
        return results;
    } catch (error) {
        console.error(`Failed to estimate fees: ${error.message}`);
        throw error;
    }
}

module.exports = { estimateGasFees };
