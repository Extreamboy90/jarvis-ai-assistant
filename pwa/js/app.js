/**
 * JARVIS PWA - Main Application
 * Entry point and application initialization
 */

class JarvisApp {
    constructor() {
        this.initialized = false;
    }

    /**
     * Initialize the application
     */
    async init() {
        if (this.initialized) return;

        console.log('🤖 Initializing Jarvis PWA...');

        // Initialize UI
        ui.init();

        // Check if user needs to set their name (first time setup)
        if (!api.userId) {
            this.showUserSetup();
            return; // Wait for user to set name before continuing
        }

        // Check browser compatibility
        this.checkCompatibility();

        // Initialize API connection
        await this.initializeConnection();

        // Setup WebSocket (optional, fallback to HTTP)
        this.setupWebSocket();

        // Initialize Continuous Conversation Mode
        await this.initializeContinuousMode();

        // Mark as initialized
        this.initialized = true;

        console.log('✅ Jarvis PWA initialized successfully');
    }

    /**
     * Initialize continuous conversation mode
     */
    async initializeContinuousMode() {
        // Initialize continuous voice loop
        try {
            window.continuousVoice = new ContinuousVoiceLoop(
                api.serverUrl || CONFIG.SERVER_URL,
                api.userId || 'voice_user'
            );

            // Setup callbacks
            window.continuousVoice.onStatusChange = (status, message) => {
                console.log(`Status: ${status} - ${message}`);
                // Update UI status indicator
                const statusEl = document.querySelector('.status-text');
                if (statusEl) {
                    statusEl.textContent = message;
                }
            };

            window.continuousVoice.onTranscript = (text) => {
                ui.addMessage(text, 'user');
            };

            window.continuousVoice.onResponse = (text) => {
                ui.addMessage(text, 'assistant');
            };

            await window.continuousVoice.initialize();

            ui.addMessage(
                '🎙️ Loop vocale continuo attivo! Dì "Alexa" seguito dal tuo comando.',
                'assistant'
            );

            // Auto-start continuous mode
            await window.continuousVoice.start();

        } catch (error) {
            console.warn('Continuous voice not available:', error.message);
        }
    }

    /**
     * Show user setup modal (first time only)
     */
    showUserSetup() {
        const modal = document.getElementById('userSetupModal');
        const input = document.getElementById('userSetupName');
        const btnSave = document.getElementById('btnSaveUserName');

        modal.classList.remove('hidden');
        input.focus();

        const saveUserName = async () => {
            const userName = input.value.trim();
            const userIdNormalized = userName.toLowerCase();

            if (!userName) {
                input.style.borderColor = 'var(--accent)';
                setTimeout(() => input.style.borderColor = '', 2000);
                return;
            }

            // Disable button during save
            btnSave.disabled = true;
            btnSave.textContent = 'Salvando...';

            // Set user ID
            api.setUserId(userIdNormalized);
            console.log('✅ User ID set:', userIdNormalized);

            // Send message to save memory automatically
            const message = `Mi chiamo ${userName}`;
            try {
                await api.sendMessage(message, 1);
                console.log('✅ Initial memory saved');
            } catch (error) {
                console.warn('⚠️ Could not save initial memory:', error);
            }

            // Wait a moment for memory extraction
            await new Promise(resolve => setTimeout(resolve, 2000));

            modal.classList.add('hidden');
            btnSave.disabled = false;
            btnSave.textContent = 'Continua';

            // Continue initialization
            this.init();
        };

        btnSave.addEventListener('click', saveUserName);
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') saveUserName();
        });
    }

    /**
     * Check browser compatibility
     */
    checkCompatibility() {
        const support = VoiceManager.isSupported();

        if (!support.recognition) {
            console.warn('⚠️ Speech Recognition not supported');
            ui.addMessage(
                'Il riconoscimento vocale non è supportato dal tuo browser. Usa Chrome o Edge per la funzionalità completa.',
                'assistant'
            );
        }

        if (!support.synthesis) {
            console.warn('⚠️ Speech Synthesis not supported');
        }

        // Check if PWA
        if (window.matchMedia('(display-mode: standalone)').matches) {
            console.log('📱 Running as installed PWA');
        }
    }

    /**
     * Initialize connection to backend
     */
    async initializeConnection() {
        ui.updateConnectionStatus(false);

        // Check server health
        const health = await api.checkHealth();

        if (health.healthy) {
            console.log('✅ Server healthy:', health.data);
            ui.updateConnectionStatus(true);
        } else {
            console.warn('⚠️ Server unreachable');
            ui.addMessage(
                'Impossibile connettersi al server. Verifica che Jarvis sia in esecuzione.',
                'assistant',
                true
            );
        }
    }

    /**
     * Setup WebSocket connection
     */
    setupWebSocket() {
        // Set connection change callback
        api.onConnectionChange = (connected) => {
            ui.updateConnectionStatus(connected);
            if (connected) {
                ui.addMessage('Connessione WebSocket stabilita', 'assistant');
            }
        };

        // Set message callback
        api.onMessage((data) => {
            console.log('WebSocket message received:', data);

            if (data.type === 'response') {
                ui.addMessage(data.message, 'assistant');

                // Auto-speak if enabled
                if (voice.autoSpeak) {
                    voice.speak(data.message);
                }
            } else if (data.type === 'notification') {
                ui.addMessage(data.message, 'assistant');
            }
        });

        // Initialize WebSocket (will fallback to HTTP if not available)
        try {
            api.initWebSocket();
        } catch (error) {
            console.warn('WebSocket initialization failed, using HTTP fallback');
        }
    }

    /**
     * Handle app visibility change
     */
    handleVisibilityChange() {
        if (document.hidden) {
            console.log('App hidden');
            // Optionally pause some features
        } else {
            console.log('App visible');
            // Optionally resume features
        }
    }

    /**
     * Handle app being installed as PWA
     */
    handlePWAInstall() {
        let deferredPrompt;

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;

            // Show install button or prompt
            console.log('PWA install available');

            // You could add an "Install App" button here
        });

        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
            ui.addMessage('App installata con successo!', 'assistant');
            deferredPrompt = null;
        });
    }
}

// Create global app instance
const app = new JarvisApp();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}

// Handle visibility changes
document.addEventListener('visibilitychange', () => app.handleVisibilityChange());

// Handle PWA installation
app.handlePWAInstall();

// Handle window resize
window.addEventListener('resize', () => {
    // Adjust UI if needed
});

// Handle online/offline events
window.addEventListener('online', () => {
    console.log('Connection restored');
    ui.addMessage('Connessione ripristinata', 'assistant');
    api.initWebSocket();
});

window.addEventListener('offline', () => {
    console.log('Connection lost');
    ui.addMessage('Connessione persa. Modalità offline.', 'assistant', true);
});
