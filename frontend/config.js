// ================================
// Frontend Configuration
// DO NOT COMMIT THIS FILE
// ================================

const CONFIG = {
    signalr: {
        endpoint: 'https://signalr-spy-options.service.signalr.net',
        accessKey: 'E8RGgXvdWzoRpVLV0wqleG2Mfhfgav0bsYU0XU8znYg2H2lI0b2nJQQJ99BLAC5RqLJXJ3w3AAAAASRSfYQi'
    },
    environment: 'development'
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
