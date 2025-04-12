#!/usr/bin/env python3
import os
import sys
import quickfix as fix
import uuid
import time
import hashlib
import hmac
import base64
import threading
import signal
import datetime

# --- Environment & Configuration Reading ---
# FIX Protocol Version Settings
FIX_VERSION = os.environ.get("FIX_VERSION", "FIXT.1.1")
# Default Application Version ID (FIX 5.0 SP2 is '9')
DEFAULT_APPL_VER_ID = os.environ.get("DEFAULT_APPL_VER_ID", "9")

# Credentials - **MUST BE SET AS ENVIRONMENT VARIABLES**
SVC_ACCOUNTID = os.environ.get("SVC_ACCOUNTID")  # Your API Key (used as SenderCompID/553 Username)
TARGET_COMP_ID = os.environ.get("TARGET_COMP_ID", "Coinbase") # Should remain Coinbase
API_KEY = os.environ.get("API_KEY")              # Your API Key (redundant if same as SVC_ACCOUNTID, but needed for clarity)
PASSPHRASE = os.environ.get("PASSPHRASE")        # API Passphrase (Tag 554)
API_SECRET = os.environ.get("SECRET_KEY")        # API Secret Key (for signing Logon)

# Connection Details - **SET ENVIRONMENT VARIABLES OR USE DEFAULTS**
# **IMPORTANT: Using the Order Entry Sandbox Host**
FIX_HOST = os.environ.get("FIX_HOST", "fix-ord.sandbox.exchange.coinbase.com")
FIX_PORT = os.environ.get("FIX_PORT", "6121")

# File Paths
LOG_PATH = os.environ.get("LOG_PATH", "./Logs/")
SESSION_PATH = os.environ.get("SESSION_PATH", "./.sessions/")

# --- Input Validation ---
if not all([SVC_ACCOUNTID, API_KEY, PASSPHRASE, API_SECRET]):
    print("Error: Missing required environment variables:")
    print("  - SVC_ACCOUNTID (Your API Key)")
    print("  - API_KEY (Your API Key)")
    print("  - PASSPHRASE (Your API Passphrase)")
    print("  - SECRET_KEY (Your API Secret)")
    print("\nPlease set these environment variables before running.")
    sys.exit(1)

# --- Crucial Clock Check ---
# **IMPORTANT:** ENSURE YOUR SYSTEM CLOCK IS ACCURATE (UTC)
# Use `sudo date -s "$(wget -qSO- --max-redirect=0 google.com 2>&1 | grep Date: | cut -d' ' -f5-8)Z"` or NTP
print(f"--- System UTC Time Check: {datetime.datetime.utcnow().strftime('%Y%m%d-%H:%M:%S.%f')[:-3]} ---")
print("--- Ensure this time is accurate! ---")

if SVC_ACCOUNTID != API_KEY:
    print("Warning: SVC_ACCOUNTID and API_KEY differ.")
    print(f"         Using SVC_ACCOUNTID='{SVC_ACCOUNTID}' for SenderCompID (49)")
    print(f"         Using API_KEY='{API_KEY}' for Username (553)")

# Ensure log and session directories exist
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)

# --- Session Configuration String (Corrected Comments) ---
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
# Time in seconds between reconnect attempts
ReconnectInterval=10
# Optional: Timeout for socket operations
SocketTimeout=15
ValidateUserDefinedFields=N
ValidateIncomingMessage=N
# Reset seq nums to 1 on successful logon
ResetOnLogon=Y
ResetOnLogout=N
# Reset seq nums if disconnected unexpectedly
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
SocketConnectPort={FIX_PORT}
FileLogPath={LOG_PATH}
# Coinbase Specific Logon Field (also set explicitly in toAdmin)
CancelOrdersOnDisconnect=Y

[SESSION]
BeginString={FIX_VERSION}
DefaultApplVerID={DEFAULT_APPL_VER_ID}
SenderCompID={SVC_ACCOUNTID}
TargetCompID={TARGET_COMP_ID}
HeartBtInt=30
SocketConnectHost={FIX_HOST}
FileStorePath={SESSION_PATH}
"""

# --- FIX Tag Constants (Selected) ---
TAG_MSG_TYPE             = 35
TAG_BEGIN_STRING         = 8
TAG_SENDER_COMP_ID       = 49
TAG_TARGET_COMP_ID       = 56
TAG_MSG_SEQ_NUM          = 34
TAG_SENDING_TIME         = 52
TAG_ENCRYPT_METHOD       = 98
TAG_HEART_BT_INT         = 108
TAG_RESET_SEQ_NUM_FLAG   = 141
TAG_USERNAME             = 553
TAG_PASSWORD             = 554
TAG_DEFAULT_APPL_VER_ID  = 1137
TAG_RAW_DATA_LENGTH      = 95
TAG_RAW_DATA             = 96
TAG_TEXT                 = 58
TAG_CL_ORD_ID            = 11
TAG_ORIG_CL_ORD_ID       = 41
TAG_SYMBOL               = 55
TAG_SIDE                 = 54
TAG_ORDER_QTY            = 38
TAG_ORD_TYPE             = 40
TAG_PRICE                = 44
TAG_ORD_STATUS           = 39
TAG_EXEC_TYPE            = 150
TAG_LEAVES_QTY           = 151
TAG_CUM_QTY              = 14
TAG_AVG_PX               = 6
TAG_LAST_PX              = 31
TAG_LAST_QTY             = 32
TAG_ORDER_ID             = 37
TAG_EXEC_ID              = 17
TAG_ORD_REJ_REASON       = 103
TAG_CXL_REJ_REASON       = 102
TAG_CXL_REJ_RESPONSE_TO  = 434
TAG_CANCEL_ORDERS_ON_DISCONNECT = 8013 # Coinbase specific Logon field
TAG_REF_SEQ_NUM          = 45
TAG_REF_TAG_ID           = 371
TAG_REF_MSG_TYPE         = 372
TAG_SESSION_REJECT_REASON= 373
TAG_TEST_REQ_ID          = 112 # Added for Test Request
TAG_TRANSACT_TIME        = 60 # Added for completeness
TAG_TIME_IN_FORCE        = 59 # Added for completeness

# Message types (as strings)
MSG_TYPE_LOGON                 = "A"
MSG_TYPE_LOGOUT                = "5"
MSG_TYPE_HEARTBEAT             = "0"
MSG_TYPE_TEST_REQUEST          = "1" # Added for Test Request
MSG_TYPE_RESEND_REQUEST        = "2"
MSG_TYPE_REJECT                = "3"
MSG_TYPE_SEQUENCE_RESET        = "4"
MSG_TYPE_NEW_ORDER_SINGLE      = "D"
MSG_TYPE_ORDER_STATUS_REQUEST  = "H"
MSG_TYPE_EXECUTION_REPORT      = "8"
MSG_TYPE_ORDER_CANCEL_REJECT   = "9"
MSG_TYPE_BUSINESS_MESSAGE_REJECT = "j"

# --- Order Parameters Declaration ---
# ** IMPORTANT: Use realistic values for Sandbox **
product      = 'BTC-USD'      # Example product
order_type   = 'LIMIT'        # LIMIT or MARKET
side         = 'SELL'         # BUY or SELL
# Adjust quantity to meet minimum order size for BTC-USD if needed
base_quantity= '5'        # Example: Size of the order in base currency (BTC)
# Adjust price to be near the current market price in the sandbox
limit_price  = '2'        # Example: Required for LIMIT orders (e.g., $50,000)

# --- Helper Functions ---
def build_new_order_message():
    """ Builds a NewOrderSingle message with realistic example values. """
    new_order = fix.Message()
    header = new_order.getHeader()
    header.setField(fix.MsgType(MSG_TYPE_NEW_ORDER_SINGLE)) # 35=D

    cl_ord_id = str(uuid.uuid4()) # UUID for client order ID
    new_order.setField(fix.StringField(TAG_CL_ORD_ID, cl_ord_id))      # 11
    new_order.setField(fix.StringField(TAG_SYMBOL, product))           # 55
    side_code = '2' if side.upper() == 'SELL' else '1'
    new_order.setField(fix.CharField(TAG_SIDE, side_code))             # 54
    new_order.setField(fix.StringField(TAG_ORDER_QTY, base_quantity))  # 38

    ord_type_code = '2' if order_type.upper() == 'LIMIT' else '1'
    new_order.setField(fix.CharField(TAG_ORD_TYPE, ord_type_code))     # 40
    if order_type.upper() == 'LIMIT':
        new_order.setField(fix.StringField(TAG_PRICE, limit_price))    # 44

    new_order.setField(fix.CharField(TAG_TIME_IN_FORCE, '1')) # 59=1 (GTC)

    # Create and set TransactTime field
    transact_time_field = fix.TransactTime()                           # 60
    new_order.setField(transact_time_field)

    return new_order, cl_ord_id

def build_order_status_request(original_cl_ord_id):
    """ Builds an OrderStatusRequest message. """
    order_status = fix.Message()
    header = order_status.getHeader()
    header.setField(fix.MsgType(MSG_TYPE_ORDER_STATUS_REQUEST)) # 35=H

    status_cl_ord_id = str(uuid.uuid4()) # UUID for this request's ClOrdID
    order_status.setField(fix.StringField(TAG_CL_ORD_ID, status_cl_ord_id))        # 11
    # Set the ClOrdID (UUID) of the order we want status for
    order_status.setField(fix.StringField(TAG_ORIG_CL_ORD_ID, original_cl_ord_id)) # 41
    order_status.setField(fix.StringField(TAG_SYMBOL, product))                    # 55

    side_code = '2' if side.upper() == 'SELL' else '1'
    order_status.setField(fix.CharField(TAG_SIDE, side_code))                      # 54

    return order_status

def build_test_request(test_req_id):
    """ Builds a TestRequest message. """
    test_req_msg = fix.Message()
    header = test_req_msg.getHeader()
    header.setField(fix.MsgType(MSG_TYPE_TEST_REQUEST)) # 35=1
    test_req_msg.setField(fix.StringField(TAG_TEST_REQ_ID, test_req_id)) # 112
    return test_req_msg


# --- FIX Application Class ---
class FixApplication(fix.Application):
    def __init__(self):
        super().__init__()
        self.sessionID = None
        self.logged_on = False
        self.order_placed_clordid = None
        self.order_event = threading.Event()
        self.pending_test_req_id = None

    def onCreate(self, sessionID):
        self.sessionID = sessionID
        print(f"Session created: {sessionID}")

    def onLogon(self, sessionID):
        self.logged_on = True
        print(f"Logon successful: {sessionID}")
        # --- Step 1: Logon complete, now send Test Request ---
        self.send_test_request(sessionID)

    def onLogout(self, sessionID):
        self.logged_on = False
        print(f"Logout: {sessionID}")
        self.pending_test_req_id = None

    def toAdmin(self, message, sessionID):
        """ Prepares and signs Logon, handles other admin messages. """
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()

        try:
            if msg_type_val == MSG_TYPE_LOGON:
                print("--- Preparing Logon Message (toAdmin) ---")
                # Set Logon fields (same as before)
                message.setField(fix.IntField(TAG_ENCRYPT_METHOD, 0))
                message.setField(fix.IntField(TAG_HEART_BT_INT, 30))
                message.setField(fix.CharField(TAG_RESET_SEQ_NUM_FLAG, 'Y'))
                message.setField(fix.StringField(TAG_USERNAME, API_KEY))
                message.setField(fix.StringField(TAG_PASSWORD, PASSPHRASE))
                message.setField(fix.StringField(TAG_DEFAULT_APPL_VER_ID, DEFAULT_APPL_VER_ID))
                message.setField(fix.CharField(TAG_CANCEL_ORDERS_ON_DISCONNECT, 'Y'))

                # Extract fields for signing (same as before)
                sending_time_field = fix.SendingTime()
                msg_seq_num_field = fix.MsgSeqNum()
                sender_comp_id_field = fix.SenderCompID()
                target_comp_id_field = fix.TargetCompID()
                password_field = fix.Password()
                message.getHeader().getField(sending_time_field)
                message.getHeader().getField(msg_seq_num_field)
                message.getHeader().getField(sender_comp_id_field)
                message.getHeader().getField(target_comp_id_field)
                if message.isSetField(password_field):
                    message.getField(password_field)
                    password_value = password_field.getValue()
                else:
                    print("CRITICAL ERROR: Password field (554) not found in Logon message before signing.")
                    return

                # Generate and set signature (same as before)
                signature = self.sign(
                    sending_time_field.getString(), msg_type_val, msg_seq_num_field.getString(),
                    sender_comp_id_field.getString(), target_comp_id_field.getString(), password_value
                )
                message.setField(fix.IntField(TAG_RAW_DATA_LENGTH, len(signature)))
                message.setField(fix.StringField(TAG_RAW_DATA, signature))

                print(">>> Sending Admin (Logon):")
                print(message.toString().replace('\x01', '|'))

            elif msg_type_val == MSG_TYPE_TEST_REQUEST:
                 print(f">>> Sending Admin ({msg_type_val}):")
                 print(message.toString().replace('\x01', '|'))
            # else:
            #     # Optionally print other outgoing admin messages like heartbeats
            #     print(f">>> Sending Admin ({msg_type_val}): {message.toString().replace(chr(1), '|')}")

        except Exception as e:
             print(f"Error in toAdmin for MsgType {msg_type_val}: {e}")


    def fromAdmin(self, message, sessionID):
        """ Handles incoming admin messages, including Heartbeat response to TestRequest. """
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()

        print(f"<<< Received Admin ({msg_type_val}):")
        # Print raw message if needed for debugging admin messages
        # print(f"  Raw Admin Message: {message.toString().replace(chr(1), '|')}")

        try:
            if msg_type_val == MSG_TYPE_HEARTBEAT: # '0'
                test_req_id_field = fix.TestReqID()
                if self.pending_test_req_id and message.isSetField(test_req_id_field):
                    message.getField(test_req_id_field)
                    received_test_req_id = test_req_id_field.getValue()
                    print(f"  Heartbeat contains TestReqID (112): {received_test_req_id}")
                    if received_test_req_id == self.pending_test_req_id:
                        print(f"  +++ Test Request {self.pending_test_req_id} Confirmed +++")
                        self.pending_test_req_id = None
                        print("  Triggering order placement...")
                        threading.Thread(target=self.place_order, args=(sessionID,), daemon=True).start()
                    else:
                         print(f"  WARNING: Received TestReqID {received_test_req_id} does not match pending {self.pending_test_req_id}")

            elif msg_type_val == MSG_TYPE_LOGOUT: # '5'
                # (Logic remains the same)
                reason_field = fix.StringField(TAG_TEXT)
                if message.isSetField(reason_field):
                    message.getField(reason_field)
                    print(f"  Logout Reason (58): {reason_field.getValue()}")
                self.logged_on = False
                self.pending_test_req_id = None

            elif msg_type_val == MSG_TYPE_REJECT: # '3' (Session Reject)
                 # (Logic remains the same)
                ref_seq_num_field = fix.RefSeqNum()
                reason_field = fix.SessionRejectReason()
                text_field = fix.Text()
                ref_tag_id_field = fix.RefTagID()
                ref_msg_type_field = fix.RefMsgType()

                if message.isSetField(ref_seq_num_field):
                     message.getField(ref_seq_num_field)
                     print(f"  RefSeqNum (45): {ref_seq_num_field.getValue()}")
                if message.isSetField(reason_field):
                     message.getField(reason_field)
                     print(f"  SessionRejectReason (373): {reason_field.getValue()}")
                if message.isSetField(text_field):
                     message.getField(text_field)
                     print(f"  Text (58): {text_field.getValue()}")
                if message.isSetField(ref_tag_id_field):
                     message.getField(ref_tag_id_field)
                     print(f"  RefTagID (371): {ref_tag_id_field.getValue()}")

                if message.isSetField(ref_seq_num_field) and ref_seq_num_field.getValue() == 1:
                     print("  ERROR: Logon message appears to have been rejected by the server.")

                if message.isSetField(ref_msg_type_field):
                     message.getField(ref_msg_type_field)
                     if ref_msg_type_field.getValue() == MSG_TYPE_TEST_REQUEST:
                          print("  ERROR: Our TestRequest was rejected.")
                          self.pending_test_req_id = None

        except fix.FieldNotFound as e:
            print(f"  Error parsing admin message: Field not found - {e}")
        except Exception as e:
            print(f"  Error processing incoming admin message: {e}")


    def toApp(self, message, sessionID):
        """ Handles outgoing application messages. Ensures TransactTime is set. """
        header = message.getHeader()
        # Ensure TransactTime (Tag 60) is set if sending an App message
        if not header.isSetField(TAG_TRANSACT_TIME): # Use constant 60
             print("  [toApp] Setting missing TransactTime (60)")
             transact_time_field = fix.TransactTime()
             header.setField(transact_time_field)

        msgType = fix.MsgType()
        header.getField(msgType)
        print(f">>> Sending App ({msgType.getValue()}):")
        print(message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        """ Handles incoming application messages (Exec Reports, etc.). Prints raw message. """
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()

        print(f"<<< Received App ({msg_type_val}):")
        # --- Print the raw message string ---
        print(f"  Raw Message: {message.toString().replace(chr(1), '|')}")
        # ------------------------------------

        try:
            if msg_type_val == MSG_TYPE_EXECUTION_REPORT: # '8'
                # Define field objects to extract data
                clordid_field = fix.ClOrdID()
                origclordid_field = fix.OrigClOrdID()
                orderid_field = fix.OrderID()
                exectype_field = fix.ExecType()
                ordstatus_field = fix.OrdStatus()
                leavesqty_field = fix.LeavesQty()
                cumqty_field = fix.CumQty()
                avgpx_field = fix.AvgPx()
                lastpx_field = fix.LastPx()
                lastqty_field = fix.LastQty()
                text_field = fix.Text()
                ord_rej_reason_field = fix.OrdRejReason()

                # Extract required fields first
                exec_type = message.getField(exectype_field) if message.isSetField(exectype_field) else "N/A"
                ord_status = message.getField(ordstatus_field) if message.isSetField(ordstatus_field) else "N/A"
                print(f"  ExecType (150): {exec_type}")
                print(f"  OrdStatus (39): {ord_status}")

                # Extract and print optional fields
                current_clordid = message.getField(clordid_field) if message.isSetField(clordid_field) else None
                current_origclordid = message.getField(origclordid_field) if message.isSetField(origclordid_field) else None
                if current_clordid: print(f"  ClOrdID (11): {current_clordid}")
                if current_origclordid: print(f"  OrigClOrdID (41): {current_origclordid}")

                # Signal if this ExecReport is for the order we placed
                if (current_clordid == self.order_placed_clordid or
                    current_origclordid == self.order_placed_clordid):
                     if not self.order_event.is_set():
                          print("  Signaling order event received.")
                          self.order_event.set()

                if message.isSetField(orderid_field): print(f"  OrderID (37): {message.getField(orderid_field)}")
                if message.isSetField(leavesqty_field): print(f"  LeavesQty (151): {message.getField(leavesqty_field)}")
                if message.isSetField(cumqty_field): print(f"  CumQty (14): {message.getField(cumqty_field)}")
                if message.isSetField(avgpx_field): print(f"  AvgPx (6): {message.getField(avgpx_field)}")
                if message.isSetField(lastpx_field): print(f"  LastPx (31): {message.getField(lastpx_field)}")
                if message.isSetField(lastqty_field): print(f"  LastQty (32): {message.getField(lastqty_field)}")
                if message.isSetField(text_field): print(f"  Text (58): {message.getField(text_field)}")
                if message.isSetField(ord_rej_reason_field): print(f"  OrdRejReason (103): {message.getField(ord_rej_reason_field)}")

            elif msg_type_val == MSG_TYPE_ORDER_CANCEL_REJECT: # '9'
                 # Define necessary fields
                 clordid_field = fix.ClOrdID()
                 origclordid_field = fix.OrigClOrdID()
                 ordstatus_field = fix.OrdStatus()
                 cxlrejresponse_field = fix.CxlRejResponseTo()
                 cxlrejreason_field = fix.CxlRejReason()
                 text_field = fix.Text()

                 # Extract and print fields
                 if message.isSetField(clordid_field): print(f"  ClOrdID (11): {message.getField(clordid_field)}")
                 current_origclordid = message.getField(origclordid_field) if message.isSetField(origclordid_field) else None
                 if current_origclordid:
                     print(f"  OrigClOrdID (41): {current_origclordid}")
                     if current_origclordid == self.order_placed_clordid and not self.order_event.is_set():
                          print("  Signaling order event received (Cancel Reject).")
                          self.order_event.set()
                 if message.isSetField(ordstatus_field): print(f"  OrdStatus (39): {message.getField(ordstatus_field)}")
                 if message.isSetField(cxlrejresponse_field): print(f"  CxlRejResponseTo (434): {message.getField(cxlrejresponse_field)}")
                 if message.isSetField(cxlrejreason_field): print(f"  CxlRejReason (102): {message.getField(cxlrejreason_field)}")
                 if message.isSetField(text_field): print(f"  Text (58): {message.getField(text_field)}")

            elif msg_type_val == MSG_TYPE_BUSINESS_MESSAGE_REJECT: # 'j'
                 # Define necessary fields
                 ref_msg_type_field = fix.RefMsgType()
                 rej_reason_field = fix.BusinessRejectReason()
                 text_field = fix.Text()
                 # Extract and print fields
                 if message.isSetField(ref_msg_type_field): print(f"  RefMsgType (372): {message.getField(ref_msg_type_field)}")
                 if message.isSetField(rej_reason_field): print(f"  BusinessRejectReason (380): {message.getField(rej_reason_field)}")
                 if message.isSetField(text_field): print(f"  Text (58): {message.getField(text_field)}")

        except fix.FieldNotFound as e:
            print(f"  Error parsing app message: Field not found - {e}")
        except Exception as e:
            print(f"  Error processing incoming app message: {e}")


    def sign(self, sending_time, msg_type, seq_num, sender_comp, target_comp, password):
        """ Generates HMAC-SHA256 signature for Logon, includes debug prints. """
        data_to_sign = f"{sending_time}\x01{msg_type}\x01{seq_num}\x01{sender_comp}\x01{target_comp}\x01{password}"
        print(f"  [DEBUG SIGN] Data to sign: '{data_to_sign.replace(chr(1), '|')}'")
        try:
            secret_bytes = base64.b64decode(API_SECRET)
            # print(f"  [DEBUG SIGN] Secret decoded successfully (length: {len(secret_bytes)})") # Optional: uncomment if needed
            hmac_digest = hmac.new(secret_bytes, data_to_sign.encode('utf-8'), hashlib.sha256).digest()
            signature = base64.b64encode(hmac_digest).decode('utf-8')
            # print(f"  [DEBUG SIGN] Generated Signature: {signature}") # Optional: uncomment if needed
            return signature
        except Exception as e:
            print(f"  [DEBUG SIGN] Error during signing: {e}")
            raise

    def send_test_request(self, sessionID):
        """ Builds and sends a TestRequest message after successful logon. """
        if not self.logged_on:
            print("Cannot send Test Request: Not logged on.")
            return
        try:
            test_req_id = f"test-{uuid.uuid4()}"
            self.pending_test_req_id = test_req_id
            test_req_msg = build_test_request(test_req_id)
            print(f"\n--- Sending Test Request (TestReqID: {test_req_id}) ---")
            fix.Session.sendToTarget(test_req_msg, sessionID)
            print("Test Request Sent.")
        except fix.SessionNotFound:
            print(f"Error sending Test Request: Session '{sessionID}' not found.")
        except Exception as e:
            print(f"Error sending Test Request: {e}")

    def place_order(self, sessionID):
        """ Builds and sends a NewOrderSingle message. Called after TestRequest confirmation. """
        if not self.logged_on:
            print("Cannot place order: Not logged on.")
            return
        try:
            new_order, cl_ord_id = build_new_order_message()
            self.order_placed_clordid = cl_ord_id
            self.order_event.clear()
            print(f"\n--- Placing Order (ClOrdID: {cl_ord_id}) ---")
            fix.Session.sendToTarget(new_order, sessionID)
            print("New Order Sent.")

            print("Waiting up to 10s for order Execution Report (ack/reject)...")
            if self.order_event.wait(timeout=10.0):
                 print("Received an Execution Report/Reject for the order.")
                 self.request_order_status(sessionID)
            else:
                 print("Timed out waiting for initial Execution Report. Requesting status anyway.")
                 self.request_order_status(sessionID)

        except fix.SessionNotFound:
            print(f"Error placing order: Session '{sessionID}' not found (perhaps disconnected?).")
        except Exception as e:
            print(f"Error placing order: {e}")

    def request_order_status(self, sessionID):
        """ Waits briefly, then sends an OrderStatusRequest. """
        print("Waiting 3s before sending status request...")
        time.sleep(3)
        if not self.order_placed_clordid:
            print("Cannot request order status: No order ClOrdID available.")
            return

        try:
            if not fix.Session.isLoggedOn(sessionID):
                 print(f"Cannot request status: Session '{sessionID}' is no longer logged on.")
                 return

            status_request = build_order_status_request(self.order_placed_clordid)
            print(f"\n--- Requesting Status for Order (OrigClOrdID: {self.order_placed_clordid}) ---")
            fix.Session.sendToTarget(status_request, sessionID)
            print("Order Status Request Sent.")
        except fix.SessionNotFound:
            print(f"Error requesting status: Session '{sessionID}' not found.")
        except Exception as e:
            print(f"Error requesting order status: {e}")

# --- Signal Handler ---
initiator = None
def shutdown_handler(signum, frame):
    # (Implementation is the same as before)
    print(f"\nReceived signal {signum}. Shutting down...")
    global initiator
    if initiator and not initiator.isStopped():
        print("Stopping QuickFIX initiator...")
        initiator.stop()
        print("Initiator stopped.")
    time.sleep(1)
    print("Exiting script.")
    sys.exit(0)

# --- Main Execution ---
def main():
    # (Implementation is the same as before)
    global initiator

    print("--- Configuration ---")
    print(f"SVC_ACCOUNTID (SenderCompID): {SVC_ACCOUNTID}")
    print(f"API_KEY (Username):           {API_KEY}")
    print(f"PASSPHRASE:                   {'*' * len(PASSPHRASE) if PASSPHRASE else 'None'}")
    print(f"API_SECRET:                   {'*' * len(API_SECRET) if API_SECRET else 'None'}")
    print(f"FIX Host:                     {FIX_HOST}:{FIX_PORT}")
    print(f"FIX Version:                  {FIX_VERSION} (DefaultApplVerID: {DEFAULT_APPL_VER_ID})")
    print("---------------------")

    config_path = os.path.join(SESSION_PATH, "fix_client_sandbox.cfg")
    try:
        with open(config_path, 'w') as cfg_file:
            cfg_file.write(SESSION_CONFIG)
        print(f"QuickFIX config written to: {config_path}")
    except IOError as e:
        print(f"Error writing config file '{config_path}': {e}")
        sys.exit(1)

    try:
        settings = fix.SessionSettings(config_path)
        app = FixApplication()
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        # Using SSLSocketInitiator based on previous finding that it worked
        initiator = fix.SSLSocketInitiator(app, storeFactory, settings, logFactory)
    except fix.ConfigError as e:
         print(f"QuickFIX Configuration Error: {e}")
         sys.exit(1)
    except Exception as e:
        print(f"Error creating QuickFIX initiator components: {e}")
        sys.exit(1)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("Starting initiator...")
    try:
        initiator.start()
        print("Initiator started. Waiting for connection and logon...")

        while True:
            time.sleep(1)
            if initiator.isStopped():
                 print("Initiator reported stopped. Exiting main loop.")
                 break

    except (KeyboardInterrupt, SystemExit):
        print("Shutdown initiated by user or system signal.")
    except Exception as e:
         print(f"An unexpected error occurred in the main loop: {e}")
    finally:
        if initiator and not initiator.isStopped():
            print("Ensuring initiator is stopped in finally block...")
            initiator.stop()
        print("Main function finished.")


if __name__ == "__main__":
    main()