// ================================
// Frontend Configuration Template
// Copy to config.js and fill with real values
// ================================

const CONFIG = {
    signalr: {
        endpoint: 'https://YOUR-SIGNALR-NAME.service.signalr.net',
        accessKey: 'YOUR_SIGNALR_ACCESS_KEY_HERE'
    },
    environment: 'development'
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
