#!/usr/bin/env python3
"""
A minimal FIX client that:
  - Reads configuration values from OS environment variables.
  - Writes a QuickFIX config file using FIX dictionaries.
  - Sends Market Data Request (35=V).
  - Listens for Market Data Incremental Refresh (35=X) messages.
  - Parses 35=X message entries based on dictionary structure and user logic.
  - Translates entries into JSON commands and posts to a local API.

Reference:
https://docs.cdp.coinbase.com/exchange/docs/fix-msg-market-data
https://docs.cdp.coinbase.com/exchange/docs/fix-api-authentication
"""

import os
import quickfix as fix
import uuid
import time
# import tempfile # No longer needed with named config
import hashlib
import hmac
import base64
import signal
import sys
import json
import requests
from decimal import Decimal, InvalidOperation
import logging
# import traceback # Uncomment for detailed exception traces

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration Reading ---
FIX_VERSION = os.environ.get("FIX_VERSION", "FIXT.1.1")
# DefaultApplVerID needs to match the App Dictionary Service Pack!
# FIX 5.0 SP0 -> '7'
# FIX 5.0 SP1 -> '8'
# FIX 5.0 SP2 -> '9'
# Using '7' because FIX50-prod-sand.xml defines SP0
DEFAULT_APPL_VER_ID_FOR_DICT = "7"

SVC_ACCOUNTID = os.environ.get("SVC_ACCOUNTID")
TARGET_COMP_ID = os.environ.get("TARGET_COMP_ID", "Coinbase")
API_KEY = os.environ.get("API_KEY")
PASSPHRASE = os.environ.get("PASSPHRASE")
API_SECRET = os.environ.get("SECRET_KEY")
FIX_HOST = os.environ.get("FIX_HOST", "fix-md.sandbox.exchange.coinbase.com")
FIX_PORT = os.environ.get("FIX_PORT", "6121")
LOG_PATH = os.environ.get("LOG_PATH", "./Logs/")
SESSION_PATH = os.environ.get("SESSION_PATH", "./.sessions/")
ORDER_API_URL = os.environ.get("ORDER_API_URL", "http://localhost:7001/orders")
ORDER_API_TIMEOUT = int(os.environ.get("ORDER_API_TIMEOUT", 10))

# --- Path to Dictionaries ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Assuming dictionaries are in 'cb_exch_fix_dictionaries-latest/market-data' relative to script
DEFAULT_DICT_PATH = os.path.join(SCRIPT_DIR, "cb_exch_fix_dictionaries-latest", "market-data")
FIX_DICTIONARY_PATH = os.environ.get("FIX_DICTIONARY_PATH", DEFAULT_DICT_PATH)

TRANSPORT_DICT_FILE = "FIXT11-prod-sand.xml"
APP_DICT_FILE = "FIX50-prod-sand.xml" # This file defines FIX 5.0 SP0

TRANSPORT_DICT_FULL_PATH = os.path.join(FIX_DICTIONARY_PATH, TRANSPORT_DICT_FILE)
APP_DICT_FULL_PATH = os.path.join(FIX_DICTIONARY_PATH, APP_DICT_FILE)

# --- Input Validation ---
if not all([SVC_ACCOUNTID, API_KEY, PASSPHRASE, API_SECRET]):
    logging.error("Error: Missing required environment variables (SVC_ACCOUNTID, API_KEY, PASSPHRASE, SECRET_KEY)")
    sys.exit(1)
if SVC_ACCOUNTID != API_KEY:
     logging.warning("Warning: SVC_ACCOUNTID (SenderCompID) and API_KEY (Username) are different.")
if not os.path.isfile(TRANSPORT_DICT_FULL_PATH):
    logging.error(f"Transport Dictionary not found: {TRANSPORT_DICT_FULL_PATH}")
    sys.exit(1)
if not os.path.isfile(APP_DICT_FULL_PATH):
    logging.error(f"Application Dictionary not found: {APP_DICT_FULL_PATH}")
    sys.exit(1)

os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)

# --- Session Configuration (Using Dictionary) ---
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=Y
TransportDataDictionary={TRANSPORT_DICT_FULL_PATH}
AppDataDictionary={APP_DICT_FULL_PATH}
ReconnectInterval=10
ValidateUserDefinedFields=Y
CancelOnDisconnect=N
CancelOrdersOnDisconnect=Y
ValidateIncomingMessage=Y
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
SocketConnectPort={FIX_PORT}
FileLogPath={LOG_PATH}

[SESSION]
BeginString={FIX_VERSION}
# --- DefaultApplVerID MUST match the App Dictionary version ---
DefaultApplVerID={DEFAULT_APPL_VER_ID_FOR_DICT} # Use '7' for FIX 5.0 SP0
SenderCompID={SVC_ACCOUNTID}
TargetCompID={TARGET_COMP_ID}
HeartBtInt=30
SocketConnectHost={FIX_HOST}
FileStorePath={SESSION_PATH}
"""

# --- HTTP Post Helper ---
def send_order_to_api(payload):
    """Sends the constructed JSON payload to the order API."""
    headers = {'Content-Type': 'application/json'}
    payload_json = json.dumps(payload)
    logging.info(f"--> Posting to API {ORDER_API_URL}: {payload_json}")
    try:
        response = requests.post(ORDER_API_URL, headers=headers, data=payload_json, timeout=ORDER_API_TIMEOUT)
        response.raise_for_status()
        logging.info(f"<-- API Response {response.status_code}: {response.text}")
        return True
    except requests.exceptions.Timeout: logging.error(f"!!! API Error: Timeout connecting to {ORDER_API_URL}")
    except requests.exceptions.ConnectionError as e: logging.error(f"!!! API Error: Connection error to {ORDER_API_URL}: {e}")
    except requests.exceptions.HTTPError as e: logging.error(f"!!! API Error: HTTP error from {ORDER_API_URL}: {e.response.status_code} - {e.response.text}")
    except requests.exceptions.RequestException as e: logging.error(f"!!! API Error: Unexpected error during request to {ORDER_API_URL}: {e}")
    except json.JSONDecodeError as e:
         logging.error(f"!!! API Error: Could not decode JSON response: {e}")
         logging.error(f"    Raw Response Text: {response.text if 'response' in locals() else 'N/A'}")
    return False

# --- QuickFIX Application Class ---
class MarketDataApp(fix.Application):
    def __init__(self, api_key, passphrase, api_secret):
        super().__init__()
        self.api_key = api_key
        self.passphrase = passphrase
        self.api_secret = api_secret
        self.sessionID = None
        self.logged_on = False

    def onCreate(self, sessionID):
        logging.info(f"Session created: {sessionID}")
        self.sessionID = sessionID

    def onLogon(self, sessionID):
        logging.info(f"Logon successful: {sessionID}")
        self.logged_on = True

    def onLogout(self, sessionID):
        logging.info(f"Logout: {sessionID}")
        self.logged_on = False

    # --- Using DICTIONARY AWARE classes below ---
    def toAdmin(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()

        if mt == fix.MsgType_Reject: logging.info(">>> Admin Out: [Admin Reject - Suppressed]"); return

        if mt == fix.MsgType_Logon: # 'A'
            logging.info("Modifying Logon message in toAdmin...")
            message.setField(fix.EncryptMethod(0))
            message.setField(fix.HeartBtInt(30))
            message.setField(fix.ResetSeqNumFlag(True)) # Sets 141=Y
            message.setField(fix.Username(self.api_key))
            message.setField(fix.Password(self.passphrase))
            # Set DefaultApplVerID *in the Logon message itself* for FIXT
            message.setField(fix.DefaultApplVerID(DEFAULT_APPL_VER_ID_FOR_DICT)) # Use '7'

            sending_time_field = fix.SendingTime()
            msg_seq_num_field = fix.MsgSeqNum()
            sender_comp_id_field = fix.SenderCompID()
            target_comp_id_field = fix.TargetCompID()
            password_field = fix.Password() # Use specific type

            message.getHeader().getField(sending_time_field)
            message.getHeader().getField(msg_seq_num_field)
            message.getHeader().getField(sender_comp_id_field)
            message.getHeader().getField(target_comp_id_field)

            password_value = ""
            if message.isSetField(password_field):
                message.getField(password_field)
                password_value = password_field.getValue() # Use getValue()
            else: logging.error("!!! Error: Password field not found in Logon message before signing."); return

            rawData = self.sign(
                sending_time_field.getString(), # getString() for UTCTimestamp
                mt,
                str(msg_seq_num_field.getValue()), # getValue() for SeqNum, convert to string
                sender_comp_id_field.getValue(),
                target_comp_id_field.getValue(),
                password_value
            )
            message.setField(fix.RawDataLength(len(rawData)))
            message.setField(fix.RawData(rawData))

            logging.info(">>> Sending Logon (toAdmin - Modified):")
            logging.info(message.toString().replace('\x01', '|'))
        else:
            logging.info(f">>> Admin Out ({mt}): {message.toString().replace(chr(1), '|')}")

    def fromAdmin(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()
        if mt == fix.MsgType_Reject: logging.info("<<< Admin In : [Admin Reject - Suppressed]"); return

        logging.info(f"<<< Admin In ({mt}): {message.toString().replace(chr(1), '|')}")
        if mt == fix.MsgType_Logout:
             text = fix.Text() # Use specific field class
             if message.isSetField(text):
                 try: message.getField(text); logging.warning(f"    Logout Reason: {text.getValue()}")
                 except Exception as e: logging.error(f"    Error getting Logout Text: {e}")

    def toApp(self, message, sessionID):
        logging.info(f">>> App Out  : {message.toString().replace(chr(1), '|')}")

    def fromApp(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()

        full_message_str = message.toString().replace('\x01', '|')
        logging.info(f"<<< App In ({mt}): {full_message_str}")

        # --- Process Market Data Incremental Refresh ('X') using Dictionary ---
        if mt == fix.MsgType_MarketDataIncrementalRefresh:
            logging.info("\n--- Processing Market Data Incremental Refresh (X) ---")

            symbol_field = fix.Symbol()
            symbol = None
            if message.isSetField(symbol_field):
                try: message.getField(symbol_field); symbol = symbol_field.getValue(); logging.info(f"    Extracted Symbol(55) from main body: {symbol}")
                except Exception as e: logging.error(f"    [ERROR] Error getting Symbol(55) from body: {e}")

            noMDEntries_field = fix.NoMDEntries()
            num_entries = 0
            try:
                 if message.isSetField(noMDEntries_field): message.getField(noMDEntries_field); num_entries = noMDEntries_field.getValue(); logging.info(f"    Found {num_entries} MDEntries (Tag {noMDEntries_field.getField()})")
                 else: logging.warning(f"    [WARNING] NoMDEntries count (Tag {noMDEntries_field.getField()}) not found.")
            except Exception as e: logging.warning(f"    [WARNING] Error getting NoMDEntries count: {e}")

            if num_entries == 0: logging.info("    No entries to process."); logging.info("--- Finished processing Market Data Incremental Refresh (X) ---"); return

            md_entry_group = fix.MarketDataIncrementalRefresh.NoMDEntries()

            for i in range(1, num_entries + 1):
                logging.info(f"    Processing Entry {i}/{num_entries}")
                try:
                    message.getGroup(i, md_entry_group) # Populate the group object
                    update_action, entry_type, order_id_37, order_id_278 = None, None, None, None
                    price_str, size_str, price, size = None, None, None, None
                    entry_symbol = symbol

                    # Extract using dictionary field classes
                    entry_type_field = fix.MDEntryType(); update_action_field = fix.MDUpdateAction()
                    order_id_field = fix.OrderID(); md_entry_id_field = fix.MDEntryID()
                    price_field = fix.MDEntryPx(); size_field = fix.MDEntrySize()
                    symbol_field_group = fix.Symbol()

                    if md_entry_group.isSetField(entry_type_field): try: md_entry_group.getField(entry_type_field); entry_type = entry_type_field.getValue(); logging.info(f"      Extracted MDEntryType(269): {entry_type}") except Exception as e: logging.error(f"      [ERROR] getting MDEntryType: {e}")
                    if md_entry_group.isSetField(update_action_field): try: md_entry_group.getField(update_action_field); update_action = update_action_field.getValue(); logging.info(f"      Extracted MDUpdateAction(279): {update_action}") except Exception as e: logging.error(f"      [ERROR] getting MDUpdateAction: {e}")
                    elif entry_type == '2': logging.info("      [INFO] MDUpdateAction(279) missing, assuming OK for Trade Type=2.")
                    if md_entry_group.isSetField(order_id_field): try: md_entry_group.getField(order_id_field); order_id_37 = order_id_field.getValue(); logging.info(f"      Extracted OrderID(37): {order_id_37}") except Exception as e: logging.error(f"      [ERROR] getting OrderID: {e}")
                    if md_entry_group.isSetField(md_entry_id_field): try: md_entry_group.getField(md_entry_id_field); order_id_278 = md_entry_id_field.getValue(); logging.info(f"      Extracted MDEntryID(278): {order_id_278}") except Exception as e: logging.error(f"      [ERROR] getting MDEntryID: {e}")
                    if md_entry_group.isSetField(price_field):
                        try: md_entry_group.getField(price_field); price_str = price_field.getValue(); logging.info(f"      Extracted MDEntryPx(270): {price_str}"); price = Decimal(price_str)
                        except InvalidOperation: logging.warning(f"      [WARNING] Invalid price format '{price_str}'."); price = None
                        except Exception as e: logging.error(f"      [ERROR] getting MDEntryPx: {e}")
                    if md_entry_group.isSetField(size_field):
                         try: md_entry_group.getField(size_field); size_str = size_field.getValue(); logging.info(f"      Extracted MDEntrySize(271): {size_str}"); size = Decimal(size_str)
                         except InvalidOperation: logging.warning(f"      [WARNING] Invalid size format '{size_str}'."); size = None
                         except Exception as e: logging.error(f"      [ERROR] getting MDEntrySize: {e}")
                    if not entry_symbol and md_entry_group.isSetField(symbol_field_group): try: md_entry_group.getField(symbol_field_group); entry_symbol = symbol_field_group.getValue(); logging.info(f"      Extracted Symbol(55) from group: {entry_symbol}") except Exception as e: logging.error(f"      [ERROR] getting Symbol from group: {e}")

                    if not entry_symbol: logging.error(f"      [ERROR] Symbol missing. Skipping."); continue

                    payloads_to_send = []; action_taken = False; final_order_id = None
                    side = "BID" if entry_type == '0' else "ASK" if entry_type == '1' else "TRADE_MATCH" if entry_type == '2' else "UNKNOWN"

                    # --- USER LOGIC Mapping ---
                    if entry_type == '2': # Trade Match -> CANCEL using Tag 37
                        final_order_id = order_id_37
                        if not final_order_id: logging.error(f"      [ERROR] Trade Match (Type=2) but OrderID(37) missing. Skipping."); continue
                        cancel_payload = { "command": "CANCEL_ORDER", "userId": 1, "symbol": entry_symbol, "orderUUID": final_order_id }
                        payloads_to_send.append(cancel_payload)
                        logging.info(f"      Action: Trade Match (Type=2) -> CANCEL_ORDER (UUID from Tag 37: {final_order_id})")
                        action_taken = True
                    elif update_action == '0': # New -> PLACE_ORDER using Tag 37
                        final_order_id = order_id_37
                        if not final_order_id: logging.error(f"      [ERROR] New order (Action=0) but OrderID(37) missing. Skipping."); continue
                        if side not in ["BID", "ASK"]: logging.error(f"      [ERROR] New order (Action=0) but side unknown (MDEntryType={entry_type}). Skipping."); continue
                        if price is None or size is None: logging.error(f"      [ERROR] New order (Action=0) but Price/Size missing/invalid. Skipping."); continue
                        place_payload = { "command": "PLACE_ORDER", "orderType": "GTC", "userId": 1, "userType": "MM", "orderUUID": final_order_id, "symbol": entry_symbol, "side": side, "price": float(price), "size": float(size) }
                        payloads_to_send.append(place_payload)
                        logging.info(f"      Action: New (Action=0) -> PLACE_ORDER (UUID from Tag 37: {final_order_id})")
                        action_taken = True
                    elif update_action == '1': # Change -> CANCEL using Tag 278
                        final_order_id = order_id_278
                        if not final_order_id: logging.error(f"      [ERROR] Change order (Action=1) but MDEntryID(278) missing. Skipping."); continue
                        cancel_payload = { "command": "CANCEL_ORDER", "userId": 1, "symbol": entry_symbol, "orderUUID": final_order_id }
                        payloads_to_send.append(cancel_payload)
                        logging.info(f"      Action: Change (Action=1) -> CANCEL_ORDER (UUID from Tag 278: {final_order_id})")
                        action_taken = True
                    elif update_action == '2': # Delete -> CANCEL using Tag 278
                        final_order_id = order_id_278
                        if not final_order_id: logging.error(f"      [ERROR] Delete order (Action=2) but MDEntryID(278) missing. Skipping."); continue
                        cancel_payload = { "command": "CANCEL_ORDER", "userId": 1, "symbol": entry_symbol, "orderUUID": final_order_id }
                        payloads_to_send.append(cancel_payload)
                        logging.info(f"      Action: Delete (Action=2) -> CANCEL_ORDER (UUID from Tag 278: {final_order_id})")
                        action_taken = True

                    if not action_taken: logging.warning(f"      [INFO] No action defined by user logic for entry {i}. UpdateAction='{update_action}', EntryType='{entry_type}'. Ignoring."); continue

                    for pload in payloads_to_send: send_order_to_api(pload); time.sleep(0.05)

                except Exception as e: logging.error(f"    [UNEXPECTED ERROR] processing group item {i}: {type(e).__name__} - {e}. Skipping."); # traceback.print_exc()

            logging.info("--- Finished processing Market Data Incremental Refresh (X) ---")

        # --- Handle other App message types ---
        elif mt == fix.MsgType_MarketDataRequestReject: # 'Y'
             reason = fix.MDReqRejReason(); text = fix.Text()
             if message.isSetField(reason): try: message.getField(reason); logging.warning(f"    MD Reject Reason Code: {reason.getValue()}") except Exception as e: logging.error(f"    Error getting MD Reject Reason: {e}")
             if message.isSetField(text): try: message.getField(text); logging.warning(f"    MD Reject Text: {text.getValue()}") except Exception as e: logging.error(f"    Error getting MD Reject Text: {e}")
        elif mt == fix.MsgType_BusinessMessageReject: # 'j'
            reason = fix.BusinessRejectReason(); text = fix.Text()
            if message.isSetField(reason): try: message.getField(reason); logging.warning(f"    Business Reject Reason Code: {reason.getValue()}") except Exception as e: logging.error(f"    Error getting Business Reject Reason: {e}")
            if message.isSetField(text): try: message.getField(text); logging.warning(f"    Business Reject Text: {text.getValue()}") except Exception as e: logging.error(f"    Error getting Business Reject Text: {e}")


    def sign(self, sending_time, msg_type, seq_num, sender_comp, target_comp, password):
        """Generate Coinbase FIX API signature."""
        message_data = f"{sending_time}\x01{msg_type}\x01{seq_num}\x01{sender_comp}\x01{target_comp}\x01{password}"
        secret_bytes = base64.b64decode(self.api_secret)
        hmac_digest = hmac.new(secret_bytes, message_data.encode('utf-8'), hashlib.sha256)
        signature_b64 = base64.b64encode(hmac_digest.digest()).decode('utf-8')
        return signature_b64

    def send_message(self, message):
        """Helper function to send a message if logged on."""
        if self.logged_on and self.sessionID:
            try:
                # No need to manually set ApplVerID header with dictionary
                sent = fix.Session.sendToTarget(message, self.sessionID)
                if not sent: logging.error("!!! Error sending message (sendToTarget returned false)")
                return sent
            except fix.SessionNotFound as e: logging.error(f"!!! Error sending message: Session not found - {e}")
            except Exception as e: logging.error(f"!!! Unexpected error sending message: {e}")
            return False
        else:
            logging.warning("!!! Cannot send message: Not logged on or no sessionID.")
            return False

    def sendMarketDataRequest(self, symbol):
        """Build and send Market Data Request (V) using dictionary classes."""
        logging.info(f"--> Preparing Market Data Request for symbol: {symbol}")
        request = fix.MarketDataRequest()
        request.setField(fix.MDReqID(str(uuid.uuid4())))
        request.setField(fix.SubscriptionRequestType('1'))
        request.setField(fix.MarketDepth(0))
        group_types = fix.MarketDataRequest().NoMDEntryTypes()
        group_types.setField(fix.MDEntryType(fix.MDEntryType_BID))
        request.addGroup(group_types)
        group_types.setField(fix.MDEntryType(fix.MDEntryType_OFFER))
        request.addGroup(group_types)
        group_sym = fix.MarketDataRequest().NoRelatedSym()
        group_sym.setField(fix.Symbol(symbol))
        request.addGroup(group_sym)
        self.send_message(request)

# --- Global Initiator for Signal Handling ---
initiator = None
def shutdown_handler(signum, frame):
    logging.info(f"\nReceived signal {signum}, shutting down...")
    global initiator
    if initiator:
        try:
            if not initiator.isStopped(): initiator.stop(); logging.info("Initiator stop requested.")
            else: logging.info("Initiator already stopped.")
        except Exception as e: logging.error(f"Error stopping initiator: {e}")

# --- Main Execution ---
def main():
    global initiator
    logging.info("--- FIX Client Configuration ---")
    logging.info(f"FIX Version: {FIX_VERSION} (App Ver ID: {DEFAULT_APPL_VER_ID_FOR_DICT})")
    logging.info(f"SenderCompID: {SVC_ACCOUNTID}, TargetCompID: {TARGET_COMP_ID}")
    logging.info(f"API Key: {API_KEY}, Passphrase: [REDACTED], Secret: [REDACTED]")
    logging.info(f"Host: {FIX_HOST}:{FIX_PORT}, Logs: {LOG_PATH}, Sessions: {SESSION_PATH}")
    logging.info(f"Order API URL: {ORDER_API_URL}")
    logging.info(f"TransportDict: {TRANSPORT_DICT_FULL_PATH}")
    logging.info(f"AppDict: {APP_DICT_FULL_PATH}")
    logging.info("--------------------------------")

    # --- Clean Session State ---
    session_dir = os.path.abspath(SESSION_PATH)
    logging.info(f"Checking for session directory: {session_dir}")
    if os.path.isdir(session_dir):
        logging.warning(f"*** Deleting existing session directory: {session_dir} ***")
        import shutil
        try:
            shutil.rmtree(session_dir)
            logging.info("    Session directory deleted.")
            os.makedirs(session_dir, exist_ok=True)
            logging.info(f"    Recreated empty session directory.")
        except OSError as e:
            logging.error(f"    Error deleting session directory: {e}. Please delete manually.")
            sys.exit(1) # Exit if cannot clean state
    else:
        logging.info("    Session directory does not exist, creating.")
        os.makedirs(session_dir, exist_ok=True)

    config_path = os.path.join(SESSION_PATH, "fix_client_dict.cfg")
    with open(config_path, 'w') as cfg_file: cfg_file.write(SESSION_CONFIG)
    logging.info(f"Wrote QuickFIX config to: {config_path}")

    try:
        settings = fix.SessionSettings(config_path)
        app = MarketDataApp(API_KEY, PASSPHRASE, API_SECRET)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        initiator = fix.SSLSocketInitiator(app, storeFactory, settings, logFactory)
    except fix.ConfigError as e: logging.error(f"QuickFIX Configuration Error: {e}"); sys.exit(1)
    except FileNotFoundError as e: logging.error(f"File Not Found Error during setup: {e}"); sys.exit(1)
    except Exception as e: logging.error(f"Unexpected error during setup: {e}"); sys.exit(1)

    signal.signal(signal.SIGINT, shutdown_handler); signal.signal(signal.SIGTERM, shutdown_handler)

    logging.info("Starting initiator..."); initiator.start()
    logging.info("Initiator started. Waiting for logon...")

    logon_timeout = 30; start_time = time.time()
    while not app.logged_on and (time.time() - start_time) < logon_timeout:
        if initiator and initiator.isStopped(): logging.warning("Initiator stopped unexpectedly during logon wait."); break
        time.sleep(0.5)

    if not app.logged_on:
        logging.error(f"Logon timed out or failed after {logon_timeout} seconds. Stopping.")
        if initiator and not initiator.isStopped(): initiator.stop()
        sys.exit(1)

    logging.info("Logon confirmed. Sending application requests...")
    time.sleep(1); app.sendMarketDataRequest("BTC-USD"); time.sleep(2)

    logging.info("Requests sent. Client running. Waiting for messages... Press Ctrl+C to exit.")
    try:
        while True:
             if initiator and initiator.isStopped(): logging.info("Initiator reported stopped. Exiting main loop."); break
             time.sleep(5)
    except KeyboardInterrupt: logging.info("Ctrl+C detected by main loop, shutdown already initiated.")
    finally:
        logging.info("Main loop finished.")
        if initiator and not initiator.isStopped(): logging.info("Ensuring initiator is stopped in finally block..."); initiator.stop()
        logging.info("Exiting.")

if __name__ == '__main__':
    main()