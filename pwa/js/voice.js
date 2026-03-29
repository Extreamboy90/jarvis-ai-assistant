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
            const transcript = result[0].transcript;
            const isFinal = result.isFinal;

            console.log('Transcript:', transcript, 'Final:', isFinal);

            if (this.onTranscriptCallback) {
                this.onTranscriptCallback(transcript, isFinal);
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
     * Start listening
     */
    startListening() {
        if (!this.recognition) {
            alert('Riconoscimento vocale non supportato dal tuo browser');
            return false;
        }

        if (this.isListening) {
            console.log('Already listening');
            return false;
        }

        try {
            this.recognition.start();
            return true;
        } catch (error) {
            console.error('Error starting recognition:', error);
            return false;
        }
    }

    /**
     * Stop listening
     */
    stopListening() {
        if (this.recognition && this.isListening) {
            this.recognition.stop();
        }
    }

    /**
     * Speak text using TTS
     */
    speak(text, onEnd = null) {
        if (!this.synthesis) {
            console.warn('Speech Synthesis not supported');
            return false;
        }

        // Cancel any ongoing speech
        this.synthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = CONFIG.TTS.LANG;
        utterance.rate = CONFIG.TTS.RATE;
        utterance.pitch = CONFIG.TTS.PITCH;
        utterance.volume = CONFIG.TTS.VOLUME;

        // Try to find Italian voice
        const voices = this.synthesis.getVoices();
        const italianVoice = voices.find(voice => voice.lang.startsWith('it'));
        if (italianVoice) {
            utterance.voice = italianVoice;
        }

        utterance.onend = () => {
            console.log('Speech finished');
            if (onEnd) onEnd();
        };

        utterance.onerror = (event) => {
            console.error('Speech error:', event.error);
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
