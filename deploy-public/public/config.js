// ================================
// Public Dashboard Configuration
// Azure Static Web App
// ================================

const CONFIG = {
    backend: {
        // NodePort público (accessible desde internet)
        baseUrl: 'http://192.168.1.134:30081'
    },
    signalr: {
        endpoint: 'https://signalr-spy-options.service.signalr.net',
        negotiateUrl: 'https://func-spy-negotiate.azurewebsites.net/api/negotiate'
    },
    environment: 'production'
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
