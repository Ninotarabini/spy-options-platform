// ================================
// Frontend Configuration Template
// Copy to config.js and fill with real values
// ================================

const CONFIG = {
    signalr: {
        endpoint: 'https://signalr-spy-options.service.signalr.net',
        accessKey: 'YOUR_SIGNALR_ACCESS_KEY_HERE'
    },
    environment: 'production'
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
