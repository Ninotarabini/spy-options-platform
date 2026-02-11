// ================================
// PHASE 8: SignalR Configuration
// ================================

// Configuration (loaded from config.js or environment)
const SIGNALR_ENDPOINT = CONFIG?.signalr?.endpoint || 'https://signalr-spy-options.service.signalr.net';
const SIGNALR_ACCESS_KEY = CONFIG?.signalr?.accessKey || null;

// Validate configuration
if (!SIGNALR_ACCESS_KEY) {
   // console.warn('⚠️ SignalR Access Key not configured. Connection will fail.');
   // console.warn('📝 Copy config.template.js to config.js and add your key');
}

// ================================
// PHASE 8: SignalR Configuration (updated)
// ================================

let signalRConnection = null;
let isConnected = false;

async function initSignalR() {
    try {
        // Step 1: Get SignalR connection info from backend
        const backendUrl = CONFIG.backend.baseUrl || 'http://localhost:8000';
        const negotiateUrl = CONFIG.signalr.negotiateUrl;

        console.log(`[SignalR] Fetching connection info from ${negotiateUrl}`);
        const response = await fetch(negotiateUrl);

        if (!response.ok) {
            throw new Error(`Negotiate failed: ${response.status}`);
        }

        const connectionInfo = await response.json();
        console.log('[SignalR] Connection info received:', connectionInfo.url);
        console.log('[SignalR] connectionInfo:', connectionInfo);  

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
            updateConnectionStatus(true, '● LIVE - SignalR Connected');
        }

    } catch (error) {
        console.error('[SignalR] Connection failed:', error);
        updateConnectionStatus(false, '● ERROR - SignalR Disconnected');
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
        statusEl.style.color = connected ? '#00ff88' : '#ff6b6b';
    }
}

// Handle incoming anomaly alert
function handleAnomalyAlert(anomaly) {
    const alertsContainer = document.querySelector('.alerts-list');
    if (!alertsContainer) return;

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert-item';
    alertDiv.innerHTML = `
        <div class="alert-header">
            <span class="alert-time">${new Date().toLocaleTimeString()}</span>
            <span class="alert-severity">${anomaly.severity || 'HIGH'}</span>
        </div>
        <div class="alert-content">
            <strong>${anomaly.strike || 'N/A'} ${anomaly.type || 'CALL'}</strong>
            <p>${anomaly.description || 'Anomaly detected'}</p>
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
        priceEl.textContent = `$${price.toFixed(2)}`;
    }
}

// ================================
// EXISTING CODE CONTINUES BELOW
// ================================
        // Internationalization
        const i18n = {
            en: {
                spyCurrentPrice: "SPY Current Price",
                statusLive: "● LIVE - IBKR Connected",
                monitoredRange: "Monitored Range",
                maxStrike: "Max Strike",
                minStrike: "Min Strike",
                updateFreq: "Update: Every 2sec",
                chartTitle: "📊 Real-Time Cumulative Volume (Last 2 Hours)",
                volumeCalls: "CALLs Volume",
                volumePuts: "PUTs Volume",
                spyPrice: "SPY Price ($684.23)",
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
                statusLive: "● EN VIVO - IBKR Conectado",
                monitoredRange: "Rango Monitoreado",
                maxStrike: "Strike Máximo",
                minStrike: "Strike Mínimo",
                updateFreq: "Actualización: Cada 2seg",
                chartTitle: "📊 Volumen Acumulado en Tiempo Real (Últimas 2 Horas)",
                volumeCalls: "Volumen CALLs",
                volumePuts: "Volumen PUTs",
                spyPrice: "Precio SPY ($684.23)",
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

        function switchLanguage(lang) {
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

        // Initialize language
        window.addEventListener('DOMContentLoaded', () => {
            initSignalR();
            const saved = localStorage.getItem('preferredLanguage') || 'en';
            if (saved !== 'en') switchLanguage(saved);
            drawChart();
        });

        // Chart drawing code (ORIGINAL from spy-options-monitor_1.html)
        const timeLabels = [];
        const now = new Date();
        for (let i = 120; i >= 0; i--) {
            timeLabels.push(new Date(now - i * 60000));
        }

        const callVolumeHistory = Array.from({length: 121}, (_, i) => 1500000 + i * 30000 + Math.random() * 200000);
        const putVolumeHistory = Array.from({length: 121}, (_, i) => -1200000 - i * 25000 - Math.random() * 150000);
        const spyPriceHistory = Array.from({length: 121}, () => 684 + (Math.random() - 0.5) * 2);

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
                const volumeLabel = (volumeValue / 1000000).toFixed(0) + 'M';
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
                ctx.fillText('$' + priceValue.toFixed(2), width - paddingRight + 10, y + 4);
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
            ctx.fillText('CALLs: ' + (latestCall / 1000000).toFixed(1) + 'M', width - paddingRight - 170, padding + 28);
            
            ctx.fillStyle = '#ff0064';
            ctx.fillText('PUTs: ' + (latestPut / 1000000).toFixed(1) + 'M', width - paddingRight - 170, padding + 48);
            
            ctx.fillStyle = '#ffd700';
            ctx.fillText('SPY: $' + latestSpy.toFixed(2), width - paddingRight - 170, padding + 68);
            
            const netFlow = latestCall + latestPut;
            ctx.fillStyle = netFlow > 0 ? '#00ff88' : '#ff0064';
            ctx.fillText('Net: ' + (netFlow / 1000000).toFixed(1) + 'M', width - paddingRight - 170, padding + 83);
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

        setInterval(updateData, 2000);
        window.addEventListener('resize', drawChart);
// ================================
// PHASE 9: Initial State Loader
// ================================
async function loadInitialState() {
    try {
        const backendUrl = CONFIG.backend?.baseUrl || 'http://localhost:8000';
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

// ================================
// Initialize on Page Load
// ================================
window.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Dashboard initializing...');
    loadInitialState();
    initSignalR();
    const saved = localStorage.getItem('preferredLanguage') || 'en';
    if (saved !== 'en') switchLanguage(saved);
    drawChart();
});