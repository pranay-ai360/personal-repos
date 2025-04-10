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
  - Uses a separate thread to send any "App In" messages to a webhook URL.
  
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
import signal  # For cleaner shutdown handling
import sys
import threading
import queue
import requests

# --- Global Queue for Inter-Thread Communication ---
app_in_queue = queue.Queue()

# --- Webhook Sender Thread (Thread2) ---
def webhook_sender():
    """
    This function runs on a separate thread. It continuously reads messages
    from the global queue and sends them via HTTP POST to the specified webhook URL.
    """
    webhook_url = "https://a2ea-111-220-49-33.ngrok-free.app"
    while True:
        msg = app_in_queue.get()
        if msg is None:
            # Sentinel found; exit the loop.
            app_in_queue.task_done()
            break
        try:
            response = requests.post(webhook_url, json={"message": msg})
            print(f"Webhook sender: sent message, response status: {response.status_code}")
        except Exception as e:
            print(f"Webhook sender: Error sending message: {e}")
        finally:
            app_in_queue.task_done()

# --- Configuration Reading ---
FIX_VERSION = os.environ.get("FIX_VERSION", "FIXT.1.1")
DEFAULT_APPL_VER_ID = os.environ.get("DEFAULT_APPL_VER_ID", "9")  # FIX 5.0 SP2
SVC_ACCOUNTID = os.environ.get("SVC_ACCOUNTID")  # API Key used as SenderCompID
TARGET_COMP_ID = os.environ.get("TARGET_COMP_ID", "Coinbase")
API_KEY = os.environ.get("API_KEY")
PASSPHRASE = os.environ.get("PASSPHRASE")
API_SECRET = os.environ.get("SECRET_KEY")  # Renamed from SECRET_KEY for clarity
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
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
ReconnectInterval=10
ValidateUserDefinedFields=N
CancelOnDisconnect=N
CancelOrdersOnDisconnect=Y
ValidateIncomingMessage=N
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
# SSLCheckCertificate=Y
# SSLCAFile=/path/to/your/ca/bundle.crt
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
# Header
TAG_BEGIN_STRING = 8
TAG_MSG_TYPE = 35
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
MSG_TYPE_LOGON = fix.MsgType_Logon         # 'A'
MSG_TYPE_MARKET_DATA_REQUEST = fix.MsgType_MarketDataRequest  # 'V'
MSG_TYPE_SECURITY_STATUS_REQUEST = fix.MsgType_SecurityStatusRequest  # 'f'
MSG_TYPE_SECURITY_LIST_REQUEST = fix.MsgType_SecurityListRequest      # 'x'
# Received Message Types
MSG_TYPE_MARKET_DATA_SNAPSHOT_FULL_REFRESH = fix.MsgType_MarketDataSnapshotFullRefresh  # 'W'
MSG_TYPE_MARKET_DATA_INCREMENTAL_REFRESH = fix.MsgType_MarketDataIncrementalRefresh    # 'X'
MSG_TYPE_SECURITY_STATUS = fix.MsgType_SecurityStatus     # 'f'
MSG_TYPE_SECURITY_LIST = fix.MsgType_SecurityList         # 'y'
MSG_TYPE_MARKET_DATA_REQUEST_REJECT = fix.MsgType_MarketDataRequestReject  # 'Y'
MSG_TYPE_BUSINESS_MESSAGE_REJECT = fix.MsgType_BusinessMessageReject        # 'j'
MSG_TYPE_LOGOUT = fix.MsgType_Logout                      # '5'

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

        if msgType.getValue() == MSG_TYPE_LOGON:  # 'A'
            # Set required fields for Logon
            message.setField(fix.IntField(TAG_ENCRYPT_METHOD, 0))  # EncryptMethod(98)=0
            message.setField(fix.IntField(TAG_HEART_BT_INT, 30))
            message.setField(fix.CharField(TAG_RESET_SEQ_NUM_FLAG, 'Y'))  # ResetSeqNumFlag(141)=Y

            # Set credentials
            message.setField(fix.StringField(TAG_USERNAME, self.api_key))    # Username(553)
            message.setField(fix.StringField(TAG_PASSWORD, self.passphrase))   # Password(554)
            message.setField(fix.StringField(TAG_DEFAULT_APPL_VER_ID, DEFAULT_APPL_VER_ID))

            # Generate signature
            sending_time_field = fix.SendingTime()
            msg_seq_num_field = fix.MsgSeqNum()
            sender_comp_id_field = fix.SenderCompID()
            target_comp_id_field = fix.TargetCompID()
            password_field = fix.StringField(TAG_PASSWORD)

            message.getHeader().getField(sending_time_field)
            message.getHeader().getField(msg_seq_num_field)
            message.getHeader().getField(sender_comp_id_field)
            message.getHeader().getField(target_comp_id_field)
            if message.isSetField(password_field):
                message.getField(password_field)
                password_value = password_field.getString()
            else:
                print("!!! Error: Password field not found in Logon message before signing.")
                return

            rawData = self.sign(
                sending_time_field.getString(),
                msgType.getValue(),
                msg_seq_num_field.getString(),
                sender_comp_id_field.getString(),
                target_comp_id_field.getString(),
                password_value
            )
            message.setField(fix.IntField(TAG_RAW_DATA_LENGTH, len(rawData)))
            message.setField(fix.StringField(TAG_RAW_DATA, rawData))

            print(">>> Sending Logon (toAdmin - Modified):")
            print(message.toString().replace('\x01', '|'))
        else:
            print(">>> Admin Out:", message.toString().replace('\x01', '|'))

    def fromAdmin(self, message, sessionID):
        print("<<< Admin In :", message.toString().replace('\x01', '|'))
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == MSG_TYPE_LOGOUT:
            local_field_text = fix.StringField(FIELD_TEXT.getField())
            if message.isSetField(local_field_text):
                message.getField(local_field_text)
                print(f"    Logout Reason: {local_field_text.getValue()}")

    def toApp(self, message, sessionID):
        print(">>> App Out  :", message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()
        
        # Build the output message string
        app_in_msg = f"<<< App In ({mt}): " + message.toString().replace('\x01', '|')
        print(app_in_msg)
        # Enqueue the message so that thread2 (the webhook sender) can process it.
        app_in_queue.put(app_in_msg)
        
        # Example: Log specific reject reasons
        if mt == MSG_TYPE_MARKET_DATA_REQUEST_REJECT:  # 'Y'
            local_field_reason = fix.CharField(FIELD_MD_REQ_REJ_REASON.getField())
            local_field_text = fix.StringField(FIELD_TEXT.getField())
            if message.isSetField(local_field_reason):
                message.getField(local_field_reason)
                print(f"    MD Reject Reason Code: {local_field_reason.getValue()}")
            if message.isSetField(local_field_text):
                message.getField(local_field_text)
                print(f"    MD Reject Text: {local_field_text.getValue()}")
        elif mt == MSG_TYPE_BUSINESS_MESSAGE_REJECT:  # 'j'
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
        return signature_b64

    def send_message(self, message):
        """Helper function to send a message if logged on."""
        if self.logged_on and self.sessionID:
            try:
                if FIX_VERSION == "FIXT.1.1":
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
        Subscribes to snapshot + updates.
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_MARKET_DATA_REQUEST))
        request.setField(fix.StringField(TAG_MD_REQ_ID, str(uuid.uuid4())))
        request.setField(fix.CharField(TAG_SUBSCRIPTION_REQUEST_TYPE, '1'))
        request.setField(fix.IntField(TAG_MARKET_DEPTH, 0))
        group_types = fix.Group(TAG_NO_MD_ENTRY_TYPES, TAG_MD_ENTRY_TYPE)
        group_types.setField(fix.CharField(TAG_MD_ENTRY_TYPE, '0'))
        request.addGroup(group_types)
        group_types.setField(fix.CharField(TAG_MD_ENTRY_TYPE, '1'))
        request.addGroup(group_types)
        group_sym = fix.Group(TAG_NO_RELATED_SYM, TAG_SYMBOL)
        group_sym.setField(fix.StringField(TAG_SYMBOL, symbol))
        request.addGroup(group_sym)
        print(f"--> Preparing Market Data Request for symbol: {symbol}")
        self.send_message(request)

    def sendSecurityStatusRequest(self, symbol):
        """
        Build and send a Security Status Request (MsgType=f) using generic fields.
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_SECURITY_STATUS_REQUEST))
        request.setField(fix.StringField(TAG_SECURITY_STATUS_REQ_ID, str(uuid.uuid4())))
        request.setField(fix.CharField(TAG_SUBSCRIPTION_REQUEST_TYPE, '0'))
        request.setField(fix.StringField(TAG_SYMBOL, symbol))
        print(f"--> Preparing Security Status Request for symbol: {symbol}")
        self.send_message(request)

    def sendSecurityListRequest(self):
        """
        Build and send a Security List Request (MsgType=x) using generic fields.
        """
        request = fix.Message()
        header = request.getHeader()
        header.setField(fix.MsgType(MSG_TYPE_SECURITY_LIST_REQUEST))
        request.setField(fix.StringField(TAG_SECURITY_REQ_ID, str(uuid.uuid4())))
        request.setField(fix.IntField(TAG_SECURITY_LIST_REQUEST_TYPE, 4))
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
            if not initiator.isStopped():
                initiator.stop()
                print("Initiator stop requested.")
            else:
                print("Initiator already stopped.")
        except Exception as e:
            print(f"Error stopping initiator: {e}")

# --- Main Execution ---
def main():
    global initiator

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
        logFactory = fix.FileLogFactory(settings)
        initiator = fix.SSLSocketInitiator(app, storeFactory, settings, logFactory)
    except (fix.ConfigError, FileNotFoundError) as e:
        print(f"Error in QuickFIX setup: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during setup: {e}")
        sys.exit(1)

    # Start the webhook sender thread (Thread2)
    webhook_thread = threading.Thread(target=webhook_sender, name="WebhookSender")
    webhook_thread.start()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("Starting initiator...")
    initiator.start()
    print("Initiator started. Waiting for logon...")

    logon_timeout = 30
    start_time = time.time()
    while not app.logged_on and (time.time() - start_time) < logon_timeout:
        if initiator and initiator.isStopped():
            print("Initiator stopped unexpectedly during logon wait.")
            break
        time.sleep(0.5)

    if not app.logged_on:
        print(f"Logon timed out or failed after {logon_timeout} seconds. Stopping.")
        if initiator and not initiator.isStopped():
            initiator.stop()
        sys.exit(1)

    print("Logon confirmed. Sending application requests...")
    time.sleep(1)
    app.sendMarketDataRequest("BTC-USD")
    time.sleep(2)
    # Optional further requests can be uncommented here.
    print("Requests sent. Client running. Press Ctrl+C to exit.")
    try:
        while True:
            if initiator and initiator.isStopped():
                print("Initiator reported stopped. Exiting main loop.")
                break
            time.sleep(5)
    except KeyboardInterrupt:
        print("Ctrl+C detected by main loop, shutdown already initiated.")
    finally:
        print("Main loop finished.")
        if initiator and not initiator.isStopped():
            print("Ensuring initiator is stopped in finally block...")
            initiator.stop()
        # Signal the webhook sender thread to exit.
        app_in_queue.put(None)
        webhook_thread.join()
        print("Exiting.")
        # Optional cleanup: os.remove(config_path)

if __name__ == '__main__':
    main()