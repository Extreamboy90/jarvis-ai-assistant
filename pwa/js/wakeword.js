/**
 * JARVIS PWA - Wake Word Detection
 * Uses OpenWakeWord + ONNX Runtime for "Hey Jarvis" detection
 */

class WakeWordDetector {
    constructor() {
        this.session = null;
        this.audioContext = null;
        this.processor = null;
        this.stream = null;
        this.isListening = false;
        this.onDetectCallback = null;

        // Model parameters (from OpenWakeWord hey_jarvis model)
        this.modelPath = '/models/hey_jarvis.onnx';
        this.sampleRate = 16000;
        this.frameSize = 1280; // 80ms at 16kHz
        this.threshold = 0.5;
        this.cooldownMs = 2000;
        this.lastDetectionTime = 0;

        this.audioBuffer = [];
    }

    /**
     * Initialize ONNX Runtime and load model
     */
    async initialize() {
        try {
            console.log('🔧 Initializing Wake Word Detector...');

            // Load ONNX Runtime
            const ort = window.ort;
            if (!ort) {
                console.error('ONNX Runtime not found in window.ort');
                throw new Error('ONNX Runtime not loaded');
            }

            console.log('✅ ONNX Runtime found, version:', ort.version || 'unknown');

            // Load model
            console.log('📥 Loading hey_jarvis.onnx model from:', this.modelPath);

            try {
                this.session = await ort.InferenceSession.create(this.modelPath, {
                    executionProviders: ['wasm'],
                    graphOptimizationLevel: 'all'
                });
            } catch (modelError) {
                console.error('❌ Model loading failed:', modelError);
                console.error('Model path:', this.modelPath);
                console.error('Error details:', modelError.message);
                throw new Error(`Cannot load model: ${modelError.message}`);
            }

            console.log('✅ Wake Word Detector initialized successfully');
            console.log('Model input names:', this.session.inputNames);
            console.log('Model output names:', this.session.outputNames);
            return true;

        } catch (error) {
            console.error('❌ Wake word initialization failed:', error);
            console.error('Full error:', error);
            return false;
        }
    }

    /**
     * Start listening for wake word
     */
    async start() {
        if (this.isListening) {
            console.log('Already listening for wake word');
            return false;
        }

        try {
            // Get microphone access
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: this.sampleRate,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });

            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate
            });

            const source = this.audioContext.createMediaStreamSource(this.stream);

            // Create script processor for audio data
            const bufferSize = 4096;
            this.processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

            this.processor.onaudioprocess = (event) => {
                const inputData = event.inputBuffer.getChannelData(0);
                this.processAudio(inputData);
            };

            source.connect(this.processor);
            this.processor.connect(this.audioContext.destination);

            this.isListening = true;
            console.log('🎤 Wake word detection started - say "Hey Jarvis"');
            return true;

        } catch (error) {
            console.error('❌ Failed to start wake word detection:', error);
            return false;
        }
    }

    /**
     * Process audio frames for wake word detection
     */
    processAudio(audioData) {
        // Add to buffer
        this.audioBuffer.push(...audioData);

        // Process when we have enough data
        while (this.audioBuffer.length >= this.frameSize) {
            const frame = this.audioBuffer.splice(0, this.frameSize);
            this.detectWakeWord(frame);
        }
    }

    /**
     * Run ONNX model inference
     */
    async detectWakeWord(audioFrame) {
        try {
            // Check cooldown
            const now = Date.now();
            if (now - this.lastDetectionTime < this.cooldownMs) {
                return;
            }

            // Prepare input tensor (Float32Array)
            const inputTensor = new ort.Tensor('float32', new Float32Array(audioFrame), [1, this.frameSize]);

            // Run inference
            const feeds = { audio: inputTensor };
            const results = await this.session.run(feeds);

            // Get output score
            const output = results.output;
            const score = output.data[0];

            // Check threshold
            if (score > this.threshold) {
                console.log(`🎯 Wake word detected! Score: ${score.toFixed(3)}`);
                this.lastDetectionTime = now;

                if (this.onDetectCallback) {
                    this.onDetectCallback(score);
                }
            }

        } catch (error) {
            console.error('❌ Wake word detection error:', error);
        }
    }

    /**
     * Stop listening
     */
    stop() {
        if (!this.isListening) return;

        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }

        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.audioBuffer = [];
        this.isListening = false;
        console.log('🛑 Wake word detection stopped');
    }

    /**
     * Set detection callback
     */
    onDetect(callback) {
        this.onDetectCallback = callback;
    }

    /**
     * Check if wake word detection is supported
     */
    static isSupported() {
        return !!(navigator.mediaDevices && window.ort);
    }
}

// Create global instance
const wakeWord = new WakeWordDetector();
