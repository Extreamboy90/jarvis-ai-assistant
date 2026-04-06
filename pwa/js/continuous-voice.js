/**
 * Continuous Voice Loop
 *
 * Modalità wake word → dopo prima attivazione → modalità conversazione diretta
 *
 * Flusso:
 *   1. In ascolto wake word ("Hey Jarvis" / "Alexa")
 *   2. Wake word rilevata → beep → registra comando
 *   3. Risposta audio → torna ad ascoltare
 *      - Se conversazione attiva: ascolta direttamente (no wake word)
 *      - Dopo 30s di silenzio: torna a modalità wake word
 */

class ContinuousVoiceLoop {
    constructor(serverUrl, userId) {
        this.serverUrl = serverUrl;
        this.userId = userId;
        this.isActive = false;
        this.isProcessing = false;
        this.conversationActive = false;   // true dopo prima wake word

        this.voiceLoop = null;
        this.wakeDetector = null;
        this.fallbackRecog = null;
        this._directRecog = null;
        this._conversationTimer = null;

        this.onStatusChange = null;
        this.onTranscript = null;
        this.onResponse = null;
    }

    async initialize() {
        // 1. VoiceLoopWebSocket
        this.voiceLoop = new VoiceLoopWebSocket(this.serverUrl, this.userId);

        this.voiceLoop.onTranscription = (text) => {
            if (this.onTranscript) this.onTranscript(text);
        };

        this.voiceLoop.onResponse = (text) => {
            if (this.onResponse) this.onResponse(text);
        };

        this.voiceLoop.onAudioPlay = () => {
            console.log('🔊 Audio finito, riprendo ascolto...');
            this.isProcessing = false;
            this._resetConversationTimer();
            this._startListening();
        };

        this.voiceLoop.onError = (error) => {
            console.warn('Voice loop error:', error);
            this.isProcessing = false;
            this._startListening();
        };

        await this.voiceLoop.initialize();
        const connected = await this.voiceLoop.connect();
        if (!connected) throw new Error('Failed to connect to voice service (/ws/voice)');

        // 2. Wake word ONNX (se disponibile)
        if (WakeWordDetector.isSupported()) {
            try {
                this.wakeDetector = new WakeWordDetector();
                const ok = await this.wakeDetector.initialize();
                if (ok) {
                    this.wakeDetector.onDetect((score) => {
                        if (!this.isProcessing) this._onWakeWord();
                    });
                    console.log('✅ Wake word ONNX pronto');
                } else {
                    this.wakeDetector = null;
                }
            } catch(e) {
                console.warn('ONNX non disponibile, uso fallback SpeechRecognition:', e.message);
                this.wakeDetector = null;
            }
        }

        // 3. Fallback SpeechRecognition per wake word
        if (!this.wakeDetector) this._initFallbackRecognition();

        console.log('✅ ContinuousVoiceLoop inizializzato');
        return true;
    }

    async start() {
        if (this.isActive) return;
        this.isActive = true;
        this._startListening();
    }

    // ── Routing ascolto ──────────────────────────────────────────────────────

    _startListening() {
        if (!this.isActive || this.isProcessing) return;

        if (this.conversationActive) {
            this._listenDirect();
        } else {
            this._startWakeWordListening();
        }
    }

    _startWakeWordListening() {
        if (this.onStatusChange) this.onStatusChange('listening', 'Di\' "Hey Jarvis" per iniziare');

        if (this.wakeDetector) {
            this.wakeDetector.start();
        } else {
            this._startFallbackListening();
        }
    }

    /**
     * Modalità conversazione: ascolta qualsiasi frase senza wake word.
     * Timeout 30s → torna a modalità wake word.
     */
    _listenDirect() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) { this._startWakeWordListening(); return; }

        if (this.onStatusChange) this.onStatusChange('listening', '👂 Ti ascolto...');

        this._directRecog = new SR();
        this._directRecog.lang = 'it-IT';
        this._directRecog.continuous = false;
        this._directRecog.interimResults = false;

        this._directRecog.onresult = (event) => {
            const transcript = event.results[0][0].transcript.trim();
            if (transcript && !this.isProcessing) {
                clearTimeout(this._conversationTimer);
                this._onCommand();
            }
        };

        this._directRecog.onerror = (event) => {
            if (event.error === 'no-speech') {
                // Silenzio: decrementa timer (già impostato in _resetConversationTimer)
            } else if (event.error !== 'aborted') {
                this._endConversation();
            }
        };

        this._directRecog.onend = () => {
            if (this.isActive && !this.isProcessing && this.conversationActive) {
                setTimeout(() => this._listenDirect(), 200);
            }
        };

        try { this._directRecog.start(); } catch(e) {}
    }

    // ── Wake word rilevata ───────────────────────────────────────────────────

    async _onWakeWord() {
        if (this.isProcessing) return;

        // Ferma tutti i listener
        if (this.wakeDetector) this.wakeDetector.stop();
        if (this.fallbackRecog) { try { this.fallbackRecog.stop(); } catch(e) {} }

        this.conversationActive = true;
        if (this.onStatusChange) this.onStatusChange('recording', '✅ Attivato! Ti ascolto...');

        // Risposta vocale di conferma, poi piccola pausa prima di registrare
        await this._say('Dimmi');
        await new Promise(r => setTimeout(r, 300));

        await this._onCommand();
    }

    async _onCommand() {
        if (this.isProcessing) return;
        this.isProcessing = true;

        // Ferma direct listener se attivo
        if (this._directRecog) { try { this._directRecog.stop(); } catch(e) {} this._directRecog = null; }

        if (this.onStatusChange) this.onStatusChange('recording', 'Parla pure...');

        // Piccola pausa prima di registrare
        await new Promise(r => setTimeout(r, 200));

        const started = await this.voiceLoop.startRecording();
        if (!started) {
            this.isProcessing = false;
            this._startListening();
            return;
        }

        // Auto-stop dopo 10s
        this._recordingTimeout = setTimeout(() => {
            if (this.voiceLoop.isRecording) this.voiceLoop.stopRecording();
        }, 10000);

        this._startSilenceDetection();
    }

    // ── Rilevamento silenzio ─────────────────────────────────────────────────

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

    // ── Timer conversazione (30s inattività → torna a wake word) ─────────────

    _resetConversationTimer() {
        clearTimeout(this._conversationTimer);
        this._conversationTimer = setTimeout(() => {
            if (!this.isProcessing) {
                console.log('⏱️ 30s inattività, torno a modalità wake word');
                this._endConversation();
            }
        }, 30000);
    }

    _endConversation() {
        this.conversationActive = false;
        clearTimeout(this._conversationTimer);
        if (this._directRecog) { try { this._directRecog.stop(); } catch(e) {} this._directRecog = null; }
        this._startWakeWordListening();
    }

    // ── Fallback SpeechRecognition per wake word ─────────────────────────────

    _initFallbackRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;

        this.fallbackRecog = new SR();
        this.fallbackRecog.lang = 'it-IT';
        this.fallbackRecog.continuous = true;
        this.fallbackRecog.interimResults = false;

        this.fallbackRecog.onresult = (event) => {
            const t = event.results[event.results.length - 1][0].transcript.toLowerCase().trim();
            if ((t.includes('jarvis') || t.includes('alexa')) && !this.isProcessing) {
                console.log('🎯 Wake word rilevata (fallback):', t);
                this._onWakeWord();
            }
        };

        this.fallbackRecog.onerror = (event) => {
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                setTimeout(() => this._startFallbackListening(), 1000);
            }
        };

        this.fallbackRecog.onend = () => {
            if (this.isActive && !this.isProcessing && !this.conversationActive) {
                setTimeout(() => this._startFallbackListening(), 200);
            }
        };
    }

    _startFallbackListening() {
        if (!this.fallbackRecog || !this.isActive || this.isProcessing || this.conversationActive) return;
        try { this.fallbackRecog.start(); } catch(e) {}
    }

    // ── Risposta vocale breve ────────────────────────────────────────────────

    async _say(text) {
        return new Promise((resolve) => {
            if (!window.speechSynthesis) { resolve(); return; }
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(text);
            u.lang = 'it-IT';
            // Prova a usare voce italiana se disponibile
            const voices = window.speechSynthesis.getVoices();
            const itVoice = voices.find(v => v.lang.startsWith('it'));
            if (itVoice) u.voice = itVoice;
            u.onend = resolve;
            u.onerror = resolve;
            window.speechSynthesis.speak(u);
        });
    }

    // ── Stop ─────────────────────────────────────────────────────────────────

    stop() {
        this.isActive = false;
        this.conversationActive = false;
        clearTimeout(this._conversationTimer);
        clearTimeout(this._recordingTimeout);
        if (this.wakeDetector) this.wakeDetector.stop();
        if (this.fallbackRecog) { try { this.fallbackRecog.stop(); } catch(e) {} }
        if (this._directRecog) { try { this._directRecog.stop(); } catch(e) {} }
        if (this.voiceLoop) this.voiceLoop.disconnect();
        if (this.onStatusChange) this.onStatusChange('stopped', 'Loop vocale fermato');
        console.log('🛑 ContinuousVoiceLoop fermato');
    }
}

window.ContinuousVoiceLoop = ContinuousVoiceLoop;
