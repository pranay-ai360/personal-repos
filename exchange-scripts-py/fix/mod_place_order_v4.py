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
import queue
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
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
FIX_PORT = int(os.environ.get("FIX_PORT", "6121"))
LOG_PATH = os.environ.get("LOG_PATH", "./Logs/")
SESSION_PATH = os.environ.get("SESSION_PATH", "./.sessions/")
FASTAPI_PORT = int(os.environ.get("FASTAPI_PORT", 9001))

# --- Input Validation ---
if not all([SVC_ACCOUNTID, API_KEY, PASSPHRASE, API_SECRET]):
    print("Error: Missing required environment variables (SVC_ACCOUNTID, API_KEY, PASSPHRASE, SECRET_KEY)")
    sys.exit(1)

# --- Clock Check ---
# **IMPORTANT:** ENSURE YOUR SYSTEM CLOCK IS ACCURATE (UTC)
print(f"--- System UTC Time Check: {datetime.datetime.utcnow().strftime('%Y%m%d-%H:%M:%S.%f')[:-3]} ---")
print("--- Ensure this time is accurate! (CRITICAL FOR FIX LOGON) ---")

if SVC_ACCOUNTID != API_KEY:
    print("Warning: SVC_ACCOUNTID and API_KEY differ.") # (Same warning as before)

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

# Order Statuses considered final
FINAL_ORD_STATUSES = {'2', '4', '5', '8', 'C'} # Filled, Canceled, Replaced, Rejected, Expired

# --- Default Order Parameters ---
DEFAULT_PRODUCT = 'BTC-USD'
DEFAULT_ORDER_TYPE = 'LIMIT'

# --- FastAPI Pydantic Models ---
class OrderItem(BaseModel):
    takerOrderId: str
    takerUserId: int
    takerAction: str
    makerOrderId: str
    makerUserId: int
    price: float
    size: float
    timestamp: int
    makerOrderCompleted: bool
    takerOrderCompleted: bool

# --- Shared Queue for Orders ---
order_queue = queue.Queue()

# --- FIX Application Class ---
class FixApplication(fix.Application):
    def __init__(self, order_queue_ref):
        super().__init__()
        self.sessionID = None
        self.logged_on = False
        # Track orders placed: { clordid: {'side': '1', 'qty': 1.0, 'price': 10000, 'latest_ord_status': '0', 'final_status_reached': False}, ... }
        self.order_details = {}
        self.details_lock = threading.Lock() # Lock for accessing order_details
        self.pending_test_req_id = None
        self.order_queue = order_queue_ref
        self.processing_thread = None
        self.stop_processing = threading.Event()

    # --- Helper Functions as Methods ---
    def build_new_order_message(self, side, quantity, price, product_id=DEFAULT_PRODUCT, order_type_code=DEFAULT_ORDER_TYPE):
        """ Builds a NewOrderSingle message. """
        new_order = fix.Message()
        header = new_order.getHeader(); header.setField(fix.MsgType(MSG_TYPE_NEW_ORDER_SINGLE))
        cl_ord_id = str(uuid.uuid4())
        new_order.setField(fix.StringField(TAG_CL_ORD_ID, cl_ord_id))
        new_order.setField(fix.StringField(TAG_SYMBOL, product_id))
        new_order.setField(fix.CharField(TAG_SIDE, side))
        new_order.setField(fix.StringField(TAG_ORDER_QTY, str(quantity)))
        ord_type_fix = '2' if order_type_code.upper() == 'LIMIT' else '1'
        new_order.setField(fix.CharField(TAG_ORD_TYPE, ord_type_fix))
        if order_type_code.upper() == 'LIMIT': new_order.setField(fix.StringField(TAG_PRICE, str(price)))
        new_order.setField(fix.CharField(TAG_TIME_IN_FORCE, '1')) # GTC
        transact_time_field = fix.TransactTime(); new_order.setField(transact_time_field)
        return new_order, cl_ord_id

    def build_order_status_request(self, original_cl_ord_id):
        """ Builds an OrderStatusRequest message. """
        order_status = fix.Message()
        header = order_status.getHeader(); header.setField(fix.MsgType(MSG_TYPE_ORDER_STATUS_REQUEST))
        status_cl_ord_id = str(uuid.uuid4())
        order_status.setField(fix.StringField(TAG_CL_ORD_ID, status_cl_ord_id))
        order_status.setField(fix.StringField(TAG_ORIG_CL_ORD_ID, original_cl_ord_id))
        order_status.setField(fix.StringField(TAG_SYMBOL, DEFAULT_PRODUCT)) # Assuming same product for now
        # Side might be required by some exchanges for status request lookup
        # Need original side - retrieve from self.order_details if possible
        side_code = '1' # Default or lookup required
        with self.details_lock:
            if original_cl_ord_id in self.order_details:
                side_code = self.order_details[original_cl_ord_id].get('side', '1')
        order_status.setField(fix.CharField(TAG_SIDE, side_code))
        return order_status

    def build_test_request(self, test_req_id):
        """ Builds a TestRequest message. """
        test_req_msg = fix.Message()
        header = test_req_msg.getHeader(); header.setField(fix.MsgType(MSG_TYPE_TEST_REQUEST))
        test_req_msg.setField(fix.StringField(TAG_TEST_REQ_ID, test_req_id))
        return test_req_msg

    # --- Standard Callbacks ---
    def onCreate(self, sessionID): self.sessionID = sessionID; print(f"FIX Session created: {sessionID}")
    def onLogon(self, sessionID):
        self.logged_on = True; print(f"FIX Logon successful: {sessionID}")
        if self.processing_thread is None or not self.processing_thread.is_alive():
            self.stop_processing.clear()
            self.processing_thread = threading.Thread(target=self.process_order_queue, daemon=True)
            self.processing_thread.start(); print("FIX order processing thread started.")
        # self.send_test_request(sessionID) # Optional: Keep if needed

    def onLogout(self, sessionID):
        self.logged_on = False; print(f"FIX Logout: {sessionID}"); self.pending_test_req_id = None; self.stop_processing.set()

    # --- Message Handling Callbacks ---
    def toAdmin(self, message, sessionID):
        # (Implementation is the same as before)
        msgType = fix.MsgType(); message.getHeader().getField(msgType); msg_type_val = msgType.getValue()
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
        msgType = fix.MsgType(); message.getHeader().getField(msgType); msg_type_val = msgType.getValue()
        print(f"<<< Received Admin ({msg_type_val}):")
        try:
            if msg_type_val == MSG_TYPE_HEARTBEAT:
                test_req_id_field = fix.TestReqID()
                if self.pending_test_req_id and message.isSetField(test_req_id_field):
                    message.getField(test_req_id_field); received_test_req_id = test_req_id_field.getValue()
                    print(f"  Heartbeat contains TestReqID (112): {received_test_req_id}")
                    if received_test_req_id == self.pending_test_req_id: print(f"  +++ Test Request {self.pending_test_req_id} Confirmed +++"); self.pending_test_req_id = None
                    else: print(f"  WARNING: Received TestReqID {received_test_req_id} != pending {self.pending_test_req_id}")
            elif msg_type_val == MSG_TYPE_LOGOUT:
                reason_field = fix.StringField(TAG_TEXT);
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
                    message.getField(ref_msg_type_field);
                    if ref_msg_type_field.getValue() == MSG_TYPE_TEST_REQUEST: print("  ERROR: TestRequest rejected."); self.pending_test_req_id = None
        except Exception as e: print(f"  Error processing admin message: {e}")


    def toApp(self, message, sessionID):
        # (Implementation is the same as before)
        header = message.getHeader()
        if not header.isSetField(TAG_TRANSACT_TIME): print("  [toApp] Setting missing TransactTime (60)"); transact_time_field = fix.TransactTime(); header.setField(transact_time_field)
        msgType = fix.MsgType(); header.getField(msgType)
        print(f">>> Sending App ({msgType.getValue()}):"); print(message.toString().replace('\x01', '|'))

    def fromApp(self, message, sessionID):
        """ Handles incoming application messages, updates order status. """
        msgType = fix.MsgType(); message.getHeader().getField(msgType); msg_type_val = msgType.getValue()
        raw_msg_str = message.toString().replace(chr(1), '|')
        print(f"<<< Received App ({msg_type_val}):")
        print(f"  Raw Message: {raw_msg_str}")

        order_key = None
        new_ord_status = None
        try:
            # Determine the key (ClOrdID or OrigClOrdID)
            clordid_field = fix.ClOrdID(); origclordid_field = fix.OrigClOrdID()
            if message.isSetField(clordid_field): order_key = message.getField(clordid_field)
            if message.isSetField(origclordid_field): order_key = message.getField(origclordid_field)

            if msg_type_val == MSG_TYPE_EXECUTION_REPORT:
                ordstatus_field = fix.OrdStatus()
                if message.isSetField(ordstatus_field):
                    new_ord_status = message.getField(ordstatus_field)
                    print(f"  Extracted OrdStatus (39): {new_ord_status}")
                # Print other fields... (add more as needed)
                if message.isSetField(150): print(f"  ExecType (150): {message.getField(150)}")
                if message.isSetField(37): print(f"  OrderID (37): {message.getField(37)}")
                if message.isSetField(151): print(f"  LeavesQty (151): {message.getField(151)}")
                if message.isSetField(14): print(f"  CumQty (14): {message.getField(14)}")
                if message.isSetField(58): print(f"  Text (58): {message.getField(58)}")
                if message.isSetField(103): print(f"  OrdRejReason (103): {message.getField(103)}")

            elif msg_type_val == MSG_TYPE_ORDER_CANCEL_REJECT:
                 print("  Received Order Cancel Reject")
                 # Consider status '8' (Rejected) if a cancel reject occurs for the order key
                 new_ord_status = '8'
            elif msg_type_val == MSG_TYPE_BUSINESS_MESSAGE_REJECT:
                 print("  Received Business Message Reject")
                 # This usually doesn't directly update order status, but log it

            # Update the stored order status if relevant
            if order_key and new_ord_status:
                with self.details_lock:
                    if order_key in self.order_details:
                        print(f"  Updating status for {order_key} to {new_ord_status}")
                        self.order_details[order_key]['latest_ord_status'] = new_ord_status
                        # Check if it's a final state
                        if new_ord_status in FINAL_ORD_STATUSES:
                            self.order_details[order_key]['final_status_reached'] = True
                            print(f"  Order {order_key} reached final state: {new_ord_status}")
                    else:
                         # Received response for an order we didn't track (e.g., from previous session)
                         print(f"  Received response for untracked order key: {order_key}")

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
            test_req_msg = self.build_test_request(test_req_id) # Use self.
            print(f"\n--- Sending Test Request (TestReqID: {test_req_id}) ---")
            fix.Session.sendToTarget(test_req_msg, sessionID); print("Test Request Sent.")
        except Exception as e: print(f"Error sending Test Request: {e}"); self.pending_test_req_id = None

    def send_fix_order(self, sessionID, side, quantity, price, product_id=DEFAULT_PRODUCT, order_type_code=DEFAULT_ORDER_TYPE):
        """ Sends a NewOrderSingle message via the FIX session. """
        if not self.logged_on: print(f"Cannot send order: Not logged on to session {sessionID}."); return None
        cl_ord_id = None
        try:
            # Use self.build_new_order_message
            new_order, cl_ord_id = self.build_new_order_message(side, quantity, price, product_id, order_type_code)

            print(f"\n--- Sending Order (ClOrdID: {cl_ord_id}, Side: {side}, Qty: {quantity}, Px: {price}) ---")
            # Store details *before* sending, marking status as PENDING_SEND
            with self.details_lock:
                 self.order_details[cl_ord_id] = {
                     'side': side, 'qty': quantity, 'price': price, 'product': product_id,
                     'latest_ord_status': 'PENDING_SEND', 'final_status_reached': False
                 }
            fix.Session.sendToTarget(new_order, sessionID)
            print("  FIX Order Message Sent.")
            # Update status after successful send
            with self.details_lock:
                 if cl_ord_id in self.order_details: # Check if still there
                     self.order_details[cl_ord_id]['latest_ord_status'] = 'SENT'
            return cl_ord_id
        except fix.SessionNotFound: print(f"Error sending order: Session '{sessionID}' not found."); self.logged_on = False
        except Exception as e: print(f"Error sending FIX order (ClOrdID: {cl_ord_id}): {e}")
        # Clean up if send failed
        if cl_ord_id:
             with self.details_lock:
                 if cl_ord_id in self.order_details: del self.order_details[cl_ord_id]
        return None

    def send_order_status_request(self, sessionID, original_cl_ord_id):
        """ Sends an OrderStatusRequest. """
        if not self.logged_on: print(f"Cannot request status: Not logged on to session {sessionID}."); return
        if not original_cl_ord_id: print("Cannot request status: No original ClOrdID provided."); return

        try:
            session = fix.Session.lookupSession(sessionID)
            if not session or not session.isLoggedOn(): print(f"Cannot request status: Session '{sessionID}' not valid/logged on."); return

            # Use self.build_order_status_request
            status_request = self.build_order_status_request(original_cl_ord_id)
            print(f"--- Requesting Status (OrigClOrdID: {original_cl_ord_id}) ---")
            fix.Session.sendToTarget(status_request, sessionID)
            # print("  Order Status Request Sent.") # Reduce log noise
        except fix.SessionNotFound: print(f"Error requesting status: Session '{sessionID}' not found.")
        except Exception as e: print(f"Error requesting order status (OrigClOrdID: {original_cl_ord_id}): {e}")

    def poll_order_status_until_final(self, sessionID, clordid_to_poll):
        """ Repeatedly sends status requests until a final state is reached or timeout. """
        if not clordid_to_poll: return
        print(f"--- Starting status polling for order {clordid_to_poll} ---")
        start_time = time.time()
        timeout_seconds = 60  # Max time to poll for status
        poll_interval_seconds = 5 # Time between status requests

        while time.time() - start_time < timeout_seconds:
            if self.stop_processing.is_set() or not self.logged_on:
                 print(f"Stopping status poll for {clordid_to_poll} due to shutdown/logout.")
                 break

            # Check current stored status (thread-safe read)
            current_status = None
            final_reached = False
            with self.details_lock:
                if clordid_to_poll in self.order_details:
                    current_status = self.order_details[clordid_to_poll].get('latest_ord_status')
                    final_reached = self.order_details[clordid_to_poll].get('final_status_reached', False)
                else:
                     print(f"Warning: Order {clordid_to_poll} not found in details for status check.")
                     break # Exit polling if we lost track

            if final_reached:
                 print(f"--- Final status '{current_status}' reached for order {clordid_to_poll}. Stopping poll. ---")
                 break # Exit loop

            # If not final, send another status request
            print(f"Polling status for {clordid_to_poll} (Current: {current_status})...")
            self.send_order_status_request(sessionID, clordid_to_poll)

            # Wait before next poll
            time.sleep(poll_interval_seconds)
        else:
             # Loop finished due to timeout
             print(f"--- Status polling timed out after {timeout_seconds}s for order {clordid_to_poll}. Last known status: {current_status} ---")

        # Optionally: Clean up order details after polling is complete
        # with self.details_lock:
        #     if clordid_to_poll in self.order_details:
        #         del self.order_details[clordid_to_poll]

    # --- Queue Processing ---
    def process_order_queue(self):
        """ Continuously checks the order queue and sends/polls FIX orders. """
        print("FIX order processing thread waiting for logon...")
        while not self.logged_on:
            if self.stop_processing.is_set(): print("FIX order processing thread stopping before logon."); return
            time.sleep(0.5)

        print("FIX order processing thread active.")
        while not self.stop_processing.is_set():
            order_details_from_queue = None
            try:
                order_details_from_queue = self.order_queue.get(block=True, timeout=1.0)

                if order_details_from_queue and self.logged_on and self.sessionID:
                    print(f"Processing order from queue: {order_details_from_queue}")
                    side = order_details_from_queue['side']
                    quantity = order_details_from_queue['size']
                    price = order_details_from_queue['price']

                    # Send the order via FIX
                    placed_clordid = self.send_fix_order(self.sessionID, side, quantity, price)

                    if placed_clordid:
                        # Start polling loop for this specific order
                        self.poll_order_status_until_final(self.sessionID, placed_clordid)
                    else:
                         print(f"Failed to send order for details: {order_details_from_queue}")

                if order_details_from_queue: self.order_queue.task_done()

            except queue.Empty: continue
            except Exception as e:
                print(f"Error in order processing thread: {e}")
                if order_details_from_queue: self.order_queue.task_done()
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

@api.post("/trades", status_code=status.HTTP_202_ACCEPTED)
async def receive_trades(payload: List[OrderItem], request: Request):
    """ Receives a LIST of trade data items and queues corresponding FIX orders. """
    # (Implementation is the same as before)
    print(f"\n--- Received POST /trades request from {request.client.host} ---")
    processed_count = 0; queued_results = []; errors = []
    if not fix_app.logged_on: print("API Error: FIX session not logged on."); raise HTTPException(status_code=503, detail="FIX session not connected/logged on")
    if not payload: raise HTTPException(status_code=400, detail="Request body cannot be empty list.")

    for item in payload:
        try:
            print(f"  Processing trade item: Taker {item.takerUserId} {item.takerAction} / Maker {item.makerUserId} @ {item.price} x {item.size}")
            if item.takerUserId != 1:
                if item.takerAction.upper() in ["BID", "ASK"]:
                    result = fix_app.request_order_placement(item)
                    queued_results.append(result)
                    if result["status"] == "queued": processed_count += 1
                    else: errors.append({"input": item.dict(), "error": result.get("reason", "Failed to queue")})
                else: print(f"  Skipping item: Invalid takerAction '{item.takerAction}'"); errors.append({"input": item.dict(), "error": f"Invalid takerAction: {item.takerAction}"})
            else: print(f"  Skipping item: takerUserId is 1")
        except Exception as e: print(f"  Error processing item {item}: {e}"); errors.append({"input": item.dict(), "error": str(e)})

    print(f"--- Finished processing /trades request. Queued {processed_count} orders. Errors: {len(errors)} ---")
    return {"message": f"Received {len(payload)} items. Queued {processed_count} orders.", "results": queued_results, "errors": errors}

# --- Global Initiator Variable ---
initiator = None

# --- Signal Handler ---
def shutdown_handler(signum, frame):
    # (Implementation is the same as before)
    print(f"\nReceived signal {signum}. Initiating shutdown...")
    global initiator; fix_app.stop_processing.set()
    if initiator and not initiator.isStopped():
        print("Stopping QuickFIX initiator...");
        try: initiator.stop(True)
        except: pass
        print("Initiator stopped.")
    time.sleep(2); print("Exiting script."); os._exit(0)

# --- Main Execution ---
def run_fix_client():
    # (Implementation is the same as before)
    global initiator; print("--- Starting FIX Client Thread ---")
    config_path = os.path.join(SESSION_PATH, "fix_client_sandbox.cfg");
    try:
        with open(config_path, 'w') as cfg_file: cfg_file.write(SESSION_CONFIG); print(f"QuickFIX config written to: {config_path}")
    except IOError as e: print(f"Error writing config file '{config_path}': {e}"); sys.exit(1)
    try:
        settings = fix.SessionSettings(config_path); storeFactory = fix.FileStoreFactory(settings); logFactory = fix.FileLogFactory(settings)
        initiator = fix.SSLSocketInitiator(fix_app, storeFactory, settings, logFactory)
    except Exception as e: print(f"Error creating QuickFIX initiator components: {e}"); sys.exit(1)
    try:
        initiator.start(); print("FIX Initiator started. Running event loop.")
        while not initiator.isStopped(): time.sleep(1)
    except (KeyboardInterrupt, SystemExit): print("FIX client shutdown requested.")
    except Exception as e: print(f"An unexpected error occurred in the FIX client thread: {e}")
    finally:
        if initiator and not initiator.isStopped(): print("Ensuring FIX initiator is stopped..."); initiator.stop()
        print("--- FIX Client Thread Finished ---")

def run_fastapi_server():
    # (Implementation is the same as before)
    print(f"--- Starting FastAPI Server on 0.0.0.0:{FASTAPI_PORT} ---")
    try:
        config = uvicorn.Config(api, host="0.0.0.0", port=FASTAPI_PORT, log_level="info"); server = uvicorn.Server(config)
        server.run()
    except Exception as e: print(f"FastAPI server error: {e}")
    finally: print("--- FastAPI Server Thread Finished ---")

if __name__ == "__main__":
    print("--- Main Application Start ---")
    # (Print config details - same as before)
    print("--- Configuration ---")
    print(f"SVC_ACCOUNTID (SenderCompID): {SVC_ACCOUNTID}"); print(f"API_KEY (Username):           {API_KEY}"); print(f"PASSPHRASE:                   {'*' * len(PASSPHRASE) if PASSPHRASE else 'None'}"); print(f"API_SECRET:                   {'*' * len(API_SECRET) if API_SECRET else 'None'}"); print(f"FIX Host:                     {FIX_HOST}:{FIX_PORT}"); print(f"FastAPI Host:                 0.0.0.0:{FASTAPI_PORT}"); print("---------------------")

    signal.signal(signal.SIGINT, shutdown_handler); signal.signal(signal.SIGTERM, shutdown_handler)
    fix_thread = threading.Thread(target=run_fix_client, name="FIXClientThread"); api_thread = threading.Thread(target=run_fastapi_server, name="FastAPIServerThread")
    print("Starting FIX thread..."); fix_thread.start()
    print("Starting API thread..."); api_thread.start()
    try:
        fix_thread.join(); api_thread.join() # Wait for threads to complete
    except (KeyboardInterrupt, SystemExit): print("Main thread interrupted. Initiating shutdown via signal handler..."); shutdown_handler(signal.SIGINT, None)
    print("--- Main Application Finished ---")