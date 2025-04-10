#!/usr/bin/env python3

import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import ngrok

# Set ngrok authtoken directly in the script
os.environ["NGROK_AUTHTOKEN"] = "2vF6IAJElqcu0kcdtOmmWPeNymR_69xausyWKehkPfzYB3ik1"

class HelloHandler(BaseHTTPRequestHandler):

    def log_request_info(self, method, body=None):
        """Logs request details (method, path, headers, and optional body)
        into the message.txt file."""
        log_entry = []
        log_entry.append(f"Received {method} request:")
        log_entry.append(f"Path: {self.path}")
        log_entry.append("Headers:")
        for header, value in self.headers.items():
            log_entry.append(f"  {header}: {value}")
        if body:
            try:
                # Try to decode body using UTF-8
                body_text = body.decode('utf-8', errors='replace')
            except Exception:
                body_text = str(body)
            log_entry.append("Body:")
            log_entry.append(body_text)
        log_entry.append("-" * 40)  # A separator line
        
        # Append the log entry to message.txt
        with open("message.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(log_entry) + "\n")

    def do_GET(self):
        # Log the GET request details (without a body)
        self.log_request_info("GET")
        self.respond_hello()

    def do_POST(self):
        # Read the POST body based on the provided Content-Length header
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        # Log the POST request along with the body
        self.log_request_info("POST", body)
        self.respond_hello()
        
    def respond_hello(self):
        # Prepare the response content
        response = "Hello"
        response_bytes = response.encode("utf-8")
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

# Configure logging for console output
logging.basicConfig(level=logging.INFO)

# Create the HTTP server on localhost at any available port
server = HTTPServer(("localhost", 0), HelloHandler)

# Attach the ngrok tunnel to expose the local server publicly
ngrok.listen(server)

try:
    logging.info("Starting server. Press Ctrl+C to stop.")
    server.serve_forever()
except KeyboardInterrupt:
    logging.info("Shutting down server...")
    server.server_close()
    ngrok.kill()
    logging.info("Server stopped cleanly.")