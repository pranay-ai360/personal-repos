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
import queue  # For thread-safe communication
import uvicorn # ASGI server for FastAPI
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Environment & Configuration Reading ---
FIX_VERSION = os.environ.get("FIX_VERSION", "FIXT.1.1")
DEFAULT_APPL_VER_ID = os.environ.get("DEFAULT_APPL_VER_ID", "9")
SVC_ACCOUNTID = os.environ.get("SVC_ACCOUNTID")
TARGET_COMP_ID = os.environ.get("TARGET_COMP_ID", "Coinbase")
API_KEY = os.environ.get("API_KEY")
PASSPHRASE = os.environ.get("PASSPHRASE")
API_SECRET = os.environ.get("SECRET_KEY")
FIX_HOST = os.environ.get("FIX_HOST", "fix-ord.sandbox.exchange.coinbase.com")
FIX_PORT = int(os.environ.get("FIX_PORT", "6121")) # Ensure port is int
LOG_PATH = os.environ.get("LOG_PATH", "./Logs/")
SESSION_PATH = os.environ.get("SESSION_PATH", "./.sessions/")
FASTAPI_PORT = int(os.environ.get("FASTAPI_PORT", 9001)) # Port for FastAPI

# --- Input Validation ---
if not all([SVC_ACCOUNTID, API_KEY, PASSPHRASE, API_SECRET]):
    print("Error: Missing required environment variables (SVC_ACCOUNTID, API_KEY, PASSPHRASE, SECRET_KEY)")
    sys.exit(1)

# --- Clock Check ---
# **IMPORTANT:** ENSURE YOUR SYSTEM CLOCK IS ACCURATE (UTC)
print(f"--- System UTC Time Check: {datetime.datetime.utcnow().strftime('%Y%m%d-%H:%M:%S.%f')[:-3]} ---")
print("--- Ensure this time is accurate! (CRITICAL FOR FIX LOGON) ---")

if SVC_ACCOUNTID != API_KEY:
    print("Warning: SVC_ACCOUNTID and API_KEY differ.")
    print(f"         Using SVC_ACCOUNTID='{SVC_ACCOUNTID}' for SenderCompID (49)")
    print(f"         Using API_KEY='{API_KEY}' for Username (553)")

os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)

# --- Session Configuration String ---
SESSION_CONFIG = f"""
[DEFAULT]
ConnectionType=initiator
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=N
ReconnectInterval=10
SocketTimeout=15
ValidateUserDefinedFields=N
ValidateIncomingMessage=N
ResetOnLogon=Y
ResetOnLogout=N
ResetOnDisconnect=Y
SSLEnable=Y
SSLProtocols=TlsV1.2
SocketConnectPort={FIX_PORT}
FileLogPath={LOG_PATH}
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

# --- FIX Tag Constants ---
TAG_MSG_TYPE = 35; TAG_BEGIN_STRING = 8; TAG_SENDER_COMP_ID = 49; TAG_TARGET_COMP_ID = 56; TAG_MSG_SEQ_NUM = 34; TAG_SENDING_TIME = 52; TAG_ENCRYPT_METHOD = 98; TAG_HEART_BT_INT = 108; TAG_RESET_SEQ_NUM_FLAG = 141; TAG_USERNAME = 553; TAG_PASSWORD = 554; TAG_DEFAULT_APPL_VER_ID = 1137; TAG_RAW_DATA_LENGTH = 95; TAG_RAW_DATA = 96; TAG_TEXT = 58; TAG_CL_ORD_ID = 11; TAG_ORIG_CL_ORD_ID = 41; TAG_SYMBOL = 55; TAG_SIDE = 54; TAG_ORDER_QTY = 38; TAG_ORD_TYPE = 40; TAG_PRICE = 44; TAG_ORD_STATUS = 39; TAG_EXEC_TYPE = 150; TAG_LEAVES_QTY = 151; TAG_CUM_QTY = 14; TAG_AVG_PX = 6; TAG_LAST_PX = 31; TAG_LAST_QTY = 32; TAG_ORDER_ID = 37; TAG_EXEC_ID = 17; TAG_ORD_REJ_REASON = 103; TAG_CXL_REJ_REASON = 102; TAG_CXL_REJ_RESPONSE_TO = 434; TAG_CANCEL_ORDERS_ON_DISCONNECT = 8013; TAG_REF_SEQ_NUM = 45; TAG_REF_TAG_ID = 371; TAG_REF_MSG_TYPE = 372; TAG_SESSION_REJECT_REASON = 373; TAG_TEST_REQ_ID = 112; TAG_TRANSACT_TIME = 60; TAG_TIME_IN_FORCE = 59

# Message types (as strings)
MSG_TYPE_LOGON="A"; MSG_TYPE_LOGOUT="5"; MSG_TYPE_HEARTBEAT="0"; MSG_TYPE_TEST_REQUEST="1"; MSG_TYPE_RESEND_REQUEST="2"; MSG_TYPE_REJECT="3"; MSG_TYPE_SEQUENCE_RESET="4"; MSG_TYPE_NEW_ORDER_SINGLE="D"; MSG_TYPE_ORDER_STATUS_REQUEST="H"; MSG_TYPE_EXECUTION_REPORT="8"; MSG_TYPE_ORDER_CANCEL_REJECT="9"; MSG_TYPE_BUSINESS_MESSAGE_REJECT="j"

# --- Default Order Parameters ---
DEFAULT_PRODUCT = 'BTC-USD'
DEFAULT_ORDER_TYPE = 'LIMIT'

# --- FastAPI Pydantic Models ---
class OrderItem(BaseModel):
    takerOrderId: str
    takerUserId: int
    takerAction: str # Expect "BID" or "ASK"
    makerOrderId: str
    makerUserId: int
    price: float
    size: float
    timestamp: int
    makerOrderCompleted: bool
    takerOrderCompleted: bool

# --- Shared Queue for Orders ---
# Use LifoQueue if order matters for processing (last in, first out)
# Use Queue for FIFO (first in, first out)
order_queue = queue.Queue()

# --- FIX Application Class ---
class FixApplication(fix.Application):
    def __init__(self, order_queue_ref):
        super().__init__()
        self.sessionID = None
        self.logged_on = False
        # Track orders placed by this session: { clordid: {details}, ... }
        self.order_details = {}
        # Track responses received: { clordid/origclordid : [list_of_exec_reports] }
        self.order_responses = {}
        self.response_lock = threading.Lock() # Lock for accessing order_responses
        self.pending_test_req_id = None
        self.order_queue = order_queue_ref
        self.processing_thread = None
        self.stop_processing = threading.Event()

    # --- Standard Callbacks ---
    def onCreate(self, sessionID):
        self.sessionID = sessionID
        print(f"FIX Session created: {sessionID}")

    def onLogon(self, sessionID):
        self.logged_on = True
        print(f"FIX Logon successful: {sessionID}")
        if self.processing_thread is None or not self.processing_thread.is_alive():
            self.stop_processing.clear()
            self.processing_thread = threading.Thread(target=self.process_order_queue, daemon=True)
            self.processing_thread.start()
            print("FIX order processing thread started.")
        # Optional: Send initial Test Request
        self.send_test_request(sessionID)

    def onLogout(self, sessionID):
        self.logged_on = False
        print(f"FIX Logout: {sessionID}")
        self.pending_test_req_id = None
        self.stop_processing.set() # Signal processing thread to stop

    # --- Message Handling Callbacks ---
    def toAdmin(self, message, sessionID):
        # (Implementation is the same as before)
        msgType = fix.MsgType(); message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()
        try:
            if msg_type_val == MSG_TYPE_LOGON:
                print("--- Preparing Logon Message (toAdmin) ---")
                message.setField(fix.IntField(TAG_ENCRYPT_METHOD, 0)); message.setField(fix.IntField(TAG_HEART_BT_INT, 30)); message.setField(fix.CharField(TAG_RESET_SEQ_NUM_FLAG, 'Y')); message.setField(fix.StringField(TAG_USERNAME, API_KEY)); message.setField(fix.StringField(TAG_PASSWORD, PASSPHRASE)); message.setField(fix.StringField(TAG_DEFAULT_APPL_VER_ID, DEFAULT_APPL_VER_ID)); message.setField(fix.CharField(TAG_CANCEL_ORDERS_ON_DISCONNECT, 'Y'))
                sending_time_field = fix.SendingTime(); msg_seq_num_field = fix.MsgSeqNum(); sender_comp_id_field = fix.SenderCompID(); target_comp_id_field = fix.TargetCompID(); password_field = fix.Password()
                message.getHeader().getField(sending_time_field); message.getHeader().getField(msg_seq_num_field); message.getHeader().getField(sender_comp_id_field); message.getHeader().getField(target_comp_id_field)
                if message.isSetField(password_field): message.getField(password_field); password_value = password_field.getValue()
                else: print("CRITICAL ERROR: Password field (554) not found..."); return
                signature = self.sign(sending_time_field.getString(), msg_type_val, msg_seq_num_field.getString(), sender_comp_id_field.getString(), target_comp_id_field.getString(), password_value)
                message.setField(fix.IntField(TAG_RAW_DATA_LENGTH, len(signature))); message.setField(fix.StringField(TAG_RAW_DATA, signature))
                print(">>> Sending Admin (Logon):"); print(message.toString().replace('\x01', '|'))
            elif msg_type_val == MSG_TYPE_TEST_REQUEST:
                 print(f">>> Sending Admin ({msg_type_val}):"); print(message.toString().replace('\x01', '|'))
        except Exception as e: print(f"Error in toAdmin for MsgType {msg_type_val}: {e}")


    def fromAdmin(self, message, sessionID):
        # (Implementation is the same as before)
        msgType = fix.MsgType(); message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()
        print(f"<<< Received Admin ({msg_type_val}):")
        try:
            if msg_type_val == MSG_TYPE_HEARTBEAT:
                test_req_id_field = fix.TestReqID()
                if self.pending_test_req_id and message.isSetField(test_req_id_field):
                    message.getField(test_req_id_field); received_test_req_id = test_req_id_field.getValue()
                    print(f"  Heartbeat contains TestReqID (112): {received_test_req_id}")
                    if received_test_req_id == self.pending_test_req_id:
                        print(f"  +++ Test Request {self.pending_test_req_id} Confirmed +++"); self.pending_test_req_id = None
                    else: print(f"  WARNING: Received TestReqID {received_test_req_id} != pending {self.pending_test_req_id}")
            elif msg_type_val == MSG_TYPE_LOGOUT:
                reason_field = fix.StringField(TAG_TEXT)
                if message.isSetField(reason_field): message.getField(reason_field); print(f"  Logout Reason (58): {reason_field.getValue()}")
                self.logged_on = False; self.pending_test_req_id = None; self.stop_processing.set()
            elif msg_type_val == MSG_TYPE_REJECT:
                ref_seq_num_field=fix.RefSeqNum(); reason_field=fix.SessionRejectReason(); text_field=fix.Text(); ref_tag_id_field=fix.RefTagID(); ref_msg_type_field=fix.RefMsgType()
                if message.isSetField(ref_seq_num_field): message.getField(ref_seq_num_field); print(f"  RefSeqNum (45): {ref_seq_num_field.getValue()}")
                if message.isSetField(reason_field): message.getField(reason_field); print(f"  SessionRejectReason (373): {reason_field.getValue()}")
                if message.isSetField(text_field): message.getField(text_field); print(f"  Text (58): {text_field.getValue()}")
                if message.isSetField(ref_tag_id_field): message.getField(ref_tag_id_field); print(f"  RefTagID (371): {ref_tag_id_field.getValue()}")
                if message.isSetField(ref_seq_num_field) and ref_seq_num_field.getValue() == 1: print("  ERROR: Logon message rejected.")
                if message.isSetField(ref_msg_type_field):
                    message.getField(ref_msg_type_field)
                    if ref_msg_type_field.getValue() == MSG_TYPE_TEST_REQUEST: print("  ERROR: TestRequest rejected."); self.pending_test_req_id = None
        except Exception as e: print(f"  Error processing admin message: {e}")


    def toApp(self, message, sessionID):
        # (Implementation is the same as before)
        header = message.getHeader()
        if not header.isSetField(TAG_TRANSACT_TIME): print("  [toApp] Setting missing TransactTime (60)"); transact_time_field = fix.TransactTime(); header.setField(transact_time_field)
        msgType = fix.MsgType(); header.getField(msgType)
        print(f">>> Sending App ({msgType.getValue()}):"); print(message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        """ Handles incoming application messages, stores responses. """
        msgType = fix.MsgType(); message.getHeader().getField(msgType)
        msg_type_val = msgType.getValue()
        raw_msg_str = message.toString().replace(chr(1), '|')
        print(f"<<< Received App ({msg_type_val}):")
        print(f"  Raw Message: {raw_msg_str}")

        clordid_field = fix.ClOrdID()
        origclordid_field = fix.OrigClOrdID()
        order_key = None
        is_exec_report = False

        try:
            # Determine the key (ClOrdID or OrigClOrdID) to associate this response
            if message.isSetField(clordid_field):
                order_key = message.getField(clordid_field)
            if message.isSetField(origclordid_field):
                 # If OrigClOrdID is present (e.g., status response), use that as the primary key
                 order_key = message.getField(origclordid_field)

            if msg_type_val == MSG_TYPE_EXECUTION_REPORT: # '8'
                is_exec_report = True
                exectype_field=fix.ExecType(); ordstatus_field=fix.OrdStatus()
                exec_type = message.getField(exectype_field) if message.isSetField(exectype_field) else "N/A"
                ord_status = message.getField(ordstatus_field) if message.isSetField(ordstatus_field) else "N/A"
                print(f"  ExecType (150): {exec_type}")
                print(f"  OrdStatus (39): {ord_status}")
                # Print other relevant fields from previous version...
                if message.isSetField(11): print(f"  ClOrdID (11): {message.getField(11)}")
                if message.isSetField(41): print(f"  OrigClOrdID (41): {message.getField(41)}")
                if message.isSetField(37): print(f"  OrderID (37): {message.getField(37)}")
                if message.isSetField(151): print(f"  LeavesQty (151): {message.getField(151)}")
                if message.isSetField(14): print(f"  CumQty (14): {message.getField(14)}")
                if message.isSetField(6): print(f"  AvgPx (6): {message.getField(6)}")
                if message.isSetField(31): print(f"  LastPx (31): {message.getField(31)}")
                if message.isSetField(32): print(f"  LastQty (32): {message.getField(32)}")
                if message.isSetField(58): print(f"  Text (58): {message.getField(58)}")
                if message.isSetField(103): print(f"  OrdRejReason (103): {message.getField(103)}")

            elif msg_type_val == MSG_TYPE_ORDER_CANCEL_REJECT: # '9'
                 print("  Received Order Cancel Reject") # Add specific field parsing if needed
            elif msg_type_val == MSG_TYPE_BUSINESS_MESSAGE_REJECT: # 'j'
                 print("  Received Business Message Reject") # Add specific field parsing if needed

            # Store the raw response string associated with the order key
            if order_key:
                with self.response_lock:
                    if order_key not in self.order_responses:
                        self.order_responses[order_key] = []
                    self.order_responses[order_key].append(raw_msg_str)
                # If this is the first ack/reject for an order placed via queue, signal
                if order_key in self.order_details and 'event' in self.order_details[order_key]:
                    print(f"  Signaling event for order {order_key}")
                    self.order_details[order_key]['event'].set()


        except Exception as e: print(f"  Error processing app message: {e}")


    # --- Signing Function ---
    def sign(self, sending_time, msg_type, seq_num, sender_comp, target_comp, password):
        # (Implementation is the same as before)
        data_to_sign = f"{sending_time}\x01{msg_type}\x01{seq_num}\x01{sender_comp}\x01{target_comp}\x01{password}"
        # print(f"  [DEBUG SIGN] Data to sign: '{data_to_sign.replace(chr(1), '|')}'")
        try:
            secret_bytes = base64.b64decode(API_SECRET)
            hmac_digest = hmac.new(secret_bytes, data_to_sign.encode('utf-8'), hashlib.sha256).digest()
            signature = base64.b64encode(hmac_digest).decode('utf-8')
            return signature
        except Exception as e: print(f"  [DEBUG SIGN] Error during signing: {e}"); raise

    # --- Action Functions ---
    def send_test_request(self, sessionID):
        # (Implementation is the same as before)
        if not self.logged_on: print("Cannot send Test Request: Not logged on."); return
        try:
            test_req_id = f"test-{uuid.uuid4()}"; self.pending_test_req_id = test_req_id
            test_req_msg = build_test_request(test_req_id)
            print(f"\n--- Sending Test Request (TestReqID: {test_req_id}) ---")
            fix.Session.sendToTarget(test_req_msg, sessionID); print("Test Request Sent.")
        except Exception as e: print(f"Error sending Test Request: {e}"); self.pending_test_req_id = None

    def send_fix_order(self, sessionID, side, quantity, price, product_id=DEFAULT_PRODUCT, order_type_code=DEFAULT_ORDER_TYPE):
        """ Sends a NewOrderSingle message via the FIX session. """
        if not self.logged_on:
            print(f"Cannot send order: Not logged on to session {sessionID}.")
            return None # Indicate failure

        cl_ord_id = None # Initialize
        try:
            new_order = fix.Message()
            header = new_order.getHeader(); header.setField(fix.MsgType(MSG_TYPE_NEW_ORDER_SINGLE))
            cl_ord_id = str(uuid.uuid4()) # Generate UUID for this order
            new_order.setField(fix.StringField(TAG_CL_ORD_ID, cl_ord_id))
            new_order.setField(fix.StringField(TAG_SYMBOL, product_id))
            new_order.setField(fix.CharField(TAG_SIDE, side)) # 1=Buy, 2=Sell
            new_order.setField(fix.StringField(TAG_ORDER_QTY, str(quantity)))

            ord_type_fix = '2' if order_type_code.upper() == 'LIMIT' else '1'
            new_order.setField(fix.CharField(TAG_ORD_TYPE, ord_type_fix))
            if order_type_code.upper() == 'LIMIT':
                new_order.setField(fix.StringField(TAG_PRICE, str(price)))

            new_order.setField(fix.CharField(TAG_TIME_IN_FORCE, '1')) # GTC
            transact_time_field = fix.TransactTime(); new_order.setField(transact_time_field)

            print(f"\n--- Sending Order (ClOrdID: {cl_ord_id}, Side: {side}, Qty: {quantity}, Px: {price}) ---")
            fix.Session.sendToTarget(new_order, sessionID)
            print("  FIX Order Message Sent.")
            # Store details including an event to wait for the first response
            self.order_details[cl_ord_id] = {
                'side': side, 'qty': quantity, 'price': price,
                'status': 'SENT', 'event': threading.Event()
            }
            return cl_ord_id # Return the ID placed
        except fix.SessionNotFound:
            print(f"Error sending order: Session '{sessionID}' not found (disconnected?).")
        except Exception as e:
            print(f"Error sending FIX order (ClOrdID: {cl_ord_id}): {e}")
            if cl_ord_id in self.order_details: del self.order_details[cl_ord_id] # Clean up if send fails
        return None

    def send_order_status_request(self, sessionID, original_cl_ord_id):
        """ Sends an OrderStatusRequest. """
        if not self.logged_on: print(f"Cannot request status: Not logged on to session {sessionID}."); return
        if not original_cl_ord_id: print("Cannot request status: No original ClOrdID provided."); return

        try:
            # Check if session is still valid before sending
            session = fix.Session.lookupSession(sessionID)
            if not session or not session.isLoggedOn():
                 print(f"Cannot request status: Session '{sessionID}' is no longer valid/logged on.")
                 return

            status_request = build_order_status_request(original_cl_ord_id)
            print(f"\n--- Requesting Status for Order (OrigClOrdID: {original_cl_ord_id}) ---")
            fix.Session.sendToTarget(status_request, sessionID)
            print("  Order Status Request Sent.")
        except fix.SessionNotFound:
            print(f"Error requesting status: Session '{sessionID}' not found.")
        except Exception as e:
            print(f"Error requesting order status (OrigClOrdID: {original_cl_ord_id}): {e}")

    # --- Queue Processing ---
    def process_order_queue(self):
        """ Continuously checks the order queue and sends FIX orders. """
        print("FIX order processing thread waiting for logon...")
        while not self.logged_on:
            if self.stop_processing.is_set(): print("FIX order processing thread stopping before logon."); return
            time.sleep(0.5)

        print("FIX order processing thread active.")
        while not self.stop_processing.is_set():
            order_details = None
            try:
                order_details = self.order_queue.get(block=True, timeout=1.0)

                if order_details and self.logged_on and self.sessionID:
                    print(f"Processing order from queue: {order_details}")
                    side = order_details['side']; quantity = order_details['size']; price = order_details['price']

                    # Send the order via FIX
                    placed_clordid = self.send_fix_order(self.sessionID, side, quantity, price)

                    if placed_clordid:
                        # Wait briefly for the first ACK/Reject before requesting status
                        print(f"Waiting up to 5s for initial response for order {placed_clordid}...")
                        event = self.order_details[placed_clordid].get('event')
                        if event and event.wait(timeout=5.0):
                            print(f"Initial response received for {placed_clordid}.")
                        else:
                            print(f"Timed out waiting for initial response for {placed_clordid}. Requesting status anyway.")

                        # Now request status
                        self.send_order_status_request(self.sessionID, placed_clordid)
                    else:
                         print(f"Failed to send order for details: {order_details}")

                # Important: Mark task done *outside* the if block if get was successful
                if order_details:
                    self.order_queue.task_done()

            except queue.Empty: continue # Timeout, no order, loop again
            except Exception as e:
                print(f"Error in order processing thread: {e}")
                if order_details: self.order_queue.task_done() # Mark done even on error to prevent blocking
                time.sleep(1)

        print("FIX order processing thread finished.")

    # --- Method for FastAPI ---
    def request_order_placement(self, order_item: OrderItem):
        """ Puts order details onto the queue. """
        if self.logged_on:
            side_code = '1' if order_item.takerAction.upper() == 'BID' else '2'
            order_data = {'side': side_code, 'size': order_item.size, 'price': order_item.price}
            print(f"Queueing order request from API: {order_data}")
            self.order_queue.put(order_data)
            return {"status": "queued", "details": order_data}
        else:
            print("Cannot queue order: FIX session not logged on.")
            return {"status": "rejected", "reason": "FIX session not logged on"}

# --- FastAPI Application Setup ---
fix_app = FixApplication(order_queue)
api = FastAPI(title="FIX Order Gateway")

@api.post("/trades", status_code=status.HTTP_202_ACCEPTED) # Use 202 for accepted queueing
async def receive_trades(payload: List[OrderItem], request: Request):
    """ Receives a LIST of trade data items and queues corresponding FIX orders. """
    print(f"\n--- Received POST /trades request from {request.client.host} ---")
    processed_count = 0
    queued_results = []
    errors = []

    if not fix_app.logged_on:
         print("API Error: FIX session not logged on.")
         raise HTTPException(status_code=503, detail="FIX session not connected/logged on")

    if not payload:
         raise HTTPException(status_code=400, detail="Request body cannot be empty list.")

    for item in payload:
        try:
            print(f"  Processing trade item: Taker {item.takerUserId} {item.takerAction} / Maker {item.makerUserId} @ {item.price} x {item.size}")
            if item.takerUserId != 1:
                if item.takerAction.upper() in ["BID", "ASK"]:
                    result = fix_app.request_order_placement(item)
                    queued_results.append(result)
                    if result["status"] == "queued":
                         processed_count += 1
                    else: # Should only happen if logged_on status changes mid-request
                         errors.append({"input": item.dict(), "error": result.get("reason", "Failed to queue")})

                else:
                    print(f"  Skipping item: Invalid takerAction '{item.takerAction}'")
                    errors.append({"input": item.dict(), "error": f"Invalid takerAction: {item.takerAction}"})
            else:
                print(f"  Skipping item: takerUserId is 1")
        except Exception as e:
             print(f"  Error processing item {item}: {e}")
             errors.append({"input": item.dict(), "error": str(e)})


    print(f"--- Finished processing /trades request. Queued {processed_count} orders. Errors: {len(errors)} ---")
    return {"message": f"Received {len(payload)} items. Queued {processed_count} orders.", "results": queued_results, "errors": errors}

# --- Global Initiator Variable ---
initiator = None

# --- Signal Handler ---
def shutdown_handler(signum, frame):
    print(f"\nReceived signal {signum}. Initiating shutdown...")
    global initiator
    fix_app.stop_processing.set() # Signal queue processing thread to stop
    # Stop QuickFIX initiator (this should trigger onLogout)
    if initiator and not initiator.isStopped():
        print("Stopping QuickFIX initiator...")
        try:
            initiator.stop(True) # Force stop if necessary
        except: pass # Ignore errors during stop
        print("Initiator stopped.")
    # Give threads a moment to clean up
    time.sleep(2)
    print("Exiting script.")
    # Force exit if threads are stuck (though daemons should allow exit)
    os._exit(0) # Use os._exit for forceful termination if needed

# --- Main Execution ---
def run_fix_client():
    """ Starts and runs the QuickFIX initiator. """
    global initiator
    print("--- Starting FIX Client Thread ---")
    config_path = os.path.join(SESSION_PATH, "fix_client_sandbox.cfg")
    try:
        with open(config_path, 'w') as cfg_file: cfg_file.write(SESSION_CONFIG)
        print(f"QuickFIX config written to: {config_path}")
    except IOError as e: print(f"Error writing config file '{config_path}': {e}"); sys.exit(1)

    try:
        settings = fix.SessionSettings(config_path)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        initiator = fix.SSLSocketInitiator(fix_app, storeFactory, settings, logFactory)
    except Exception as e: print(f"Error creating QuickFIX initiator components: {e}"); sys.exit(1)

    try:
        initiator.start()
        print("FIX Initiator started. Running event loop.")
        # initiator.block() # block() waits for initiator to stop
        while not initiator.isStopped(): # Keep thread alive while QF runs
             time.sleep(1)
    except (KeyboardInterrupt, SystemExit): print("FIX client shutdown requested.")
    except Exception as e: print(f"An unexpected error occurred in the FIX client thread: {e}")
    finally:
        if initiator and not initiator.isStopped(): print("Ensuring FIX initiator is stopped..."); initiator.stop()
        print("--- FIX Client Thread Finished ---")


def run_fastapi_server():
    """ Starts the FastAPI Uvicorn server. """
    print(f"--- Starting FastAPI Server on 0.0.0.0:{FASTAPI_PORT} ---")
    try:
        # Run uvicorn. Config handles signals.
        config = uvicorn.Config(api, host="0.0.0.0", port=FASTAPI_PORT, log_level="info")
        server = uvicorn.Server(config)
        server.run() # This blocks until shutdown
    except Exception as e:
        print(f"FastAPI server error: {e}")
    finally:
        print("--- FastAPI Server Thread Finished ---")

if __name__ == "__main__":
    print("--- Main Application Start ---")
    # Print config details
    print("--- Configuration ---")
    print(f"SVC_ACCOUNTID (SenderCompID): {SVC_ACCOUNTID}")
    print(f"API_KEY (Username):           {API_KEY}")
    print(f"PASSPHRASE:                   {'*' * len(PASSPHRASE) if PASSPHRASE else 'None'}")
    print(f"API_SECRET:                   {'*' * len(API_SECRET) if API_SECRET else 'None'}")
    print(f"FIX Host:                     {FIX_HOST}:{FIX_PORT}")
    print(f"FastAPI Host:                 0.0.0.0:{FASTAPI_PORT}")
    print("---------------------")

    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Create threads
    # Use daemon=False if you want the main thread to explicitly wait using join()
    fix_thread = threading.Thread(target=run_fix_client, name="FIXClientThread")
    api_thread = threading.Thread(target=run_fastapi_server, name="FastAPIServerThread")

    # Start threads
    print("Starting FIX thread...")
    fix_thread.start()
    print("Starting API thread...")
    api_thread.start()

    # Keep the main thread alive and wait for threads to complete
    try:
        fix_thread.join() # Wait for FIX thread to finish (e.g., on shutdown)
        api_thread.join() # Wait for API thread to finish (e.g., on shutdown)
    except (KeyboardInterrupt, SystemExit):
        print("Main thread interrupted. Initiating shutdown via signal handler...")
        # Signal handler should be invoked to stop other threads
        shutdown_handler(signal.SIGINT, None) # Manually invoke if needed

    print("--- Main Application Finished ---")