/**
 * SPY Options - Configuration Manager
 * Universal file for Local (K3s) and Azure environments.
 */
(function () {
    const hostname = window.location.hostname;
    const port = window.location.port;

    function detectBackend() {
        // 1. Entorno de Azure (Producción Pública)
        if (hostname.includes("azurestaticapps.net")) {
            return "https://app-spy-options-backend.azurewebsites.net";
        }

        // 2. Entorno Local (LAN, Localhost o 127.0.0.1)
        // Combinamos todo lo que no sea Azure para que use el puerto 30081
        if (
            hostname.includes("192.168.") ||
            hostname.includes("10.") ||
            hostname === "localhost" ||
            hostname === "127.0.0.1"
        ) {
            // Al estar tras un Ingress, usamos el mismo host y puerto de la web
            return "";
        }

        // 3. Fallback (Por si accedes por un nombre de red local diferente)
        // En local, mejor devolver la IP con el puerto que la URL de Azure
        return "http://" + hostname + ":30080";
    }

    const backendUrl = detectBackend();

    // Inyectamos el objeto CONFIG en el scope global (window)
    window.CONFIG = {
        signalr: {
            negotiateUrl: hostname.includes("azurestaticapps.net")
                ? "https://func-spy-negotiate.azurewebsites.net/negotiate"
                : `${backendUrl}/negotiate`
        },
        backend: {
            baseUrl: backendUrl
        },
        environment: hostname.includes("azurestaticapps.net") ? "production" : "local",
        version: "2.14"
    };

    // Log de verificación para la consola del navegador
    console.log(`%c🚀 CONFIG LOADED [%c${window.CONFIG.environment}%c]`,
        "color: #888", "color: #00ff00; font-weight: bold", "color: #888");
    console.log("[CONFIG] Backend Target:", window.CONFIG.backend.baseUrl);
})();