// ================================
// PHASE 8: SignalR Configuration
// ================================
console.log("APP.JS LOADED", performance.now());
// Configuration (loaded from config.js or environment)
const SIGNALR_ENDPOINT = CONFIG?.signalr?.endpoint || 'https://signalr-spy-options.service.signalr.net';
const SIGNALR_ACCESS_KEY = CONFIG?.signalr?.accessKey || null;

// Validate configuration
//if (!SIGNALR_ACCESS_KEY) {
   // console.warn('⚠️ SignalR Access Key not configured. Connection will fail.');
   // console.warn('📝 Copy config.template.js to config.js and add your key');
//}

function safeToFixed(value, decimals = 2) {
    return Number.isFinite(value)
        ? value.toFixed(decimals)
        : (0).toFixed(decimals);
}

// Helper para formatear timestamps Unix a hora legible
function formatTimestamp(unixTimestamp) {
    return new Date(unixTimestamp * 1000).toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// ================================
// PHASE 8: SignalR Configuration (updated)
// ================================

let timeLabels = [];
let callVolumeHistory = [];
let putVolumeHistory = [];
let spyPriceHistory = [];
let smoothCalls = 0;
let smoothPuts = 0;
let flowChartInstance = null;
const SMOOTHING_FACTOR = 0.2;

let signalRConnection = null;
let isConnected = false;

// =====================================
// ANOMALY ALERTS MANAGEMENT (OPTIMIZED)
// =====================================

const MAX_ANOMALIES_BUFFER = 100;  // Previene memory leak
let callsAnomalies = [];
let putsAnomalies = [];

// DOM cache (performance optimization)
let callsColumn = null;
let putsColumn = null;
let renderTimeout = null;  // Debouncing

// ========================================
// PERSISTENCIA DE DATOS (4 HORAS)
// ========================================

// Cargar datos guardados al inicio
// Línea ~47

function setupFlowChart() {
    const ctx = document.getElementById('flowChart');
    if (!ctx) return;

    flowChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [
                {
                    label: 'Calls',
                    data: callVolumeHistory,
                    borderColor: '#00ff88',
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'Puts',
                    data: putVolumeHistory,
                    borderColor: '#ff4444',
                    backgroundColor: 'rgba(255, 68, 68, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'SPY Price',
                    data: spyPriceHistory,
                    borderColor: '#ffd700',
                    borderDash: [1, 1],
                    tension: 0.2,
                    pointRadius: 0,
                    borderWidth: 1.5,
                    yAxisID: 'yPrice'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: false
                },
/*                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(13, 20, 38, 0.9)',
                    titleColor: '#00d4ff',
                    bodyColor: '#ffffff',
                    borderColor: '#1e293b',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            let value = context.parsed.y;
                            if (label.includes('Price')) {
                                return `${label}: $${value.toFixed(2)}`;
                            }
                            return `${label}: $${value.toFixed(2)}M`;
                        }
                    }
                }
                    */

                annotation: {
                    annotations: {
                        previousCloseLine: {
                            type: 'line',
                            scaleID: 'yPrice',
                            value: () => window.lastPreviousClose ?? 688,  // Arrow function para actualización dinámica
                            borderColor: '#45648e',
                            borderWidth: 1,
                            label: {
                                display: true,
                                content: () => `Cierre ant: ${(window.lastPreviousClose ?? 688).toFixed(2)}`,  // También dinámico
                                position: 'start'
                            }
                        },
                        
                        // ✅ Línea vertical apertura 15:30 CET
                        marketOpenLine: {
                            type: 'line',
                            scaleID: 'x',
                            value: null, // Se calcula dinámicamente
                            borderColor: '#00d4ff',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            display: (ctx) => {
                                // Solo mostrar si 15:30 CET está en rango visible
                                const chart = ctx.chart;
                                const xScale = chart.scales.x;
                                if (!xScale || !xScale._labelItems) return false;

                                // Calcular timestamp de hoy 15:30 CET
                                const now = new Date();
                                const cetTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
                                const marketOpen = new Date(cetTime);
                                marketOpen.setHours(15, 30, 0, 0);

                                // Obtener rango visible del gráfico
                                const visibleLabels = chart.data.labels || [];
                                if (visibleLabels.length === 0) return false;

                                const firstLabel = visibleLabels[0];
                                const lastLabel = visibleLabels[visibleLabels.length - 1];

                                // Verificar si marketOpen está dentro del rango
                                return marketOpen >= firstLabel && marketOpen <= lastLabel;
                            },
                            label: {
                                display: true,
                                content: '📈 Open 15:30',
                                position: 'start',
                                backgroundColor: 'rgba(0, 212, 255, 0.8)',
                                color: '#fff',
                                font: {
                                    size: 11,
                                    weight: 'bold'
                                },
                                padding: 4
                            },
                            // Actualizar value antes de cada render
                            beforeDraw: (chart) => {
                                const now = new Date();
                                const cetTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
                                const marketOpen = new Date(cetTime);
                                marketOpen.setHours(15, 30, 0, 0);

                                // Actualizar el value dinámicamente
                                const annotation = chart.options.plugins.annotation.annotations.marketOpenLine;
                                annotation.value = marketOpen;
                            }
                        },

                        // ✅ Zona naranja cierre 22:00-22:15 CET
                        marketCloseZone: {
                            type: 'box',
                            xScaleID: 'x',
                            yScaleID: 'y',
                            xMin: null, // Se calcula dinámicamente
                            xMax: null,
                            yMin: -1000, // Cubre todo el eje Y
                            yMax: 1000,
                            backgroundColor: 'rgba(255, 100, 0, 0.12)',
                            borderColor: 'rgba(255, 100, 0, 0.3)',
                            borderWidth: 1,
                            display: (ctx) => {
                                // Solo mostrar si 22:00-22:15 está en rango visible
                                const chart = ctx.chart;
                                const visibleLabels = chart.data.labels || [];
                                if (visibleLabels.length === 0) return false;

                                // Calcular timestamps de hoy 22:00 y 22:15 CET
                                const now = new Date();
                                const cetTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
                                const closeStart = new Date(cetTime);
                                closeStart.setHours(22, 0, 0, 0);
                                const closeEnd = new Date(cetTime);
                                closeEnd.setHours(22, 15, 0, 0);

                                const firstLabel = visibleLabels[0];
                                const lastLabel = visibleLabels[visibleLabels.length - 1];

                                // Mostrar si cualquier parte de la zona está visible
                                return (closeStart <= lastLabel && closeEnd >= firstLabel);
                            },
                            label: {
                                display: true,
                                content: '🔴 Close 22:00-22:15',
                                position: 'center',
                                backgroundColor: 'rgba(255, 100, 0, 0.8)',
                                color: '#fff',
                                font: {
                                    size: 11,
                                    weight: 'bold'
                                },
                                padding: 4
                            },
                            // Actualizar xMin/xMax antes de cada render
                            beforeDraw: (chart) => {
                                const now = new Date();
                                const cetTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
                                const closeStart = new Date(cetTime);
                                closeStart.setHours(22, 0, 0, 0);
                                const closeEnd = new Date(cetTime);
                                closeEnd.setHours(22, 15, 0, 0);

                                // Actualizar los límites dinámicamente
                                const annotation = chart.options.plugins.annotation.annotations.marketCloseZone;
                                annotation.xMin = closeStart;
                                annotation.xMax = closeEnd;
                            }
                        }
                    }
                },

                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(15, 20, 70, 0.8)',
                    titleColor: '#cccccc',
                    titleFont: {
                        size: 12,
                        weight: 'bold'
                    },
                    bodyColor: '#cccccc',
                    bodyFont: {
                        size: 12
                    },
                    borderColor: 'rgba(14, 58, 67, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    boxWidth: 10,
                    boxHeight: 10,
                    usePointStyle: true,
                    pointStyle: 'circle',
                    callbacks: {
                        title: function (context) {
                            const raw = context[0].raw; // o context[0].label
                            let date;

                            // Si raw es objeto con propiedad x (timestamp)
                            if (raw && raw.x) {
                                date = new Date(raw.x);
                            }
                            // Si raw es directamente un Date o string
                            else if (raw instanceof Date) {
                                date = raw;
                            }
                            // Si context[0].label es Date
                            else if (context[0].label instanceof Date) {
                                date = context[0].label;
                            }
                            // Fallback: convertir string si es necesario
                            else {
                                date = new Date(context[0].label);
                            }

                            if (date instanceof Date && !isNaN(date)) {
                                const timeStr = date.toLocaleTimeString('es-ES', {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    second: '2-digit'
                                });
                                const dateStr = date.toLocaleDateString('es-ES', {
                                    day: '2-digit',
                                    month: '2-digit',
                                    year: '2-digit'
                                });
                                return `🕐 ${timeStr} ${dateStr} CET`;
                            }

                            return '🕐 --:--:-- --/--/-- CET';
                        }
                    }
                }   
            },
            scales: {
                x: {
                    display: false,
                    type: 'category',
                    grid: { display: false },
                    ticks: {
                        autoSkip: false,
                        maxTicksLimit: 12,
                        callback: function (value, index, values) {
                            const label = this.getLabelForValue(value); // ← ahora es Date
                            if (!label) return null;

                            // Extraer hora y minuto del Date
                            const hours = label.getHours().toString().padStart(2, '0');
                            const minutes = label.getMinutes().toString().padStart(2, '0');

                            // Mostrar solo :00 y :30
                            if (minutes === '00' || minutes === '30') {
                                return `${hours}:${minutes}`;
                            }
                            return null;
                        },
                        color: '#94a3b8',
                        font: { size: 10 }
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Flow (Millions $)' }
                },
                yPrice: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'SPY Price ($)', color: '#94a3b8' },
                    ticks: { color: '#94a3b8' },
                    afterDataLimits: (axis) => {
                        axis.min -= 0.5;
                        axis.max += 0.5;
                    }
                }
            }
        }
    });
}


function loadPersistedFlowData() {
    try {
        const saved = localStorage.getItem('flowData');
        if (!saved) return;

        const data = JSON.parse(saved);

        // Solo cargar si los datos no son muy viejos (menos de 6 horas)
        if (data.lastUpdate && data.lastUpdate > (Date.now() - 6 * 60 * 60 * 1000)) {
            if (data.timeLabels && data.timeLabels.length > 0) {
                // Convertir strings guardados a objetos Date
                timeLabels = data.timeLabels.map(str => new Date(str));
                callVolumeHistory = data.callVolumeHistory || [];
                putVolumeHistory = data.putVolumeHistory || [];
                spyPriceHistory = data.spyPriceHistory || [];

                console.log(`✅ Cargados ${timeLabels.length} puntos históricos (convertidos a Date)`);
                drawChart();
            } else {
                console.log('⚠️ Formato de datos obsoleto, limpiando localStorage');
                localStorage.removeItem('flowData');
            }
        }
    } catch (e) {
        console.warn('Error cargando datos históricos:', e);
        localStorage.removeItem('flowData');
    }
}

// Guardar datos en localStorage
function persistFlowData() {
    try {
        localStorage.setItem('flowData', JSON.stringify({
            timeLabels,
            callVolumeHistory,
            putVolumeHistory,
            spyPriceHistory,
            lastUpdate: Date.now()
        }));
    } catch (e) {
        console.warn('Error guardando datos:', e);
    }
}

// ========================================
// PERSISTENCIA DE MARKET STATE (NUEVO)
// ========================================

// Guardar estado de mercado (% SPY, ATM Range)
function persistMarketState() {
    try {
        localStorage.setItem('marketState', JSON.stringify({
            spyChangePct: window.lastSpyChangePct,
            atmRange: window.atmRange,
            spyPrice: window.currentSpyPrice,
            lastUpdate: Date.now()
        }));
    } catch (e) {
        console.warn('Error guardando market state:', e);
    }
}

// Cargar estado de mercado guardado
function loadPersistedMarketState() {
    try {
        const saved = localStorage.getItem('marketState');
        if (!saved) return;

        const state = JSON.parse(saved);
        
        // Restaurar % SPY
        if (state.spyChangePct !== undefined) {
            updateSpyChangePct(state.spyChangePct);
            window.lastSpyChangePct = state.spyChangePct;
        }
        
        // Restaurar ATM Range
        if (state.atmRange?.min && state.atmRange?.max) {
            updateATMRange(state.atmRange);
            window.atmRange = state.atmRange;
        }
        
        // Restaurar precio SPY
        if (state.spyPrice) {
            window.currentSpyPrice = state.spyPrice;
        }
        
        console.log('✅ Market state restored:', state);
    } catch (e) {
        console.warn('Error loading market state:', e);
    }
}

// ==========================================
// ORQUESTADOR DE ARRANQUE
// =

// === LOAD MARKET STATE (FASE 2) ===
async function loadMarketState() {
    try {
        const response = await fetch(`${CONFIG.apiUrl}/api/market/state`);
        if (!response.ok) {
            console.warn('⚠️ Market state not available yet');
            return;
        }
        
        const state = await response.json();
        
        // Cache valores globales
        window.previousClose = state.previous_close;
        window.atmRange = {
            min: state.atm_min,
            max: state.atm_max
        };
        window.marketStatus = state.market_status;
        
        console.log('✅ Market state loaded:', state);
        console.log(`📌 Cached: previous_close=${window.previousClose}, atm_range=[${window.atmRange.min}, ${window.atmRange.max}]`);
        
        // Update UI with initial values
        updateATMRange(window.atmRange);
        updateMarketStatus(window.marketStatus);
        
    } catch (error) {
        console.error('❌ Error loading market state:', error);
    }
}

// Calculate derived metrics locally
function calculateDerivedMetrics(spyPrice) {
    if (!spyPrice || !window.previousClose) return;
    
    // Calculate % change
    const pct = ((spyPrice - window.previousClose) / window.previousClose) * 100;
    updateSpyChangePct(pct);
    
    // ATM range (only if integer strike changed)
    const atmCenter = Math.round(spyPrice);
    if (!window.currentAtmCenter || window.currentAtmCenter !== atmCenter) {
        window.currentAtmCenter = atmCenter;
        window.atmRange = {
            min: atmCenter - 5,
            max: atmCenter + 5
        };
        updateATMRange(window.atmRange);
        console.log(`🎯 ATM updated: ${atmCenter} (±5)`);
    }
}

async function startApp() {
    console.log("🚀 Iniciando aplicación...");

    setupFlowChart();           // Crea el gráfico vacío
    await loadInitialVolumes(); // Carga las 96h de datos de Azure
    await initSignalR();        // Conecta el tiempo real
}

// EJECUTAMOS EL ARRANQUE
//startApp();

// Luego iniciamos la conexión para recibir datos
async function initSignalR() {
    try {
        // Step 1: Get SignalR connection info from backend
        const negotiateUrl = CONFIG.signalr.negotiateUrl;

        console.log(`[SignalR] Fetching connection info from ${negotiateUrl}`);
        const response = await fetch(negotiateUrl);

        if (!response.ok) {
            throw new Error(`Negotiate failed: ${response.status}`);
        }

        const connectionInfo = await response.json();
        console.log('[SignalR] Connection info received:', connectionInfo.url);
        console.log('[SignalR] Token received (hidden for security)');

        // Step 2: Build SignalR connection with token
        signalRConnection = new signalR.HubConnectionBuilder()
            .withUrl(connectionInfo.url, {
                accessTokenFactory: () => connectionInfo.accessToken,
                transport: signalR.HttpTransportType.WebSockets,
            })
            .withAutomaticReconnect()
            .build();

        // Step 3: Event handlers
        signalRConnection.on('anomalyDetected', handleAnomalyAlert);
        
        signalRConnection.on('flow', (data) => {
            console.log(`📊 Flow Update [${formatTimestamp(data.timestamp)}]:`, data);

            if (!window.lastPreviousClose) {
                window.lastPreviousClose = 684.50; // estimado hasta que IBKR envíe el real
                console.log('📌 Usando previous_close estimado: 684.50');
            }

            // Cachear previous_close solo la primera vez (evitar logs constantes)
            if (data.previous_close && !window.previousCloseSet) {
                window.lastPreviousClose = data.previous_close;
                window.previousCloseSet = true;
                console.log('✅ previous_close inicializado:', data.previous_close);
            }

            // Siempre guardamos los datos (rápido)
            timeLabels.push(new Date());
            callVolumeHistory.push(data.cum_call_flow / 1e6);
            putVolumeHistory.push(data.cum_put_flow / 1e6);
            spyPriceHistory.push(data.spy_price);
            if (!window.flowTimestamps) window.flowTimestamps = [];
            window.flowTimestamps.push(data.timestamp);
            updateSpyPrice(data.spy_price, data.atm_range);
            if (data.spy_change_pct !== undefined) {
                updateSpyChangePct(data.spy_change_pct);
            }

            // Control de update cada 2 segundos
            const ahora = Date.now();
            if (!window.ultimoUpdate) window.ultimoUpdate = 0;
            const INTERVALO_UPDATE = 2000;

            if (ahora - window.ultimoUpdate >= INTERVALO_UPDATE) {
                window.ultimoUpdate = ahora;

                // Limpieza eficiente con búsqueda binaria
                const cuatroHorasAtras = ahora - 4 * 60 * 60 * 1000;

                // Búsqueda binaria del primer índice válido
                let left = 0;
                let right = timeLabels.length - 1;
                let primerValido = timeLabels.length;

                while (left <= right) {
                    const mid = Math.floor((left + right) / 2);
                    if (timeLabels[mid].getTime() >= cuatroHorasAtras) {
                        primerValido = mid;
                        right = mid - 1;
                    } else {
                        left = mid + 1;
                    }
                }

                // Quitar todos los anteriores de una vez
                if (primerValido > 0) {
                    timeLabels.splice(0, primerValido);
                    callVolumeHistory.splice(0, primerValido);
                    putVolumeHistory.splice(0, primerValido);
                    spyPriceHistory.splice(0, primerValido);
                    window.flowTimestamps.splice(0, primerValido);
                }

                // Persistir cada 10 segundos
                if (!window.lastPersist || ahora - window.lastPersist > 10000) {
                    persistFlowData();
                    persistMarketState(); // ✅ NUEVO: Guardar market state también
                    window.lastPersist = ahora;
                }

                // Actualizar tarjetas
                const callsM = data.cum_call_flow / 1e6;
                const putsM = data.cum_put_flow / 1e6;
                updateMetricCards(callsM, putsM);

                // Actualizar gráfico de forma optimizada
                if (flowChartInstance) {
                    flowChartInstance.update('none'); 
                }
            }
        });

    // === PRICE CHANNEL (FASE 2) ===
    signalRConnection.on('price', (data) => {
        console.log(`💲 Price Update: $${data.price}`);
        window.currentSpyPrice = data.price;
        updateSpyPrice(data.price);
        calculateDerivedMetrics(data.price);
    });

        
        signalRConnection.onreconnecting((error) => {
            console.warn('[SignalR] Reconnecting...', error);
            updateConnectionStatus('reconnecting');
        });

        signalRConnection.onreconnected(() => {
            console.log('[SignalR] Reconnected');
            updateConnectionStatus('connected');
        });

        signalRConnection.onclose((error) => {
            console.error('[SignalR] Connection closed', error);
            updateConnectionStatus('disconnected');
            startMockDataFallback();
        });

        // Step 4: Start connection once
        if (!isConnected) {
            await signalRConnection.start();
            isConnected = true;
            console.log('[SignalR] Connected successfully');

            // Cargar datos históricos guardados
            loadPersistedFlowData();

            updateConnectionStatus(true, '● Market Data Connected');
        }

    } 
    
    catch (error) {
        console.error('[SignalR] Connection failed:', error);
        updateConnectionStatus(false, '● Connection Error');
        startMockDataFallback();
    }
}

// Fallback function to simulate data
function startMockDataFallback() {
    if (!window.mockDataRunning) {
        console.log('[Mock] Using simulated data for development');
        window.mockDataRunning = true;
    }
}

// Update connection status UI
function updateConnectionStatus(connected, text) {
    const statusEl = document.querySelector('.status');
    if (statusEl) {
        statusEl.textContent = text;
        statusEl.style.color = connected ? '#FF2A00' : '#ff6b6b';
    }
}

// Handle incoming anomaly alert (OPTIMIZED VERSION)
function handleAnomalyAlert(anomaly) {
    // Validación básica
    if (!anomaly || !anomaly.option_type) return;
    
    // Clasificar por tipo
    const isPut = anomaly.option_type === 'PUT' || anomaly.option_type === 'P';
    
    if (isPut) {
        putsAnomalies.push(anomaly);
        // Limitar buffer para prevenir memory leak
        if (putsAnomalies.length > MAX_ANOMALIES_BUFFER) {
            putsAnomalies.shift();
        }
    } else {
        callsAnomalies.push(anomaly);
        if (callsAnomalies.length > MAX_ANOMALIES_BUFFER) {
            callsAnomalies.shift();
        }
    }
    
    // Debounced render (evita render en cada anomalía durante carga inicial)
    if (renderTimeout) clearTimeout(renderTimeout);
    renderTimeout = setTimeout(() => {
        renderAnomaliesGrid();
    }, 50);  // 50ms debounce
}

function renderAnomaliesGrid() {
    // Cache DOM selectors (solo una vez)
    if (!callsColumn) callsColumn = document.querySelector('.calls-column');
    if (!putsColumn) putsColumn = document.querySelector('.puts-column');
    
    if (!callsColumn || !putsColumn) return;
    
    // Clonar y ordenar (no mutar arrays originales)
    const sortedCalls = callsAnomalies.slice().sort((a, b) => 
        new Date(b.timestamp) - new Date(a.timestamp)
    );
    const sortedPuts = putsAnomalies.slice().sort((a, b) => 
        new Date(b.timestamp) - new Date(a.timestamp)
    );
    
    // Limitar a 5 más recientes
    const topCalls = sortedCalls.slice(0, 5);
    const topPuts = sortedPuts.slice(0, 5);
    
    // DocumentFragment (batch DOM operations)
    const callsFragment = document.createDocumentFragment();
    const putsFragment = document.createDocumentFragment();
    
    // Renderizar CALLS
    topCalls.forEach(anomaly => {
        const card = createAlertCard(anomaly, false);
        callsFragment.appendChild(card);
    });
    
    // Renderizar PUTS
    topPuts.forEach(anomaly => {
        const card = createAlertCard(anomaly, true);
        putsFragment.appendChild(card);
    });
    
    // Single DOM update (evita reflow múltiple)
    callsColumn.innerHTML = '';
    putsColumn.innerHTML = '';
    callsColumn.appendChild(callsFragment);
    putsColumn.appendChild(putsFragment);
}

function createAlertCard(anomaly, isPut) {
    const card = document.createElement('div');
    card.className = 'alert-card';
    
    const emoji = isPut ? '🔴' : '🟢';
    const type = isPut ? 'PUT' : 'CALL';
    
    // Sanitización básica (previene XSS)
    const strike = safeToFixed(parseFloat(anomaly.strike) || 0, 0);
    const price = safeToFixed(parseFloat(anomaly.mid_price) || 0, 2);
    const deviation = Math.abs(parseFloat(anomaly.deviation_percent) || 0).toFixed(1);
    
    // Determinar severity class
    const severityMap = {
        'HIGH': 'severity-high',
        'MEDIUM': 'severity-med',
        'LOW': 'severity-low'
    };
    const severityClass = severityMap[anomaly.severity] || 'severity-med';
    const severityLabel = anomaly.severity || 'MED';
    
    // Formatear timestamp
    const timestamp = new Date(anomaly.timestamp + (anomaly.timestamp.includes("Z") || anomaly.timestamp.includes("+") ? "" : "Z"));
    const time = !isNaN(timestamp) ? timestamp.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }) : '--:--:--';
    
    // Usar textContent (más seguro que innerHTML)
    const line1 = document.createElement('div');
    line1.className = 'alert-line-1';
    line1.textContent = `${emoji} ${type} $${strike} → $${price}`;
    
    const line2 = document.createElement('div');
    line2.className = 'alert-line-2';
    line2.innerHTML = `Deviation: ${deviation}% <span class="${severityClass}">[${severityLabel}]</span>`;
    
    const line3 = document.createElement('div');
    line3.className = 'alert-line-3';
    line3.textContent = time;
    
    card.appendChild(line1);
    card.appendChild(line2);
    card.appendChild(line3);
    
    return card;
}

// ========================================
// UPDATE ATM RANGE (NUEVO - FIX BUG)
// ========================================
function updateATMRange(atmRange) {
    const rangeMax = document.getElementById('range-max');
    const rangeMin = document.getElementById('range-min');
    
    if (atmRange?.max && atmRange?.min) {
        if (rangeMax) rangeMax.textContent = `${atmRange.max}`;
        if (rangeMin) rangeMin.textContent = `${atmRange.min}`;
    }
}

// Update SPY price
function updateSpyPrice(price, atmRange = null) {
    window.currentSpyPrice = price; // ✅ NUEVO: Cachear precio
    
    const priceEl = document.querySelector('.spy-price');
    if (priceEl) {
        priceEl.textContent = `$${safeToFixed(price, 2)}`;
    }

    // Update ATM range (Backend SIEMPRE envía atm_range en Fase 1)
    if (atmRange && atmRange.max_strike && atmRange.min_strike) {
        // ✅ Cachear ATM range
        window.atmRange = { min: atmRange.min_strike, max: atmRange.max_strike };
        updateATMRange(window.atmRange);
    } else {
        // Placeholder si backend no envía datos
        const rangeMax = document.getElementById('range-max');
        const rangeMin = document.getElementById('range-min');
        if (rangeMax) rangeMax.textContent = '--';
        if (rangeMin) rangeMin.textContent = '--';
    }
}

function updateSpyChangePct(pct) {
    window.lastSpyChangePct = pct; // ✅ NUEVO: Cachear % para persistencia
    
    const el = document.getElementById('price-change');
    if (!el || pct === null || pct === undefined) return;
    const sign = pct >= 0 ? '+' : '';
    el.textContent = `${sign}${safeToFixed(pct, 2)}%`;
    el.className = `price-change ${pct >= 0 ? 'positive' : 'negative'}`;
}

// ================================
// EXISTING CODE CONTINUES BELOW
// ================================
        // Internationalization
        const i18n = {
            en: {
                spyCurrentPrice: "SPY Current Price",
                statusLive: "● Market Data Connected",
                monitoredRange: "Monitored Range",
                maxStrike: "Max Strike",
                minStrike: "Min Strike",
                updateFreq: "Update: Every 2sec",
                chartTitle: "📊 Real-Time Signed Premium Flow",
                volumeCalls: "CALLs Volume",
                volumePuts: "PUTs Volume",
                spyPrice: "SPY Price",
                alertsTitle: "🚨 Detected Anomaly Alerts",
                alert1: "83% price drop vs previous strike ($2.65 → $0.45)",
                alert1Detail: "Wide bid-ask spread detected | Abnormal Bid/Ask ratio (32%/68%)",
                alert2: "Strong buying pressure on CALLs (56% bid) vs selling pressure on PUTs (56% ask)",
                alert2Detail: "Possible institutional bullish sentiment",
                alert3: "Unusually high ask volume (62%) indicating aggressive put selling",
                alert3Detail: "Possible protection sale or covered puts strategy",
                confrontedView: "📊 CONFRONTED VIEW - 7 Strikes Around ATM",
                price: "Price",
                totalVol: "Total Vol",
                bidVol: "Bid Vol",
                askVol: "Ask Vol",
                flowVisual: "Flow Visual"
            },
            es: {
                spyCurrentPrice: "Precio Actual SPY",
                statusLive: "● Datos de Mercado Conectados",
                monitoredRange: "Rango Monitoreado",
                maxStrike: "Strike Máximo",
                minStrike: "Strike Mínimo",
                updateFreq: "Actualización: Cada 2seg",
                chartTitle: "📊 Flujo de Primas en Tiempo Real",
                volumeCalls: "Volumen CALLs",
                volumePuts: "Volumen PUTs",
                sspyPrice: "Precio SPY",
                alertsTitle: "🚨 Alertas de Anomalías Detectadas",
                alert1: "Caída de precio del 83% respecto a strike anterior ($2.65 → $0.45)",
                alert1Detail: "Spread bid-ask amplio detectado | Bid/Ask ratio anormal (32%/68%)",
                alert2: "Presión compradora fuerte en CALLs (56% bid) vs presión vendedora en PUTs (56% ask)",
                alert2Detail: "Posible sentimiento alcista institucional",
                alert3: "Volumen ask inusualmente alto (62%) indicando venta agresiva de puts",
                alert3Detail: "Posible venta de protección o estrategia de covered puts",
                confrontedView: "📊 VISTA CONFRONTADA - 7 Strikes Alrededor del ATM",
                price: "Precio",
                totalVol: "Vol Total",
                bidVol: "Bid Vol",
                askVol: "Ask Vol",
                flowVisual: "Flow Visual"
            }
        };

        let currentLang = 'en';

        window.switchLanguage = function(lang) {
            currentLang = lang;
            document.getElementById('btn-en').classList.toggle('active', lang === 'en');
            document.getElementById('btn-es').classList.toggle('active', lang === 'es');
            
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (i18n[lang][key]) {
                    el.textContent = i18n[lang][key];
                }
            });
            
            document.documentElement.lang = lang;
            localStorage.setItem('preferredLanguage', lang);
        }

        

        // Chart drawing code 
                       

        function formatTime(time) {
            // Si ya es string, retornar tal cual
            if (typeof time === 'string') return time;
    
            // Si es Date, formatear
            if (time instanceof Date) {
                return time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
            }
    
            return '--:--';
        }

        function drawChart() {
            const canvas = document.getElementById('volumeChart');
            if (!canvas) return;
            
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.offsetWidth;
            canvas.height = canvas.offsetHeight;

            const width = canvas.width;
            const height = canvas.height;
            const padding = 60;
            const paddingRight = 80;
            const chartHeight = height - 2 * padding;
            const chartWidth = width - padding - paddingRight;

            ctx.clearRect(0, 0, width, height);

            // Guard: empty arrays crash Math.max/min
            if (callVolumeHistory.length === 0 || spyPriceHistory.length === 0) return;
            console.log('✅ drawChart() ejecutándose con:', {
                calls: callVolumeHistory.length,
                puts: putVolumeHistory.length,
                spy: spyPriceHistory.length,
                tiempo: new Date().toLocaleTimeString()
            });

            const recentWindow = Math.min(14400, callVolumeHistory.length);
            const recentCalls = callVolumeHistory.slice(-recentWindow);
            const recentPuts = putVolumeHistory.slice(-recentWindow);

            const maxCallVolume = Math.max(...recentCalls, 10) * 1.10;
            const minPutVolume = Math.min(...recentPuts, -10) * 1.10;
            const volumeRange = maxCallVolume - minPutVolume;
            const volumeScale = chartHeight / volumeRange;
            const zeroY = padding + (maxCallVolume * volumeScale);

            const maxSpyPrice = Math.max(...spyPriceHistory);
            const minSpyPrice = Math.min(...spyPriceHistory);
            const spyRange = maxSpyPrice - minSpyPrice;
            const spyScale = chartHeight / spyRange;

            // Grid
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
            ctx.lineWidth = 1;
            
            for (let i = 0; i <= 5; i++) {
                const y = padding + (chartHeight / 5) * i;
                ctx.beginPath();
                ctx.moveTo(padding, y);
                ctx.lineTo(width - paddingRight, y);
                ctx.stroke();
                
                const volumeValue = maxCallVolume - (volumeRange / 5) * i;
                const volumeLabel = safeToFixed(volumeValue, 0);
                ctx.fillStyle = '#888';
                ctx.font = '10px Arial';
                ctx.textAlign = 'right';
                ctx.fillText(volumeLabel, padding - 10, y + 4);
            }
            
            // SPY price labels (right)
            for (let i = 0; i <= 5; i++) {
                const y = padding + (chartHeight / 5) * i;
                const priceValue = maxSpyPrice - (spyRange / 5) * i;
                ctx.fillStyle = '#ffd700';
                ctx.font = 'bold 12px Arial';
                ctx.textAlign = 'left';
                ctx.fillText('$' + safeToFixed(priceValue, 0), width - paddingRight + 10, y + 4);
            }
            
            // Zero line
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(padding, zeroY);
            ctx.lineTo(width - paddingRight, zeroY);
            ctx.stroke();
            ctx.setLineDash([]);
            
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 10px Arial';
            ctx.textAlign = 'right';
            ctx.fillText('0', padding - 10, zeroY + 4);
            
            // Axes
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(padding, height - padding);
            ctx.lineTo(width - paddingRight, height - padding);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(padding, padding);
            ctx.lineTo(padding, height - padding);
            ctx.stroke();
            
            // Time labels
            const recentTimeLabels = timeLabels.slice(-recentWindow);
            const timeStep = Math.floor(recentTimeLabels.length / 8);
            for (let i = 0; i < recentTimeLabels.length; i += timeStep) {
                const x = padding + (chartWidth / (recentTimeLabels.length - 1)) * i;
                ctx.fillStyle = '#888';
                ctx.font = '10px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(formatTime(recentTimeLabels[i]), x, height - padding + 15);
            }
            
            function drawSmoothLine(data, color, lineWidth = 2.5, isPrice = false) {
                if (!data || data.length === 0) return;

                ctx.strokeStyle = color;
                ctx.lineWidth = lineWidth;
                ctx.lineJoin = 'round';
                ctx.lineCap = 'round';

                // OPTIMIZACIÓN: Eliminar sombras (shadowBlur) reduce el uso de CPU en un 70%
                ctx.shadowBlur = 0;

                ctx.beginPath();

                const points = data.map((value, i) => ({
                    x: padding + (chartWidth / (data.length - 1)) * i,
                    y: isPrice
                        ? padding + (maxSpyPrice - value) * spyScale
                        : padding + (maxCallVolume - value) * volumeScale
                }));

                // OPTIMIZACIÓN: Si hay más de 500 puntos, las curvas de Bezier son imperceptibles 
                // pero carísimas de calcular. Usamos lineTo para rendimiento masivo.
                if (points.length > 500) {
                    points.forEach((p, i) => {
                        if (i === 0) ctx.moveTo(p.x, p.y);
                        else ctx.lineTo(p.x, p.y);
                    });
                } else {
                    // Solo usamos Bezier para pocos puntos (suavizado estético inicial)
                    points.forEach((p, i) => {
                        if (i === 0) ctx.moveTo(p.x, p.y);
                        else {
                            const prev = points[i - 1];
                            const cpX = (prev.x + p.x) / 2;
                            ctx.bezierCurveTo(cpX, prev.y, cpX, p.y, p.x, p.y);
                        }
                    });
                }

                ctx.stroke();
            }
            
            drawSmoothLine(putVolumeHistory, '#ff0064', 2.5);
            drawSmoothLine(callVolumeHistory, '#00ff88', 2.5);
            drawSmoothLine(spyPriceHistory, '#ffd700', 3, false);
            
            // Title
            ctx.fillStyle = '#00d4ff';
            
            // Axis labels
            ctx.fillStyle = '#888';
            ctx.font = '11px Arial';
            ctx.fillText(currentLang === 'es' ? 'Hora' : 'Time', width / 2, height - 10);
            
            ctx.save();
            ctx.translate(15, height / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.textAlign = 'center';
            ctx.fillText('Net Premiums (Vol. Acumulado)', 0, 0);
            ctx.restore();
            
            ctx.save();
            ctx.translate(width - 15, height / 2);
        }

// Event listener para hover en chart
function setupChartHover() {
    const canvas = document.getElementById('volumeChart');
    if (!canvas || canvas.hasHoverListener) return;

    createTooltip();
    const tooltip = document.getElementById('flow-tooltip');

    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Calcular índice del punto más cercano
        const padding = 60;
        const paddingRight = 80;
        const chartWidth = canvas.width - padding - paddingRight;
        const recentWindow = Math.min(14400, callVolumeHistory.length);

        if (x < padding || x > canvas.width - paddingRight) {
            tooltip.style.display = 'none';
            return;
        }

        const relativeX = (x - padding) / chartWidth;
        const index = Math.round(relativeX * (recentWindow - 1));
        const actualIndex = callVolumeHistory.length - recentWindow + index;

        if (actualIndex < 0 || actualIndex >= callVolumeHistory.length) {
            tooltip.style.display = 'none';
            return;
        }

        // Obtener datos del punto
        const time = timeLabels[actualIndex];
        const callFlow = callVolumeHistory[actualIndex];
        const putFlow = putVolumeHistory[actualIndex];
        const spyPrice = spyPriceHistory[actualIndex];
        const netFlow = callFlow - putFlow;

        // Formatear hora
        const timeStr = time.toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        // Mostrar tooltip con valores DINÁMICOS del punto
        tooltip.innerHTML = `
            <div style="font-weight: bold; margin-bottom: 8px; color: #cccccc; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 4px;">
                🕐 ${timeStr}
            </div>
            
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="position: relative; width: 16px; height: 16px; margin-right: 8px;">
                    <div style="position: absolute; width: 16px; height: 16px; background: #ffd700; border-radius: 50%;"></div>
                    <div style="position: absolute; width: 8px; height: 8px; background: white; border-radius: 50%; top: 4px; left: 4px;"></div>
                </div>
                <span style="color: #cccccc;">SPY: $${spyPrice.toFixed(2)}</span>
            </div>
            
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="position: relative; width: 16px; height: 16px; margin-right: 8px;">
                    <div style="position: absolute; width: 16px; height: 16px; background: #00ff88; border-radius: 50%;"></div>
                    <div style="position: absolute; width: 8px; height: 8px; background: white; border-radius: 50%; top: 4px; left: 4px;"></div>
                </div>
                <span style="color: #cccccc;">CALLs: $${(callFlow / 1e6).toFixed(1)}M</span>
            </div>
            
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="position: relative; width: 16px; height: 16px; margin-right: 8px;">
                    <div style="position: absolute; width: 16px; height: 16px; background: #ff4444; border-radius: 50%;"></div>
                    <div style="position: absolute; width: 8px; height: 8px; background: white; border-radius: 50%; top: 4px; left: 4px;"></div>
                </div>
                <span style="color: #cccccc;">PUTs: $${(putFlow / 1e6).toFixed(1)}M</span>
            </div>
            
            <div style="display: flex; align-items: center; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 6px; margin-top: 2px;">
                <div style="position: relative; width: 16px; height: 16px; margin-right: 8px;">
                    <div style="position: absolute; width: 16px; height: 16px; background: ${netFlow >= 0 ? '#00ff88' : '#ff4444'}; border-radius: 50%;"></div>
                    <div style="position: absolute; width: 8px; height: 8px; background: white; border-radius: 50%; top: 4px; left: 4px;"></div>
                </div>
                <span style="color: ${netFlow >= 0 ? '#00ff88' : '#ff4444'}; font-weight: bold;">
                    Net: $${(netFlow / 1e6).toFixed(1)}M
                </span>
            </div>
        `;

        tooltip.style.left = (e.clientX + 15) + 'px';
        tooltip.style.top = (e.clientY - 80) + 'px';
        tooltip.style.display = 'block';
    });

    canvas.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });

    canvas.hasHoverListener = true;
}

        function updateData() {
            const newTime = new Date();
            timeLabels.shift();
            timeLabels.push(newTime);
            
            const lastCall = callVolumeHistory[callVolumeHistory.length - 1];
            const lastPut = putVolumeHistory[putVolumeHistory.length - 1];
            const lastSpy = spyPriceHistory[spyPriceHistory.length - 1];
            
            callVolumeHistory.shift();
            callVolumeHistory.push(lastCall + 150000 + Math.random() * 200000);
            
            putVolumeHistory.shift();
            putVolumeHistory.push(lastPut - 100000 - Math.random() * 150000);
            
            spyPriceHistory.shift();
            spyPriceHistory.push(lastSpy + (Math.random() - 0.5) * 0.3);
            
            drawChart();
        }

        window.addEventListener('resize', drawChart);


// ================================
// PHASE 9: Initial State Loader
// ================================
async function loadInitialState() {
    try {
        const backendUrl = CONFIG.backend?.baseUrl;
        console.log(`📊 Loading initial state from ${backendUrl}/dashboard/snapshot`);

        const response = await fetch(`${backendUrl}/dashboard/snapshot`);

        if (!response.ok) {
            console.warn('⚠️ Could not load initial state:', response.status);
            return;
        }

        const data = await response.json();
        console.log(`✅ Initial state loaded: ${data.anomalies.length} anomalies`);

        if (data.anomalies && data.anomalies.length > 0) {
            const sortedAnomalies = data.anomalies.sort((a, b) =>
                new Date(b.timestamp) - new Date(a.timestamp)
            );
        }

        // Renderizar anomalías iniciales
        data.anomalies.slice(0,50).forEach(anomaly => handleAnomalyAlert(anomaly));

        // ✅ FIX: Actualizar estado de mercado
        updateMarketStatus();

    } catch (error) {
        console.warn('⚠️ Initial state error:', error.message);
    }
}

// =====================================
// Market Status Checker (NYSE Hours)
// =====================================
function updateMarketStatus() {
    const now = new Date();
    const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const hour = nyTime.getHours();
    const minute = nyTime.getMinutes();
    const day = nyTime.getDay();

    // Weekend: 0=Sunday, 6=Saturday
    const isWeekend = (day === 0 || day === 6);

    // Market hours: 9:30 AM - 4:00 PM ET
    const isPreMarket = (hour === 9 && minute >= 30) || (hour >= 10 && hour < 16);
    const isMarketHours = !isWeekend && isPreMarket;

    if (isMarketHours) {
        updateConnectionStatus(true, '● Market Data Connected');
    } else {
        updateConnectionStatus(false, '● Market Closed');
    }
}


// =====================================
// PHASE 10: Volume Snapshot Loader
// =====================================
async function loadInitialVolumes() {
    try {
        const backendUrl = CONFIG.backend?.baseUrl;
        const url = `${backendUrl}/flow/snapshot?hours=96`;
        console.log('📊 Loading flow history from', url);

        const response = await fetch(url);

        if (!response.ok) {
            console.warn('⚠️ Could not load flow history', response.status);
            return;
        }

        const data = await response.json();
        console.log('✅ Flow history loaded', data.count, 'snapshots');

        if (data.history && data.history.length > 0) {
            data.history.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

            // Formatear timestamps
            timeLabels = data.history.map(v => {
                return new Date(v.timestamp + (v.timestamp.includes("Z") || v.timestamp.includes("+") ? "" : "Z"));
            });

            // Usar flow acumulado directamente (en millones)
            callVolumeHistory = data.history.map(v => (v.cum_call_flow || 0) / 1e6);
            putVolumeHistory = data.history.map(v => (v.cum_put_flow || 0) / 1e6);
            spyPriceHistory = data.history.map(v => v.spy_price || 0);

            const lastSnapshot = data.history[data.history.length - 1];
            //updateSpyPrice(lastSnapshot.spy_price);

            console.log('📊 Datos cargados en loadInitialVolumes:', {
                total: data.history.length,
                calls: callVolumeHistory.length,
                puts: putVolumeHistory.length,
                spy: spyPriceHistory.length,
                primerTimestamp: timeLabels[0],
                ultimoTimestamp: timeLabels[timeLabels.length - 1]
            });

            // ✅ AÑADIR DESPUÉS DE LÍNEA 1369:

            // Calcular y persistir market state desde histórico
            
            const firstSnapshot = data.history[0];

            // Previous close (primera spy_price del histórico)
            const previousClose = firstSnapshot.spy_price;
            window.lastPreviousClose = previousClose;

            // Calcular % change
            const spyChangePct = ((lastSnapshot.spy_price - previousClose) / previousClose) * 100;

            // Calcular ATM range
            const atmCenter = Math.round(lastSnapshot.spy_price);
            const atmRange = { min: atmCenter - 5, max: atmCenter + 5 };

            // Cachear en window
            window.lastSpyChangePct = spyChangePct;
            window.atmRange = atmRange;
            window.currentSpyPrice = lastSnapshot.spy_price;

            // Actualizar UI
            updateSpyChangePct(spyChangePct);
            updateATMRange(atmRange);

            // Actualizar precio en DOM
            const priceEl = document.querySelector('.spy-price');
            if (priceEl) {
                priceEl.textContent = `$${safeToFixed(lastSnapshot.spy_price, 2)}`;
            }

            // Persistir
            persistMarketState();

            console.log('✅ Market state from history:', { spyChangePct, atmRange, previousClose });


            if (flowChartInstance) {
                // Sincronizamos los datos nuevos con el gráfico
                flowChartInstance.data.labels = timeLabels;
                flowChartInstance.data.datasets[0].data = callVolumeHistory;
                flowChartInstance.data.datasets[1].data = putVolumeHistory;
                flowChartInstance.data.datasets[2].data = spyPriceHistory;

                if (callVolumeHistory.length > 0 && putVolumeHistory.length > 0) {
                    const lastCalls = callVolumeHistory[callVolumeHistory.length - 1];
                    const lastPuts = putVolumeHistory[putVolumeHistory.length - 1];
                    updateMetricCards(lastCalls, lastPuts);
                }    
                // Refrescamos visualmente
                flowChartInstance.update();
            }

        }

    } catch (error) {
        console.warn('⚠️ Flow history error:', error.message);
    }
}

// =====================================
// PHASE 10: Real-time Volume Handler
// =====================================
function handleVolumeUpdate(data) {
    // Formatear fecha como string
    const d = new Date(data.timestamp + (data.timestamp.includes("Z") || data.timestamp.includes("+") ? "" : "Z"));
    timeLabels.push(d);

    // Usar deltas con suavizado EMA
    const callDelta = data.calls_volume_delta || 0;
    const putDelta = data.puts_volume_delta || 0;

    smoothCalls = smoothCalls === 0
        ? callDelta
        : smoothCalls + SMOOTHING_FACTOR * (callDelta - smoothCalls);

    smoothPuts = smoothPuts === 0
        ? putDelta
        : smoothPuts + SMOOTHING_FACTOR * (putDelta - smoothPuts);

    callVolumeHistory.push(Math.round(smoothCalls));
    putVolumeHistory.push(-Math.round(smoothPuts)); // Negativo para mostrar abajo

    spyPriceHistory.push(data.spy_price);
    updateSpyPrice(data.spy_price, data.atm_range);
    updateSpyChangePct(data.spy_change_pct);

    if (callVolumeHistory.length > 480) {
        timeLabels.shift();
        callVolumeHistory.shift();
        putVolumeHistory.shift();
        spyPriceHistory.shift();
    }

    drawChart();
}

// ================================
// Initialize on Page Load
// ================================
    
    window.addEventListener('DOMContentLoaded', async () => {
        console.log('🚀 Dashboard initializing...');

        setupFlowChart();  // Crear chart PRIMERO

    // ✅ NUEVO: Cargar estado guardado ANTES de backend
        loadPersistedMarketState();

    // Ejecutamos con try/catch individuales para que uno no rompa al otro
    // 1. Cargamos Historial de Volúmenes (Ahora configurado a 72h en Backend)
        try {
            console.log('[Init] Cargando volúmenes históricos...');
            await loadInitialVolumes();
        } catch (e) {
            console.error("Fallo carga volumenes:", e);
        }
    // 2. Cargamos Últimas Anomalías (Ahora configurado a 50 registros)
        try {
            console.log('[Init] Recuperando últimas 50 anomalías de Azure...');
            await loadInitialState();
        } catch (e) {
            console.error("❌ Fallo carga anomalías históricas:", e);
        }
    // 3. Conexión en vivo (Si el mercado está cerrado, se mantendrá en espera silenciosa)
        console.log('[Init] Estableciendo conexión en tiempo real...');
        await initSignalR();

    // 4. Verificar estado de mercado cada 60 segundos
        setInterval(updateMarketStatus, 60000);

    // 5. Preferencias de usuario
        const saved = localStorage.getItem('preferredLanguage') || 'en';
        if (typeof switchLanguage === 'function') switchLanguage(saved);

        drawChart();
    });

// =====================================
// MARKET CLOCKS & COUNTDOWN
// =====================================
function updateMarketClocks() {
    const now = new Date();

    // NYSE Time (ET)
    const nyseTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const nyseTimeStr = nyseTime.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    document.getElementById('nyse-time').textContent = nyseTimeStr;

    // CET Time
    const cetTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
    const cetTimeStr = cetTime.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    document.getElementById('cet-time').textContent = cetTimeStr;

    // Market Status & Countdown
    const hour = nyseTime.getHours();
    const minute = nyseTime.getMinutes();
    const day = nyseTime.getDay();
    const isWeekend = (day === 0 || day === 6);

    const countdownCard = document.querySelector('.countdown-card');
    const countdownLabel = document.getElementById('countdown-label');
    const countdownTime = document.getElementById('countdown-time');

    // Remove all state classes
    countdownCard.classList.remove('market-open', 'market-closed', 'market-premarket');

    if (isWeekend) {
        // Weekend
        const daysUntilMonday = day === 0 ? 1 : 2;
        const mondayOpen = new Date(nyseTime);
        mondayOpen.setDate(mondayOpen.getDate() + daysUntilMonday);
        mondayOpen.setHours(9, 30, 0, 0);

        const diff = mondayOpen - nyseTime;
        const hours = Math.floor(diff / 3600000);
        const minutes = Math.floor((diff % 3600000) / 60000);

        countdownLabel.textContent = '⏱ TILL MONDAY OPEN';
        countdownTime.textContent = `${hours}h ${minutes}m`;
        countdownCard.classList.add('market-closed');

    } else if (hour >= 9 && (hour < 16 || (hour === 16 && minute === 0))) {
        // Market hours: 9:30 AM - 4:00 PM ET
        if (hour === 9 && minute < 30) {
            // Pre-market (9:00-9:30)
            const openTime = new Date(nyseTime);
            openTime.setHours(9, 30, 0, 0);
            const diff = openTime - nyseTime;
            const mins = Math.floor(diff / 60000);

            countdownLabel.textContent = '⏱ TILL OPEN';
            countdownTime.textContent = `${mins}m`;
            countdownCard.classList.add('market-premarket');
        } else {
            // Market open
            const closeTime = new Date(nyseTime);
            closeTime.setHours(16, 0, 0, 0);
            const diff = closeTime - nyseTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);

            countdownLabel.textContent = '⏱ TILL CLOSE';
            countdownTime.textContent = `${hours}h ${minutes}m`;
            countdownCard.classList.add('market-open');
        }

    } else {
        // After hours or before 9:00 AM
        const nextOpen = new Date(nyseTime);

        if (hour >= 16 && hour < 20) {
            // After-hours trading (16:00-20:00 ET) - naranja
            nextOpen.setDate(nextOpen.getDate() + 1);
            nextOpen.setHours(9, 30, 0, 0);

            const diff = nextOpen - nyseTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);

            const label = currentLang === 'es' ? '⏱ HASTA APERTURA' : '⏱ UNTIL OPEN';
            countdownLabel.textContent = label;
            countdownTime.textContent = `${hours}h ${minutes}m`;
            countdownCard.classList.add('market-premarket'); // Naranja

        } else if (hour >= 20 || hour < 7) {
            // Mercado totalmente cerrado (20:00-7:00 ET) - rojo
            if (hour >= 20) {
                nextOpen.setDate(nextOpen.getDate() + 1);
            }
            nextOpen.setHours(9, 30, 0, 0);

            const diff = nextOpen - nyseTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);

            const label = currentLang === 'es' ? '⏱ HASTA APERTURA' : '⏱ UNTIL OPEN';
            countdownLabel.textContent = label;
            countdownTime.textContent = `${hours}h ${minutes}m`;
            countdownCard.classList.add('market-closed'); // Rojo

        } else if (hour >= 7 && hour < 9) {
            // Pre-market (7:00-9:00 ET) - naranja
            nextOpen.setHours(9, 30, 0, 0);

            const diff = nextOpen - nyseTime;
            const hours = Math.floor(diff / 3600000);
            const minutes = Math.floor((diff % 3600000) / 60000);

            const label = currentLang === 'es' ? '⏱ HASTA APERTURA' : '⏱ UNTIL OPEN';
            countdownLabel.textContent = label;
            countdownTime.textContent = `${hours}h ${minutes}m`;
            countdownCard.classList.add('market-premarket'); // Naranja
        }
    }
}

// Initialize clocks
updateMarketClocks();
setInterval(updateMarketClocks, 1000); // Update every second   

function updateMetricCards(calls, puts) {
    const callEl = document.getElementById('call-metric-value');
    const putEl = document.getElementById('put-metric-value');
    const netEl = document.getElementById('net-metric-value');
    if (callEl && putEl && netEl) {
        const c = calls || 0;
        const p = puts || 0;
        const net = c - p;
        callEl.innerText = '$' + c.toFixed(2) + 'M';
        putEl.innerText = '$' + p.toFixed(2) + 'M';
        netEl.innerText = '$' + net.toFixed(2) + 'M';
        netEl.style.color = net >= 0 ? '#00ff88' : '#ff4444';
    }
}
function animationLoop() {
    if (window.needsChartUpdate && flowChartInstance) {
        flowChartInstance.update('none');
        window.needsChartUpdate = false;
    }
    requestAnimationFrame(animationLoop);
}
animationLoop();
