/**
 * JARVIS PWA - API Communication
 * Handles HTTP and WebSocket communication with backend
 */

class JarvisAPI {
    constructor() {
        this.serverUrl = Storage.get(CONFIG.STORAGE_KEYS.SERVER_URL, CONFIG.DEFAULT_SERVER_URL);
        // [FIX] User ID from localStorage - set by user on first launch
        this.userId = Storage.get(CONFIG.STORAGE_KEYS.USER_ID) || null;
        this.sessionId = getSessionId();
        this.ws = null;
        this.wsReconnectAttempts = 0;
        this.wsMaxReconnectAttempts = 5;
        this.wsReconnectDelay = 1000;
        this.onMessageCallback = null;
        this.onConnectionChange = null;
    }

    /**
     * Set server URL
     */
    setServerUrl(url) {
        this.serverUrl = url;
        Storage.set(CONFIG.STORAGE_KEYS.SERVER_URL, url);
    }

    /**
     * Set user ID
     */
    setUserId(userId) {
        this.userId = userId;
        Storage.set(CONFIG.STORAGE_KEYS.USER_ID, userId);
    }

    /**
     * Send chat message via HTTP POST
     */
    async sendMessage(message, maxHistory = 3) {
        try {
            const response = await fetch(`${this.serverUrl}${CONFIG.API_ENDPOINTS.CHAT}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    user_id: this.userId,
                    session_id: this.sessionId,
                    max_history: maxHistory
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return {
                success: true,
                response: data.response,
                functionCalls: data.function_calls
            };
        } catch (error) {
            console.error('API Error:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Check server health
     */
    async checkHealth() {
        try {
            const response = await fetch(`${this.serverUrl}${CONFIG.API_ENDPOINTS.HEALTH}`, {
                method: 'GET',
                signal: AbortSignal.timeout(5000) // 5 second timeout
            });

            if (response.ok) {
                const data = await response.json();
                return { healthy: true, data };
            }
            return { healthy: false };
        } catch (error) {
            console.error('Health check failed:', error);
            return { healthy: false, error: error.message };
        }
    }

    /**
     * Get available functions
     */
    async getFunctions() {
        try {
            const response = await fetch(`${this.serverUrl}${CONFIG.API_ENDPOINTS.FUNCTIONS}`);
            if (!response.ok) throw new Error('Failed to fetch functions');
            const data = await response.json();
            return data.functions || [];
        } catch (error) {
            console.error('Failed to get functions:', error);
            return [];
        }
    }

    /**
     * Initialize WebSocket connection
     */
    initWebSocket() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return;
        }

        const wsUrl = this.serverUrl.replace('http://', 'ws://').replace('https://', 'wss://');
        const wsEndpoint = `${wsUrl}${CONFIG.WS_ENDPOINT}?user_id=${this.userId}&session_id=${this.sessionId}`;

        console.log('Connecting to WebSocket:', wsEndpoint);

        try {
            this.ws = new WebSocket(wsEndpoint);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.wsReconnectAttempts = 0;
                if (this.onConnectionChange) {
                    this.onConnectionChange(true);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (this.onMessageCallback) {
                        this.onMessageCallback(data);
                    }
                } catch (error) {
                    console.error('WebSocket message parse error:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                if (this.onConnectionChange) {
                    this.onConnectionChange(false);
                }

                // Attempt reconnection
                if (this.wsReconnectAttempts < this.wsMaxReconnectAttempts) {
                    this.wsReconnectAttempts++;
                    const delay = this.wsReconnectDelay * this.wsReconnectAttempts;
                    console.log(`Reconnecting in ${delay}ms (attempt ${this.wsReconnectAttempts})`);
                    setTimeout(() => this.initWebSocket(), delay);
                }
            };
        } catch (error) {
            console.error('WebSocket initialization error:', error);
        }
    }

    /**
     * Send message via WebSocket
     */
    sendWebSocketMessage(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.error('WebSocket not connected');
            return false;
        }
        return true;
    }

    /**
     * Set WebSocket message callback
     */
    onMessage(callback) {
        this.onMessageCallback = callback;
    }

    /**
     * Close WebSocket connection
     */
    closeWebSocket() {
        if (this.ws) {
            this.wsReconnectAttempts = this.wsMaxReconnectAttempts; // Prevent reconnection
            this.ws.close();
            this.ws = null;
        }
    }
}

// Create global API instance
const api = new JarvisAPI();
