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
    print("\nExample Linux/macOS export:")
    print("  export SVC_ACCOUNTID='your_api_key'")
    print("  export API_KEY='your_api_key'")
    print("  export PASSPHRASE='your_passphrase'")
    print("  export SECRET_KEY='your_secret_key'")
    print("\nExample Windows (cmd):")
    print("  set SVC_ACCOUNTID=your_api_key")
    print("  set API_KEY=your_api_key")
    print("  set PASSPHRASE=your_passphrase")
    print("  set SECRET_KEY=your_secret_key")
    sys.exit(1)

if SVC_ACCOUNTID != API_KEY:
    # Coinbase uses the API Key for both SenderCompID and Username (Tag 553)
    print("Warning: SVC_ACCOUNTID and API_KEY differ.")
    print(f"         Using SVC_ACCOUNTID='{SVC_ACCOUNTID}' for SenderCompID")
    print(f"         Using API_KEY='{API_KEY}' for Username (Tag 553)")
    # Ensure API_KEY is used for Username if they differ intentionally
    # If they should be the same, set API_KEY=SVC_ACCOUNTID above or fix env vars.

# Ensure log and session directories exist
os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)

# --- Session Configuration String ---
# Note: UseDataDictionary=N means less validation, okay for sandbox but Y is better for prod.
# CancelOrdersOnDisconnect=Y in the config *might* be redundant if Tag 8013 is sent in Logon,
# but doesn't hurt. ResetOnLogon=Y is typical for resetting sequence numbers on connect.
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
ReconnectInterval=10
ValidateUserDefinedFields=N
ValidateIncomingMessage=N
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
SocketConnectPort={FIX_PORT}
FileLogPath={LOG_PATH}
# Coinbase Specific Logon Field (set also in toAdmin)
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

# Message types (as strings)
MSG_TYPE_LOGON                 = "A"
MSG_TYPE_LOGOUT                = "5"
MSG_TYPE_HEARTBEAT             = "0"
MSG_TYPE_TEST_REQUEST          = "1"
MSG_TYPE_RESEND_REQUEST        = "2"
MSG_TYPE_REJECT                = "3"
MSG_TYPE_SEQUENCE_RESET        = "4"
MSG_TYPE_NEW_ORDER_SINGLE      = "D"
MSG_TYPE_ORDER_STATUS_REQUEST  = "H"
MSG_TYPE_EXECUTION_REPORT      = "8"
MSG_TYPE_ORDER_CANCEL_REJECT   = "9"
MSG_TYPE_BUSINESS_MESSAGE_REJECT = "j"

# --- Order Parameters Declaration ---
product      = 'BTC-USD' # Example product
order_type   = 'LIMIT'   # LIMIT or MARKET
side         = 'SELL'    # BUY or SELL
base_quantity= '0.0001'  # Size of the order in base currency (BTC)
limit_price  = '100000'  # Required for LIMIT orders

# --- Helper Functions to Build Order Messages ---
def build_new_order_message():
    """
    Build a NewOrderSingle (MsgType 'D') to place an order.
    Returns a tuple (new_order_message, cl_ord_id).
    """
    new_order = fix.Message()
    header = new_order.getHeader()
    header.setField(fix.MsgType(MSG_TYPE_NEW_ORDER_SINGLE)) # 35=D

    cl_ord_id = f"test-{uuid.uuid4()}" # Generate a unique client order ID
    new_order.setField(fix.StringField(TAG_CL_ORD_ID, cl_ord_id))      # 11=Client Order ID
    new_order.setField(fix.StringField(TAG_SYMBOL, product))           # 55=Symbol (e.g., BTC-USD)

    # Set Side (54): 1=Buy, 2=Sell
    side_code = '2' if side.upper() == 'SELL' else '1'
    new_order.setField(fix.CharField(TAG_SIDE, side_code))             # 54=Side

    # Set OrderQty (38)
    new_order.setField(fix.StringField(TAG_ORDER_QTY, base_quantity))  # 38=Order Quantity

    # Set OrdType (40): 1=Market, 2=Limit
    ord_type_code = '2' if order_type.upper() == 'LIMIT' else '1'
    new_order.setField(fix.CharField(TAG_ORD_TYPE, ord_type_code))     # 40=Order Type

    # Set Price (44) only for Limit orders
    if order_type.upper() == 'LIMIT':
        new_order.setField(fix.StringField(TAG_PRICE, limit_price))    # 44=Price

    # Set TimeInForce (59) - Example: 1=Good Till Cancel (GTC)
    # Other common values: 3=ImmediateOrCancel (IOC), 4=FillOrKill (FOK)
    new_order.setField(fix.CharField(59, '1')) # 59=TimeInForce (GTC)

    # Set TransactTime (60)
    transact_time = fix.UTCTimestamp() # Creates timestamp with millisecond precision
    new_order.setField(transact_time)                                  # 60=TransactTime

    return new_order, cl_ord_id

def build_order_status_request(original_cl_ord_id):
    """
    Build an Order Status Request (MsgType 'H') message using the original order's ClOrdID.
    """
    order_status = fix.Message()
    header = order_status.getHeader()
    header.setField(fix.MsgType(MSG_TYPE_ORDER_STATUS_REQUEST)) # 35=H

    # Required fields for OrderStatusRequest according to standard FIX & likely Coinbase
    status_cl_ord_id = f"stat-{uuid.uuid4()}" # Needs its own unique ClOrdID
    order_status.setField(fix.StringField(TAG_CL_ORD_ID, status_cl_ord_id))        # 11=ClOrdID (for this status request)
    order_status.setField(fix.StringField(TAG_ORIG_CL_ORD_ID, original_cl_ord_id)) # 41=OrigClOrdID (the order you want status for)
    order_status.setField(fix.StringField(TAG_SYMBOL, product))                    # 55=Symbol (of the original order)

    # Side is often required or helpful for exchanges to locate the order
    side_code = '2' if side.upper() == 'SELL' else '1'
    order_status.setField(fix.CharField(TAG_SIDE, side_code))                      # 54=Side (of the original order)

    return order_status

# --- FIX Application Class ---
class FixApplication(fix.Application):
    def __init__(self):
        super().__init__()
        self.sessionID = None
        self.logged_on = False
        self.order_placed_clordid = None # Store the ClOrdID of the placed order
        self.order_event = threading.Event() # To signal when an order ack/reject is received

    def onCreate(self, sessionID):
        self.sessionID = sessionID
        print(f"Session created: {sessionID}")

    def onLogon(self, sessionID):
        self.logged_on = True
        print(f"Logon successful: {sessionID}")
        # --- Step 1: Logon complete, now place the order ---
        self.place_order(sessionID)

    def onLogout(self, sessionID):
        self.logged_on = False
        print(f"Logout: {sessionID}")

    def toAdmin(self, message, sessionID):
        """Called when sending an admin message (Logon, Logout, Heartbeat, etc.)"""
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)

        if msgType.getValue() == MSG_TYPE_LOGON:
            # --- Populate Logon Message ---
            message.setField(fix.IntField(TAG_ENCRYPT_METHOD, 0))       # 98=0 (No encryption within FIX message itself)
            message.setField(fix.IntField(TAG_HEART_BT_INT, 30))        # 108=30 (Heartbeat interval in seconds)
            message.setField(fix.CharField(TAG_RESET_SEQ_NUM_FLAG, 'Y'))# 141=Y (Reset sequence numbers on logon)

            # Coinbase Specific Credentials
            message.setField(fix.StringField(TAG_USERNAME, API_KEY))         # 553=API Key
            message.setField(fix.StringField(TAG_PASSWORD, PASSPHRASE))      # 554=API Passphrase
            message.setField(fix.StringField(TAG_DEFAULT_APPL_VER_ID, DEFAULT_APPL_VER_ID)) # 1137=App Version (e.g., 9 for FIX 5.0 SP2)

            # Coinbase Specific Logon Options (Refer to their FIX docs)
            message.setField(fix.CharField(TAG_CANCEL_ORDERS_ON_DISCONNECT, 'Y')) # 8013=Y (Recommended)
            # message.setField(fix.CharField(9406, 'N')) # 9406=DropCopyFlag (optional, 'N' for order entry)

            # --- Signing Logic ---
            # Extract fields needed for signing AFTER they've been set
            sending_time_field = fix.SendingTime()
            msg_seq_num_field = fix.MsgSeqNum()
            sender_comp_id_field = fix.SenderCompID()
            target_comp_id_field = fix.TargetCompID()
            password_field = fix.Password() # Use fix.Password() to extract tag 554

            message.getHeader().getField(sending_time_field)
            message.getHeader().getField(msg_seq_num_field)
            message.getHeader().getField(sender_comp_id_field)
            message.getHeader().getField(target_comp_id_field)
            if message.isSetField(password_field):
                message.getField(password_field)
                password_value = password_field.getValue()
            else:
                print("CRITICAL ERROR: Password field (554) not found in Logon message before signing.")
                # Optionally raise an exception or handle error appropriately
                return # Avoid sending unsigned/incorrectly signed message

            # Generate the signature
            signature = self.sign(
                sending_time_field.getString(), # Use getString() for UTCTimestamp
                msgType.getValue(),
                msg_seq_num_field.getString(),  # Use getString() for SeqNum/Int
                sender_comp_id_field.getString(),
                target_comp_id_field.getString(),
                password_value
            )

            # Add signature to the message
            message.setField(fix.IntField(TAG_RAW_DATA_LENGTH, len(signature))) # 95=Length of signature
            message.setField(fix.StringField(TAG_RAW_DATA, signature))          # 96=Base64 encoded signature

            print(">>> Sending Admin (Logon):")
            print(message.toString().replace('\x01', '|'))
        else:
            # Print other outgoing admin messages (Heartbeat, etc.)
            print(f">>> Sending Admin ({msgType.getValue()}):")
            # print(message.toString().replace('\x01', '|')) # Optional: reduce noise for heartbeats

    def fromAdmin(self, message, sessionID):
        """Called when receiving an admin message"""
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()

        print(f"<<< Received Admin ({msg_type_val}):")
        # print(message.toString().replace('\x01', '|')) # Print full message if needed

        if msg_type_val == MSG_TYPE_LOGOUT:
            reason_field = fix.StringField(TAG_TEXT)
            if message.isSetField(reason_field):
                message.getField(reason_field)
                print(f"  Logout Reason (58): {reason_field.getValue()}")

    def toApp(self, message, sessionID):
        """Called when sending an application message (orders, status requests, etc.)"""
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        print(f">>> Sending App ({msgType.getValue()}):")
        print(message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        """Called when receiving an application message (ExecReports, Rejects, etc.)"""
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()

        print(f"<<< Received App ({msg_type_val}):")
        # print(message.toString().replace('\x01', '|')) # Optional: Print full message

        try:
            if msg_type_val == MSG_TYPE_EXECUTION_REPORT: # '8'
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

                message.getField(exectype_field)
                message.getField(ordstatus_field)

                exec_type = exectype_field.getValue()
                ord_status = ordstatus_field.getValue()

                print(f"  ExecType (150): {exec_type}")
                print(f"  OrdStatus (39): {ord_status}")

                if message.isSetField(clordid_field):
                    message.getField(clordid_field)
                    print(f"  ClOrdID (11): {clordid_field.getValue()}")
                    # If this matches the order we placed, signal that we got a response
                    if clordid_field.getValue() == self.order_placed_clordid:
                         self.order_event.set()
                if message.isSetField(origclordid_field): # Present in status responses
                     message.getField(origclordid_field)
                     print(f"  OrigClOrdID (41): {origclordid_field.getValue()}")
                     if origclordid_field.getValue() == self.order_placed_clordid:
                          self.order_event.set() # Also signal on status response
                if message.isSetField(orderid_field):
                    message.getField(orderid_field)
                    print(f"  OrderID (37): {orderid_field.getValue()}") # Exchange Order ID
                if message.isSetField(leavesqty_field):
                    message.getField(leavesqty_field)
                    print(f"  LeavesQty (151): {leavesqty_field.getValue()}")
                if message.isSetField(cumqty_field):
                    message.getField(cumqty_field)
                    print(f"  CumQty (14): {cumqty_field.getValue()}")
                if message.isSetField(avgpx_field):
                    message.getField(avgpx_field)
                    print(f"  AvgPx (6): {avgpx_field.getValue()}")
                if message.isSetField(lastpx_field):
                    message.getField(lastpx_field)
                    print(f"  LastPx (31): {lastpx_field.getValue()}")
                if message.isSetField(lastqty_field):
                    message.getField(lastqty_field)
                    print(f"  LastQty (32): {lastqty_field.getValue()}")
                if message.isSetField(text_field):
                    message.getField(text_field)
                    print(f"  Text (58): {text_field.getValue()}")
                if message.isSetField(ord_rej_reason_field):
                     message.getField(ord_rej_reason_field)
                     print(f"  OrdRejReason (103): {ord_rej_reason_field.getValue()}")


            elif msg_type_val == MSG_TYPE_ORDER_CANCEL_REJECT: # '9'
                clordid_field = fix.ClOrdID()
                origclordid_field = fix.OrigClOrdID()
                ordstatus_field = fix.OrdStatus()
                cxlrejresponse_field = fix.CxlRejResponseTo()
                cxlrejreason_field = fix.CxlRejReason()
                text_field = fix.Text()

                if message.isSetField(clordid_field):
                     message.getField(clordid_field)
                     print(f"  ClOrdID (11): {clordid_field.getValue()}")
                if message.isSetField(origclordid_field):
                     message.getField(origclordid_field)
                     print(f"  OrigClOrdID (41): {origclordid_field.getValue()}")
                     if origclordid_field.getValue() == self.order_placed_clordid:
                          self.order_event.set() # Signal even on reject
                if message.isSetField(ordstatus_field):
                     message.getField(ordstatus_field)
                     print(f"  OrdStatus (39): {ordstatus_field.getValue()}")
                if message.isSetField(cxlrejresponse_field):
                     message.getField(cxlrejresponse_field)
                     print(f"  CxlRejResponseTo (434): {cxlrejresponse_field.getValue()}")
                if message.isSetField(cxlrejreason_field):
                     message.getField(cxlrejreason_field)
                     print(f"  CxlRejReason (102): {cxlrejreason_field.getValue()}")
                if message.isSetField(text_field):
                     message.getField(text_field)
                     print(f"  Text (58): {text_field.getValue()}")

            elif msg_type_val == MSG_TYPE_BUSINESS_MESSAGE_REJECT: # 'j'
                 ref_msg_type = fix.RefMsgType()
                 rej_reason = fix.BusinessRejectReason()
                 text_field = fix.Text()
                 if message.isSetField(ref_msg_type):
                      message.getField(ref_msg_type)
                      print(f"  RefMsgType (372): {ref_msg_type.getValue()}")
                 if message.isSetField(rej_reason):
                      message.getField(rej_reason)
                      print(f"  BusinessRejectReason (380): {rej_reason.getValue()}")
                 if message.isSetField(text_field):
                      message.getField(text_field)
                      print(f"  Text (58): {text_field.getValue()}")


        except fix.FieldNotFound as e:
            print(f"  Error parsing message: Field not found - {e}")
        except Exception as e:
            print(f"  Error processing incoming app message: {e}")


    def sign(self, sending_time, msg_type, seq_num, sender_comp, target_comp, password):
        """
        Generates the HMAC-SHA256 signature for the Coinbase FIX Logon message.
        Fields MUST be concatenated with the SOH (\x01) delimiter.
        The API secret MUST be base64 decoded first.
        The final signature MUST be base64 encoded.
        """
        # Concatenate fields with SOH delimiter
        data_to_sign = f"{sending_time}\x01{msg_type}\x01{seq_num}\x01{sender_comp}\x01{target_comp}\x01{password}"

        try:
            # Decode the API secret from base64
            secret_bytes = base64.b64decode(API_SECRET)

            # Create HMAC-SHA256 digest
            hmac_digest = hmac.new(secret_bytes, data_to_sign.encode('utf-8'), hashlib.sha256).digest()

            # Encode the digest in base64
            signature = base64.b64encode(hmac_digest).decode('utf-8')
            return signature
        except Exception as e:
            print(f"Error during signing: {e}")
            # Handle error appropriately, maybe raise it or return None
            raise

    def place_order(self, sessionID):
        """Builds and sends a NewOrderSingle message."""
        try:
            new_order, cl_ord_id = build_new_order_message()
            self.order_placed_clordid = cl_ord_id # Store the ClOrdID
            self.order_event.clear() # Reset event before sending
            print(f"\n--- Placing Order (ClOrdID: {cl_ord_id}) ---")
            fix.Session.sendToTarget(new_order, sessionID)
            print("New Order Sent.")

            # --- Step 2: Wait for confirmation/reject then send Order Status Request ---
            print("Waiting for order Execution Report (ack/reject)...")
            # Wait for a short period for the execution report to arrive
            if self.order_event.wait(timeout=10.0): # Wait up to 10 seconds
                 print("Received an Execution Report/Reject for the order.")
                 # Use a thread to avoid blocking the main FIX thread
                 threading.Thread(target=self.request_order_status, args=(sessionID,)).start()
            else:
                 print("Timed out waiting for initial Execution Report. Requesting status anyway.")
                 # Proceed to request status even if timeout occurs
                 threading.Thread(target=self.request_order_status, args=(sessionID,)).start()

        except fix.SessionNotFound:
            print(f"Error placing order: Session '{sessionID}' not found.")
        except Exception as e:
            print(f"Error placing order: {e}")

    def request_order_status(self, sessionID):
        """Waits briefly, then sends an OrderStatusRequest."""
        time.sleep(3) # Wait a few seconds after placing the order or getting the ack
        if not self.order_placed_clordid:
            print("Cannot request order status: No order was placed in this session.")
            return

        try:
            status_request = build_order_status_request(self.order_placed_clordid)
            print(f"\n--- Requesting Status for Order (OrigClOrdID: {self.order_placed_clordid}) ---")
            fix.Session.sendToTarget(status_request, sessionID)
            print("Order Status Request Sent.")
        except fix.SessionNotFound:
            print(f"Error requesting status: Session '{sessionID}' not found.")
        except Exception as e:
            print(f"Error requesting order status: {e}")

# --- Signal Handler for Graceful Shutdown ---
initiator = None # Global variable to hold the initiator instance

def shutdown_handler(signum, frame):
    print(f"\nReceived signal {signum}. Shutting down...")
    global initiator
    if initiator and not initiator.isStopped():
        print("Stopping QuickFIX initiator...")
        initiator.stop()
        print("Initiator stopped.")
    # Allow some time for logout messages if needed
    time.sleep(1)
    sys.exit(0) # Exit gracefully

# --- Main Execution ---
def main():
    global initiator # Allow modification of the global variable

    # Write the SESSION_CONFIG to a temporary config file.
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
        initiator = fix.SocketInitiator(app, storeFactory, settings, logFactory)
    except fix.ConfigError as e:
         print(f"QuickFIX Configuration Error: {e}")
         sys.exit(1)
    except Exception as e:
        print(f"Error creating QuickFIX initiator components: {e}")
        sys.exit(1)

    # Set up signal handlers for graceful shutdown (Ctrl+C).
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print("Starting initiator...")
    try:
        initiator.start()
        print("Initiator started. Waiting for logon...")

        # Keep the main thread alive while the initiator runs in background threads.
        # The actual work (placing order, requesting status) is triggered by onLogon.
        while True:
            time.sleep(1)
            if not initiator.isLoggedOn(): # Check if session dropped unexpectedly
                 print("Detected session is not logged on. Waiting for reconnect or shutdown...")
                 # You might want more sophisticated logic here, e.g., exit after timeout
                 # For now, just keeps the loop running for reconnection attempts

    except (KeyboardInterrupt, SystemExit):
        print("Shutdown initiated by user or system.")
    except Exception as e:
         print(f"An unexpected error occurred in the main loop: {e}")
    finally:
        if initiator and not initiator.isStopped():
            print("Ensuring initiator is stopped in finally block...")
            initiator.stop()
        print("Exiting.")

if __name__ == "__main__":
    main()