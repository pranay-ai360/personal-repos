package com.example.coinbasefix;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import quickfix.*;
import quickfix.field.*;
// Import specific message and group classes for FIX 5.0 SP2 from QFJ 2.0.0 structure
import quickfix.fix50sp2.MarketDataSnapshotFullRefresh;
import quickfix.fix50sp2.MarketDataIncrementalRefresh;
import quickfix.fix50sp2.MarketDataRequestReject;
import quickfix.fix50sp2.BusinessMessageReject;
import quickfix.fix50sp2.MarketDataRequest; // Still needed for creating the request

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneOffset; // Use standard Java Time API constant
import java.util.Arrays;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
import java.util.stream.Collectors;

public class CoinbaseFixClientApplication extends MessageCracker implements Application {

    private static final Logger log = LoggerFactory.getLogger(CoinbaseFixClientApplication.class);
    private final Properties config;
    private SessionID currentSessionId = null;
    private boolean marketDataRequested = false; // Flag to prevent multiple requests per session


    public CoinbaseFixClientApplication(Properties config) {
        if (config == null) {
            throw new IllegalArgumentException("Configuration properties cannot be null");
        }
        this.config = config;
    }

    @Override
    public void onCreate(SessionID sessionId) {
        log.info("Session Created: {}", sessionId);
        this.currentSessionId = sessionId;
    }

    @Override
    public void onLogon(SessionID sessionId) {
        log.info("Logon Successful: {}", sessionId);
        this.currentSessionId = sessionId;
        this.marketDataRequested = false; // Reset request flag on new logon
        sendMarketDataRequest(sessionId);
    }

    @Override
    public void onLogout(SessionID sessionId) {
        log.info("Logout: {}", sessionId);
        this.currentSessionId = null;
        this.marketDataRequested = false;
    }

    /**
     * Callback for outgoing administrative messages.
     * Handles Coinbase-specific authentication for Logon (A) messages.
     */
    @Override
    public void toAdmin(Message message, SessionID sessionId) {
        try {
            // Check if the message is a Logon message using the header MsgType
            if (MsgType.LOGON.equals(message.getHeader().getString(MsgType.FIELD))) {
                log.info("Modifying outgoing Logon message for Coinbase authentication");

                // 1. Set standard fields needed by Coinbase
                message.setInt(HeartBtInt.FIELD, 30); // Recommended Heartbeat interval
                // *** ADD EncryptMethod(98)=0 EXPLICITLY ***
                message.setInt(EncryptMethod.FIELD, 0); // 0 = None / Other
                message.setString(Password.FIELD, config.getProperty("coinbase.fix.passphrase"));
                message.setString(Username.FIELD, config.getProperty("coinbase.fix.username"));
                // *** ADD DefaultApplVerID(1137) as required by Coinbase for FIXT ***
                message.setString(DefaultApplVerID.FIELD, config.getProperty("coinbase.fix.defaultApplVerId", "9")); // Default to 9 if not in props

                // *** REMOVED dynamic check for ResetSeqNumFlag ***
                // ResetSeqNumFlag (141) should be set automatically by QuickFIX/J
                // based on the ResetOnLogon=Y setting in quickfix.cfg for QFJ 2.0.0

                // 2. Prepare for signing - retrieve necessary fields AFTER they are set
                // Ensure SendingTime is set
                if (!message.getHeader().isSetField(SendingTime.FIELD)) {
                     message.getHeader().setField(new SendingTime(LocalDateTime.now(ZoneOffset.UTC)));
                     log.warn("SendingTime was not set on Logon, setting it now for signing.");
                }
                String sendingTimeStr = message.getHeader().getString(SendingTime.FIELD);
                String msgType = message.getHeader().getString(MsgType.FIELD);
                String msgSeqNum = message.getHeader().getString(MsgSeqNum.FIELD);
                String senderCompId = message.getHeader().getString(SenderCompID.FIELD);
                String targetCompId = message.getHeader().getString(TargetCompID.FIELD);
                String password = message.getString(Password.FIELD); // Use the passphrase

                // 3. Generate Prehash String using the authenticator (now with SOH)
                String prehash = CoinbaseAuthenticator.createPrehash(sendingTimeStr, msgType, msgSeqNum,
                        senderCompId, targetCompId, password);

                // 4. Sign using HMAC-SHA256
                String secretKey = config.getProperty("coinbase.fix.secretKey");
                if (secretKey == null || secretKey.trim().isEmpty()) {
                    throw new ConfigError("Coinbase secret key (coinbase.fix.secretKey) is missing or empty.");
                }
                String signature = CoinbaseAuthenticator.sign(secretKey, prehash);

                // 5. Add signature fields to Logon message
                message.setString(RawData.FIELD, signature);
                message.setInt(RawDataLength.FIELD, signature.length());

                log.debug("Logon message modified with auth fields.");
                log.info(">>> Sending Logon (modified): {}", message.toString().replace('\u0001','|')); // Log modified message

            } else {
                 log.debug(">>> Outgoing Admin: {}", message.toString().replace('\u0001','|'));
            }
        } catch (FieldNotFound e) {
            log.error("!!! CRITICAL: Missing required field for signing Logon message ({}). Connection will likely fail.", e.field, e);
        } catch (ConfigError e) { // Catch ConfigError specifically from createPrehash or property loading
             log.error("!!! CRITICAL: Configuration error during Logon modification: {}", e.getMessage(), e);
        } catch (Exception e) { // Catch broader exceptions during signing
            log.error("!!! CRITICAL: Failed to sign Logon message. Connection will likely fail.", e);
            // Consider stopping the session or preventing send if auth fails critically
        }
    }

    /**
     * Callback for incoming administrative messages.
     */
    @Override
    public void fromAdmin(Message message, SessionID sessionId) throws FieldNotFound, IncorrectDataFormat, IncorrectTagValue, RejectLogon {
        log.info("<<< Incoming Admin: {}", message.toString().replace('\u0001','|'));
        // Optional: Handle specific admin messages like Logout with Text reason
         if (MsgType.LOGOUT.equals(message.getHeader().getString(MsgType.FIELD))) {
            if(message.isSetField(Text.FIELD)) {
                log.warn("Logout Reason from Server: {}", message.getString(Text.FIELD));
            }
             // Consider setting logged_on = false here? QuickFIX/J state machine usually handles this via onLogout.
        } else if (MsgType.LOGON.equals(message.getHeader().getString(MsgType.FIELD))) {
            // This is the confirmation we were waiting for! onLogon callback will also fire.
            log.info("Logon confirmation received from server.");
        } else if (MsgType.REJECT.equals(message.getHeader().getString(MsgType.FIELD))) {
             // Log session-level rejects
             String refSeqNum = message.isSetField(RefSeqNum.FIELD) ? message.getString(RefSeqNum.FIELD) : "N/A";
             String reason = message.isSetField(Text.FIELD) ? message.getString(Text.FIELD) : "N/A";
             String rejectCode = message.isSetField(SessionRejectReason.FIELD) ? message.getString(SessionRejectReason.FIELD) : "N/A";
             log.error("!!! Session Reject Received: RefSeqNum={}, ReasonCode={}, Reason='{}'", refSeqNum, rejectCode, reason);
         }
    }

    /**
     * Callback for outgoing application messages. Add ApplVerID if using FIXT.
     */
    @Override
    public void toApp(Message message, SessionID sessionId) throws DoNotSend {
         try {
            // *** ADD ApplVerID(1128) to application message headers if using FIXT ***
            if (FixVersions.BEGINSTRING_FIXT11.equals(sessionId.getBeginString())) {
                 message.getHeader().setString(ApplVerID.FIELD, config.getProperty("coinbase.fix.defaultApplVerId", "9"));
            }
            log.debug(">>> Outgoing App: {}", message.toString().replace('\u0001','|'));
        } catch (Exception e) {
             log.error("Error adding ApplVerID to outgoing application message", e);
             throw new DoNotSend(); // Prevent sending a potentially malformed message
        }
    }

    /**
     * Callback for incoming application messages. Routes to specific handlers via MessageCracker.
     */
    @Override
    public void fromApp(Message message, SessionID sessionId) throws FieldNotFound, IncorrectDataFormat, IncorrectTagValue, UnsupportedMessageType {
        log.info("<<< Incoming App [{}]: {}", message.getHeader().getString(MsgType.FIELD), message.toString().replace('\u0001', '|'));
        // Use MessageCracker to route messages to specific handlers (onMessage methods)
        crack(message, sessionId);
    }

    // --- Message Cracker Handlers for Application Messages ---

    /**
     * Handles Market Data Snapshot / Full Refresh (MsgType=W).
     */
    @Handler
    public void onMessage(MarketDataSnapshotFullRefresh message, SessionID sessionId) // Method name matches default convention
            throws FieldNotFound {
        String symbol = message.isSetSymbol() ? message.getSymbol().getValue() : "[No Symbol]";
        log.info("Processing Market Data Snapshot/Full Refresh (W) for Symbol: {}", symbol);

        // Process NoMDEntries repeating group
        if (message.isSetField(NoMDEntries.FIELD)) {
            int noMDEntries = message.getNoMDEntries().getValue();
            log.debug("--> Number of MD Entries: {}", noMDEntries);

            MarketDataSnapshotFullRefresh.NoMDEntries group = new MarketDataSnapshotFullRefresh.NoMDEntries();
            BigDecimal bestBid = BigDecimal.ZERO;
            BigDecimal bestAsk = BigDecimal.ZERO;
            boolean askFound = false;

            for (int i = 1; i <= noMDEntries; i++) {
                try {
                    message.getGroup(i, group); // Populate the group object

                    char entryType = group.getMDEntryType().getValue();
                    double priceDouble = group.getMDEntryPx().getValue();
                    BigDecimal price = BigDecimal.valueOf(priceDouble);
                    double sizeDouble = group.isSetMDEntrySize() ? group.getMDEntrySize().getValue() : 0.0;
                    BigDecimal size = BigDecimal.valueOf(sizeDouble);

                    switch (entryType) {
                        case MDEntryType.BID:
                            log.trace("  BID: Price={}, Size={}", price, size);
                            if (price.compareTo(bestBid) > 0) { bestBid = price; }
                            // TODO: Update local bid book
                            break;
                        case MDEntryType.OFFER:
                            log.trace("  ASK: Price={}, Size={}", price, size);
                            if (!askFound || price.compareTo(bestAsk) < 0) { bestAsk = price; askFound = true; }
                            // TODO: Update local ask book
                            break;
                        case MDEntryType.TRADE:
                            log.trace("  TRADE: Price={}, Size={}", price, size);
                            // TODO: Process trade
                            break;
                        default:
                            log.trace("  OTHER Type {}: Price={}, Size={}", entryType, price, size);
                            break;
                    }
                } catch (FieldNotFound e) {
                    log.error("Field not found within MDEntries group #{} for Snapshot message: {}", i, message, e);
                }
            }
            log.info("--> Snapshot Best Bid/Ask for {}: {} / {}", symbol, bestBid, askFound ? bestAsk : "N/A");
        } else {
            log.warn("Market Data Snapshot message received with NoMDEntries field not set for symbol {}", symbol);
        }
    }

    /**
     * Handles Market Data Incremental Refresh (MsgType=X).
     */
    @Handler
    public void onMessage(MarketDataIncrementalRefresh message, SessionID sessionId) // Method name matches default convention
             throws FieldNotFound {
        log.info("Processing Market Data Incremental Refresh (X)");

         if (message.isSetField(NoMDEntries.FIELD)) {
            int noMDEntries = message.getNoMDEntries().getValue();
            log.debug("--> Number of Incremental MD Entries: {}", noMDEntries);

            MarketDataIncrementalRefresh.NoMDEntries group = new MarketDataIncrementalRefresh.NoMDEntries();

            for (int i = 1; i <= noMDEntries; i++) {
                 try {
                     message.getGroup(i, group);
                     char updateAction = group.getMDUpdateAction().getValue(); // 0=New, 1=Change, 2=Delete
                     char entryType = group.getMDEntryType().getValue();
                     String symbol = group.isSetSymbol() ? group.getSymbol().getValue() : "[No Symbol In Group]";
                     BigDecimal price = group.isSetMDEntryPx() ? BigDecimal.valueOf(group.getMDEntryPx().getValue()) : null;
                     BigDecimal size = group.isSetMDEntrySize() ? BigDecimal.valueOf(group.getMDEntrySize().getValue()) : null;
                     String entryId = group.isSetMDEntryID() ? group.getMDEntryID().getValue() : null; // Important for updates/deletes

                     log.trace("  Action={}, Symbol={}, Type={}, Price={}, Size={}, EntryID={}",
                             updateAction, symbol, entryType, price, size, entryId);

                     // TODO: Implement logic to update local order book using Action, EntryID, etc.

                 } catch (FieldNotFound e) {
                    log.error("Field not found within Incremental MDEntries group #{} for message: {}", i, message, e);
                 }
            }
            log.warn("Incremental Refresh processing logic (order book update) is not implemented.");
         } else {
              log.warn("Market Data Incremental Refresh message received with NoMDEntries field not set.");
         }
    }

    /**
     * Handles Market Data Request Reject (MsgType=Y).
     */
    @Handler
    public void onMessage(MarketDataRequestReject message, SessionID sessionId) // Method name matches default convention
            throws FieldNotFound {
        String mdReqId = message.isSetField(MDReqID.FIELD) ? message.getMDReqID().getValue() : "[No MDReqID]";
        String rejectReasonCode = message.isSetField(MDReqRejReason.FIELD) ? String.valueOf(message.getMDReqRejReason().getValue()) : "N/A";
        String text = message.isSetField(Text.FIELD) ? message.getText().getValue() : "No additional text.";
        log.error("!!! Market Data Request Rejected (Y): MDReqID={}, ReasonCode={}, Text='{}'", mdReqId, rejectReasonCode, text);
        marketDataRequested = false; // Allow resending if appropriate
    }

     /**
      * Handles Business Message Reject (MsgType=j).
      */
     @Handler
     public void onMessage(BusinessMessageReject message, SessionID sessionId) // Method name matches default convention
             throws FieldNotFound {
        String refMsgType = message.isSetField(RefMsgType.FIELD) ? message.getRefMsgType().getValue() : "N/A";
        String refSeqNum = message.isSetField(RefSeqNum.FIELD) ? message.getString(RefSeqNum.FIELD) : "N/A";
        String rejectReasonCode = message.isSetField(BusinessRejectReason.FIELD) ? String.valueOf(message.getBusinessRejectReason().getValue()) : "N/A";
        String text = message.isSetField(Text.FIELD) ? message.getText().getValue() : "No additional text.";
        log.error("!!! Business Message Reject Received (j): RefMsgType={}, RefSeqNum={}, ReasonCode={}, Reason='{}'",
                refMsgType, refSeqNum, rejectReasonCode, text);
     }

    // --- Helper Methods ---

    /**
     * Creates and sends a MarketDataRequest message.
     */
    private void sendMarketDataRequest(SessionID sessionId) {
        if (marketDataRequested) {
            log.warn("Market data already requested for session {}, skipping.", sessionId);
            return;
        }

        log.info("Attempting to send Market Data Request...");
        try {
            String products = config.getProperty("coinbase.fix.subscribe.products", "");
            if (products.isEmpty()) {
                log.error("No products specified in coinbase.fix.subscribe.products property. Cannot send Market Data Request.");
                return;
            }

            List<String> productList = Arrays.stream(products.split(","))
                                              .map(String::trim)
                                              .filter(s -> !s.isEmpty())
                                              .collect(Collectors.toList());

            if (productList.isEmpty()) {
                log.error("Product list is empty after trimming/filtering. Cannot send Market Data Request.");
                return;
            }
            log.info("Requesting market data for products: {}", productList);

            char subscriptionType = (char) (Integer.parseInt(config.getProperty("coinbase.fix.subscribe.type", "1")) + '0');
            int marketDepth = Integer.parseInt(config.getProperty("coinbase.fix.subscribe.depth", "0"));
            char updateType = (char) (Integer.parseInt(config.getProperty("coinbase.fix.subscribe.updateType", "0")) + '0');
            String entryTypesRaw = config.getProperty("coinbase.fix.subscribe.entryTypes", "0,1");

            MarketDataRequest mdRequest = new MarketDataRequest(
                    new MDReqID(generateUUID()),
                    new SubscriptionRequestType(subscriptionType),
                    new MarketDepth(marketDepth)
            );

            mdRequest.setField(new MDUpdateType(updateType));

            if (!entryTypesRaw.isEmpty()) {
                MarketDataRequest.NoMDEntryTypes entryTypeGroup = new MarketDataRequest.NoMDEntryTypes();
                boolean addedEntry = false;
                for (String typeStr : entryTypesRaw.split(",")) {
                    String trimmedType = typeStr.trim();
                    if (!trimmedType.isEmpty()) {
                        entryTypeGroup.set(new MDEntryType(trimmedType.charAt(0)));
                        mdRequest.addGroup(entryTypeGroup);
                        addedEntry = true;
                        log.debug("Added MDEntryType: {}", trimmedType.charAt(0));
                    }
                }
                if (!addedEntry) {
                     log.warn("No valid MDEntryTypes found after parsing configuration '{}'. Request might fail.", entryTypesRaw);
                }
            } else {
                 log.warn("No MDEntryTypes specified ('coinbase.fix.subscribe.entryTypes'). Request might fail or use server defaults.");
            }

            MarketDataRequest.NoRelatedSym symbolGroup = new MarketDataRequest.NoRelatedSym();
            for(String product : productList) {
                 symbolGroup.set(new Symbol(product));
                 mdRequest.addGroup(symbolGroup);
            }

            // ApplVerID will be added by toApp callback if needed (for FIXT)

            log.info("Prepared MarketDataRequest (V). Sending...");
            Session.sendToTarget(mdRequest, sessionId);
            marketDataRequested = true; // Mark as requested for this session logon
            log.info("Market Data Request sent attempt finished."); // Confirmation is receiving data or reject

        } catch (SessionNotFound e) {
            log.error("Session [{}] not found, cannot send Market Data Request.", sessionId, e);
        } catch (NumberFormatException e) {
             log.error("Invalid number format found in market data subscription configuration properties.", e);
        } catch (Exception e) { // Catch broader exceptions during request creation/sending
            log.error("Failed to create or send Market Data Request for session [{}].", sessionId, e);
            marketDataRequested = false; // Allow retry on next logon if appropriate
        }
    }

    /**
     * Generates a unique string ID.
     */
    private String generateUUID() {
        return UUID.randomUUID().toString();
    }
} // *** END OF CoinbaseFixClientApplication CLASS ***