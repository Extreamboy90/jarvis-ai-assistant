/**
 * JARVIS PWA - UI Manager
 * Handles all UI interactions and updates
 */

class UIManager {
    constructor() {
        this.elements = {};
        this.isVoiceOverlayOpen = false;
        this.isSettingsOpen = false;
        this.currentTranscript = '';
    }

    /**
     * Initialize UI elements and event listeners
     */
    init() {
        // Get DOM elements
        this.elements = {
            messages: document.getElementById('messages'),
            messageInput: document.getElementById('messageInput'),
            btnSend: document.getElementById('btnSend'),
            btnVoice: document.getElementById('btnVoice'),
            btnCamera: document.getElementById('btnCamera'),
            voiceOverlay: document.getElementById('voiceOverlay'),
            voiceText: document.getElementById('voiceText'),
            voiceTranscript: document.getElementById('voiceTranscript'),
            btnCancelVoice: document.getElementById('btnCancelVoice'),
            connectionStatus: document.getElementById('connectionStatus'),
            fabMenu: document.getElementById('fabMenu'),
            settingsPanel: document.getElementById('settingsPanel'),
            btnCloseSettings: document.getElementById('btnCloseSettings'),
            serverUrl: document.getElementById('serverUrl'),
            userId: document.getElementById('userId'),
            autoSpeak: document.getElementById('autoSpeak'),
            darkMode: document.getElementById('darkMode'),
            btnSaveSettings: document.getElementById('btnSaveSettings')
        };

        this.bindEvents();
        this.loadSettings();
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        // Send message
        this.elements.btnSend.addEventListener('click', () => this.handleSendMessage());
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleSendMessage();
        });

        // Voice input
        this.elements.btnVoice.addEventListener('click', () => this.handleVoiceInput());
        this.elements.btnCancelVoice.addEventListener('click', () => this.closeVoiceOverlay());

        // Camera (placeholder)
        this.elements.btnCamera.addEventListener('click', () => this.handleCamera());

        // Settings
        this.elements.fabMenu.addEventListener('click', () => this.openSettings());
        this.elements.btnCloseSettings.addEventListener('click', () => this.closeSettings());
        this.elements.btnSaveSettings.addEventListener('click', () => this.saveSettings());
    }

    /**
     * Handle send message
     */
    async handleSendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message) return;

        // Clear input
        this.elements.messageInput.value = '';

        // Add user message to UI
        this.addMessage(message, 'user');

        // Show typing indicator
        this.showTypingIndicator();

        // Send to API
        const result = await api.sendMessage(message);

        // Remove typing indicator
        this.removeTypingIndicator();

        if (result.success) {
            this.addMessage(result.response, 'assistant');

            // Auto-speak if enabled
            if (voice.autoSpeak) {
                voice.speak(result.response);
            }
        } else {
            this.addMessage(`Errore: ${result.error}`, 'assistant', true);
        }
    }

    /**
     * Handle voice input
     */
    handleVoiceInput() {
        this.openVoiceOverlay();
        this.currentTranscript = '';

        voice.onTranscript((transcript, isFinal) => {
            this.elements.voiceTranscript.textContent = transcript;
            this.currentTranscript = transcript;

            if (isFinal) {
                // Send message
                this.closeVoiceOverlay();
                this.elements.messageInput.value = transcript;
                this.handleSendMessage();
            }
        });

        voice.onError((error) => {
            this.closeVoiceOverlay();
            this.addMessage(`Errore riconoscimento vocale: ${error}`, 'assistant', true);
        });

        voice.startListening();
    }

    /**
     * Handle camera
     */
    async handleCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            // TODO: Implement camera capture
            alert('Funzionalità fotocamera in sviluppo');
            stream.getTracks().forEach(track => track.stop());
        } catch (error) {
            alert('Impossibile accedere alla fotocamera: ' + error.message);
        }
    }

    /**
     * Add message to chat
     */
    addMessage(text, sender = 'assistant', isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message${isError ? ' error-message' : ''}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = sender === 'user' ? 'U' : 'J';

        const content = document.createElement('div');
        content.className = 'message-content';

        const p = document.createElement('p');
        p.textContent = text;

        content.appendChild(p);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    /**
     * Show typing indicator
     */
    showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'message assistant-message typing-message';
        indicator.id = 'typingIndicator';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = 'J';

        const content = document.createElement('div');
        content.className = 'message-content';

        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

        content.appendChild(typing);
        indicator.appendChild(avatar);
        indicator.appendChild(content);

        this.elements.messages.appendChild(indicator);
        this.scrollToBottom();
    }

    /**
     * Remove typing indicator
     */
    removeTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    /**
     * Scroll chat to bottom
     */
    scrollToBottom() {
        this.elements.messages.parentElement.scrollTop = this.elements.messages.parentElement.scrollHeight;
    }

    /**
     * Open voice overlay
     */
    openVoiceOverlay() {
        this.elements.voiceOverlay.classList.remove('hidden');
        this.elements.voiceTranscript.textContent = '';
        this.isVoiceOverlayOpen = true;
    }

    /**
     * Close voice overlay
     */
    closeVoiceOverlay() {
        this.elements.voiceOverlay.classList.add('hidden');
        this.isVoiceOverlayOpen = false;
        voice.stopListening();
    }

    /**
     * Open settings
     */
    openSettings() {
        this.elements.settingsPanel.classList.remove('hidden');
        this.isSettingsOpen = true;
    }

    /**
     * Close settings
     */
    closeSettings() {
        this.elements.settingsPanel.classList.add('hidden');
        this.isSettingsOpen = false;
    }

    /**
     * Load settings from storage
     */
    loadSettings() {
        this.elements.serverUrl.value = api.serverUrl;
        this.elements.userId.value = api.userId;
        this.elements.autoSpeak.checked = voice.autoSpeak;
        this.elements.darkMode.checked = Storage.get(CONFIG.STORAGE_KEYS.DARK_MODE, true);
    }

    /**
     * Save settings
     */
    saveSettings() {
        const serverUrl = this.elements.serverUrl.value.trim();
        const userId = this.elements.userId.value.trim();
        const autoSpeak = this.elements.autoSpeak.checked;
        const darkMode = this.elements.darkMode.checked;

        if (serverUrl) {
            api.setServerUrl(serverUrl);
        }

        if (userId) {
            api.setUserId(userId);
        }

        voice.setAutoSpeak(autoSpeak);
        Storage.set(CONFIG.STORAGE_KEYS.DARK_MODE, darkMode);

        this.closeSettings();
        this.addMessage('Impostazioni salvate', 'assistant');

        // Reconnect WebSocket with new settings
        api.closeWebSocket();
        api.initWebSocket();
    }

    /**
     * Update connection status
     */
    updateConnectionStatus(connected) {
        const statusDot = this.elements.connectionStatus.querySelector('.status-dot');
        const statusText = this.elements.connectionStatus.querySelector('.status-text');

        if (connected) {
            statusDot.classList.add('connected');
            statusDot.classList.remove('disconnected');
            statusText.textContent = 'Connesso';
        } else {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected');
            statusText.textContent = 'Disconnesso';
        }
    }
}

// Create global UI manager instance
const ui = new UIManager();
