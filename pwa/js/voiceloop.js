/**
 * Voice Loop WebSocket
 * Browser Audio → WebSocket → Server (STT→LLM→TTS) → WebSocket → Browser Audio
 *
 * Tecnica chiave: AudioContext creato DENTRO getUserMedia() callback,
 * così Chrome lo considera "user-activated" e non blocca la riproduzione audio.
 */

class VoiceLoopWebSocket {
    constructor(serverUrl, userId) {
        this.serverUrl = serverUrl;
        this.userId = userId;
        this.ws = null;
        this.audioContext = null;   // creato durante getUserMedia (user gesture)
        this.mediaStream = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.isConnected = false;
        this._lastResponseText = null;

        // Callbacks
        this.onTranscription = null;
        this.onResponse = null;
        this.onError = null;
        this.onAudioPlay = null;
    }

    async initialize() {
        console.log('✅ Voice loop initialized');
        return true;
    }

    async connect() {
        if (this.isConnected) return true;

        try {
            const wsUrl = this.serverUrl.replace(/^http/, 'ws') + `/ws/voice?user_id=${this.userId}`;
            console.log('🔌 Connecting to:', wsUrl);

            this.ws = new WebSocket(wsUrl);

            this.ws.onopen  = () => { console.log('✅ WebSocket connected'); this.isConnected = true; };
            this.ws.onmessage = (event) => this.handleMessage(event);
            this.ws.onerror = () => { this.isConnected = false; if (this.onError) this.onError('Connection error'); };
            this.ws.onclose = () => { console.log('🔌 WebSocket closed'); this.isConnected = false; };

            return new Promise((resolve) => {
                const timer = setTimeout(() => resolve(false), 5000);
                this.ws.addEventListener('open',  () => { clearTimeout(timer); resolve(true);  }, { once: true });
                this.ws.addEventListener('error', () => { clearTimeout(timer); resolve(false); }, { once: true });
            });
        } catch (e) {
            console.error('❌ Connection failed:', e);
            return false;
        }
    }

    async handleMessage(event) {
        // Audio binario dal server (TTS)
        if (event.data instanceof Blob) {
            console.log('🔊 Received audio response');
            await this.playAudio(event.data);
            if (this.onAudioPlay) this.onAudioPlay();
            return;
        }

        // Messaggi JSON
        try {
            const data = JSON.parse(event.data);
            console.log('📨 Received:', data.type);

            if (data.type === 'transcription') {
                console.log('📝 Transcription:', data.text);
                if (this.onTranscription) this.onTranscription(data.text);
            }
            if (data.type === 'response') {
                console.log('💬 Response:', data.text);
                this._lastResponseText = data.text;
                if (this.onResponse) this.onResponse(data.text);
            }
            if (data.type === 'error') {
                console.error('❌ Server error:', data.message);
                if (this.onError) this.onError(data.message);
            }
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    }

    async startRecording() {
        if (this.isRecording)   { console.log('Already recording'); return false; }
        if (!this.isConnected)  { console.error('Not connected');    return false; }

        try {
            // getUserMedia — questo è il "user gesture" che sblocca l'audio
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: { sampleRate: 16000, channelCount: 1,
                         echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            });

            // ── Crea/riprendi AudioContext QUI, subito dopo getUserMedia ──
            // Chrome considera questo contesto "user-activated": playback futuro sarà permesso
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            console.log('🔓 AudioContext state:', this.audioContext.state);

            // MediaRecorder
            this.mediaRecorder = new MediaRecorder(this.mediaStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 16000
            });
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = async () => {
                console.log('🎙️ Recording stopped, sending audio...');
                const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
                const buffer = await blob.arrayBuffer();
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(buffer);
                    this.ws.send(JSON.stringify({ type: 'audio_end' }));
                }
                this.mediaStream.getTracks().forEach(t => t.stop());
                this.audioChunks = [];
                this.isRecording = false;
            };

            this.mediaRecorder.start();
            this.isRecording = true;

            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'audio_start' }));
            }

            console.log('🎤 Recording started');
            return true;

        } catch (e) {
            console.error('❌ Failed to start recording:', e);
            if (this.onError) this.onError('Microphone access denied');
            return false;
        }
    }

    stopRecording() {
        if (this.isRecording && this.mediaRecorder?.state === 'recording') {
            this.mediaRecorder.stop();
        }
    }

    async playAudio(audioBlob) {
        // Usa Web Audio API se il contesto è già sbloccato (caso normale)
        if (this.audioContext && this.audioContext.state === 'running') {
            try {
                const arrayBuffer = await audioBlob.arrayBuffer();
                const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
                const source = this.audioContext.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(this.audioContext.destination);
                source.start();
                console.log('🔊 Playing via AudioContext...');
                return new Promise((resolve) => { source.onended = () => { console.log('✅ Playback finished'); resolve(); }; });
            } catch (e) {
                console.warn('Web Audio failed, fallback:', e.message);
            }
        }

        // Fallback 1: speechSynthesis con il testo della risposta
        if (this._lastResponseText && window.speechSynthesis) {
            console.log('🔊 Fallback: speechSynthesis');
            return new Promise((resolve) => {
                const utterance = new SpeechSynthesisUtterance(this._lastResponseText);
                utterance.lang = 'it-IT';
                const itVoice = window.speechSynthesis.getVoices().find(v => v.lang.startsWith('it'));
                if (itVoice) utterance.voice = itVoice;
                utterance.onend = () => resolve();
                utterance.onerror = () => resolve();
                window.speechSynthesis.speak(utterance);
            });
        }

        // Fallback 2: niente audio, riprendi il loop
        console.warn('⚠️ No audio playback available');
    }

    disconnect() {
        if (this.mediaRecorder?.state === 'recording') this.mediaRecorder.stop();
        this.mediaStream?.getTracks().forEach(t => t.stop());
        this.mediaStream = null;
        this.ws?.close();
        this.ws = null;
        if (this.audioContext) { this.audioContext.close(); this.audioContext = null; }
        this.isRecording = false;
        this.isConnected = false;
        console.log('🔌 Voice loop disconnected');
    }
}

window.VoiceLoopWebSocket = VoiceLoopWebSocket;
