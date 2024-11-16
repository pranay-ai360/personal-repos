const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { sign } = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');
const { exit } = require('process');
const { inspect } = require('util');

// API Credentials and Initialization
const apiSecretPath = "./fb.key";
const apiSecret = fs.readFileSync(path.resolve(apiSecretPath), "utf8");
const apiKey = "68937138-8c6a-826d-88d7-f843d981927a";
const baseUrl = "https://api.fireblocks.io";

const omniBusVaultID = 3;
const gasStationVaultID = 232613;

// JSON payload of assets
const assetsPayload = [
    {
        AssetID: "ETH_TEST5",
        AssetType: "Coin",
        FeeAssetID: null,
        threshold: '7',
        anyvaultAbove: '0.1',
    }
    // Additional assets can be added here as needed.
];

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

    async fetchVaultAssetWallets(totalAmountLargerThan, assetId, orderBy = 'DESC', limit = 500) {
        const queryParams = new URLSearchParams({ totalAmountLargerThan, assetId, orderBy, limit }).toString();
        return this.req(this.jwtSign(`/v1/vault/asset_wallets?${queryParams}`), `/v1/vault/asset_wallets?${queryParams}`, undefined, 'get');
    }

    async transferFunds(sourceId, destinationId, assetId, amount) {
        const path = "/v1/transactions";
        const data = {
            operation: "TRANSFER",
            source: { type: "VAULT_ACCOUNT", id: sourceId.toString() }, // Ensure ID is a string
            destination: { type: "VAULT_ACCOUNT", id: destinationId.toString() }, // Ensure ID is a string
            assetId: assetId,
            amount: amount
        };
        const transferResponse = await this.req(this.jwtSign(path, data), path, data, "POST");
        console.log("Transfer initiated. Transaction ID:", transferResponse.id);
        return transferResponse.id; // Returning the transaction ID for status check
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

async function fetchSingleVaultBalance(handler, vaultID, assetID) {
    const vaultDetails = await handler.fetchVaultAccountDetails(vaultID);
    const assetDetails = vaultDetails.assets.find(asset => asset.id === assetID);
    return assetDetails ? parseFloat(assetDetails.balance) : null;
}

async function processAssets(assets) {
    const handler = new FireblocksRequestHandler(apiSecret, apiKey, baseUrl);

    for (let assetDetails of assets) {
        console.log(`Processing ${assetDetails.AssetID}...`);

        const omniBusBalance = await fetchSingleVaultBalance(handler, omniBusVaultID, assetDetails.AssetID);
        console.log(`OmniBus Vault Balance for ${assetDetails.AssetID}:`, omniBusBalance);

        if (omniBusBalance < parseFloat(assetDetails.threshold)) {
            console.log(`Checking for vaults with balance above ${assetDetails.anyvaultAbove} for asset ${assetDetails.AssetID}.`);
            const walletsResponse = await handler.fetchVaultAssetWallets(parseFloat(assetDetails.anyvaultAbove), assetDetails.AssetID);
            const eligibleVaults = walletsResponse.assetWallets.filter(wallet => 
                parseFloat(wallet.available) > parseFloat(assetDetails.anyvaultAbove) &&
                ![omniBusVaultID.toString(), gasStationVaultID.toString()].includes(wallet.vaultId)
            );

            if (eligibleVaults.length > 0) {
                console.log(`Found eligible vaults for top-up:`, eligibleVaults.map(v => `Vault ID: ${v.vaultId}, Available: ${v.available}`));
                const firstEligibleVaultId = eligibleVaults[0].vaultId;
                const transferAmount = eligibleVaults[0].available; // Adjust this based on your criteria
                const transactionId = await handler.transferFunds(firstEligibleVaultId, omniBusVaultID, assetDetails.AssetID, transferAmount);
                // Waiting for transaction completion
                const finalStatus = await handler.waitForTransactionCompletion(transactionId);
                console.log("Final Transaction Status:", JSON.stringify(finalStatus, null, 2));
                
                // Start the process again once transaction is completed or failed
                await processAssets(assets);
                return;
            } else {
                console.log(`No eligible vaults found with available balance above ${assetDetails.anyvaultAbove} for asset ${assetDetails.AssetID}.`);
            }
        } else {
            console.log(`Adequate balance in OmniBus vault for ${assetDetails.AssetID}. No top-up required.`);
        }
    }
}

// Execute the processing for the provided JSON payload
(async () => {
    try {
        await processAssets(assetsPayload);
    } catch (error) {
        console.error(`Unhandled error: ${inspect(error)}`);
        exit(-1);
    }
})();
