/**
 * Voice Loop WebSocket - Browser-based continuous voice assistant
 * Handles: Browser Audio → WebSocket → Server (STT→LLM→TTS) → WebSocket → Browser Audio
 */

class VoiceLoopWebSocket {
    constructor(serverUrl, userId) {
        this.serverUrl = serverUrl;
        this.userId = userId;
        this.ws = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.isConnected = false;

        // Callbacks
        this.onTranscription = null;
        this.onResponse = null;
        this.onError = null;
        this.onAudioPlay = null;
    }

    async initialize() {
        try {
            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            console.log('✅ Voice loop initialized');
            return true;

        } catch (error) {
            console.error('❌ Failed to initialize:', error);
            return false;
        }
    }

    async connect() {
        if (this.isConnected) {
            console.log('Already connected');
            return;
        }

        try {
            // Convert HTTP URL to WebSocket URL
            const wsUrl = this.serverUrl.replace(/^http/, 'ws') + `/ws/voice?user_id=${this.userId}`;

            console.log('🔌 Connecting to:', wsUrl);

            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('✅ WebSocket connected');
                this.isConnected = true;
            };

            this.ws.onmessage = async (event) => {
                await this.handleMessage(event);
            };

            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                this.isConnected = false;
                if (this.onError) this.onError('Connection error');
            };

            this.ws.onclose = () => {
                console.log('🔌 WebSocket closed');
                this.isConnected = false;
            };

            return new Promise((resolve) => {
                this.ws.addEventListener('open', () => resolve(true), { once: true });
                this.ws.addEventListener('error', () => resolve(false), { once: true });
            });

        } catch (error) {
            console.error('❌ Connection failed:', error);
            return false;
        }
    }

    async handleMessage(event) {
        // Handle binary audio data
        if (event.data instanceof Blob) {
            console.log('🔊 Received audio response');
            await this.playAudio(event.data);
            if (this.onAudioPlay) this.onAudioPlay();
            return;
        }

        // Handle JSON messages
        try {
            const data = JSON.parse(event.data);
            console.log('📨 Received:', data.type);

            if (data.type === 'transcription') {
                console.log('📝 Transcription:', data.text);
                if (this.onTranscription) this.onTranscription(data.text);
            }

            if (data.type === 'response') {
                console.log('💬 Response:', data.text);
                if (this.onResponse) this.onResponse(data.text);
            }

            if (data.type === 'error') {
                console.error('❌ Server error:', data.message);
                if (this.onError) this.onError(data.message);
            }

        } catch (error) {
            console.error('Failed to parse message:', error);
        }
    }

    async startRecording() {
        if (this.isRecording) {
            console.log('Already recording');
            return false;
        }

        if (!this.isConnected) {
            console.error('Not connected to server');
            return false;
        }

        try {
            // Request microphone access
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Create MediaRecorder
            this.mediaRecorder = new MediaRecorder(this.mediaStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 16000
            });

            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                console.log('🎙️ Recording stopped, sending audio...');

                // Combine chunks
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });

                // Convert to ArrayBuffer and send
                const arrayBuffer = await audioBlob.arrayBuffer();

                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(arrayBuffer);
                    this.ws.send(JSON.stringify({ type: 'audio_end' }));
                }

                // Cleanup
                this.mediaStream.getTracks().forEach(track => track.stop());
                this.audioChunks = [];
                this.isRecording = false;
            };

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;

            // Send start signal
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'audio_start' }));
            }

            console.log('🎤 Recording started');
            return true;

        } catch (error) {
            console.error('❌ Failed to start recording:', error);
            if (this.onError) this.onError('Microphone access denied');
            return false;
        }
    }

    stopRecording() {
        if (!this.isRecording) return;

        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }
    }

    async playAudio(audioBlob) {
        try {
            // Convert blob to ArrayBuffer
            const arrayBuffer = await audioBlob.arrayBuffer();

            // Decode audio
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

            // Create source
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);

            // Play
            source.start();

            console.log('🔊 Playing audio response...');

            return new Promise((resolve) => {
                source.onended = () => {
                    console.log('✅ Audio playback finished');
                    resolve();
                };
            });

        } catch (error) {
            console.error('❌ Failed to play audio:', error);
        }
    }

    disconnect() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.isRecording = false;
        this.isConnected = false;

        console.log('🔌 Voice loop disconnected');
    }
}

// Export to window
window.VoiceLoopWebSocket = VoiceLoopWebSocket;
