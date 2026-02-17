// ============================================
// app.js - VERSIÓN OPTIMIZADA (70% reducción)
// ============================================

// ==================== CONFIG ====================
const CONFIG = {
    API: window.CONFIG?.backend?.baseUrl || 'https://default-api.example.com',
    SIGNALR: window.CONFIG?.signalr?.negotiateUrl || 'https://default-signalr.example.com/negotiate',
    USE_BACKEND_STATUS: true,
    TESTING_MODE: window.CONFIG?.TESTING_MODE || false,  // Control de conexión SignalR fuera de horario
    
    // ⚠️ FEATURE FLAGS
    ENABLE_FLOW_FEATURE: true,  // ← Desactiva todo el sistema de Flow
    MAX_ANOMALIES: 100,
    UPDATE_INTERVAL: 2000,
    PERSIST_INTERVAL: 30000,
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY_MS: 2000,
    CACHE_MAX_AGE_MS: 6 * 60 * 60 * 1000 // 6 horas
};

let chartUpdateTimeout = null;

// ==================== ENDPOINTS (NUEVO) ====================
const ENDPOINTS = {
    FLOW_SNAP: `${CONFIG.API}/flow/Flow_snap_last_4h`,
    ANOMALIES_SNAP: `${CONFIG.API}/anomalies/anom_snap`,
    SPY_MARKET_LATEST: `${CONFIG.API}/spymarket/spy_latest`
};

// ==================== ESTADO GLOBAL ====================
const State = {
    history: { time: [], calls: [], puts: [], spy: [] },
    current: { spy: null, change: null, prevClose: null, atm: { min: null, max: null }, status: 'unknown' },
    anomalies: { calls: [], puts: [] },
    market: { isOpen: false, mode: 'snapshot' },
    frozen: { isFrozen: false, start: null, end: null, date: null },
    connection: { isConnected: false, retries: 0 }
};

// ==================== UTILIDADES ====================
const toCET = (d = new Date()) => new Date(d.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
const toET = (d = new Date()) => new Date(d.toLocaleString('en-US', { timeZone: 'America/New_York' }));
const toUnix = d => Math.floor(d.getTime() / 1000);
const fromUnix = ts => new Date(ts * 1000);
const formatTime = ts => fromUnix(ts).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const formatPrice = v => Number.isFinite(v) ? v.toFixed(2) : '0.00';

// ==================== CALENDARIO Y MERCADO (NUEVO BLOQUE) ====================
const HOLIDAYS = ['01-01', '12-25'];

const isTradingDay = (date) => {
    const day = date.getDay();
    if (day === 0 || day === 6) return false;
    const mmdd = `${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
    return !HOLIDAYS.includes(mmdd);
};

const isMarketOpen = (date = toCET()) => {
    if (!isTradingDay(date)) return false;
    const h = date.getHours(), m = date.getMinutes();
    return (h > 15 || (h === 15 && m >= 15)) && (h < 22 || (h === 22 && m <= 15));
};

const getLastMarketClose = (fecha) => {
    let cursor = new Date(fecha);
    cursor.setHours(22, 15, 0, 0);
    if (fecha < cursor) cursor.setDate(cursor.getDate() - 1);
    while (!isTradingDay(cursor)) cursor.setDate(cursor.getDate() - 1);
    cursor.setHours(22, 15, 0, 0);
    return cursor;
};

const getGraphMode = () => {
    const ahora = toCET();
    if (!isTradingDay(ahora)) return 'snapshot';
    if (isMarketOpen(ahora)) return 'live';
    return 'snapshot';
};

// ==================== PERSISTENCIA ====================
const Storage = {
    save: (key, data) => {
        try {
            localStorage.setItem(key, JSON.stringify({
                ...data,
                ts: Date.now()
            }));
        } catch (e) { }
    },
    load: (key, maxAge = 21600000) => {
        try {
            const d = JSON.parse(localStorage.getItem(key) || '{}');
            return d.ts && Date.now() - d.ts < maxAge ? d : null;
        } catch { return null; }
    },
    // NUEVOS MÉTODOS
    saveFrozen: (frozenState) => {
        try {
            localStorage.setItem('frozenState', JSON.stringify({
                ...frozenState,
                ts: Date.now()
            }));
        } catch (e) { }
    },
    loadFrozen: () => {
        try {
            const d = JSON.parse(localStorage.getItem('frozenState') || '{}');
            if (!d.ts || Date.now() - d.ts > 72 * 3600000) return null;
            return d;
        } catch { return null; }
    },
    // --- NUEVOS MÉTODOS ESPECÍFICOS (desde app_anterior, adaptados) ---
    saveFlow: function (data) {
        this.save('flowData', data);
    },
    loadFlow: function () {
        const data = this.load('flowData', CONFIG.CACHE_MAX_AGE_MS);
        return data || null;
    },
    saveMarketState: function (data) {
        this.save('marketState', data);
    },
    loadMarketState: function () {
        return this.load('marketState', CONFIG.CACHE_MAX_AGE_MS);
    },
    saveAnomalies: function (data) {
        this.save('anomalies', data);
    },
    loadAnomalies: function () {
        // Las anomalías pueden durar más (72h para cubrir findes)
        return this.load('anomalies', 72 * 60 * 60 * 1000);
    }
};

// ==================== CHART ====================
let chart = null;

// ==================== NUEVA VENTANA CONGELABLE ====================
const getWindow = () => {
    // Si está congelado, devolver límites congelados
    if (State.frozen.isFrozen) {
        return { 
            start: State.frozen.start, 
            end: State.frozen.end 
        };
    }

    const ahora = toCET();
    const modo = getGraphMode();

    let start, end;

    if (modo === 'live') {
        // Modo live: ventana deslizante normal
        end = isMarketOpen(ahora) ? ahora : getLastMarketClose(ahora);
        start = new Date(end.getTime() - 4 * 3600000);
    } else {
        // Modo snapshot: congelado en último cierre
        end = getLastMarketClose(ahora);
        start = new Date(end.getTime() - 4 * 3600000);
    }

    return {
        start: start.getTime(),
        end: end.getTime()
    };
};

// ==================== FUNCIÓN FETCH CON RETRY (NUEVA) ====================
/**
 * Fetch con retry exponencial (desde app_anterior.js, adaptado)
 */
async function fetchWithRetry(url, options = {}, retryCount = 0) {
    try {
        const response = await fetch(url, options);

        if (!response.ok) {
            // Si es error 5xx (servidor) y tenemos reintentos, reintentamos
            if (response.status >= 500 && retryCount < CONFIG.RETRY_ATTEMPTS) {
                const nextRetry = retryCount + 1;
                const delay = CONFIG.RETRY_DELAY_MS * Math.pow(2, retryCount);

                console.warn(`[Fetch] Error ${response.status} en ${url}, reintento ${nextRetry}/${CONFIG.RETRY_ATTEMPTS} en ${delay}ms`);

                await new Promise(resolve => setTimeout(resolve, delay));
                return fetchWithRetry(url, options, nextRetry);
            }
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        // Si es error de red y tenemos reintentos
        if (retryCount < CONFIG.RETRY_ATTEMPTS) {
            const nextRetry = retryCount + 1;
            const delay = CONFIG.RETRY_DELAY_MS * Math.pow(2, retryCount);

            console.warn(`[Fetch] Error de red en ${url}, reintento ${nextRetry}/${CONFIG.RETRY_ATTEMPTS} en ${delay}ms`);

            await new Promise(resolve => setTimeout(resolve, delay));
            return fetchWithRetry(url, options, nextRetry);
        }
        throw error;
    }
};

// ==================== PROCESAMIENTO DE DATOS HISTÓRICOS (NUEVO) ====================
/**
* Procesa datos históricos y actualiza State.history (desde app_anterior.js, adaptado)
* @param {Array} history - Array de snapshots del backend
* @returns {boolean} - true si se procesaron datos
*/
function procesarDatosHistoricos(history) {
    if (!history || history.length === 0) return false;

    // Backend ya entrega ASC (cronológico) - sort innecesario
    // Limpiar y poblar State.history
    State.history = { time: [], calls: [], puts: [], spy: [] };

    history.forEach(item => {
        const timestamp = typeof item.timestamp === 'number'
            ? item.timestamp
            : toUnix(new Date(item.timestamp));

        State.history.time.push(timestamp);
        State.history.calls.push((item.cum_call_flow || 0) / 1e6);
        State.history.puts.push((item.cum_put_flow || 0) / 1e6);
        State.history.spy.push(item.spy_price || 0);
    });

    // Actualizar ATM y prevClose si existen en el último registro
    if (history.length > 0) {
        const last = history[history.length - 1];
        if (last.atm_min && last.atm_max) {
            State.current.atm = { min: last.atm_min, max: last.atm_max };
        }
        if (last.previous_close) {
            State.current.prevClose = last.previous_close;
        }
    }

    console.log(`[Historic] Procesados ${State.history.time.length} puntos históricos`);
    return true;
}

const initChart = () => {
    const ctx = document.getElementById('flowChart');
    if (!ctx) {
        console.error('[Chart] Canvas no encontrado');
        return false;
    }

    // ==================== TOOLTIP CON EFECTO MAGNET (SUAVIZADO) ====================
    // Variables globales para suavizado
    let tooltipTarget = { x: 0, y: 0 };
    let tooltipCurrent = { x: 0, y: 0 };
    const SMOOTH_FACTOR = 0.15; // Ajusta entre 0.05 (muy suave) y 0.3 (rápido)

    if (typeof Chart !== 'undefined' && Chart.Tooltip && !Chart.Tooltip.positioners.followMouse) {
        Chart.Tooltip.positioners.followMouse = function (elements, eventPosition) {
            const tooltip = this;
            const chart = tooltip.chart;

            if (!chart) return { x: eventPosition.x, y: eventPosition.y };

            const rect = chart.canvas.getBoundingClientRect();
            const midX = rect.width / 2;

            // Calcular posición objetivo
            let targetX, xAlign;

            if (eventPosition.x < midX) {
                targetX = eventPosition.x + 20;
                xAlign = 'left';
            } else {
                targetX = eventPosition.x - 20;
                xAlign = 'right';
            }

            const targetY = eventPosition.y;
            const yAlign = 'center';

            // Inicializar posición si es primera vez
            if (tooltipCurrent.x === 0 && tooltipCurrent.y === 0) {
                tooltipCurrent.x = targetX;
                tooltipCurrent.y = targetY;
            }

            // Interpolar suavemente (lerp)
            tooltipCurrent.x += (targetX - tooltipCurrent.x) * SMOOTH_FACTOR;
            tooltipCurrent.y += (targetY - tooltipCurrent.y) * SMOOTH_FACTOR;

            return {
                x: Math.round(tooltipCurrent.x),
                y: Math.round(tooltipCurrent.y),
                xAlign,
                yAlign
            };
        };
    }

    if (chart) chart.destroy();

    if (Chart && !Chart.registry?.plugins?.get('annotation')) {
        const plugin = window.chartjsPluginAnnotation || window.ChartAnnotation;
        if (plugin) Chart.register(plugin);
    }

    Chart.defaults.elements.point = { radius: 0, hoverRadius: 4, hitRadius: 10 };

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], datasets: [
                { label: 'Calls', data: [], borderColor: '#00ff88', backgroundColor: '#00ff88', pointStyle: 'circle', tension: 0.4, yAxisID: 'y', spanGaps: true },
                { label: 'Puts', data: [], borderColor: '#ff4444', backgroundColor: '#ff4444', pointStyle: 'circle', tension: 0.4, yAxisID: 'y', spanGaps: true },
                { label: 'SPY', data: [], borderColor: '#ffd700', backgroundColor: '#ffd700', pointStyle: 'circle', borderDash: [1, 1], yAxisID: 'yPrice', spanGaps: true }
            ]
        },
        options: {
            animation: false, responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                decimation: { enabled: true, algorithm: 'lttb', samples: 500 },
                tooltip: {
                    enabled: true,
                    position: 'followMouse',
                    backgroundColor: 'rgba(15, 20, 70, 0.8)',
                    titleColor: '#ccc',
                    bodyColor: '#ccc',
                    borderColor: 'rgba(14, 58, 67, 0.5)',
                    borderWidth: 1,
                    padding: 12,
                    usePointStyle: true,
                    displayColors: true,
                    pointStyle: 'circle',
                    boxWidth: 8,
                    boxHeight: 8,
                    callbacks: {
                        title: ctx => {
                            const d = new Date(ctx[0].parsed.x);
                            const time = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                            const date = `${d.getDate().toString().padStart(2, '0')}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getFullYear().toString().slice(-2)}`;
                            return `${time} 📅 ${date}`;
                        },
                        label: ctx => {
                            const label = ctx.dataset.label || '';
                            const val = ctx.parsed.y.toFixed(2);
                            return `${label}: $${val}${label === 'SPY' ? '' : 'M'}`;
                        },
                        // ✅ CALLBACK AÑADIDO - Garantiza los colores en los círculos
                        labelColor: function (context) {
                            return {
                                borderColor: context.dataset.borderColor,
                                backgroundColor: context.dataset.borderColor,
                                borderWidth: 2,
                                borderRadius: 2,
                            };
                        }
                    }
                },
                annotation: { annotations: {} }
            },
            scales: {
                x: { type: 'time', display: false },
                y: { display: true, position: 'left', title: { display: false, text: 'Flow (M$)' } },
                yPrice: { display: true, position: 'right', grid: { drawOnChartArea: false } }
            }
        }
    });
    return true;
};

const updateChart = () => {
    if (!chart) return;

    chart.data.labels = State.history.time.map(fromUnix);
    chart.data.datasets[0].data = State.history.calls;
    chart.data.datasets[1].data = State.history.puts;
    chart.data.datasets[2].data = State.history.spy;

    const w = getWindow();
    chart.options.scales.x.min = w.start;
    chart.options.scales.x.max = w.end;

     // Declarar nowMs ANTES de usarla
    const now = toCET();
    const nowMs = now.getTime();
    const windowDay = new Date(w.end);              
    windowDay.setHours(0, 0, 0, 0);                 

    const annotations = {};

    // Línea de previous close
    if (State.current.prevClose) {
        annotations.prevClose = {
            type: 'line',
            scaleID: 'yPrice',
            value: State.current.prevClose,
            borderColor: '#69788d',
            borderDash: [5, 5],
            borderWidth: 2,
            label: {
                enabled: true,
                display: true,
                content: `$${formatPrice(State.current.prevClose)}`,
                position: 'center',
                xAdjust: 1, 
                backgroundColor: 'rgba(69, 99, 142, 0.3)',
                color: '#96adcd',
                font: { size: 12, weight: 'bold' }
            }
        };
    }

    // Franjas horarias - SIN condición que bloquee
    ['azul', 'naranja'].forEach((f, i) => {
        const start = new Date(windowDay);
        start.setHours(i ? 22 : 0, i ? 0 : 15, 0, 0);
        const end = new Date(windowDay);
        end.setHours(i ? 22 : 15, i ? 15 : 30, 0, 0);

        if (start.getTime() <= w.end && end.getTime() >= w.start) {
            annotations[`f${i}`] = {
                type: 'box',
                xScaleID: 'x',
                yScaleID: 'y',
                xMin: Math.max(start.getTime(), w.start),
                xMax: Math.min(end.getTime(), w.end, nowMs),
                backgroundColor: i ? 'rgba(255, 102, 0, 0.05)' : 'rgba(4, 99, 252, 0.05)',
                borderWidth: 0,
                label: { display: true, content: i ? 'Closing' : 'Opening' }
            };
        }
    });

    // Aplicar anotaciones
    chart.options.plugins.annotation.annotations = annotations;

    // ✅ USAR SUGGESTEDMIN/SUGGESTEDMAX para incluir prevClose
    if (State.current.prevClose && State.history.spy.length > 0) {
        const spyValues = State.history.spy.filter(v => v > 0);
        const minSpy = Math.min(...spyValues);
        const maxSpy = Math.max(...spyValues);
        const prevClose = State.current.prevClose;

        // Rango combinado con 10% de padding
        const allValues = [minSpy, maxSpy, prevClose];
        const globalMin = Math.min(...allValues);
        const globalMax = Math.max(...allValues);
        const range = globalMax - globalMin;
        const padding = range * 0.1;

        chart.options.scales.yPrice.suggestedMin = globalMin - padding;
        chart.options.scales.yPrice.suggestedMax = globalMax + padding;
    }

    chart.update('none');
};

// ==================== UI ====================
const DOM = {
    spy: document.querySelector('.spy-price'),
    change: document.getElementById('price-change'),
    atmMin: document.getElementById('range-min'),
    atmMax: document.getElementById('range-max'),
    status: document.querySelector('.status'),
    callsCol: document.querySelector('.calls-column'),
    putsCol: document.querySelector('.puts-column'),
    nyse: document.getElementById('nyse-time'),
    cet: document.getElementById('cet-time'),
    countdown: { label: document.getElementById('countdown-label'), time: document.getElementById('countdown-time'), card: document.querySelector('.countdown-card') }
};

const updateUI = {
    spy: price => { if (DOM.spy) DOM.spy.textContent = `$${formatPrice(price)}`; },
    change: pct => {
        if (!DOM.change || pct == null) return;
        DOM.change.textContent = `${pct >= 0 ? '+' : ''}${formatPrice(pct)}%`;
        DOM.change.className = `price-change ${pct >= 0 ? 'positive' : 'negative'}`;
    },
    atm: () => {
        if (DOM.atmMin && DOM.atmMax && State.current.atm.min && State.current.atm.max) {
            DOM.atmMin.textContent = `$${State.current.atm.min}`;
            DOM.atmMax.textContent = `$${State.current.atm.max}`;
        }
    },
    status: () => {
        if (!DOM.status) return;
        
        // Limpiar clases previas
        DOM.status.classList.remove('connected', 'disconnected', 'market-closed', 'data-paused');
        
        const marketOpen = isMarketOpen();
        
        if (State.connection.retries >= 10) {
            DOM.status.textContent = '● ERROR';
            DOM.status.classList.add('disconnected');  // rojo pulse
        }
        else if (!marketOpen) {
            DOM.status.textContent = '● DATA PAUSED';
            DOM.status.classList.add('data-paused');  // dorado - mercado cerrado
        }
        else if (State.connection.isConnected) {
            DOM.status.textContent = '● CONNECTED';
            DOM.status.classList.add('connected');  // verde - todo OK
        }
        else {
            DOM.status.textContent = '● CONNECTING...';
            DOM.status.classList.add('market-closed');  // naranja - intentando conectar
        }
    },
    metrics: () => {
        const last = State.history.calls.length - 1;
        if (last < 0) return;
        const c = State.history.calls[last] || 0, p = State.history.puts[last] || 0, net = c - p;
        ['call-metric-value', 'put-metric-value', 'net-metric-value'].forEach((id, i) => {
            const el = document.getElementById(id);
            if (el) {
                if (i === 0) el.innerText = `$${c.toFixed(2)}M`;
                else if (i === 1) el.innerText = `$${p.toFixed(2)}M`;
                else { el.innerText = `$${net.toFixed(2)}M`; el.style.color = net >= 0 ? '#00ff88' : '#ff4444'; }
            }
        });

        // PULSE FLOW
        const pulseElement = document.getElementById('netflow-pulse');
        if (pulseElement) {
            const last = State.history.calls.length - 1;
            const netFlow = (State.history.calls[last] || 0) - (State.history.puts[last] || 0);

            let pulseClass = 'neutral';
            if (netFlow > 5) pulseClass = 'bullish';
            else if (netFlow < -5) pulseClass = 'bearish';

            pulseElement.className = `netflow-pulse ${pulseClass}`;
        }
    },
    
    anomalies: () => {
        if (!DOM.callsCol || !DOM.putsCol) return;

        const isValidAnomaly = (a) => {
            return a &&
                a.strike !== undefined && a.strike !== null &&
                a.mid_price !== undefined && a.mid_price !== null &&
                a.timestamp !== undefined && a.timestamp !== null;
        };

        const render = (arr, isPut) => arr
            .filter(isValidAnomaly)
            .slice(0, 5)
            .map(a => {
                const card = document.createElement('div');
                card.className = 'alert-card';
                card.innerHTML = `
                    <div class="alert-line-1">${isPut ? '🔴' : '🟢'} ${isPut ? 'PUT' : 'CALL'} $${formatPrice(a.strike)} → $${formatPrice(a.mid_price)}</div>
                    <div class="alert-line-2">Deviation: ${Math.abs(a.deviation_percent || 0).toFixed(1)}% <span class="severity-${(a.severity || 'MED').toLowerCase()}">[${a.severity || 'MED'}]</span></div>
                    <div class="alert-line-3">${formatTime(a.timestamp)}</div>
                `;
                return card;
            });

        DOM.callsCol.innerHTML = '';
        DOM.putsCol.innerHTML = '';

        render(State.anomalies.calls, false).forEach(c => DOM.callsCol.appendChild(c));
        render(State.anomalies.puts, true).forEach(c => DOM.putsCol.appendChild(c));
    },
    clocks: () => {
        const now = new Date();
        if (DOM.nyse) DOM.nyse.textContent = toET(now).toLocaleTimeString('en-US', { hour12: false });
        if (DOM.cet) DOM.cet.textContent = toCET(now).toLocaleTimeString('en-US', { hour12: false });

        if (DOM.countdown.card && DOM.countdown.label && DOM.countdown.time) {
            const et = toET(now), h = et.getHours(), m = et.getMinutes(), d = et.getDay();

            // NUEVO: Limpiar clases anteriores
            DOM.countdown.card.classList.remove('market-open', 'market-closed', 'market-premarket');

            if (d === 0 || d === 6) {
                const next = new Date(et); next.setDate(next.getDate() + (d === 0 ? 1 : 2)); next.setHours(9, 30, 0, 0);
                const diff = next - et;
                DOM.countdown.label.textContent = '⏱ TILL MONDAY OPEN';
                DOM.countdown.time.textContent = `${Math.floor(diff / 3600000)}h ${Math.floor((diff % 3600000) / 60000)}m`;
                // NUEVO: Color para fin de semana
                DOM.countdown.card.classList.add('market-closed');
            } else if (h >= 9 && h < 16) {
                // NUEVO: Distinguir pre-market vs market open
                if (h === 9 && m < 30) {
                    // Pre-market (9:00-9:30)
                    const openTime = new Date(et); openTime.setHours(9, 30, 0, 0);
                    const diff = openTime - et;
                    DOM.countdown.label.textContent = '⏱ TILL OPEN';
                    DOM.countdown.time.textContent = `${Math.floor(diff / 60000)}m`; // Minutos
                    // NUEVO: Color naranja para pre-market
                    DOM.countdown.card.classList.add('market-premarket');
                } else {
                    // Market open (9:30-16:00)
                    const end = new Date(et); end.setHours(16, 0, 0, 0);
                    const diff = end - et;
                    DOM.countdown.label.textContent = '⏱ TILL CLOSE';
                    DOM.countdown.time.textContent = `${Math.floor(diff / 3600000)}h ${Math.floor((diff % 3600000) / 60000)}m`;
                    // NUEVO: Color verde para market open
                    DOM.countdown.card.classList.add('market-open');
                }
            } else {
                const next = new Date(et); next.setDate(next.getDate() + (h >= 16 ? 1 : 0)); next.setHours(9, 30, 0, 0);
                const diff = next - et;
                DOM.countdown.label.textContent = '⏱ TILL OPEN';
                DOM.countdown.time.textContent = `${Math.floor(diff / 3600000)}h ${Math.floor((diff % 3600000) / 60000)}m`;
                // NUEVO: Color para fuera de horario
                DOM.countdown.card.classList.add('market-closed');
            }
        }
    },
};

// ==================== SIGNALR ====================
let connection = null;

const initSignalR = async () => {
    // Solo conectar en horario de mercado (a menos que esté en modo testing)
    if (!CONFIG.TESTING_MODE && !isMarketOpen() && !State.frozen.isFrozen) {
        console.log('[SignalR] Mercado cerrado - reintento en 1h');
        setTimeout(initSignalR, 3600000);
        return false;
    }

    try {
        console.log('[SignalR] Fetching negotiate URL:', CONFIG.SIGNALR);
        const resp = await fetch(CONFIG.SIGNALR);
        const info = await resp.json();
        console.log('[SignalR] Negotiation OK:', { url: info.url, token: info.accessToken ? '✅ token' : '❌ no token' });

        connection = new signalR.HubConnectionBuilder()
            .withUrl(info.url, { accessTokenFactory: () => info.accessToken })
            .withAutomaticReconnect()
            .build();
        console.log('[SignalR] HubConnectionBuilder OK');    

        connection.on('marketState', data => {
            console.log('[SignalR] 📊 marketState recibido:', data);
            if (data.current_price) { State.current.spy = data.current_price; updateUI.spy(data.current_price); }
            if (data.spy_change_pct !== undefined) { State.current.change = data.spy_change_pct; updateUI.change(data.spy_change_pct); }
            if (data.atm_min && data.atm_max) { State.current.atm = { min: data.atm_min, max: data.atm_max }; updateUI.atm(); }
            if (data.previous_close) State.current.prevClose = data.previous_close;
            if (data.market_status) State.current.status = data.market_status;
        });

    if (CONFIG.ENABLE_FLOW_FEATURE) {
        connection.on('flow', data => {
            console.log('[SignalR] 📈 flow recibido:', { timestamp: data.timestamp, spy: data.spy_price });
            if (!data.timestamp) return;
            const ts = typeof data.timestamp === 'number' ? data.timestamp : toUnix(new Date(data.timestamp));
            State.history.time.push(ts);
            State.history.calls.push((data.cum_call_flow || 0) / 1e6);
            State.history.puts.push((data.cum_put_flow || 0) / 1e6);
            State.history.spy.push(data.spy_price || 0);

            if (chart) {
                chart.data.labels.push(fromUnix(ts));
                chart.data.datasets[0].data.push(State.history.calls[State.history.calls.length - 1]);
                chart.data.datasets[1].data.push(State.history.puts[State.history.puts.length - 1]);
                chart.data.datasets[2].data.push(State.history.spy[State.history.spy.length - 1]);

                // DEBOUNCE: solo actualizar cada 100ms
                if (chartUpdateTimeout) clearTimeout(chartUpdateTimeout);
                chartUpdateTimeout = setTimeout(() => {
                    chart.update('none');
                    chartUpdateTimeout = null;
                }, 100);
            }

            updateUI.metrics();
        });

        connection.on('anomalyDetected', data => {
            console.log('[SignalR] 🚨 anomalyDetected:', { type: data.option_type, strike: data.strike });
            const arr = data.option_type === 'PUT' ? State.anomalies.puts : State.anomalies.calls;
            arr.unshift(data);
            if (arr.length > 5) arr.pop();
            updateUI.anomalies();
            Storage.save('anomalies', { calls: State.anomalies.calls, puts: State.anomalies.puts });
        });
    }

        connection.onreconnecting(() => { State.connection.isConnected = false; updateUI.status(); });
            console.warn('[SignalR] 🔌 Reconnecting...'); 
        connection.onreconnected(() => { State.connection.isConnected = true; State.connection.retries = 0; updateUI.status(); });
            console.log('[SignalR] ✅ Reconnected'); 
        connection.onclose(() => {
            console.error('[SignalR] ❌ Connection closed');
            State.connection.isConnected = false;
            updateUI.status();
            if (State.connection.retries++ < 10) setTimeout(initSignalR, 2000 * Math.pow(2, State.connection.retries - 1));
        });

        console.log('[SignalR] Iniciando start()...');
        await connection.start();
        console.log('[SignalR] ✅ start() OK - Conectado');

        State.connection.isConnected = true;
        State.connection.retries = 0;
        updateUI.status();
        return true;
    } catch (e) {
        console.error('[SignalR] ❌ Error en initSignalR:', e.message);
        State.connection.isConnected = false;
        updateUI.status();
        if (State.connection.retries++ < 10) setTimeout(initSignalR, 2000 * Math.pow(2, State.connection.retries - 1));
        return false;
    }
};

// ==================== CARGA INICIAL ====================
const loadData = async () => {
    console.log('[LoadData] 🚀 Iniciando carga de datos...');

    const frozen = Storage.loadFrozen();
    if (frozen) {
        State.frozen = frozen;
        console.log('[LoadData] ❄️ Estado congelado restaurado:', frozen);
    }

    // Helper: Validar integridad de datos SPY
    const isValidSpyData = (data) => {
        return data &&
            data.price !== null && data.price !== undefined &&
            data.spy_change_pct !== null && data.spy_change_pct !== undefined &&
            data.previous_close !== null && data.previous_close !== undefined &&
            data.atm_min && data.atm_max;
    };

    // Helper: Aplicar datos SPY al State y UI
    const applySpyData = (data) => {
        State.current.spy = data.price;
        State.current.change = data.spy_change_pct;
        State.current.prevClose = data.previous_close;
        State.current.status = data.market_status || 'unknown';
        State.current.atm = { min: data.atm_min, max: data.atm_max };

        updateUI.spy(data.price);
        updateUI.change(data.spy_change_pct);
        updateUI.atm();

        // Redibujar el gráfico AHORA que tenemos prevClose
        if (chart) {
            updateChart();
            console.log('[SPY] Gráfico actualizado con prevClose:', data.previous_close);
        }
    };
    
    console.log('[LoadData] 📈 Cargando SPY market data...');

    // 1️⃣ PRIMERO: localStorage (instantáneo)
    const cachedSpy = Storage.loadMarketState();
    if (cachedSpy && isValidSpyData(cachedSpy)) {
        applySpyData(cachedSpy);
        console.log('[SPY] ✅ Datos de caché aplicados (0ms)');
    }

    // 2️⃣ DESPUÉS: API (en segundo plano)
    fetchWithRetry(ENDPOINTS.SPY_MARKET_LATEST)
        .then(freshData => {
            if (freshData && isValidSpyData(freshData)) {
                applySpyData(freshData);
                Storage.saveMarketState(freshData);
                console.log('[SPY] ✅ Datos frescos aplicados (background)');
            }
        })
        .catch(e => console.error('[SPY] Error background:', e));

    console.log('[LoadData] 📊 Cargando flow data...');
    const cached = Storage.loadFlow();
    if (cached?.history) {
        State.history = cached.history;
        console.log(`[Load] Cargados Flow ${State.history.time.length} puntos de caché`);
        updateChart();
        updateUI.metrics();
    } else if (CONFIG.ENABLE_FLOW_FEATURE) {
        try {
            // --- MODIFICADO: Usar ENDPOINTS y fetchWithRetry ---
            console.log('[Load] Cargando datos históricos del backend...');
            const data = await fetchWithRetry(ENDPOINTS.FLOW_SNAP);

            if (data?.history) {
                // --- MODIFICADO: Usar procesarDatosHistoricos() ---
                const procesado = procesarDatosHistoricos(data.history);
                console.log('[LoadData] ✅ Flow procesado:', procesado);

                if (procesado) {
                    updateChart();
                    updateUI.metrics();
                    updateUI.atm();
                    // --- MODIFICADO: Usar Storage.saveFlow() ---
                    if (CONFIG.ENABLE_FLOW_FEATURE) {
                        Storage.saveFlow({ history: State.history });
                    }
                }
            }
        } catch (e) {
            console.warn('[Load] Failed to load historical data:', e);
        }
    }

    console.log('[LoadData] 🚨 Cargando anomalías...');
    const cachedAnomalies = Storage.loadAnomalies();
        if (cachedAnomalies) {
        State.anomalies = {
            calls: cachedAnomalies.calls || [],
            puts: cachedAnomalies.puts || []
        };
        
        updateUI.anomalies();
        console.log(`[Anomalies] Cargadas ${cachedAnomalies.calls?.length || 0} calls y ${cachedAnomalies.puts?.length || 0} puts de caché`);
    }

    // Cargar anomalies desde backend para sincronizar (usando fetchWithRetry)
    try {
        console.log('[Anomalies] Cargando del backend...');
        const anomaliesData = await fetchWithRetry(ENDPOINTS.ANOMALIES_SNAP);

        if (anomaliesData?.anomalies && anomaliesData.anomalies.length > 0) {
            // Separar por tipo y limitar a 5
            const calls = anomaliesData.anomalies
                .filter(a => a.option_type === 'CALL')
                .slice(0, 5);
            const puts = anomaliesData.anomalies
                .filter(a => a.option_type === 'PUT')
                .slice(0, 5);

            // Actualizar State solo si hay datos nuevos
            if (calls.length > 0 || puts.length > 0) {
                State.anomalies = { calls, puts };
                updateUI.anomalies();
                // --- MODIFICADO: Usar Storage.saveAnomalies() ---
                Storage.saveAnomalies({ calls, puts });
                console.log(`[Anomalies] Cargadas ${calls.length} calls y ${puts.length} puts del backend`);
            }
        }
    } catch (e) {
        console.warn('[Anomalies] Error cargando del backend, usando caché existente:', e);
    }

};

// ==================== CROSSHAIR ====================
const initCrosshair = () => {
    const canvas = document.getElementById('flowChart');
    if (!canvas) return;

    let container = canvas.parentElement;
    if (!container.classList.contains('chart-container')) {
        container = document.createElement('div');
        container.className = 'chart-container';
        container.style.position = 'relative';
        canvas.parentNode.insertBefore(container, canvas);
        container.appendChild(canvas);
    }

    const vline = document.createElement('div');
    const hline = document.createElement('div');
    const style = 'position:absolute;background:rgba(115,115,115,0.8);pointer-events:none;display:none;z-index:5;';

    vline.style.cssText = style + 'width:1px;height:100%;top:0;';
    hline.style.cssText = style + 'height:1px;width:100%;left:0;';

    container.appendChild(vline);
    container.appendChild(hline);

    canvas.addEventListener('mousemove', e => {
        const rect = e.target.getBoundingClientRect();
        vline.style.left = (e.clientX - rect.left) + 'px';
        hline.style.top = (e.clientY - rect.top) + 'px';
        vline.style.display = hline.style.display = 'block';
    });

    canvas.addEventListener('mouseleave', () => {
        vline.style.display = hline.style.display = 'none';
    });
};

// ==================== INICIALIZACIÓN ====================
const start = async () => {
    console.log('[App] Starting...');
    
    // ===== ACTUALIZAR UI =====
    updateUI.status();
    updateUI.clocks();
    setInterval(updateUI.clocks, 1000);

    initChart();
    initCrosshair();

    await loadData();
    await initSignalR();   

    setInterval(() => {
        const now = toCET();
        const hours = now.getHours();
        const minutes = now.getMinutes();

        // ===== CONTROL DE CONGELACIÓN/DESCONGELACIÓN =====
        // A las 22:15 CONGELAR (cierre de mercado)
        if (hours === 22 && minutes === 15 && !State.frozen.isFrozen) {
            const currentWindow = getWindow(); // Calcula ventana actual antes de congelar
            State.frozen = {
                isFrozen: true,
                start: currentWindow.start,
                end: currentWindow.end,
                date: now.toISOString().split('T')[0]
            };

            Storage.saveFrozen(State.frozen);

            console.log('[Window] ❄️ Congelada hasta las 15:15 - Mostrando:',
                new Date(currentWindow.start).toLocaleTimeString(), 'a',
                new Date(currentWindow.end).toLocaleTimeString());
            updateChart();
        }

        // A las 15:15 DESCONGELAR (apertura de mercado)
        if (hours === 15 && minutes === 15 && State.frozen.isFrozen) {
            State.frozen.isFrozen = false;
            console.log('[Window] 🔓 Descongelada - ventana deslizante activa');
            updateChart();
        }

        // ===== ACTUALIZAR CHART SI ES NECESARIO =====
        const w = getWindow();
        if (chart && (
            chart.options.scales.x.min !== w.start ||
            chart.options.scales.x.max !== w.end
        )) {
            chart.options.scales.x.min = w.start;
            chart.options.scales.x.max = w.end;
            chart.update('none');
        }

        
       

        // ===== PERSISTENCIA CADA 30 SEGUNDOS (MEJORADA) =====
        if (Date.now() % CONFIG.PERSIST_INTERVAL < 1000) {
            // --- MODIFICADO: Usar los nuevos métodos específicos ---
            if (CONFIG.ENABLE_FLOW_FEATURE) {
                Storage.saveFlow({ history: State.history });
            }
            Storage.saveAnomalies({
                calls: State.anomalies.calls,
                puts: State.anomalies.puts
            });
            // --- MODIFICADO: También persistir market state regularmente ---
            if (State.current.spy) {
                Storage.saveMarketState({
                    price: State.current.spy,
                    spy_change_pct: State.current.change,
                    previous_close: State.current.prevClose,
                    market_status: State.current.status,
                    atm_min: State.current.atm.min,
                    atm_max: State.current.atm.max
                });
            }
            if (State.frozen.isFrozen) {
                Storage.saveFrozen(State.frozen);
            }
        }
    }, 2000); // Intervalo de 2 segundos

    const savedLang = localStorage.getItem('preferredLanguage') || 'en';
    window.switchLanguage(savedLang);

    window.app = { State, CONFIG, updateUI, chart };
    console.log('[App] Ready');
};

// ==================== IDIOMAS ====================
const i18n = {
    en: {
        monitoredRange: "Monitored Range",
        maxStrike: "Max Strike",
        minStrike: "Min Strike",
        updateFreq: "Update: Every 2sec",
        chartTitle: "📊 Real-Time Signed Premium Flow",
        alertsTitle: "🚨 Detected Anomaly Alerts"
    },
    es: {
        monitoredRange: "Rango Monitoreado",
        maxStrike: "Strike Máximo",
        minStrike: "Strike Mínimo",
        updateFreq: "Actualización: Cada 2seg",
        chartTitle: "📊 Flujo de Primas en Tiempo Real",
        alertsTitle: "🚨 Alertas de Anomalías Detectadas"
    }
};
let currentLang = localStorage.getItem('preferredLanguage') || 'en';

window.switchLanguage = lang => {
    currentLang = lang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (i18n[lang]?.[key]) {
            el.textContent = i18n[lang][key];
        }
    });
    // Actualizar clases de clock-cards activos
    document.getElementById('clock-en')?.classList.toggle('active', lang === 'en');
    document.getElementById('clock-es')?.classList.toggle('active', lang === 'es');
    localStorage.setItem('preferredLanguage', lang);
};

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();