#!/usr/bin/env python3
"""
Edge TTS Service - Simple endpoint for text-to-speech
Uses Microsoft Edge TTS (free, unlimited, natural voice)
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import asyncio
import edge_tts
import tempfile
import os

PORT = 8004
VOICE = "it-IT-ElsaNeural"  # Voce italiana femminile naturale
# Alternative: "it-IT-DiegoNeural" (maschile)

class TTSHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "status": "healthy",
                "service": "edge-tts",
                "voice": VOICE
            })
            self.wfile.write(response.encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/speak':
            try:
                # Read request body
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))

                text = data.get('text', '')
                voice = data.get('voice', VOICE)

                if not text:
                    self.send_error(400, "Missing 'text' parameter")
                    return

                # Generate speech
                audio_data = asyncio.run(self.generate_speech(text, voice))

                # Send audio
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(audio_data)))
                self.end_headers()
                self.wfile.write(audio_data)

            except Exception as e:
                self.send_error(500, f"TTS Error: {str(e)}")
        else:
            self.send_error(404)

    async def generate_speech(self, text, voice):
        """Generate speech using Edge TTS"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tmp_path = tmp.name

        try:
            # Generate speech
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)

            # Read generated audio
            with open(tmp_path, 'rb') as f:
                audio_data = f.read()

            return audio_data

        finally:
            # Cleanup
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def log_message(self, format, *args):
        # Simplified logging
        if not self.path.startswith('/health'):
            print(f"[Edge TTS] {format % args}")

# Run server
httpd = HTTPServer(('', PORT), TTSHandler)
print(f"""
╔═══════════════════════════════════════════════════════════╗
║          🎙️  EDGE TTS SERVICE                            ║
╚═══════════════════════════════════════════════════════════╝

🔊 Service URL:  http://localhost:{PORT}

🗣️  Voice:       {VOICE} (Italian Female)

📝 Usage:
   POST /speak
   {{
     "text": "Ciao, sono Jarvis",
     "voice": "{VOICE}"  (optional)
   }}

✅ Features:
   - Free & Unlimited
   - Natural Italian voice
   - Fast generation
   - No API key required

Press Ctrl+C to stop
""")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\n\n👋 Edge TTS service stopped")
