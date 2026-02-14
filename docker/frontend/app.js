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

//function safeToFixed(value, decimals = 2) {
//    return Number.isFinite(value)
//        ? value.toFixed(decimals)
//        : (0).toFixed(decimals);
//}


// ================================
// PHASE 8: SignalR Configuration (updated)
// ================================

let timeLabels = [];
let callVolumeHistory = [];
let putVolumeHistory = [];
let spyPriceHistory = [];
let smoothCalls = 0;
let smoothPuts = 0;

const SMOOTHING_FACTOR = 0.2;

let signalRConnection = null;
let isConnected = false;


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
        signalRConnection.on('spyPriceUpdate', (data) => updateSpyPrice(data.price));
        signalRConnection.on('volumeUpdate', (data) => {
            console.log('📊 Volume update:', data);
            handleVolumeUpdate(data);
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
            updateConnectionStatus(true, '● Market Data Connected');
        }

    } catch (error) {
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
        // startMockData(); // Descomentar si tienes esta función definida
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

// Handle incoming anomaly alert
function handleAnomalyAlert(anomaly) {
    const alertsContainer = document.querySelector('.alerts-list');
    if (!alertsContainer) return;
    
    // Color y emoji según tipo
    const isPut = anomaly.type === 'PUT' || anomaly.type === 'P';
    const emoji = isPut ? '🔴' : '🟢';
    const colorClass = isPut ? 'put-anomaly' : 'call-anomaly';
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert-item ${colorClass}`;
    alertDiv.innerHTML = `
        <div class="alert-header">
            <span class="alert-time">${new Date(anomaly.timestamp).toLocaleTimeString()}</span>
            <span class="alert-badge">HIGH</span>
        </div>
        <div class="alert-content">
            <strong>${emoji} ${anomaly.type} $${anomaly.strike}</strong>
            <p>Deviation: <span class="deviation">${Math.abs(anomaly.deviation).toFixed(1)}%</span> | Price: $${anomaly.price.toFixed(2)}</p>
        </div>
    `;
    alertsContainer.insertBefore(alertDiv, alertsContainer.firstChild);
    
    // Limit to 10 alerts
    while (alertsContainer.children.length > 10) {
        alertsContainer.removeChild(alertsContainer.lastChild);
    }
}

// Update SPY price
function updateSpyPrice(price) {
    const priceEl = document.querySelector('.spy-price');
    if (priceEl) {
        priceEl.textContent = `$${safeToFixed(price, 2)}`;
    }
    // Update range info (±1% from current price)
    const rangeMax = document.getElementById('range-max');
    const rangeMin = document.getElementById('range-min');
    if (rangeMax) rangeMax.textContent = `$${safeToFixed(price * 1.01, 2)}`;
    if (rangeMin) rangeMin.textContent = `$${safeToFixed(price * 0.99, 2)}`;
    // Update chart legend
    const legendEl = document.querySelector('[data-i18n="spyPrice"]');
    if (legendEl) {
        const prefix = currentLang === 'es' ? 'Precio SPY' : 'SPY Price';
        legendEl.textContent = `${prefix} ($${safeToFixed(price, 2)})`;
    }
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
                chartTitle: "📊 Real-Time Cumulative Volume (Last 2 Hours)",
                volumeCalls: "CALLs Volume",
                volumePuts: "PUTs Volume",
                spyPrice: "SPY Price ($---.--)",
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
                chartTitle: "📊 Volumen Acumulado en Tiempo Real (Últimas 2 Horas)",
                volumeCalls: "Volumen CALLs",
                volumePuts: "Volumen PUTs",
                sspyPrice: "Precio SPY ($---.--)",
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

        

        // Chart drawing code (ORIGINAL from spy-options-monitor_1.html)
        
        const now = new Date();
        for (let i = 120; i >= 0; i--) {
            timeLabels.push(new Date(now - i * 60000));
        }


        

        function formatTime(date) {
            return date.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit', hour12: false});
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

            const maxCallVolume = Math.max(...callVolumeHistory);
            const minPutVolume = Math.min(...putVolumeHistory);
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
                const volumeLabel = safeToFixed(volumeValue / 1000000, 0) + 'M';
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
                ctx.font = '10px Arial';
                ctx.textAlign = 'left';
                ctx.fillText('$' + safeToFixed(priceValue, 2), width - paddingRight + 10, y + 4);
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
            const timeStep = Math.floor(timeLabels.length / 8);
            for (let i = 0; i < timeLabels.length; i += timeStep) {
                const x = padding + (chartWidth / (timeLabels.length - 1)) * i;
                ctx.fillStyle = '#888';
                ctx.font = '10px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(formatTime(timeLabels[i]), x, height - padding + 15);
            }
            
            function drawSmoothLine(data, color, lineWidth = 2.5, isPrice = false) {
                ctx.strokeStyle = color;
                ctx.lineWidth = lineWidth;
                ctx.beginPath();
                
                data.forEach((value, i) => {
                    const x = padding + (chartWidth / (data.length - 1)) * i;
                    let y;
                    
                    if (isPrice) {
                        y = padding + (maxSpyPrice - value) * spyScale;
                    } else {
                        y = padding + (maxCallVolume - value) * volumeScale;
                    }
                    
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                });
                
                ctx.stroke();
                ctx.shadowBlur = 8;
                ctx.shadowColor = color;
                ctx.stroke();
                ctx.shadowBlur = 0;
            }
            
            drawSmoothLine(putVolumeHistory, '#ff0064', 2.5);
            drawSmoothLine(callVolumeHistory, '#00ff88', 2.5);
            drawSmoothLine(spyPriceHistory, '#ffd700', 3, true);
            
            // Title
            ctx.fillStyle = '#00d4ff';
            ctx.font = 'bold 14px Arial';
            ctx.textAlign = 'center';
            const titleText = currentLang === 'es' ? 
                'Volumen Acumulado en Tiempo Real (Últimas 2 Horas)' :
                'Real-Time Cumulative Volume (Last 2 Hours)';
            ctx.fillText(titleText, width / 2, padding - 30);
            
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
            ctx.rotate(Math.PI / 2);
            ctx.textAlign = 'center';
            ctx.fillStyle = '#ffd700';
            ctx.fillText('SPY Price', 0, 0);
            ctx.restore();
            
            // Current values box
            const latestCall = callVolumeHistory[callVolumeHistory.length - 1];
            const latestPut = putVolumeHistory[putVolumeHistory.length - 1];
            const latestSpy = spyPriceHistory[spyPriceHistory.length - 1];
            
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.fillRect(width - paddingRight - 180, padding + 10, 170, 80);
            
            ctx.font = 'bold 11px Arial';
            ctx.textAlign = 'left';
            
            ctx.fillStyle = '#00ff88';
            ctx.fillText('CALLs: ' + safeToFixed(latestCall / 1000000, 1) + 'M', width - paddingRight - 170, padding + 28);
            
            ctx.fillStyle = '#ff0064';
            ctx.fillText('PUTs: ' + safeToFixed(latestPut / 1000000, 1) + 'M', width - paddingRight - 170, padding + 48);
            
            ctx.fillStyle = '#ffd700';
            ctx.fillText('SPY: $' + safeToFixed(latestSpy, 2), width - paddingRight - 170, padding + 68);
            
            const netFlow = latestCall + latestPut;
            ctx.fillStyle = netFlow > 0 ? '#00ff88' : '#ff0064';
            ctx.fillText('Net: ' + safeToFixed(netFlow / 1000000, 1) + 'M', width - paddingRight - 170, padding + 83);
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

        // setInterval(updateData, 2000);  // DISABLED: mock data was overwriting real SignalR data
        window.addEventListener('resize', drawChart);
// ================================
// PHASE 9: Initial State Loader
// ================================
async function loadInitialState() {
    try {
        const backendUrl = CONFIG.backend?.baseUrl;
        console.log(`📊 Loading initial state from ${backendUrl}/api/dashboard/snapshot`);
        
        const response = await fetch(`${backendUrl}/api/dashboard/snapshot`);
        
        if (!response.ok) {
            console.warn('⚠️ Could not load initial state:', response.status);
            return;
        }
        
        const data = await response.json();
        console.log(`✅ Initial state loaded: ${data.anomalies.length} anomalies`);
        
        // Renderizar anomalías iniciales
        data.anomalies.forEach(anomaly => handleAnomalyAlert(anomaly));
        
    } catch (error) {
        console.warn('⚠️ Initial state error:', error.message);
    }
}
// =====================================
// PHASE 10: Volume Snapshot Loader
// =====================================
async function loadInitialVolumes() {
    try {
        const backendUrl = CONFIG.backend?.baseUrl;
        console.log('📊 Loading volume history from', `${backendUrl}/volumes/snapshot?hours=2`);
        
        const response = await fetch(`${backendUrl}/volumes/snapshot?hours=2`);
        
        if (!response.ok) {
            console.warn('⚠️ Could not load volume history', response.status);
            return;
        }
        
        const data = await response.json();
        console.log('✅ Volume history loaded', data.count, 'snapshots');
        
        // Update arrays
        timeLabels = data.history.map(v => new Date(v.timestamp));
        callVolumeHistory = data.history.map(v => v.calls_volume_atm);
        putVolumeHistory = data.history.map(v => -v.puts_volume_atm); // Negative for chart
        spyPriceHistory = data.history.map(v => v.spy_price);
        
        // Update price display with latest loaded value
        if (spyPriceHistory.length > 0) {
            updateSpyPrice(spyPriceHistory[spyPriceHistory.length - 1]);
        }
        
        drawChart();
        
    } catch (error) {
        console.warn('⚠️ Volume history error:', error.message);
    }
}
// =====================================
// PHASE 10: Real-time Volume Handler
// =====================================
function handleVolumeUpdate(data) {
    timeLabels.push(new Date(data.timestamp));

    smoothCalls = smoothCalls === 0
        ? data.calls_volume_atm
        : smoothCalls + SMOOTHING_FACTOR * (data.calls_volume_atm - smoothCalls);

    smoothPuts = smoothPuts === 0
        ? data.puts_volume_atm
        : smoothPuts + SMOOTHING_FACTOR * (data.puts_volume_atm - smoothPuts);

    callVolumeHistory.push(Math.round(smoothCalls));
    putVolumeHistory.push(-Math.round(smoothPuts));

    spyPriceHistory.push(data.spy_price);
    updateSpyPrice(data.spy_price);

    if (callVolumeHistory.length > 121) {
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
    
        // Ejecutamos con try/catch individuales para que uno no rompa al otro
        try {
            await loadInitialVolumes();
        } catch (e) {
            console.error("Fallo carga volumenes:", e);
        }

        try {
            await loadInitialState();
        } catch (e) {
            console.error("Fallo carga estado:", e);
        }
    
        // Ahora sí, esperamos a SignalR
        await initSignalR();

        const saved = localStorage.getItem('preferredLanguage') || 'en';
        if (typeof switchLanguage === 'function') switchLanguage(saved);
    
        drawChart();
    });
    