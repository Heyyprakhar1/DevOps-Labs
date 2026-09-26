#!/usr/bin/env python3
"""
Simple mock Payment API service for Linux Lab
Listens on port 8000 by default.
"""
import os
import sys
import time
import json
import socket
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

CONFIG_FILE = "/etc/app/payment.conf"
LOG_FILE = "/var/log/app/payment.log"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [payment-api] %(message)s'
)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to parse config {CONFIG_FILE}: {e}")
            raise
    return {"port": 8000, "db_host": "127.0.0.1", "db_port": 5432, "timeout": 3}

class PaymentRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "UP", "service": "payment-api"}\n')
            logging.info("GET /health HTTP/1.1 200 OK")
        elif self.path == "/process-payment":
            config = load_config()
            db_host = config.get("db_host", "127.0.0.1")
            
            # Check if database host resolves or is marked failing
            # In incident scenario, db_host might be misconfigured in /etc/hosts or config
            is_error = False
            error_reason = ""
            
            # Check /etc/hosts for simulated broken hostname or config
            try:
                ip = socket.gethostbyname(db_host)
                if ip.startswith("127.0.0.99") or db_host == "unreachable.internal":
                    is_error = True
                    error_reason = f"DatabaseConnectionError: Connection refused to database at {db_host}:5432"
            except Exception as e:
                is_error = True
                error_reason = f"DatabaseConnectionError: Unable to resolve database host '{db_host}': {e}"

            if is_error:
                logging.error(f"[CRITICAL] Transaction failed: {error_reason}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Internal Server Error",
                    "details": "Downstream payment database connection failure"
                }).encode('utf-8') + b'\n')
            else:
                logging.info(f"Transaction TX-1092 processed successfully with db at {db_host}")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "transaction_id": "TX-1092",
                    "amount": 49.99
                }).encode('utf-8') + b'\n')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run():
    try:
        config = load_config()
    except Exception as e:
        sys.stderr.write(f"FATAL: Configuration error: {e}\n")
        sys.exit(1)

    port = config.get("port", 8000)
    server_address = ('0.0.0.0', port)
    try:
        httpd = HTTPServer(server_address, PaymentRequestHandler)
        logging.info(f"Payment API started successfully on 0.0.0.0:{port}")
        httpd.serve_forever()
    except OSError as e:
        logging.error(f"Cannot bind to port {port}: {e}")
        sys.stderr.write(f"FATAL: Port conflict on {port}: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    run()
