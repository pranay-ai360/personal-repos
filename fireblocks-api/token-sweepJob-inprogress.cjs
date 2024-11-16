const fs = require('fs');
const path = require('path');
const axios = require('axios');
const { sign } = require('jsonwebtoken');
const { v4: uuid } = require('uuid');
const crypto = require('crypto');
const { exit } = require('process');
const { inspect } = require('util');
const { estimateGasFees } = require('./fees-estimate.cjs');
const { parse } = require('csv-parse/sync');


// API Credentials and Initialization
const apiSecretPath = "./fb.key";
const apiSecret = fs.readFileSync(path.resolve(apiSecretPath), "utf8");
const apiKey = "68937138-8c6a-826d-88d7-f843d981927a";
const baseUrl = "https://api.fireblocks.io";

const omniBusVaultID = 3;
const gasStationVaultID = 232613;

// Read and parse CSV file
function loadAssetsFromCSV(filePath) {
    const csvContent = fs.readFileSync(filePath, 'utf8');
    const assets = parse(csvContent, {
        columns: true,
        skip_empty_lines: true,
    });
    return assets.map(asset => ({
        AssetID: asset.assetID,
        AssetType: asset.assetType,
        FeeAssetID: asset.feeAssetID,
        fireblocksOmnibusThreshold: asset.fireblocksOmnibusThreshold,
        anyvaultAbove: asset.anyVautAbove,
        // Add more fields from CSV if needed
    }));
}

const assetsPayload = loadAssetsFromCSV('./sweep-testnet.csv');


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
        const transferResponse = await this.req(this.jwtSign(path, data), path, data, "POST");
        console.log("Transfer initiated. Transaction ID:", transferResponse.id);
        return transferResponse.id;
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

async function findEligibleVaults(handler, assetDetails) {
    const eligibleVaults = await handler.fetchVaultAssetWallets(assetDetails);
    return eligibleVaults.assetWallets.filter(wallet => 
        parseFloat(wallet.available) > parseFloat(assetDetails.anyvaultAbove) &&
        ![omniBusVaultID.toString(), gasStationVaultID.toString()].includes(wallet.vaultId)
    );
}

async function processAssets(assets) {
    const handler = new FireblocksRequestHandler(apiSecret, apiKey, baseUrl);

    for (let assetDetails of assets) {
        console.log(`Processing ${assetDetails.AssetID}...`);

        const omniBusBalance = await fetchSingleVaultBalance(handler, omniBusVaultID, assetDetails.AssetID);
        console.log(`OmniBus Vault Balance for ${assetDetails.AssetID}:`, omniBusBalance);

        if (omniBusBalance < parseFloat(assetDetails.threshold)) {
            const eligibleVaults = await findEligibleVaults(handler, assetDetails);

            if (eligibleVaults.length > 0) {
                console.log(`Found eligible vaults for top-up:`, eligibleVaults.map(v => `Vault ID: ${v.vaultId}, Available: ${v.available}`));
                const firstEligibleVaultId = eligibleVaults[0].vaultId;

                // Fetch the balance of the FeeAssetID in the first eligible vault
                const firstEligibleVaultBalance = await fetchSingleVaultBalance(handler, firstEligibleVaultId, assetDetails.FeeAssetID);

                // Estimate gas fees
                const gasFeeEstimates = await estimateGasFees(omniBusVaultID.toString(), firstEligibleVaultId, assetDetails.FeeAssetID);
                console.log(`Gas fee estimates:`, gasFeeEstimates);

                if (firstEligibleVaultBalance < parseFloat(gasFeeEstimates.medium)) {
                    console.log(`The balance of Vault ID: ${firstEligibleVaultId} is less than the estimated medium gas fee. Initiating transfer from Gas Station.`);

                    // Transfer gas fees from the gas station vault to the first eligible vault
                    const gasFeeTransferAmount = gasFeeEstimates.medium;
                    const gasFeeTransactionId = await handler.transferFunds(gasStationVaultID.toString(), firstEligibleVaultId, assetDetails.FeeAssetID, gasFeeTransferAmount);
                    console.log(`Gas fee transfer initiated. Transaction ID: ${gasFeeTransactionId}`);

                    const gasFeeTransferStatus = await handler.waitForTransactionCompletion(gasFeeTransactionId);
                    console.log(`Gas fee transfer status:`, gasFeeTransferStatus.status);

                    if (gasFeeTransferStatus.status === 'COMPLETED') {
                        console.log(`Gas fee transfer completed successfully. Initiating asset transfer from the first eligible vault to the OmniBus vault.`);

                        // Assuming you want to transfer the original asset from the first eligible vault back to the OmniBus vault
                        const assetTransferAmount = eligibleVaults[0].available;; // Define how much you want to transfer
                        const assetTransactionId = await handler.transferFunds(firstEligibleVaultId, omniBusVaultID.toString(), assetDetails.AssetID, assetTransferAmount);
                        console.log(`Asset transfer initiated. Transaction ID: ${assetTransactionId}`);
                                        // Start the process again once transaction is completed or failed
                        await processAssets(assets);
                        return;

                        // Optionally wait for transaction to complete and log the status
                        // const assetTransferStatus = await handler.waitForTransactionCompletion(assetTransactionId);
                        // console.log(`Asset transfer status:`, assetTransferStatus.status);
                    } else {
                        console.log(`Gas fee transfer did not complete successfully. Asset transfer is not initiated.`);
                    }
                } else {
                    console.log(`No need to transfer gas fees. The balance of Vault ID: ${firstEligibleVaultId} is adequate.`);
                }

                return;
            } else {
                console.log(`No eligible vaults found with available balance above ${assetDetails.anyvaultAbove} for asset ${assetDetails.AssetID}.`);
            }
        } else {
            console.log(`Adequate balance in OmniBus vault for ${assetDetails.AssetID}. No top-up required.`);
        }
    }
}

(async () => {
    try {
        await processAssets(assetsPayload);
    } catch (error) {
        console.error(`Unhandled error:`, error);
        exit(-1);
    }
})();