(function () {
    function detectBackend() {
        // 1. Prioridad: Variable inyectada por Kubernetes/Helm
        const injected = "${BACKEND_URL}";
        if (injected && injected.length > 0 && !injected.startsWith("$")) {
            return injected;
        }

        // 2. Resiliencia: Uso de origin para evitar URLs malformadas (http:///)
        if (window.location.origin && window.location.origin !== "null") {
            return window.location.origin;
        }

        // 3. Fallback: IP de respaldo si falla la detección automática
        const hostname = window.location.hostname || "192.168.1.134";
        const port = window.location.port ? `:${window.location.port}` : "";
        const protocol = window.location.protocol.includes('http') ? window.location.protocol : "http:";

        return `${protocol}//${hostname}${port}`;
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
    };

    console.log(`[CONFIG] Version: ${window.CONFIG.version} | Backend: ${window.CONFIG.backend.baseUrl}`);
})();