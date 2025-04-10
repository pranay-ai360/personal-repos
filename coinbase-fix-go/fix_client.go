package main

import (
	// "bytes" // Often not needed directly
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"

	// --- CORRECTED IMPORTS for v0.9.x Modular Ecosystem ---
	"github.com/quickfixgo/quickfix"
	"github.com/quickfixgo/quickfix/config"
	// Import the necessary utility and version packages
	"github.com/quickfixgo/enum"  // Although not explicitly used below, good practice if needed
	"github.com/quickfixgo/field" // For field types and helpers
	"github.com/quickfixgo/tag"   // For tag constants
	// Import specific FIX version packages needed for constants/routes if used
	"github.com/quickfixgo/fix50sp2"
	"github.com/quickfixgo/fixt11"
	// --- END CORRECTED IMPORTS ---
)

// --- Configuration Reading ---
// ... (Remains the same) ...
var (
	fixVersion       string
	defaultApplVerID string
	svcAccountID     string // SenderCompID
	targetCompID     string
	apiKey           string // Username(553)
	passphrase       string // Password(554)
	apiSecret        string // RawData(96) signing secret
	fixHost          string
	fixPort          string
	logPath          string
	sessionPath      string
)

// --- Custom Tags ---
// Use tag.Tag type for definition
const (
	tagUsername           tag.Tag = 553 // Use tag.Tag type from imported package
	tagPassword           tag.Tag = 554
	tagDefaultApplVerID   tag.Tag = 1137
	tagApplVerID          tag.Tag = 1128
	tagMDReqRejReason     tag.Tag = 281
	tagSecurityReqID      tag.Tag = 320
	tagSecurityStatusReqID tag.Tag = 324
)

// MarketDataApp implements the quickfix.Application interface
// NO quickfix.NullApplication embedding
type MarketDataApp struct {
	apiKey     string
	passphrase string
	apiSecret  string
	sessionID  quickfix.SessionID
	isLoggedOn bool
	wg         sync.WaitGroup
	logonMutex sync.Mutex
	stopChan   chan struct{}
}

// Implement ALL Application interface methods explicitly

func NewMarketDataApp(apiKey, passphrase, apiSecret string) *MarketDataApp {
	return &MarketDataApp{
		apiKey:     apiKey,
		passphrase: passphrase,
		apiSecret:  apiSecret,
		stopChan:   make(chan struct{}),
	}
}

func (a *MarketDataApp) OnCreate(sessionID quickfix.SessionID) {
	log.Printf("Session created: %s\n", sessionID)
	a.sessionID = sessionID
}

func (a *MarketDataApp) OnLogon(sessionID quickfix.SessionID) {
	a.logonMutex.Lock()
	a.isLoggedOn = true
	a.logonMutex.Unlock()
	log.Printf("Logon successful: %s\n", sessionID)
	a.wg.Add(1)
	go a.sendRequestsSequence()
}

func (a *MarketDataApp) OnLogout(sessionID quickfix.SessionID) {
	a.logonMutex.Lock()
	a.isLoggedOn = false
	a.logonMutex.Unlock()
	log.Printf("Logout: %s\n", sessionID)
	close(a.stopChan)
}

func (a *MarketDataApp) ToAdmin(msg *quickfix.Message, sessionID quickfix.SessionID) {
	// Use constants from the imported 'tag' package
	msgType, err := msg.Header.GetString(tag.MsgType) // Use tag.MsgType
	if err != nil {
		log.Printf("!!! Error getting MsgType from Admin message header: %v\n", err)
		return
	}

	// Use constants from imported FIX version packages (e.g., fixt11)
	if msgType == string(fixt11.MsgType_Logon) { // 'A'
		// Use tag constants and field helpers from imported 'field' package
		msg.Body.SetField(tag.EncryptMethod, field.NewInt(0))
		msg.Body.SetField(tag.HeartBtInt, field.NewInt(30))
		msg.Body.SetField(tag.ResetSeqNumFlag, field.NewBool(true)) // Use field helper

		// Use custom tags and field helpers
		msg.Body.SetField(tagUsername, field.NewString(a.apiKey))
		msg.Body.SetField(tagPassword, field.NewString(a.passphrase))

		// Use BeginString constant from quickfix package
		if fixVersion == quickfix.BeginStringFIXT11 {
			// Use custom tag and field helper
			msg.Body.SetField(tagDefaultApplVerID, field.NewString(defaultApplVerID))
		}

		// Generate signature - use tag constants
		sendingTimeField := field.FIXString("") // Use field types
		msgSeqNumField := field.FIXString("")
		senderCompIDField := field.FIXString("")
		targetCompIDField := field.FIXString("")
		passwordField := field.FIXString("")

		err = msg.Header.GetField(tag.SendingTime, &sendingTimeField) // Use tag.SendingTime
		if err != nil { log.Printf("!!! Error getting SendingTime: %v\n", err); return }
		err = msg.Header.GetField(tag.MsgSeqNum, &msgSeqNumField)      // Use tag.MsgSeqNum
		if err != nil { log.Printf("!!! Error getting MsgSeqNum: %v\n", err); return }
		err = msg.Header.GetField(tag.SenderCompID, &senderCompIDField) // Use tag.SenderCompID
		if err != nil { log.Printf("!!! Error getting SenderCompID: %v\n", err); return }
		err = msg.Header.GetField(tag.TargetCompID, &targetCompIDField) // Use tag.TargetCompID
		if err != nil { log.Printf("!!! Error getting TargetCompID: %v\n", err); return }
		// Use custom tag
		err = msg.Body.GetField(tagPassword, &passwordField)
		if err != nil { log.Printf("!!! Error getting Password: %v\n", err); return }

		rawData := a.sign(
			string(sendingTimeField),
			msgType,
			string(msgSeqNumField),
			string(senderCompIDField),
			string(targetCompIDField),
			string(passwordField),
		)

		// Use tag constants and field helpers
		msg.Body.SetField(tag.RawDataLength, field.NewInt(len(rawData)))
		msg.Body.SetField(tag.RawData, field.NewString(rawData))

		log.Printf(">>> Sending Logon (ToAdmin - Modified):\n%s\n", formatFixMessage(msg))
	} else {
		log.Printf(">>> Admin Out:\n%s\n", formatFixMessage(msg))
	}
}

func (a *MarketDataApp) FromAdmin(msg *quickfix.Message, sessionID quickfix.SessionID) quickfix.MessageRejectError {
	log.Printf("<<< Admin In:\n%s\n", formatFixMessage(msg))

	msgType, err := msg.Header.GetString(tag.MsgType) // Use tag.MsgType
	// Use constant from fixt11 package
	if err == nil && msgType == string(fixt11.MsgType_Logout) { // '5'
		textField := field.FIXString("") // Use field type
		if err := msg.Body.GetField(tag.Text, &textField); err == nil { // Use tag.Text
			log.Printf("    Logout Reason: %s\n", textField)
		}
	}
	return nil
}

func (a *MarketDataApp) ToApp(msg *quickfix.Message, sessionID quickfix.SessionID) error {
	// Use BeginString constant from quickfix package
	if fixVersion == quickfix.BeginStringFIXT11 {
		// Use custom tag and field helper
		msg.Header.SetField(tagApplVerID, field.NewString(defaultApplVerID))
	}
	log.Printf(">>> App Out:\n%s\n", formatFixMessage(msg))
	return nil
}

func (a *MarketDataApp) FromApp(msg *quickfix.Message, sessionID quickfix.SessionID) quickfix.MessageRejectError {
	msgType, err := msg.Header.GetString(tag.MsgType) // Use tag.MsgType
	if err != nil {
		log.Printf("<<< App In (Unknown Type):\n%s\n", formatFixMessage(msg))
		return nil
	}

	log.Printf("<<< App In (%s):\n%s\n", msgType, formatFixMessage(msg))

	// Use constants from fix50sp2 package
	switch msgType {
	case string(fix50sp2.MsgType_MarketDataRequestReject): // 'Y'
		mdRejReasonField := field.FIXString("") // Use field type
		textField := field.FIXString("")
		// Use custom tag
		if err := msg.Body.GetField(tagMDReqRejReason, &mdRejReasonField); err == nil {
			log.Printf("    MD Reject Reason Code: %s\n", mdRejReasonField)
		}
		if err := msg.Body.GetField(tag.Text, &textField); err == nil { // Use tag.Text
			log.Printf("    MD Reject Text: %s\n", textField)
		}
	case string(fix50sp2.MsgType_BusinessMessageReject): // 'j'
		bizRejReasonField := field.FIXInt(0) // Use field type
		textField := field.FIXString("")
		if err := msg.Body.GetField(tag.BusinessRejectReason, &bizRejReasonField); err == nil { // Use tag.BusinessRejectReason
			log.Printf("    Business Reject Reason Code: %d\n", bizRejReasonField)
		}
		if err := msg.Body.GetField(tag.Text, &textField); err == nil { // Use tag.Text
			log.Printf("    Business Reject Text: %s\n", textField)
		}
	case string(fix50sp2.MsgType_MarketDataSnapshotFullRefresh): // 'W'
		log.Println("    Received Market Data Snapshot/Full Refresh (W)")
	case string(fix50sp2.MsgType_MarketDataIncrementalRefresh): // 'X'
		log.Println("    Received Market Data Incremental Refresh (X)")
	case string(fix50sp2.MsgType_SecurityStatus): // 'f'
		log.Println("    Received Security Status (f)")
	case string(fix50sp2.MsgType_SecurityList): // 'y'
		log.Println("    Received Security List (y)")
	}

	return nil
}

// --- Helper Methods ---

// sign method remains the same internally
func (a *MarketDataApp) sign(sendingTime, msgType, seqNum, senderComp, targetComp, password string) string {
	// ... (implementation is correct) ...
	messageData := fmt.Sprintf("%s\x01%s\x01%s\x01%s\x01%s\x01%s",
		sendingTime, msgType, seqNum, senderComp, targetComp, password)
	secretBytes, err := base64.StdEncoding.DecodeString(a.apiSecret)
	if err != nil { log.Printf("!!! Error decoding API Secret: %v\n", err); return "" }
	mac := hmac.New(sha256.New, secretBytes)
	mac.Write([]byte(messageData))
	signatureBytes := mac.Sum(nil)
	return base64.StdEncoding.EncodeToString(signatureBytes)
}


func (a *MarketDataApp) IsLoggedOn() bool {
	// ... (implementation is correct) ...
	a.logonMutex.Lock()
	defer a.logonMutex.Unlock()
	return a.isLoggedOn
}

func (a *MarketDataApp) sendMessage(msg *quickfix.Message) bool {
	// ... (implementation is correct) ...
	a.logonMutex.Lock()
	loggedIn := a.isLoggedOn
	sessID := a.sessionID
	a.logonMutex.Unlock()
	if loggedIn && sessID.BeginString != "" {
		err := quickfix.SendToTarget(msg, sessID)
		if err != nil { log.Printf("!!! Error sending message: %v\n", err); return false }
		return true
	}
	log.Println("!!! Cannot send message: Not logged on or no sessionID.")
	return false
}


// sendRequestsSequence method remains the same internally
func (a *MarketDataApp) sendRequestsSequence() {
	// ... (implementation is correct) ...
	defer a.wg.Done()
	select { case <-time.After(1 * time.Second): case <-a.stopChan: return }
	if !a.IsLoggedOn() { return }
	a.sendMarketDataRequest("BTC-USD")
	select { case <-time.After(2 * time.Second): case <-a.stopChan: return }
	log.Println("Initial requests sent.")
}

func (a *MarketDataApp) sendMarketDataRequest(symbol string) {
	request := quickfix.NewMessage()
	// Use MsgType constant from fix50sp2 package
	request.Header.SetField(tag.MsgType, field.NewString(string(fix50sp2.MsgType_MarketDataRequest))) // Set as string 'V'

	// Body fields - use tag constants and field helpers
	request.Body.SetField(tag.MDReqID, field.NewString(uuid.New().String()))
	request.Body.SetField(tag.SubscriptionRequestType, field.NewString("1")) // Char as String
	request.Body.SetField(tag.MarketDepth, field.NewInt(0))
	// request.Body.SetField(tag.MDUpdateType, field.NewInt(1)) // Optional

	// --- Repeating Group: NoMDEntryTypes (267) ---
	// Use quickfix.NewRepeatingGroup and tag constants
	groupTypes := quickfix.NewRepeatingGroup(
		tag.NoMDEntryTypes,                      // Use tag constant
		quickfix.GroupElement(tag.MDEntryType), // Use tag constant
	)

	// Add elements using tag constants and field helpers
	groupTypes.Add().SetField(tag.MDEntryType, field.NewString("0")) // Bid
	groupTypes.Add().SetField(tag.MDEntryType, field.NewString("1")) // Offer

	request.Body.AddGroup(groupTypes)

	// --- Repeating Group: NoRelatedSym (146) ---
	groupSym := quickfix.NewRepeatingGroup(
		tag.NoRelatedSym,                      // Use tag constant
		quickfix.GroupElement(tag.Symbol), // Use tag constant
	)

	// Add the symbol
	symGroup := groupSym.Add()
	symGroup.SetField(tag.Symbol, field.NewString(symbol)) // Use tag constant

	request.Body.AddGroup(groupSym)

	log.Printf("--> Preparing Market Data Request for symbol: %s\n", symbol)
	a.sendMessage(request)
}


func (a *MarketDataApp) sendSecurityStatusRequest(symbol string) {
	request := quickfix.NewMessage()
	// Use MsgType constant from fix50sp2 package
	request.Header.SetField(tag.MsgType, field.NewString(string(fix50sp2.MsgType_SecurityStatusRequest))) // Set as string 'f'

	// Body fields - use custom tag and tag constants / field helpers
	request.Body.SetField(tagSecurityStatusReqID, field.NewString(uuid.New().String()))
	request.Body.SetField(tag.SubscriptionRequestType, field.NewString("0")) // Char as String

	// Instrument component block fields
	request.Body.SetField(tag.Symbol, field.NewString(symbol)) // Use tag constant

	log.Printf("--> Preparing Security Status Request for symbol: %s\n", symbol)
	a.sendMessage(request)
}

func (a *MarketDataApp) sendSecurityListRequest() {
	request := quickfix.NewMessage()
	// Use MsgType constant from fix50sp2 package
	request.Header.SetField(tag.MsgType, field.NewString(string(fix50sp2.MsgType_SecurityListRequest))) // Set as string 'x'

	// Body fields - use custom tag and tag constants / field helpers
	request.Body.SetField(tagSecurityReqID, field.NewString(uuid.New().String()))
	request.Body.SetField(tag.SecurityListRequestType, field.NewInt(4)) // Use tag constant

	log.Println("--> Preparing Security List Request")
	a.sendMessage(request)
}


// formatFixMessage helper remains the same
func formatFixMessage(msg *quickfix.Message) string {
	 return strings.ReplaceAll(msg.String(), "\x01", "|")
}


// --- Main Execution ---
func main() {
	// --- Configuration Reading (remains the same) ---
	// ... (elided for brevity) ...
	fixVersion = os.Getenv("FIX_VERSION")
	if fixVersion == "" { fixVersion = "FIXT.1.1" }
	defaultApplVerID = os.Getenv("DEFAULT_APPL_VER_ID")
	if defaultApplVerID == "" { defaultApplVerID = "9" }
	svcAccountID = os.Getenv("SVC_ACCOUNTID")
	targetCompID = os.Getenv("TARGET_COMP_ID")
	if targetCompID == "" { targetCompID = "Coinbase" }
	apiKey = os.Getenv("API_KEY")
	passphrase = os.Getenv("PASSPHRASE")
	apiSecret = os.Getenv("SECRET_KEY")
	fixHost = os.Getenv("FIX_HOST")
	if fixHost == "" { fixHost = "fix-md.sandbox.exchange.coinbase.com" }
	fixPort = os.Getenv("FIX_PORT")
	if fixPort == "" { fixPort = "6121" }
	logPath = os.Getenv("LOG_PATH")
	if logPath == "" { logPath = "./Logs/" }
	sessionPath = os.Getenv("SESSION_PATH")
	if sessionPath == "" { sessionPath = "./.sessions/" }

	if svcAccountID == "" || apiKey == "" || passphrase == "" || apiSecret == "" {
		log.Fatalln("Error: Missing required environment variables...")
	}
	if svcAccountID != apiKey { log.Println("Warning: SVC_ACCOUNTID (SenderCompID) and API_KEY (Username) are different.") }
	if err := os.MkdirAll(logPath, 0755); err != nil { log.Fatalf("Error creating LogPath directory %s: %v\n", logPath, err) }
	if err := os.MkdirAll(sessionPath, 0755); err != nil { log.Fatalf("Error creating SessionPath directory %s: %v\n", sessionPath, err) }


	// --- Session Configuration String (remains the same structure) ---
	// ... (elided for brevity) ...
	sessionConfig := fmt.Sprintf(`
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
ReconnectInterval=10
ValidateUserDefinedFields=N
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SocketConnectPort=%s
FileLogPath=%s
HeartBtInt=30
SocketConnectHost=%s
FileStorePath=%s
SSLEnable=Y
SSLProtocol=TlsV1.2

[SESSION]
BeginString=%s
SenderCompID=%s
TargetCompID=%s
`, fixPort, filepath.Clean(logPath),
		fixHost, filepath.Clean(sessionPath),
		fixVersion, svcAccountID, targetCompID)


	log.Println("--- FIX Client Configuration ---")
	// ... (logging config remains the same) ...
	log.Println("--------------------------------")

	cfg, err := quickfix.ParseSettings(strings.NewReader(sessionConfig))
	if err != nil { log.Fatalf("Error parsing settings: %v\n", err) }

	app := NewMarketDataApp(apiKey, passphrase, apiSecret)

	// *** USE FACTORIES FROM MAIN quickfix PACKAGE (as per v0.9.x) ***
	fileStoreFactory, err := quickfix.NewFileStoreFactory(cfg)
	if err != nil { log.Fatalf("Error creating FileStoreFactory: %v\n", err) }
	fileLogFactory, err := quickfix.NewFileLogFactory(cfg)
	if err != nil { log.Fatalf("Error creating FileLogFactory: %v\n", err) }
	// *** END CORRECTION ***

	initiator, err := quickfix.NewInitiator(app, fileStoreFactory, cfg, fileLogFactory)
	if err != nil { log.Fatalf("Error creating initiator: %v\n", err) }

	// --- Signal Handling (remains the same) ---
	// ... (elided for brevity) ...
	interruptChan := make(chan os.Signal, 1)
	signal.Notify(interruptChan, os.Interrupt, syscall.SIGTERM)


	// --- Start Initiator (remains the same) ---
	// ... (elided for brevity) ...
	err = initiator.Start()
	if err != nil { log.Fatalf("Error starting initiator: %v\n", err) }
	log.Println("Initiator started. Waiting for logon...")


	// --- Wait for Logon or Timeout (remains the same structure) ---
	// ... (elided for brevity) ...
	logonTimeout := 30 * time.Second
	logonTimer := time.NewTimer(logonTimeout)
	defer logonTimer.Stop()
	logonCompleteChan := make(chan struct{})
	go func() { /* ... wait logic ... */
        for { if app.IsLoggedOn() { close(logonCompleteChan); return }; select { case <-time.After(500 * time.Millisecond): continue; case <-app.stopChan: log.Println("Logon check aborted"); return } }
    }()
	select {
	case <-logonCompleteChan: log.Println("Logon confirmed.")
	case <-logonTimer.C: log.Println("Logon timed out."); initiator.Stop(); <-time.After(2*time.Second); os.Exit(1)
	case sig := <-interruptChan: log.Printf("Signal %v during logon wait\n", sig); initiator.Stop(); app.wg.Wait(); log.Println("Exiting."); os.Exit(0)
	}


	// --- Main Loop (Wait for shutdown signal) (remains the same) ---
	// ... (elided for brevity) ...
	log.Println("Client running. Press Ctrl+C to exit.")
	sig := <-interruptChan
	log.Printf("\nReceived signal %v, shutting down...\n", sig)
	select { case <-app.stopChan: default: close(app.stopChan) }
	initiator.Stop()
	app.wg.Wait()
	log.Println("Initiator stopped. Exiting.")

}