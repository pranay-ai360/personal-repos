

package main

import (
	"encoding/base64"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log"
	"math/big"
	"time"
	"golang.org/x/net/websocket"
	"github.com/go-redis/redis/v8"
	"context"
	"github.com/google/uuid"
	"strings"
)

const (
	URI          = "wss://ws-direct.sandbox.exchange.coinbase.com"
	SIGNATURE_PATH = "/users/self/verify"
	CHANNEL      = "level2"
	PRODUCT_IDS  = "BTC-USD"
	SMALLEST_UNIT = "0.0000001"
	PHPUSD_RATE   = 58.001
	REDIS_HOST    = "127.0.0.1"
	REDIS_PORT    = "6379"
	REDIS_DB      = 0
	REDIS_TIMEOUT = 1000000
	API_KEY = "24ab46f784d1b20db435b852086e3250"
	PASSPHRASE = "akmwnltyfgb"
	SECRET_KEY = "P8npGsgqjYbgeI7chrkVNHxASkL44hEIUyizOzVBvn7lzjeGhrGnZl3X+wgPb81S01Gg6+VTNlsa8+mIrz4YKw=="
)



// Redis client initialization
var ctx = context.Background()

var redisClient *redis.Client

func init() {
	redisClient = redis.NewClient(&redis.Options{
		Addr:     REDIS_HOST + ":" + REDIS_PORT,
		Password: "",
		DB:       REDIS_DB,
	})
	_, err := redisClient.Ping(ctx).Result()
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	fmt.Println("Connected to Redis successfully.")
}

func padBase64(s string) string {
	return s + strings.Repeat("=", (-len(s) % 4))
}

func formatDecimal(value *big.Float, decimalPlaces int) string {
	roundedValue := new(big.Float).SetPrec(uint(decimalPlaces)).Set(value)
	roundedValueString := fmt.Sprintf("%.*f", decimalPlaces, roundedValue)

	// Remove trailing zeros
	if i := len(roundedValueString) - 1; roundedValueString[i] == '0' {
		roundedValueString = roundedValueString[:i]
	}
	if i := len(roundedValueString) - 1; roundedValueString[i] == '.' {
		roundedValueString = roundedValueString[:i]
	}

	return roundedValueString
}

func generateSignature(secretKey string) (string, string, error) {
	timestamp := fmt.Sprintf("%v", time.Now().Unix())
	message := fmt.Sprintf("%vGET%v", timestamp, SIGNATURE_PATH)

	// Base64 decode the secret key
	decodedSecretKey, err := base64.StdEncoding.DecodeString(padBase64(secretKey))
	if err != nil {
		return "", "", fmt.Errorf("Error decoding secret key: %v", err)
	}

	// Generate HMAC SHA-256 signature
	h := hmac.New(sha256.New, decodedSecretKey)
	h.Write([]byte(message))
	signature := base64.StdEncoding.EncodeToString(h.Sum(nil))

	return signature, timestamp, nil
}

func generateOrderID() string {
	return "order:" + uuid.New().String()
}

func generateUUID() string {
	return uuid.New().String()
}

func mapSide(side string) string {
	sideMap := map[string]string{
		"BID": "buy",
		"ASK": "sell",
	}
	return sideMap[side]
}

func processSnapshot(message map[string]interface{}) {
	var data []map[string]interface{}
	productID := message["product_id"].(string)

	// Process asks and bids
	for _, side := range []string{"asks", "bids"} {
		entries := message[side].([]interface{})
		for _, entry := range entries {
			orderEntry := entry.([]interface{})
			priceUSD, ok := orderEntry[0].(string)
			if !ok {
				continue
			}
			quantity, ok := orderEntry[1].(string)
			if !ok {
				continue
			}

			// Convert strings to big.Float for accurate calculation
			priceUSDBig, _ := new(big.Float).SetString(priceUSD)
			quantityBig, _ := new(big.Float).SetString(quantity)
			totalPriceUSD := new(big.Float).Mul(priceUSDBig, quantityBig)

			// Calculate in PHP
			pricePHP := new(big.Float).Mul(priceUSDBig, big.NewFloat(PHPUSD_RATE))
			totalPricePHP := new(big.Float).Mul(totalPriceUSD, big.NewFloat(PHPUSD_RATE))

			orderData := map[string]interface{}{
				"pair":                       productID,
				"side":                       mapSide(side),
				"smallest_unit":              SMALLEST_UNIT,
				"price_per_base_asset_USD":   formatDecimal(priceUSDBig, 20),
				"quantity":                   formatDecimal(quantityBig, 20),
				"total_price_USD":            formatDecimal(totalPriceUSD, 20),
				"price_per_base_asset_PHP":   formatDecimal(pricePHP, 20),
				"total_price_PHP":            formatDecimal(totalPricePHP, 20),
			}
			data = append(data, orderData)

			// Redis Storage
			sortedSetKey := fmt.Sprintf("%s_%s", productID, mapSide(side))
			orderID := generateOrderID()

			// Add order to Redis sorted set
			redisClient.ZAdd(ctx, sortedSetKey, &redis.Z{
				Score:  priceUSDBig.Float64(),
				Member: orderID,
			})

			// Add order details in Redis hash
			redisClient.HSet(ctx, orderID, orderData)
		}
	}

	// Print data as JSON
	jsonData, _ := json.MarshalIndent(data, "", "    ")
	fmt.Println(string(jsonData))
}

func processL2Update(message map[string]interface{}) {
	productID := message["product_id"].(string)
	changes := message["changes"].([]interface{})

	for _, change := range changes {
		changeData := change.([]interface{})
		side := changeData[0].(string)
		priceStr := changeData[1].(string)
		newQuantityStr := changeData[2].(string)

		// Convert strings to big.Float for accurate calculation
		priceBig, _ := new(big.Float).SetString(priceStr)
		newQuantityBig, _ := new(big.Float).SetString(newQuantityStr)

		sideMapped := mapSide(side)
		sortedSetKey := fmt.Sprintf("%s_%s", productID, sideMapped)

		// Remove orders with the same price from Redis
		redisClient.ZRemRangeByScore(ctx, sortedSetKey, priceBig.Float64(), priceBig.Float64())

		// If quantity is zero, skip
		if newQuantityBig.Cmp(big.NewFloat(0)) <= 0 {
			continue
		}

		// Add new order to Redis
		orderID := generateOrderID()
		orderData := map[string]interface{}{
			"quantity":       formatDecimal(newQuantityBig, 20),
			"total_price_USD": formatDecimal(new(big.Float).Mul(priceBig, newQuantityBig), 20),
			"total_price_PHP": formatDecimal(new(big.Float).Mul(priceBig, newQuantityBig).Mul(big.NewFloat(PHPUSD_RATE), big.NewFloat(PHPUSD_RATE)), 20),
		}

		// Update Redis hash
		redisClient.HSet(ctx, orderID, orderData)

		// Print updated order
		fmt.Printf("Updated order at price %v for %s side with new quantity %v\n", priceStr, sideMapped, newQuantityStr)
	}

	// Optionally print the update as JSON
	jsonMessage, _ := json.MarshalIndent(message, "", "    ")
	fmt.Println(string(jsonMessage))
}

func websocketListener() {
	// Generate signature for the WebSocket request
	signature, timestamp, err := generateSignature("your_secret_key")
	if err != nil {
		log.Fatal(err)
	}

	// Prepare the WebSocket subscription message
	subscribeMessage := map[string]interface{}{
		"type":       "subscribe",
		"channels": []map[string]interface{}{
			{"name": CHANNEL, "product_ids": []string{PRODUCT_IDS}},
		},
		"signature": signature,
		"key":       "your_api_key",
		"passphrase": "your_passphrase",
		"timestamp": timestamp,
	}
	subscribeMessageBytes, _ := json.Marshal(subscribeMessage)

	// Establish WebSocket connection
	ws, err := websocket.Dial(URI, "", "http://localhost/")
	if err != nil {
		log.Fatal("Failed to connect to WebSocket:", err)
	}
	defer ws.Close()

	// Send the subscription message
	_, err = ws.Write(subscribeMessageBytes)
	if err != nil {
		log.Fatal("Failed to subscribe to WebSocket:", err)
	}
	fmt.Println("Subscribed to WebSocket channel.")

	// Listen for messages
	for {
		var message map[string]interface{}
		err := websocket.JSON.Receive(ws, &message)
		if err != nil {
			log.Printf("Error receiving message: %v", err)
			continue
		}

		msgType := message["type"].(string)

		if msgType == "snapshot" {
			processSnapshot(message)
		} else if msgType == "l2update" {
			processL2Update(message)
		} else {
			log.Printf("Unhandled message type: %v", msgType)
		}
	}
}

func main() {
	websocketListener()
}