#!/usr/bin/env python3
"""
A minimal FIX client that:
  - Reads configuration values from OS environment variables.
  - Writes a temporary QuickFIX config file modeled after your example.config,
    with data dictionary validation disabled (usedatadictionary = N) to avoid
    data dictionary parsing errors.
  - Sends a series of FIX requests in sequence:
      Logon (35=A)         [handled by QuickFIX on session start]
      Market Data Request (35=V)
      Security Status Request (35=f)
      Security List Request (35=x)
  - Listens for full market data (35=W), incremental refresh (35=X), # Note: Coinbase uses W for snapshot AND V for subsequent updates
    security status (35=f), and security list (35=y) messages.

Reference:
https://docs.cdp.coinbase.com/exchange/docs/fix-msg-market-data
https://docs.cdp.coinbase.com/exchange/docs/fix-api-authentication
"""

import os
import quickfix as fix
import uuid
import time
import tempfile
import hashlib
import hmac
import base64
import signal # Import signal for cleaner shutdown handling
import sys

# --- Configuration Reading ---
FIX_VERSION = os.environ.get("FIX_VERSION", "FIXT.1.1")
DEFAULT_APPL_VER_ID = os.environ.get("DEFAULT_APPL_VER_ID", "9") # FIX 5.0 SP2
SVC_ACCOUNTID = os.environ.get("SVC_ACCOUNTID") # API Key used as SenderCompID
TARGET_COMP_ID = os.environ.get("TARGET_COMP_ID", "Coinbase")
API_KEY = os.environ.get("API_KEY")
PASSPHRASE = os.environ.get("PASSPHRASE")
API_SECRET = os.environ.get("SECRET_KEY") # Renamed from SECRET_KEY for clarity
FIX_HOST = os.environ.get("FIX_HOST", "fix-md.sandbox.exchange.coinbase.com")
FIX_PORT = os.environ.get("FIX_PORT", "6121")
LOG_PATH = os.environ.get("LOG_PATH", "./Logs/")
SESSION_PATH = os.environ.get("SESSION_PATH", "./.sessions/")

# --- Input Validation ---
if not all([SVC_ACCOUNTID, API_KEY, PASSPHRASE, API_SECRET]):
    print("Error: Missing required environment variables:")
    print("  - SVC_ACCOUNTID (or API_KEY used as SenderCompID)")
    print("  - API_KEY (Username/553)")
    print("  - PASSPHRASE (Password/554)")
    print("  - SECRET_KEY (for signing Logon)")
    sys.exit(1)

if SVC_ACCOUNTID != API_KEY:
     print("Warning: SVC_ACCOUNTID (SenderCompID) and API_KEY (Username) are different. Ensure this is intended.")

# Ensure log and session directories exist
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)

# --- Session Configuration ---
# Note: UseDataDictionary=N means we must build messages manually using tags
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
ReconnectInterval=10
ValidateUserDefinedFields=N
CancelOnDisconnect=N
CancelOrdersOnDisconnect=Y # Usually for trading sessions, maybe irrelevant for MD
ValidateIncomingMessage=N # Set to N if you encounter validation issues without dict
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
# SSLCheckCertificate=Y # Recommended for production
# SSLCAFile=/path/to/your/ca/bundle.crt # Specify CA if needed and not using system default
SocketConnectPort={FIX_PORT}
FileLogPath={LOG_PATH}

[SESSION]
BeginString={FIX_VERSION}
DefaultApplVerID={DEFAULT_APPL_VER_ID}
SenderCompID={SVC_ACCOUNTID}
TargetCompID={TARGET_COMP_ID}
HeartBtInt=30
SocketConnectHost={FIX_HOST}
FileStorePath={SESSION_PATH}
"""

# --- Tag Number Constants ---
# It's good practice to define constants for tags when not using a dictionary
# Header
TAG_BEGIN_STRING = 8
TAG_MSG_TYPE = 35
# Logon (relevant for signing)
TAG_SENDING_TIME = 52
TAG_MSG_SEQ_NUM = 34
TAG_SENDER_COMP_ID = 49
TAG_TARGET_COMP_ID = 56
TAG_USERNAME = 553
TAG_PASSWORD = 554
TAG_RAW_DATA_LENGTH = 95
TAG_RAW_DATA = 96
TAG_ENCRYPT_METHOD = 98
TAG_HEART_BT_INT = 108
TAG_RESET_SEQ_NUM_FLAG = 141
TAG_DEFAULT_APPL_VER_ID = 1137
# Market Data Request
TAG_MD_REQ_ID = 262
TAG_SUBSCRIPTION_REQUEST_TYPE = 263
TAG_MARKET_DEPTH = 264
TAG_MD_UPDATE_TYPE = 265
TAG_NO_MD_ENTRY_TYPES = 267
TAG_MD_ENTRY_TYPE = 269
TAG_NO_RELATED_SYM = 146
TAG_SYMBOL = 55
# Security Status Request
TAG_SECURITY_STATUS_REQ_ID = 324
# Security List Request
TAG_SECURITY_REQ_ID = 320
TAG_SECURITY_LIST_REQUEST_TYPE = 559
# Application Message Types (as strings)
MSG_TYPE_LOGON = fix.MsgType_Logon # 'A'
MSG_TYPE_MARKET_DATA_REQUEST = fix.MsgType_MarketDataRequest # 'V'
MSG_TYPE_SECURITY_STATUS_REQUEST = fix.MsgType_SecurityStatusRequest # 'f'
MSG_TYPE_SECURITY_LIST_REQUEST = fix.MsgType_SecurityListRequest # 'x'
# Received Message Types
MSG_TYPE_MARKET_DATA_SNAPSHOT_FULL_REFRESH = fix.MsgType_MarketDataSnapshotFullRefresh # 'W'
MSG_TYPE_MARKET_DATA_INCREMENTAL_REFRESH = fix.MsgType_MarketDataIncrementalRefresh # 'X'
MSG_TYPE_SECURITY_STATUS = fix.MsgType_SecurityStatus # 'f'
MSG_TYPE_SECURITY_LIST = fix.MsgType_SecurityList # 'y'
MSG_TYPE_MARKET_DATA_REQUEST_REJECT = fix.MsgType_MarketDataRequestReject # 'Y'
MSG_TYPE_BUSINESS_MESSAGE_REJECT = fix.MsgType_BusinessMessageReject # 'j'
MSG_TYPE_LOGOUT = fix.MsgType_Logout # '5'

# Generic Fields for extraction when needed
FIELD_TEXT = fix.StringField(58)
FIELD_MD_REQ_REJ_REASON = fix.CharField(281)
FIELD_BUSINESS_REJECT_REASON = fix.IntField(380)


class MarketDataApp(fix.Application):
    def __init__(self, api_key, passphrase, api_secret):
        super().__init__()
        self.api_key = api_key
        self.passphrase = passphrase
        self.api_secret = api_secret
        self.sessionID = None
        self.logged_on = False

    def onCreate(self, sessionID):
        print(f"Session created: {sessionID}")
        self.sessionID = sessionID

    def onLogon(self, sessionID):
        print(f"Logon successful: {sessionID}")
        self.logged_on = True

    def onLogout(self, sessionID):
        print(f"Logout: {sessionID}")
        self.logged_on = False

    def toAdmin(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)

        if msgType.getValue() == MSG_TYPE_LOGON: # 'A'
            # Set required fields for Logon
            message.setField(fix.IntField(TAG_ENCRYPT_METHOD, 0)) # EncryptMethod(98)=0
            # HeartBtInt(108) should be picked from config, but can force here
            message.setField(fix.IntField(TAG_HEART_BT_INT, 30))
            # ResetSeqNumFlag(141) should be picked from config, use 'Y' for True
            message.setField(fix.CharField(TAG_RESET_SEQ_NUM_FLAG, 'Y')) # ResetSeqNumFlag(141)=Y

            # Set credentials
            message.setField(fix.StringField(TAG_USERNAME, self.api_key))      # Username(553)
            message.setField(fix.StringField(TAG_PASSWORD, self.passphrase))  # Password(554)
            # Set DefaultApplVerID (tag 1137) - required for FIXT.1.1 by Coinbase
            message.setField(fix.StringField(TAG_DEFAULT_APPL_VER_ID, DEFAULT_APPL_VER_ID))

            # Generate signature
            sending_time_field = fix.SendingTime()
            msg_seq_num_field = fix.MsgSeqNum()
            sender_comp_id_field = fix.SenderCompID()
            target_comp_id_field = fix.TargetCompID()
            # Need a generic field to extract Password value since fix.Password() is unavailable
            password_field = fix.StringField(TAG_PASSWORD)

            message.getHeader().getField(sending_time_field)
            message.getHeader().getField(msg_seq_num_field)
            message.getHeader().getField(sender_comp_id_field)
            message.getHeader().getField(target_comp_id_field)
            # Extract the Password(554) value from the message body we just added
            if message.isSetField(password_field):
                message.getField(password_field)
                password_value = password_field.getString()
            else:
                print("!!! Error: Password field not found in Logon message before signing.")
                # Handle this error appropriately, maybe don't send the message
                return # Prevent sending unsigned message

            rawData = self.sign(
                sending_time_field.getString(),
                msgType.getValue(),
                msg_seq_num_field.getString(),
                sender_comp_id_field.getString(),
                target_comp_id_field.getString(),
                password_value # Use the extracted value
            )
            message.setField(fix.IntField(TAG_RAW_DATA_LENGTH, len(rawData))) # RawDataLength(95)
            message.setField(fix.StringField(TAG_RAW_DATA, rawData))           # RawData(96)

            print(">>> Sending Logon (toAdmin - Modified):")
            print(message.toString().replace('\x01', '|'))
        else:
            print(">>> Admin Out:", message.toString().replace('\x01', '|'))

    def fromAdmin(self, message, sessionID):
        print("<<< Admin In :", message.toString().replace('\x01', '|'))
        # Optional: Check for Logout message reason
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == MSG_TYPE_LOGOUT:
             # Use pre-created generic field object for extraction
             local_field_text = fix.StringField(FIELD_TEXT.getField()) # Create local copy
             if message.isSetField(local_field_text):
                 message.getField(local_field_text)
                 print(f"    Logout Reason: {local_field_text.getValue()}")


    def toApp(self, message, sessionID):
        print(">>> App Out  :", message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()

        print(f"<<< App In ({mt}):", message.toString().replace('\x01', '|'))

        # Example: Log specific reject reasons
        if mt == MSG_TYPE_MARKET_DATA_REQUEST_REJECT: # 'Y'
             local_field_reason = fix.CharField(FIELD_MD_REQ_REJ_REASON.getField())
             local_field_text = fix.StringField(FIELD_TEXT.getField())
             if message.isSetField(local_field_reason):
                 message.getField(local_field_reason)
                 print(f"    MD Reject Reason Code: {local_field_reason.getValue()}")
             if message.isSetField(local_field_text):
                 message.getField(local_field_text)
                 print(f"    MD Reject Text: {local_field_text.getValue()}")
        elif mt == MSG_TYPE_BUSINESS_MESSAGE_REJECT: # 'j'
            local_field_reason = fix.IntField(FIELD_BUSINESS_REJECT_REASON.getField())
            local_field_text = fix.StringField(FIELD_TEXT.getField())
            if message.isSetField(local_field_reason):
                 message.getField(local_field_reason)
                 print(f"    Business Reject Reason Code: {local_field_reason.getValue()}")
            if message.isSetField(local_field_text):
                 message.getField(local_field_text)
                 print(f"    Business Reject Text: {local_field_text.getValue()}")


    def sign(self, sending_time, msg_type, seq_num, sender_comp, target_comp, password):
        """
        Generate Coinbase FIX API signature. Uses SOH delimiter.
        string = SendingTime + MsgType + MsgSeqNum + SenderCompID + TargetCompID + Password
        """
        message_data = f"{sending_time}\x01{msg_type}\x01{seq_num}\x01{sender_comp}\x01{target_comp}\x01{password}"
        secret_bytes = base64.b64decode(self.api_secret)
        hmac_digest = hmac.new(secret_bytes, message_data.encode('utf-8'), hashlib.sha256)
        signature_b64 = base64.b64encode(hmac_digest.digest()).decode('utf-8')
        # Debug prints (uncomment if needed)
        # print(f"    Signing string: [{message_data.replace(chr(1), '|')}]")
        # print(f"    Generated Signature (RawData): {signature_b64}")
        return signature_b64

    def send_message(self, message):
        """Helper function to send a message if logged on."""
        if self.logged_on and self.sessionID:
            try:
                # Add ApplVerID to the header for application messages if using FIXT
                if FIX_VERSION == "FIXT.1.1":
                     # Tag 1128 = ApplVerID
                     message.getHeader().setField(fix.StringField(1128, DEFAULT_APPL_VER_ID))

                sent = fix.Session.sendToTarget(message, self.sessionID)
                if not sent:
                    print("!!! Error sending message (sendToTarget returned false)")
                return sent
            except fix.SessionNotFound as e:
                print(f"!!! Error sending message: Session not found - {e}")
                return False
            except Exception as e:
                 print(f"!!! Unexpected error sending message: {e}")
                 return False
        else:
            print("!!! Cannot send message: Not logged on or no sessionID.")
            return False


    def sendMarketDataRequest(self, symbol):
        """
        Build and send a Market Data Request (MsgType=V) using generic fields.
        Subscribes to snapshot + updates (top of book or full book based on MarketDepth).
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_MARKET_DATA_REQUEST)) # 35=V

        # Body fields
        request.setField(fix.StringField(TAG_MD_REQ_ID, str(uuid.uuid4()))) # 262=unique_id
        request.setField(fix.CharField(TAG_SUBSCRIPTION_REQUEST_TYPE, '1'))  # 263=1 (Snapshot + Updates)
        request.setField(fix.IntField(TAG_MARKET_DEPTH, 0))                 # 264=0 (Full Book), 1 (Top of Book)
        # request.setField(fix.IntField(TAG_MD_UPDATE_TYPE, 1))             # 265=1 (Incremental Refresh) - Optional for SubReqType=1

        # --- Repeating Group: NoMDEntryTypes (267) ---
        # Specify desired MDEntryType(269) values
        group_types = fix.Group(TAG_NO_MD_ENTRY_TYPES, TAG_MD_ENTRY_TYPE) # numInGroupTag=267, firstFieldTag=269

        # 0 = Bid
        group_types.setField(fix.CharField(TAG_MD_ENTRY_TYPE, '0')) # 269=0
        request.addGroup(group_types)
        # 1 = Offer
        group_types.setField(fix.CharField(TAG_MD_ENTRY_TYPE, '1')) # 269=1
        request.addGroup(group_types)
        # 2 = Trade (Can also request trades this way)
        # group_types.setField(fix.CharField(TAG_MD_ENTRY_TYPE, '2')) # 269=2
        # request.addGroup(group_types)

        # --- Repeating Group: NoRelatedSym (146) ---
        group_sym = fix.Group(TAG_NO_RELATED_SYM, TAG_SYMBOL) # numInGroupTag=146, firstFieldTag=55

        # Add the symbol
        group_sym.setField(fix.StringField(TAG_SYMBOL, symbol)) # 55=BTC-USD
        # SecurityID(48) and SecurityIDSource(22) might be needed depending on exchange/asset class
        # group_sym.setField(fix.StringField(22, '8')) # Tag 22=SecurityIDSource
        # group_sym.setField(fix.StringField(48, symbol))    # Tag 48=SecurityID

        request.addGroup(group_sym)

        print(f"--> Preparing Market Data Request for symbol: {symbol}")
        self.send_message(request)


    def sendSecurityStatusRequest(self, symbol):
        """
        Build and send a Security Status Request (MsgType=f) using generic fields.
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_SECURITY_STATUS_REQUEST)) # 35=f

        # Body fields
        request.setField(fix.StringField(TAG_SECURITY_STATUS_REQ_ID, str(uuid.uuid4()))) # 324=unique_id
        # SubscriptionRequestType (263) '0' for Snapshot status request
        request.setField(fix.CharField(TAG_SUBSCRIPTION_REQUEST_TYPE, '0'))

        # Instrument component block fields (added directly to body for this message)
        request.setField(fix.StringField(TAG_SYMBOL, symbol)) # 55=BTC-USD
        # Optional: Add SecurityIDSource if needed
        # request.setField(fix.StringField(22, '8')) # Tag 22=SecurityIDSource

        print(f"--> Preparing Security Status Request for symbol: {symbol}")
        self.send_message(request)


    def sendSecurityListRequest(self):
        """
        Build and send a Security List Request (MsgType=x) using generic fields.
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_SECURITY_LIST_REQUEST)) # 35=x

        # Body fields
        request.setField(fix.StringField(TAG_SECURITY_REQ_ID, str(uuid.uuid4()))) # 320=unique_id
        # SecurityListRequestType (559): Type of list requested
        # 0=Symbol, 1=Product, 2=Tranche, 3=SecurityType/CFI, 4=All Securities
        request.setField(fix.IntField(TAG_SECURITY_LIST_REQUEST_TYPE, 4)) # 559=4 (All Securities)

        print("--> Preparing Security List Request")
        self.send_message(request)

# --- Global Initiator for Signal Handling ---
initiator = None

def shutdown_handler(signum, frame):
    """Gracefully stop the initiator on signal."""
    print(f"\nReceived signal {signum}, shutting down...")
    global initiator
    if initiator:
        try:
            # Check if already stopped to avoid errors
            if not initiator.isStopped():
                 initiator.stop()
                 print("Initiator stop requested.")
            else:
                 print("Initiator already stopped.")
        except Exception as e:
            print(f"Error stopping initiator: {e}")
    # sys.exit(0) # Exit immediately might cut off cleanup

# --- Main Execution ---
def main():
    global initiator # Allow modification by shutdown handler

    print("--- FIX Client Configuration ---")
    print(f"FIX Version: {FIX_VERSION} (DefaultApplVerID: {DEFAULT_APPL_VER_ID})")
    print(f"SenderCompID (SVC_ACCOUNTID): {SVC_ACCOUNTID}")
    print(f"TargetCompID: {TARGET_COMP_ID}")
    print(f"API Key (Username): {API_KEY}")
    print(f"Passphrase (Password): [REDACTED]")
    print(f"API Secret: [REDACTED]")
    print(f"Host: {FIX_HOST}:{FIX_PORT}")
    print(f"Log Path: {LOG_PATH}")
    print(f"Session Path: {SESSION_PATH}")
    print("--------------------------------")

    config_path = os.path.join(SESSION_PATH, "fix_client.cfg")
    with open(config_path, 'w') as cfg_file:
        cfg_file.write(SESSION_CONFIG)
    print(f"Wrote QuickFIX config to: {config_path}")

    try:
        settings = fix.SessionSettings(config_path)
        app = MarketDataApp(API_KEY, PASSPHRASE, API_SECRET)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings) # Use FileLogFactory

        initiator = fix.SSLSocketInitiator(app, storeFactory, settings, logFactory)

    except (fix.ConfigError, FileNotFoundError) as e:
        print(f"Error in QuickFIX setup: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during setup: {e}")
        sys.exit(1)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("Starting initiator...")
    initiator.start()
    print("Initiator started. Waiting for logon...")

    logon_timeout = 30
    start_time = time.time()
    while not app.logged_on and (time.time() - start_time) < logon_timeout:
        # Check if the initiator stopped unexpectedly during the wait
        # (Handles cases like config errors detected after start)
        if initiator and initiator.isStopped():
            print("Initiator stopped unexpectedly during logon wait.")
            break
        time.sleep(0.5)

    # Check why the loop exited
    if not app.logged_on:
        print(f"Logon timed out or failed after {logon_timeout} seconds. Stopping.")
        if initiator and not initiator.isStopped(): # Ensure stop is called if it didn't stop itself
             initiator.stop()
        sys.exit(1)

    # --- Logon was successful ---
    print("Logon confirmed. Sending application requests...")

    # --- Send Requests Sequence ---
    time.sleep(1) # Small delay after logon
    app.sendMarketDataRequest("BTC-USD")
    time.sleep(2) # Wait a bit after subscribing

    # --- Optional Requests ---
    # Uncomment to send:
    # time.sleep(1)
    # app.sendSecurityStatusRequest("BTC-USD")
    # time.sleep(2)

    # time.sleep(1)
    # app.sendSecurityListRequest()
    # time.sleep(2)

    print("Requests sent. Client running. Press Ctrl+C to exit.")
    try:
        # Keep main thread alive while QuickFIX threads run
        while True:
             if initiator and initiator.isStopped():
                 print("Initiator reported stopped. Exiting main loop.")
                 break
             # Optional: Check periodically if still logged on
             # if initiator and not initiator.isLoggedOn(): # Requires Session object lookup
             #    print("Detected initiator is no longer logged on.")
             #    break
             time.sleep(5) # Adjust sleep interval as needed
    except KeyboardInterrupt:
        # Shutdown is handled by the signal handler
        print("Ctrl+C detected by main loop, shutdown already initiated.")
    finally:
        print("Main loop finished.")
        # Ensure stop is called if not already handled by signal or loop exit condition
        if initiator and not initiator.isStopped():
             print("Ensuring initiator is stopped in finally block...")
             initiator.stop()
        print("Exiting.")
        # os.remove(config_path) # Optional cleanup: remove config file


if __name__ == '__main__':
    main()