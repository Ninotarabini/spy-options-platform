(function () {
    function detectBackend() {
        // 1. Variable inyectada por Helm (K3s) o GitHub Actions (Azure)
        const injected = "${BACKEND_URL}";
        if (injected && injected.length > 0 && !injected.startsWith("$")) {
            console.log("[CONFIG] Using injected BACKEND_URL:", injected);
            return injected;
        }

        // 2. Detección automática por hostname (Azure Static Web Apps)
        const hostname = window.location.hostname;
        if (hostname.includes("azurestaticapps.net") || hostname === "0dte-spy.com" || hostname === "www.0dte-spy.com") {
            const azureBackend = "https://app-spy-options-backend.azurewebsites.net";
            console.log("[CONFIG] Detected Azure environment, using:", azureBackend);
            return azureBackend;
        }

        // 3. Fallback: Mismo origen (K3s local)
        const fallback = window.location.origin;
        console.log("[CONFIG] Using fallback (same origin):", fallback);
        return fallback;
    }

    const backendUrl = detectBackend();

    window.CONFIG = {
        signalr: {
            negotiateUrl: `${backendUrl}/negotiate`
        },
        backend: {
            baseUrl: backendUrl
        },
        environment: "${ENVIRONMENT}" || "production",
        version: "${APP_VERSION}",
        atmRangePercent: 1.5,
    };

    console.log(`[CONFIG] Version: ${window.CONFIG.version} | Backend: ${window.CONFIG.backend.baseUrl}`);
})();