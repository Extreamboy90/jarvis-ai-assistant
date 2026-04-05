#!/usr/bin/env python3
"""
HTTPS server for Jarvis PWA with SSL support
Required for microphone access on iOS Safari
"""

import http.server
import ssl
import os

# Change to PWA directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PORT = 3443

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

        # No cache for development
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')

        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Simplified logging
        print(f"[{self.log_date_time_string()}] {format % args}")

# Create HTTPS server
httpd = http.server.HTTPServer(("", PORT), MyHTTPRequestHandler)

# Wrap with SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('cert.pem', 'key.pem')
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"🔒 Jarvis PWA HTTPS Server running at:")
print(f"   Local:    https://localhost:{PORT}")
print(f"   Network:  https://192.168.1.131:{PORT}")
print(f"\n⚠️  IMPORTANTE per iPad:")
print(f"   1. Apri Safari su: https://192.168.1.131:{PORT}/hud.html")
print(f"   2. Accetta il certificato self-signed (Avanzate → Procedi)")
print(f"   3. Ora il microfono funzionerà!")
print(f"\n📱 Il certificato va accettato una volta sola")
print(f"   Press Ctrl+C to stop\n")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\n\n👋 Server stopped")
