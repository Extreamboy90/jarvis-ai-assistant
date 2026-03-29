#!/usr/bin/env python3
"""
Simple HTTP server for Jarvis PWA
Serves static files with correct MIME types
"""

import http.server
import socketserver
import os

# Change to PWA directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PORT = 3001

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers for local development
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

        # Cache control for development
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')

        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

Handler = MyHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"🚀 Jarvis PWA Server running at:")
    print(f"   Local:    http://localhost:{PORT}")
    print(f"   Network:  http://<your-ip>:{PORT}")
    print(f"\n📱 Open on your phone/tablet to test!")
    print(f"   Make sure your device is on the same network")
    print(f"\nPress Ctrl+C to stop\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
