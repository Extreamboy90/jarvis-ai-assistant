/**
 * JARVIS PWA - Configuration
 */

const CONFIG = {
    // Default server URL - nginx proxia tutto sulla stessa origine (porta 443)
    DEFAULT_SERVER_URL: `${window.location.protocol}//${window.location.host}`,

    // STT e TTS instradati tramite nginx con prefisso path
    STT_URL: `${window.location.protocol}//${window.location.host}/stt`,
    TTS_URL: `${window.location.protocol}//${window.location.host}/tts`,

    // WebSocket URL
    WS_ENDPOINT: '/ws',

    // API endpoints
    API_ENDPOINTS: {
        CHAT: '/chat',
        HEALTH: '/health',
        FUNCTIONS: '/functions'
    },

    // Voice recognition settings
    VOICE: {
        LANG: 'it-IT',
        CONTINUOUS: false,
        INTERIM_RESULTS: true,
        MAX_ALTERNATIVES: 1
    },

    // TTS settings
    TTS: {
        LANG: 'it-IT',
        RATE: 1.0,
        PITCH: 1.0,
        VOLUME: 1.0
    },

    // Local storage keys
    STORAGE_KEYS: {
        SERVER_URL: 'jarvis_server_url',
        USER_ID: 'jarvis_user_id',
        AUTO_SPEAK: 'jarvis_auto_speak',
        DARK_MODE: 'jarvis_dark_mode',
        SESSION_ID: 'jarvis_session_id'
    }
};

// Helper functions per localStorage
const Storage = {
    get(key, defaultValue = null) {
        const value = localStorage.getItem(key);
        if (value === null) return defaultValue;
        try {
            return JSON.parse(value);
        } catch {
            return value;
        }
    },

    set(key, value) {
        localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
    },

    remove(key) {
        localStorage.removeItem(key);
    },

    clear() {
        localStorage.clear();
    }
};

// Generate session ID
function generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Get or create session ID
function getSessionId() {
    let sessionId = Storage.get(CONFIG.STORAGE_KEYS.SESSION_ID);
    if (!sessionId) {
        sessionId = generateSessionId();
        Storage.set(CONFIG.STORAGE_KEYS.SESSION_ID, sessionId);
    }
    return sessionId;
}
