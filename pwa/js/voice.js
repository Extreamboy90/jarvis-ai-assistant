/**
 * JARVIS PWA - Voice Recognition & Synthesis
 * Handles speech-to-text and text-to-speech using Web Speech API
 */

class VoiceManager {
    constructor() {
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.isListening = false;
        this.autoSpeak = Storage.get(CONFIG.STORAGE_KEYS.AUTO_SPEAK, true);

        // Callbacks
        this.onTranscriptCallback = null;
        this.onEndCallback = null;
        this.onErrorCallback = null;

        // Continuous listening mode
        this.isSpeaking = false; // Track if TTS is playing
        this.continuousMode = false;
        this.autoRestartAfterSpeech = false; // Auto-restart listening after TTS

        this.initRecognition();
    }

    /**
     * Initialize speech recognition
     */
    initRecognition() {
        // Check browser support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.warn('Speech Recognition not supported in this browser');
            return;
        }

        this.recognition = new SpeechRecognition();
        this.recognition.lang = CONFIG.VOICE.LANG;
        this.recognition.continuous = CONFIG.VOICE.CONTINUOUS;
        this.recognition.interimResults = CONFIG.VOICE.INTERIM_RESULTS;
        this.recognition.maxAlternatives = CONFIG.VOICE.MAX_ALTERNATIVES;

        // Event handlers
        this.recognition.onstart = () => {
            console.log('Voice recognition started');
            this.isListening = true;
        };

        this.recognition.onresult = (event) => {
            const last = event.results.length - 1;
            const result = event.results[last];
            const transcript = result[0].transcript.trim();
            const isFinal = result.isFinal;

            console.log('Transcript:', transcript, 'Final:', isFinal);

            // Only process if not currently speaking (avoid feedback loop)
            if (isFinal && !this.isSpeaking && transcript) {
                if (this.onTranscriptCallback) {
                    this.onTranscriptCallback(transcript, isFinal);
                }
            }
        };

        this.recognition.onerror = (event) => {
            console.error('Voice recognition error:', event.error);
            this.isListening = false;

            if (this.onErrorCallback) {
                this.onErrorCallback(event.error);
            }
        };

        this.recognition.onend = () => {
            console.log('Voice recognition ended');
            this.isListening = false;

            if (this.onEndCallback) {
                this.onEndCallback();
            }
        };
    }


    /**
     * Start continuous mode - auto-restart after each response
     */
    async startContinuousMode() {
        this.continuousMode = true;
        this.autoRestartAfterSpeech = true;
        console.log('✅ Continuous mode enabled');

        // Start first recording
        return await this.startListening();
    }

    /**
     * Stop continuous mode
     */
    stopContinuousMode() {
        this.continuousMode = false;
        this.autoRestartAfterSpeech = false;
        console.log('🛑 Continuous mode disabled');

        // Stop current recording if active
        if (this.isListening) {
            this.stopListening();
        }
    }

    /**
     * Start recording - Manual mode (hold to talk) or continuous
     */
    async startListening() {
        if (this.isListening) {
            console.log('Already listening');
            return false;
        }

        // Su HTTP navigator.mediaDevices non è disponibile → fallback Web Speech API
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            console.warn('⚠️ navigator.mediaDevices non disponibile (HTTP). Uso Web Speech API.');
            return this._startWebSpeech();
        }

        try {
            // Get microphone access
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm'
            });

            this.audioChunks = [];
            this.stream = stream;

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = async () => {
                console.log('🎤 Recording stopped, processing...');

                // Create audio blob
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });

                // Send to backend STT
                await this.transcribeAudio(audioBlob);

                // Stop media stream
                stream.getTracks().forEach(track => track.stop());
                this.isListening = false;
            };

            this.mediaRecorder.start();
            this.isListening = true;

            if (this.continuousMode) {
                console.log('🎤 Listening... (continuous mode - 30s max)');
                // Auto-stop after 30 seconds to process
                this.autoStopTimeout = setTimeout(() => {
                    if (this.isListening && this.continuousMode) {
                        console.log('⏱️ 30s timeout reached, processing...');
                        this.stopListening();
                    }
                }, 30000);
            } else {
                console.log('🎤 Recording started... Release button to send');
            }

            return true;

        } catch (error) {
            console.error('Error starting recording:', error);
            if (this.onErrorCallback) {
                this.onErrorCallback(error.message);
            }
            return false;
        }
    }

    /**
     * Transcribe audio using backend STT
     */
    async transcribeAudio(audioBlob) {
        try {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');

            console.log('📤 Sending audio to STT...');

            const response = await fetch(`${CONFIG.STT_URL}/transcribe`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`STT failed: ${response.status}`);
            }

            const data = await response.json();
            const transcript = data.text || data.transcription || '';

            console.log('✅ Transcription:', transcript);

            // Call transcript callback
            if (this.onTranscriptCallback && transcript && !this.isSpeaking) {
                this.onTranscriptCallback(transcript, true);
            }

        } catch (error) {
            console.error('❌ Transcription error:', error);
            if (this.onErrorCallback) {
                this.onErrorCallback(error.message);
            }
        }
    }

    /**
     * Fallback: Web Speech API per contesti HTTP (senza microfono diretto)
     */
    _startWebSpeech() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            console.error('SpeechRecognition non supportato');
            if (this.onErrorCallback) this.onErrorCallback('microfono non disponibile su HTTP');
            return false;
        }

        this.isListening = true;
        const recognition = new SR();
        recognition.lang = 'it-IT';
        recognition.continuous = false;
        recognition.interimResults = false;
        this._webSpeechInstance = recognition;

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript.trim();
            console.log('✅ Web Speech transcript:', transcript);
            this.isListening = false;
            if (this.onTranscriptCallback && transcript) {
                this.onTranscriptCallback(transcript, true);
            }
        };

        recognition.onerror = (event) => {
            console.error('Web Speech error:', event.error);
            this.isListening = false;
            if (this.onErrorCallback) this.onErrorCallback(event.error);
        };

        recognition.onend = () => {
            this.isListening = false;
        };

        recognition.start();
        return true;
    }

    /**
     * Stop recording and process
     */
    stopListening() {
        if (this._webSpeechInstance) {
            try { this._webSpeechInstance.stop(); } catch(e) {}
            this._webSpeechInstance = null;
        }
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
            console.log('🛑 Recording stopped, processing...');
        }
    }

    /**
     * Speak text using backend TTS (Edge TTS)
     */
    async speak(text, onEnd = null) {
        try {
            // Mark as speaking to prevent feedback loop
            this.isSpeaking = true;

            console.log('🔊 Requesting TTS for:', text.substring(0, 50) + '...');

            // Create Audio element BEFORE fetch (Safari iOS fix)
            const audio = new Audio();

            // Try to unlock audio context on iOS
            audio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            audio.play().catch(() => {});

            const response = await fetch(`${CONFIG.TTS_URL}/speak`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text: text })
            });

            if (!response.ok) {
                throw new Error(`TTS failed: ${response.status}`);
            }

            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);

            // Set the real audio source
            audio.src = audioUrl;

            audio.onended = () => {
                console.log('✅ Speech finished');
                URL.revokeObjectURL(audioUrl);
                this.isSpeaking = false; // Resume listening

                // Auto-restart listening if continuous mode enabled
                if (this.autoRestartAfterSpeech && this.continuousMode) {
                    console.log('🔄 Restarting listening (continuous mode)...');
                    setTimeout(() => {
                        this.startListening();
                    }, 500);
                }

                if (onEnd) onEnd();
            };

            audio.onerror = (event) => {
                console.error('❌ Audio playback error:', event);
                URL.revokeObjectURL(audioUrl);
                this.isSpeaking = false; // Resume listening even on error
            };

            console.log('▶️ Playing audio...');
            await audio.play();
            console.log('🎵 Audio playing');
            return true;

        } catch (error) {
            console.error('❌ Backend TTS failed, falling back to browser:', error);
            // Fallback to browser TTS
            return this.speakBrowser(text, onEnd);
        }
    }

    /**
     * Fallback: Browser TTS
     */
    speakBrowser(text, onEnd = null) {
        if (!this.synthesis) {
            console.warn('Speech Synthesis not supported');
            return false;
        }

        this.isSpeaking = true;
        this.synthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = CONFIG.TTS.LANG;
        utterance.rate = CONFIG.TTS.RATE;
        utterance.pitch = CONFIG.TTS.PITCH;
        utterance.volume = CONFIG.TTS.VOLUME;

        const voices = this.synthesis.getVoices();
        const italianVoice = voices.find(voice => voice.lang.startsWith('it'));
        if (italianVoice) {
            utterance.voice = italianVoice;
        }

        utterance.onend = () => {
            console.log('Speech finished');
            this.isSpeaking = false;

            // Auto-restart listening if continuous mode enabled
            if (this.autoRestartAfterSpeech && this.continuousMode) {
                console.log('🔄 Restarting listening (continuous mode)...');
                setTimeout(() => {
                    this.startListening();
                }, 500);
            }

            if (onEnd) onEnd();
        };

        utterance.onerror = (event) => {
            console.error('Speech error:', event.error);
            this.isSpeaking = false;
        };

        this.synthesis.speak(utterance);
        return true;
    }

    /**
     * Stop speaking
     */
    stopSpeaking() {
        if (this.synthesis) {
            this.synthesis.cancel();
        }
    }

    /**
     * Set callbacks
     */
    onTranscript(callback) {
        this.onTranscriptCallback = callback;
    }

    onEnd(callback) {
        this.onEndCallback = callback;
    }

    onError(callback) {
        this.onErrorCallback = callback;
    }

    /**
     * Check if browser supports voice
     */
    static isSupported() {
        const hasRecognition = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
        const hasSynthesis = !!window.speechSynthesis;
        return {
            recognition: hasRecognition,
            synthesis: hasSynthesis,
            full: hasRecognition && hasSynthesis
        };
    }

    /**
     * Get available voices
     */
    getVoices() {
        return this.synthesis ? this.synthesis.getVoices() : [];
    }

    /**
     * Set auto-speak preference
     */
    setAutoSpeak(enabled) {
        this.autoSpeak = enabled;
        Storage.set(CONFIG.STORAGE_KEYS.AUTO_SPEAK, enabled);
    }
}

// Create global voice manager instance
const voice = new VoiceManager();

// Load voices when available (Chrome needs this)
if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => {
        console.log('Voices loaded:', voice.getVoices().length);
    };
}
