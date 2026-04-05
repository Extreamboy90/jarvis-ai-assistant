#!/usr/bin/env python3
"""
HTTPS Reverse Proxy for Jarvis Orchestrator
Wraps HTTP orchestrator in HTTPS for iOS Safari compatibility
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import urllib.request
import urllib.error
import json

ORCHESTRATOR_URL = "http://localhost:8000"
PORT = 8443

class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request()

    def do_POST(self):
        self.proxy_request()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def proxy_request(self):
        # Build target URL
        target_url = ORCHESTRATOR_URL + self.path

        # Read body for POST requests
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        try:
            # Create request
            req = urllib.request.Request(
                target_url,
                data=body,
                method=self.command
            )

            # Copy headers (except Host)
            for header, value in self.headers.items():
                if header.lower() not in ['host', 'connection']:
                    req.add_header(header, value)

            # Make request to orchestrator
            with urllib.request.urlopen(req, timeout=120) as response:
                # Send response
                self.send_response(response.status)
                self.send_cors_headers()

                # Copy response headers
                for header, value in response.headers.items():
                    if header.lower() not in ['transfer-encoding', 'connection']:
                        self.send_header(header, value)

                self.end_headers()

                # Send body
                self.wfile.write(response.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(e.read())

        except Exception as e:
            self.send_response(500)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = json.dumps({"error": str(e)})
            self.wfile.write(error_response.encode())

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Max-Age', '3600')

    def log_message(self, format, *args):
        print(f"[PROXY] {format % args}")

# Create HTTPS server
httpd = HTTPServer(("", PORT), ProxyHandler)

# Wrap with SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('cert.pem', 'key.pem')
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"🔒 Jarvis HTTPS Proxy running at:")
print(f"   HTTPS:    https://192.168.1.131:{PORT}")
print(f"   Proxying: {ORCHESTRATOR_URL}")
print(f"\n✅ Usa questo URL nelle impostazioni PWA:")
print(f"   https://192.168.1.131:{PORT}")
print(f"\n   Press Ctrl+C to stop\n")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\n\n👋 Proxy stopped")
