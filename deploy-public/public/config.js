(function () {
    const hostname = window.location.hostname;

    function detectBackend() {
        // 1. LAN access (K8s NodePort)
        if (hostname.startsWith("192.168.") || hostname.startsWith("10."))
            return "http://" + hostname;  // Traefik ingress (port 80)

        // 2. Azure Static Web App
        if (hostname.includes("azurestaticapps.net"))
            return "https://app-spy-options-backend.azurewebsites.net";

        // 3. Localhost dev
        if (hostname === "localhost")
            return "http://localhost:8000";

        // 4. Fallback
        return "https://app-spy-options-backend.azurewebsites.net";
    }

    const backend = detectBackend();

    window.CONFIG = {
        signalr: {
            endpoint: "https://signalr-spy-options.service.signalr.net",
            negotiateUrl: backend + "/negotiate"
        },
        backend: {
            baseUrl: backend
        },
        environment: "production"
    };

    console.log("[CONFIG] Backend:", backend, "| Env:", window.CONFIG.environment);
})();
