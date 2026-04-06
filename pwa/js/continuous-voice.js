/**
 * Continuous Voice Loop
 * Flow: Wake word ("Hey Jarvis") → registra comando → /ws/voice → risposta audio → loop
 *
 * Usa WakeWordDetector (ONNX) se disponibile, altrimenti SpeechRecognition come fallback.
 */

class ContinuousVoiceLoop {
    constructor(serverUrl, userId) {
        this.serverUrl = serverUrl;
        this.userId = userId;
        this.isActive = false;
        this.isProcessing = false;

        this.voiceLoop = null;       // VoiceLoopWebSocket
        this.wakeDetector = null;    // WakeWordDetector (ONNX)
        this.fallbackRecog = null;   // SpeechRecognition fallback

        // Callbacks (impostati da app.js)
        this.onStatusChange = null;
        this.onTranscript = null;
        this.onResponse = null;
    }

    async initialize() {
        // 1. Inizializza VoiceLoopWebSocket
        this.voiceLoop = new VoiceLoopWebSocket(this.serverUrl, this.userId);

        this.voiceLoop.onTranscription = (text) => {
            if (this.onTranscript) this.onTranscript(text);
        };

        this.voiceLoop.onResponse = (text) => {
            if (this.onResponse) this.onResponse(text);
        };

        this.voiceLoop.onAudioPlay = async () => {
            console.log('🔊 Audio finito, riprendo ascolto...');
            this.isProcessing = false;
            this._startWakeWordListening();
        };

        this.voiceLoop.onError = (error) => {
            console.warn('Voice loop error:', error);
            this.isProcessing = false;
            this._startWakeWordListening();
        };

        await this.voiceLoop.initialize();
        const connected = await this.voiceLoop.connect();

        if (!connected) {
            throw new Error('Failed to connect to voice service (/ws/voice)');
        }

        // 2. Prova wake word ONNX
        if (WakeWordDetector.isSupported()) {
            try {
                this.wakeDetector = new WakeWordDetector();
                const ok = await this.wakeDetector.initialize();
                if (ok) {
                    console.log('✅ Wake word ONNX pronto');
                    this.wakeDetector.onDetect((score) => {
                        if (!this.isProcessing) {
                            console.log(`🎯 Wake word! score=${score.toFixed(2)}`);
                            this._onWakeWord();
                        }
                    });
                } else {
                    this.wakeDetector = null;
                }
            } catch (e) {
                console.warn('ONNX wake word non disponibile, uso fallback:', e.message);
                this.wakeDetector = null;
            }
        }

        // 3. Se ONNX non disponibile, prepara SpeechRecognition fallback
        if (!this.wakeDetector) {
            this._initFallbackRecognition();
        }

        console.log('✅ ContinuousVoiceLoop inizializzato');
        return true;
    }

    /**
     * Avvia il loop
     */
    async start() {
        if (this.isActive) return;
        this.isActive = true;
        this._startWakeWordListening();
    }

    /**
     * Avvia l'ascolto della wake word (ONNX o fallback)
     */
    _startWakeWordListening() {
        if (!this.isActive || this.isProcessing) return;

        if (this.onStatusChange) {
            const method = this.wakeDetector ? '"Hey Jarvis"' : '"Alexa"';
            this.onStatusChange('listening', `Di' ${method} per iniziare`);
        }

        if (this.wakeDetector) {
            this.wakeDetector.start();
        } else {
            this._startFallbackListening();
        }
    }

    /**
     * Quando la wake word è rilevata
     */
    async _onWakeWord() {
        if (this.isProcessing) return;
        this.isProcessing = true;

        // Ferma ascolto wake word
        if (this.wakeDetector) this.wakeDetector.stop();
        if (this.fallbackRecog) {
            try { this.fallbackRecog.stop(); } catch(e) {}
        }

        if (this.onStatusChange) this.onStatusChange('recording', 'Ti ascolto...');

        // Feedback sonoro
        this._beep();

        // Piccola pausa prima di registrare
        await new Promise(r => setTimeout(r, 300));

        // Avvia registrazione vocale via WebSocket
        const started = await this.voiceLoop.startRecording();
        if (!started) {
            console.error('Registrazione non avviata');
            this.isProcessing = false;
            this._startWakeWordListening();
            return;
        }

        if (this.onStatusChange) this.onStatusChange('recording', 'Parla pure...');

        // Auto-stop dopo 10 secondi
        this._recordingTimeout = setTimeout(() => {
            if (this.voiceLoop.isRecording) {
                this.voiceLoop.stopRecording();
            }
        }, 10000);

        // Rilevamento silenzio via SpeechRecognition
        this._startSilenceDetection();
    }

    /**
     * Rilevamento silenzio per stop automatico
     */
    _startSilenceDetection() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;

        const detector = new SR();
        detector.lang = 'it-IT';
        detector.continuous = true;
        detector.interimResults = true;

        let lastSpeech = Date.now();
        const SILENCE_MS = 1800;

        detector.onresult = () => { lastSpeech = Date.now(); };

        detector.onend = () => {
            if (Date.now() - lastSpeech >= SILENCE_MS && this.voiceLoop.isRecording) {
                clearTimeout(this._recordingTimeout);
                this.voiceLoop.stopRecording();
                if (this.onStatusChange) this.onStatusChange('processing', 'Elaboro...');
            }
        };

        try {
            detector.start();
            setTimeout(() => { try { detector.stop(); } catch(e) {} }, 10000);
        } catch(e) {}
    }

    // ── Fallback SpeechRecognition (senza ONNX) ──────────────────────────────

    _initFallbackRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;

        this.fallbackRecog = new SR();
        this.fallbackRecog.lang = 'it-IT';
        this.fallbackRecog.continuous = true;
        this.fallbackRecog.interimResults = false;

        this.fallbackRecog.onresult = (event) => {
            const transcript = event.results[event.results.length - 1][0].transcript.toLowerCase().trim();
            if ((transcript.includes('alexa') || transcript.includes('jarvis')) && !this.isProcessing) {
                console.log('🎯 Wake word rilevata (fallback):', transcript);
                this._onWakeWord();
            }
        };

        this.fallbackRecog.onerror = (event) => {
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                setTimeout(() => this._startFallbackListening(), 1000);
            }
        };

        this.fallbackRecog.onend = () => {
            if (this.isActive && !this.isProcessing) {
                setTimeout(() => this._startFallbackListening(), 200);
            }
        };
    }

    _startFallbackListening() {
        if (!this.fallbackRecog || !this.isActive || this.isProcessing) return;
        try { this.fallbackRecog.start(); } catch(e) {}
    }

    // ── Utility ──────────────────────────────────────────────────────────────

    _beep() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 880;
            gain.gain.value = 0.08;
            osc.start();
            osc.stop(ctx.currentTime + 0.12);
        } catch(e) {}
    }

    stop() {
        this.isActive = false;
        if (this.wakeDetector) this.wakeDetector.stop();
        if (this.fallbackRecog) { try { this.fallbackRecog.stop(); } catch(e) {} }
        if (this.voiceLoop) this.voiceLoop.disconnect();
        clearTimeout(this._recordingTimeout);
        if (this.onStatusChange) this.onStatusChange('stopped', 'Loop vocale fermato');
        console.log('🛑 ContinuousVoiceLoop fermato');
    }
}

window.ContinuousVoiceLoop = ContinuousVoiceLoop;
