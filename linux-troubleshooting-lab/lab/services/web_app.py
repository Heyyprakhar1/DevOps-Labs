#!/usr/bin/env python3
"""
Simple mock Web Application service for Linux Lab
Listens on port 8080 by default.
"""
import os
import sys
import time
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

CONFIG_FILE = "/etc/app/web_app.conf"
LOG_FILE = "/var/log/app/web_app.log"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [web-app] %(message)s'
)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to parse config {CONFIG_FILE}: {e}")
            raise
    return {"port": 8080, "workers": 4, "debug": False}

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "UP", "service": "web-app"}\n')
            logging.info("GET /health HTTP/1.1 200 OK")
        elif self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b'# HELP http_requests_total Total requests\nhttp_requests_total 42\n')
            logging.info("GET /metrics HTTP/1.1 200 OK")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Production Web Application Server</h1><p>Status: Healthy</p>\n")
            logging.info(f"GET {self.path} HTTP/1.1 200 OK")

    def log_message(self, format, *args):
        # Suppress default stderr logging
        pass

def run():
    try:
        config = load_config()
    except Exception as e:
        sys.stderr.write(f"FATAL: Configuration error: {e}\n")
        sys.exit(1)

    port = config.get("port", 8080)
    server_address = ('0.0.0.0', port)
    try:
        httpd = HTTPServer(server_address, RequestHandler)
        logging.info(f"Web application started successfully on 0.0.0.0:{port}")
        httpd.serve_forever()
    except OSError as e:
        logging.error(f"Cannot bind to port {port}: {e}")
        sys.stderr.write(f"FATAL: Port conflict on {port}: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    run()
