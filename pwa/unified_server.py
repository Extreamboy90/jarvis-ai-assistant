#!/usr/bin/env python3
"""
Unified HTTPS Server for Jarvis PWA
Combines: Static files + API proxy + WebSocket support
Port: 9443 (HTTPS)
"""

from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import ssl
import urllib.request
import urllib.error
import json
import os

# Configuration
PWA_DIR = os.path.dirname(os.path.abspath(__file__))
ORCHESTRATOR_URL = "http://localhost:8000"
PORT = 9443

class UnifiedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PWA_DIR, **kwargs)

    def do_GET(self):
        # Parse path
        parsed = urlparse(self.path)
        path = parsed.path

        # API Proxy routes
        if path in ['/health', '/functions']:
            self.proxy_to_orchestrator()
        elif path == '/tts/health':
            self.proxy_to_tts()
        else:
            # Serve static files
            super().do_GET()

    def do_POST(self):
        # Proxy POST requests
        if self.path in ['/chat', '/memories']:
            self.proxy_to_orchestrator()
        elif self.path == '/tts/speak':
            self.proxy_to_tts()
        elif self.path == '/stt/transcribe':
            self.proxy_to_stt()
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def proxy_to_tts(self):
        """Proxy request to TTS service (Edge TTS)"""
        # Remove /tts prefix
        path = self.path.replace('/tts', '')
        target_url = "http://localhost:8004" + path  # Edge TTS port
        self._proxy_request(target_url)

    def proxy_to_stt(self):
        """Proxy request to STT service (Faster Whisper)"""
        # Remove /stt prefix
        path = self.path.replace('/stt', '')
        target_url = "http://localhost:8001" + path  # STT port
        self._proxy_request(target_url)

    def proxy_to_orchestrator(self):
        """Proxy request to orchestrator"""
        target_url = ORCHESTRATOR_URL + self.path
        self._proxy_request(target_url)

    def _proxy_request(self, target_url):
        """Generic proxy method"""

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

            # Copy headers
            for header, value in self.headers.items():
                if header.lower() not in ['host', 'connection']:
                    req.add_header(header, value)

            # Make request
            with urllib.request.urlopen(req, timeout=120) as response:
                # Send response
                self.send_response(response.status)
                self.send_cors_headers()

                # Copy headers
                for header, value in response.headers.items():
                    if header.lower() not in ['transfer-encoding', 'connection']:
                        self.send_header(header, value)

                self.end_headers()
                self.wfile.write(response.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(e.read())

        except Exception as e:
            self.send_response(500)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error = json.dumps({"error": str(e)}).encode()
            self.wfile.write(error)

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Max-Age', '3600')

    def end_headers(self):
        # Add CORS headers to all responses
        self.send_cors_headers()
        # No cache for development
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def log_message(self, format, *args):
        # Simplified logging
        if not self.path.startswith('/icons/'):  # Skip icon requests
            print(f"[{self.log_date_time_string()}] {format % args}")

# Change to PWA directory
os.chdir(PWA_DIR)

# Create HTTPS server
httpd = HTTPServer(("", PORT), UnifiedHandler)

# Wrap with SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('cert.pem', 'key.pem')
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"""
╔═══════════════════════════════════════════════════════════╗
║          🤖 JARVIS UNIFIED HTTPS SERVER                  ║
╚═══════════════════════════════════════════════════════════╝

🔒 Server URL:  https://192.168.1.131:{PORT}

📱 Configurazione automatica:
   - PWA + API proxy integrati
   - Stesso dominio/porta = nessun mixed content
   - Certificato già accettato = tutto funziona

🎯 Accedi da iPad:
   1. Apri: https://192.168.1.131:{PORT}/hud.html
   2. Accetta certificato (una volta sola)
   3. Tutto funziona automaticamente!

⚡ Features:
   ✅ Serve PWA (HTML/CSS/JS)
   ✅ Proxy API verso orchestrator (port 8000)
   ✅ CORS abilitato
   ✅ HTTPS per microfono iOS

📝 Note:
   - Orchestrator deve essere attivo su localhost:8000
   - Accetta il certificato self-signed quando richiesto

Press Ctrl+C to stop

""")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\n\n👋 Server stopped")
