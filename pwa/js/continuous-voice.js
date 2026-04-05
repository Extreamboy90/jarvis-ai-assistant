/**
 * Continuous Voice Loop - Always listening with wake word detection
 * Flow: Listen → Wake Word → Record → Send → Response → Loop
 */

class ContinuousVoiceLoop {
    constructor(serverUrl, userId) {
        this.serverUrl = serverUrl;
        this.userId = userId;
        this.isActive = false;
        this.isProcessing = false;

        // Web Speech API
        this.recognition = null;
        this.synthesis = window.speechSynthesis;

        // WebSocket for audio streaming
        this.voiceLoop = null;

        // State
        this.listeningForWakeWord = false;
        this.recordingCommand = false;

        // Callbacks
        this.onStatusChange = null;
        this.onTranscript = null;
        this.onResponse = null;
    }

    async initialize() {
        // Check browser support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            throw new Error('Speech Recognition not supported');
        }

        // Initialize recognition for wake word
        this.recognition = new SpeechRecognition();
        this.recognition.lang = 'it-IT';
        this.recognition.continuous = true;
        this.recognition.interimResults = false;

        // Initialize voice loop WebSocket
        this.voiceLoop = new VoiceLoopWebSocket(this.serverUrl, this.userId);

        // Setup voice loop callbacks
        this.voiceLoop.onTranscription = (text) => {
            console.log('📝 Transcription:', text);
            if (this.onTranscript) this.onTranscript(text);
        };

        this.voiceLoop.onResponse = (text) => {
            console.log('💬 Response:', text);
            if (this.onResponse) this.onResponse(text);
        };

        this.voiceLoop.onAudioPlay = async () => {
            console.log('🔊 Audio finished, restarting loop...');
            this.isProcessing = false;
            // Restart listening after response
            await this.startListeningForWakeWord();
        };

        this.voiceLoop.onError = (error) => {
            console.error('❌ Voice loop error:', error);
            this.isProcessing = false;
            this.startListeningForWakeWord();
        };

        await this.voiceLoop.initialize();
        const connected = await this.voiceLoop.connect();

        if (!connected) {
            throw new Error('Failed to connect to voice service');
        }

        console.log('✅ Continuous voice loop initialized');
        return true;
    }

    async start() {
        if (this.isActive) {
            console.log('Already active');
            return;
        }

        this.isActive = true;
        console.log('🎙️ Starting continuous voice loop...');

        if (this.onStatusChange) {
            this.onStatusChange('listening', 'In ascolto per wake word...');
        }

        await this.startListeningForWakeWord();
    }

    async startListeningForWakeWord() {
        if (!this.isActive || this.isProcessing) return;

        this.listeningForWakeWord = true;
        this.recordingCommand = false;

        console.log('👂 Listening for wake word (say "Alexa")...');

        if (this.onStatusChange) {
            this.onStatusChange('listening', 'Dimmi "Alexa" per iniziare...');
        }

        // Setup recognition handlers
        this.recognition.onresult = async (event) => {
            const last = event.results.length - 1;
            const transcript = event.results[last][0].transcript.toLowerCase().trim();

            console.log('Heard:', transcript);

            // Check for wake word
            if (transcript.includes('alexa') || transcript.includes('alexia')) {
                console.log('🎯 Wake word detected!');
                this.recognition.stop();
                await this.handleWakeWordDetected();
            }
        };

        this.recognition.onerror = (event) => {
            console.error('Recognition error:', event.error);
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                // Restart on error
                setTimeout(() => {
                    if (this.isActive && !this.isProcessing) {
                        this.recognition.start();
                    }
                }, 1000);
            }
        };

        this.recognition.onend = () => {
            // Auto-restart if still active and not processing
            if (this.isActive && !this.isProcessing && this.listeningForWakeWord) {
                console.log('🔄 Restarting wake word detection...');
                setTimeout(() => this.recognition.start(), 100);
            }
        };

        try {
            this.recognition.start();
        } catch (error) {
            console.error('Failed to start recognition:', error);
        }
    }

    async handleWakeWordDetected() {
        if (this.isProcessing) return;

        this.isProcessing = true;
        this.listeningForWakeWord = false;
        this.recordingCommand = true;

        console.log('🎤 Wake word activated! Recording command...');

        if (this.onStatusChange) {
            this.onStatusChange('recording', 'Ti ascolto, parla pure...');
        }

        // Play feedback beep (optional)
        this.playBeep();

        // Wait a moment for user to start speaking
        await new Promise(resolve => setTimeout(resolve, 300));

        // Start recording via voice loop
        const started = await this.voiceLoop.startRecording();

        if (!started) {
            console.error('Failed to start recording');
            this.isProcessing = false;
            this.startListeningForWakeWord();
            return;
        }

        // Auto-stop after 10 seconds (max command length)
        this.commandTimeout = setTimeout(() => {
            if (this.recordingCommand) {
                console.log('⏱️ Command timeout, stopping...');
                this.voiceLoop.stopRecording();
                this.recordingCommand = false;
            }
        }, 10000);

        // Detect silence to auto-stop (using Web Speech as VAD)
        this.startSilenceDetection();
    }

    startSilenceDetection() {
        // Create temporary recognition for silence detection
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const silenceDetector = new SpeechRecognition();
        silenceDetector.lang = 'it-IT';
        silenceDetector.continuous = true;
        silenceDetector.interimResults = true;

        let lastSpeechTime = Date.now();
        const SILENCE_THRESHOLD = 2000; // 2 seconds of silence

        silenceDetector.onresult = (event) => {
            // Update last speech time
            lastSpeechTime = Date.now();
        };

        silenceDetector.onend = () => {
            // Check if we should stop recording
            const silenceDuration = Date.now() - lastSpeechTime;

            if (silenceDuration >= SILENCE_THRESHOLD && this.recordingCommand) {
                console.log('🔇 Silence detected, stopping recording...');
                clearTimeout(this.commandTimeout);
                this.voiceLoop.stopRecording();
                this.recordingCommand = false;

                if (this.onStatusChange) {
                    this.onStatusChange('processing', 'Elaborazione in corso...');
                }
            }
        };

        // Start silence detection
        try {
            silenceDetector.start();

            // Stop after command timeout
            setTimeout(() => {
                silenceDetector.stop();
            }, 10000);
        } catch (error) {
            console.warn('Silence detection not available, using timeout only');
        }
    }

    playBeep() {
        // Simple beep sound to confirm wake word
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.value = 800; // Hz
        gainNode.gain.value = 0.1; // Volume

        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.1); // 100ms beep
    }

    stop() {
        this.isActive = false;
        this.listeningForWakeWord = false;
        this.recordingCommand = false;

        if (this.recognition) {
            this.recognition.stop();
        }

        if (this.commandTimeout) {
            clearTimeout(this.commandTimeout);
        }

        if (this.voiceLoop) {
            this.voiceLoop.disconnect();
        }

        console.log('🛑 Continuous voice loop stopped');

        if (this.onStatusChange) {
            this.onStatusChange('stopped', 'Loop vocale fermato');
        }
    }
}

// Export to window
window.ContinuousVoiceLoop = ContinuousVoiceLoop;
