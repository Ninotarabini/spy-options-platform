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

        // 2. Entorno K3s Local (LAN)
        // Si accedemos por IP, determinamos si el backend está en el mismo host
        if (hostname.startsWith("192.168.") || hostname.startsWith("10.")) {
            // Si el frontend está en el 30080, el backend suele estar en el 30081 (NodePort)
            // Si usas un Ingress (Traefik) en puerto 80, se queda sin puerto.
            const backendPort = (port === "30080") ? ":30081" : "";
            return "http://" + hostname + backendPort;
        }

        // 3. Localhost (Desarrollo)
        if (hostname === "localhost") {
            return "http://localhost:8000";
        }

        // 4. Fallback de Seguridad (Azure)
        return "https://app-spy-options-backend.azurewebsites.net";
    }

    const backendUrl = detectBackend();

    // Inyectamos el objeto CONFIG en el scope global (window)
    window.CONFIG = {
        signalr: {
            // URL directa del servicio SignalR o el endpoint de negociación
            endpoint: "https://signalr-spy-options.service.signalr.net",
            negotiateUrl: backendUrl + "/negotiate" // Ajustado según rutas estándar de Azure
        },
        backend: {
            baseUrl: backendUrl
        },
        environment: hostname.includes("azurestaticapps") ? "production" : "local",
        version: "2.1.0"
    };

    // Log de verificación para la consola del navegador
    console.log(`%c🚀 CONFIG LOADED [%c${window.CONFIG.environment}%c]`,
        "color: #888", "color: #00ff00; font-weight: bold", "color: #888");
    console.log("[CONFIG] Backend Target:", window.CONFIG.backend.baseUrl);
})();