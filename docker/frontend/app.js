// ============================================
// app.js - VERSIÓN OPTIMIZADA (70% reducción)
// ============================================

// ==================== CONFIG ====================
const CONFIG = {
    API: window.CONFIG?.backend?.baseUrl || 'https://default-api.example.com',
    SIGNALR: window.CONFIG?.signalr?.negotiateUrl || 'https://default-signalr.example.com/negotiate',
    USE_BACKEND_STATUS: true,
    TESTING_MODE: window.CONFIG?.TESTING_MODE || false,

    // ⚠️ FEATURE FLAGS
    ENABLE_FLOW_FEATURE: true,
    MAX_ANOMALIES: 100,
    UPDATE_INTERVAL: 2000,
    PERSIST_INTERVAL: 30000,
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY_MS: 2000,
    CACHE_MAX_AGE_MS: 6 * 60 * 60 * 1000, // 6 horas

    // ✅ OPT: Throttle de renderizado del chart (evita renders por cada tick)
    CHART_THROTTLE_MS: 500,    // máx 2 renders/segundo
    PERSIST_MIN_CHANGE: 50000, // $50k de cambio mínimo para persistir flow
};

let chartUpdateTimeout = null;
let pendingChartFrame = null;   // ✅ OPT: referencia a requestAnimationFrame pendiente
let lastChartRender = 0;        // ✅ OPT: timestamp del último render para throttle

// ==================== ENDPOINTS (NUEVO) ====================
const ENDPOINTS = {
    FLOW_SNAP: `${CONFIG.API}/flow/Flow_snap_last_4h`,
    ANOMALIES_SNAP: `${CONFIG.API}/anomalies/anom_snap`,
    SPY_MARKET_LATEST: `${CONFIG.API}/spymarket/spy_latest`
};

// ==================== ESTADO GLOBAL ====================
const State = {
    history: { time: [], calls: [], puts: [], net: [], spy: [] },
    current: { spy: null, change: null, prevClose: null, atm: { min: null, max: null }, status: 'unknown' },
    anomalies: { calls: [], puts: [] },
    market: { isOpen: false, mode: 'snapshot' },
    frozen: { isFrozen: false, start: null, end: null, date: null },
    connection: { isConnected: false, retries: 0 }
};

// ==================== UTILIDADES ====================
const toCET = (d = new Date()) => new Date(d.toLocaleString('en-US', { timeZone: 'Europe/Madrid' }));
const toET = (d = new Date()) => new Date(d.toLocaleString('en-US', { timeZone: 'America/New_York' }));
const toUnix = d => d.getTime(); // Ahora devuelve milisegundos
const fromUnix = ts => new Date(ts);
const formatTime = ts => fromUnix(ts).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const formatPrice = v => Number.isFinite(v) ? v.toFixed(2) : '0.00';

// ==================== CALENDARIO Y MERCADO (CORREGIDO) ====================
const HOLIDAYS = ['01-01', '12-25'];

// Configuración de horarios de mercado 2026
const MARKET_HOURS = {
    // Horarios fijos de USA (ET)
    OPEN_ET: "09:30",
    CLOSE_ET: "16:00",

    // Fechas de cambio de horario 2026
    DST_START: "2026-03-08",
    DST_END: "2026-11-01",

    // Cache de último cálculo
    _cachedHours: null,
    _cachedDate: null,

    isDSTActive: function (date = new Date()) {
        const dstStart = new Date(this.DST_START + "T02:00:00-05:00");
        const dstEnd = new Date(this.DST_END + "T02:00:00-04:00");
        return date >= dstStart && date < dstEnd;
    },

    getHoursCET: function (date = new Date()) {
        const dateStr = date.toISOString().split('T')[0];
        if (this._cachedDate === dateStr && this._cachedHours) {
            return this._cachedHours;
        }

        // Horarios CET según época del año
        if (this.isDSTActive(date)) {
            // Verano (marzo - octubre): 14:30 - 21:00 CET
            this._cachedHours = { open: 14.5, close: 21 };
        } else {
            // Invierno (noviembre - febrero): 15:30 - 22:00 CET
            this._cachedHours = { open: 15.5, close: 22 };
        }

        this._cachedDate = dateStr;
        return this._cachedHours;
    }
};

const isTradingDay = (date) => {
    const day = date.getDay();
    if (day === 0 || day === 6) return false;
    const mmdd = `${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
    return !HOLIDAYS.includes(mmdd);
};

const isMarketOpen = (date = toCET()) => {
    if (!isTradingDay(date)) return false;

    const hours = MARKET_HOURS.getHoursCET(date);
    const currentHour = date.getHours() + date.getMinutes() / 60;

    return currentHour >= hours.open && currentHour < hours.close;
};

const getLastMarketClose = (fecha) => {
    let cursor = new Date(fecha);
    const hours = MARKET_HOURS.getHoursCET(cursor);

    cursor.setHours(Math.floor(hours.close), Math.round((hours.close % 1) * 60), 0, 0);

    if (fecha < cursor) cursor.setDate(cursor.getDate() - 1);
    while (!isTradingDay(cursor)) cursor.setDate(cursor.getDate() - 1);

    cursor.setHours(Math.floor(hours.close), Math.round((hours.close % 1) * 60), 0, 0);
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
    // Si está congelado, devolver límites del último estado guardado
    if (State.frozen.isFrozen) {
        return {
            start: State.frozen.start,
            end: State.frozen.end
        };
    }

    const totalPoints = State.history.time.length;
    if (totalPoints === 0) return { start: 0, end: 100 };

    // Buscamos el índice que corresponde a hace 4 horas
    const nowTs = State.history.time[totalPoints - 1];
    const cutoffTs = nowTs - (4 * 3600 * 1000); // Window de 4 horas en ms
    
    let startIndex = 0;
    for (let i = totalPoints - 1; i >= 0; i--) {
        if (State.history.time[i] < cutoffTs) {
            startIndex = i;
            break;
        }
    }

    return {
        start: startIndex,
        end: totalPoints - 1
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
    if (!history || history.length === 0) {
        console.warn('[Historic] No hay datos disponibles para sincronizar');
        return false;
    }

    // SINCRONIZACIÓN TOTAL: Limpiar estado y datasets del chart
    State.history = { time: [], calls: [], puts: [], net: [], spy: [] };
    if (chart) {
        chart.data.datasets.forEach(ds => ds.data = []);
    }

    history.forEach((item, index) => {
        let ts = typeof item.timestamp === 'number' ? item.timestamp : new Date(item.timestamp).getTime();
        if (ts < 10000000000) ts *= 1000;
        ts = Math.floor(ts / 1000) * 1000;

        if (State.history.time.length > 0) {
            const lastTs = State.history.time[State.history.time.length - 1];
            if (ts <= lastTs) ts = lastTs + 1;
        }

        const spyPrice = (item.spy_price && item.spy_price > 0) ? item.spy_price : null;
        const c = (item.cum_call_flow || 0) / 1e6;
        const p = (item.cum_put_flow || 0) / 1e6;
        const net = c - p;

        State.history.time.push(ts);
        State.history.calls.push(c);
        State.history.puts.push(p);
        State.history.net.push(net);
        State.history.spy.push(spyPrice);

        // ✅ OPT: Actualizar datasets del chart incrementalmente
        if (chart) {
            const idx = State.history.time.length - 1;
            chart.data.datasets[0].data.push({ x: index, y: c });
            chart.data.datasets[1].data.push({ x: index, y: p });
            chart.data.datasets[2].data.push({ x: index, y: net });
            chart.data.datasets[3].data.push({ x: index, y: spyPrice });
            
            // Momentum (instantáneo)
            const prevNet = State.history.net.length > 1 ? State.history.net[State.history.net.length - 2] : net;
            const momentum = net - prevNet;
            chart.data.datasets[4].data.push({ x: ts, y: momentum });
        }
    });

    if (chart && chart.data.datasets[4]) {
        chart.data.datasets[4].backgroundColor = chart.data.datasets[4].data.map(d => d.y >= 0 ? 'rgba(0, 255, 136, 0.4)' : 'rgba(255, 68, 68, 0.4)');
    }

    // Sincronizar ATM y Cierre Previo
    if (history.length > 0) {
        const last = history[history.length - 1];
        if (last.atm_min && last.atm_max) State.current.atm = { min: last.atm_min, max: last.atm_max };
        if (last.previous_close) State.current.prevClose = last.previous_close;
    }

    console.log(`[Sync] Sincronizados ${State.history.time.length} puntos. Primer TS: ${State.history.time[0]}, Último: ${State.history.time[State.history.time.length-1]}`);
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
    const SMOOTH_FACTOR = 0.05; // Ajusta entre 0.05 (muy suave) y 0.3 (rápido)

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

    // ✅ SEGURIDAD CORE: Verificar que el adaptador de tiempo esté cargado (v3 usa _adapters)
    if (typeof Chart !== 'undefined' && !Chart._adapters?._date) {
        console.warn('[Chart] Esperando al adaptador de tiempo...');
        setTimeout(initChart, 200);
        return false;
    }

    if (Chart && !Chart.registry?.plugins?.get('annotation')) {
        const plugin = window.chartjsPluginAnnotation || window.ChartAnnotation;
        if (plugin) Chart.register(plugin);
    }

    Chart.defaults.elements.point = { radius: 0, hoverRadius: 4, hitRadius: 10 };

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                { label: 'Calls', data: [], borderColor: '#00ff88', backgroundColor: 'rgba(0, 255, 136, 0.15)', fill: true, borderCapStyle: 'round', pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: false, order: 2, parsing: false },
                { label: 'Puts', data: [], borderColor: '#ff4444', backgroundColor: 'rgba(255, 68, 68, 0.15)', fill: true, borderCapStyle: 'round', pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: false, order: 2, parsing: false },
                { label: 'Net Flow (NOFA)', data: [], borderColor: '#00d4ff', borderWidth: 2.5, pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: false, order: 1, parsing: false },
                { label: 'SPY', data: [], borderColor: '#ffd700', backgroundColor: '#ffd700', pointStyle: 'circle', borderDash: [2, 2], borderWidth: 1.5, yAxisID: 'yPrice', spanGaps: false, order: 1, parsing: false },
                { label: 'Momentum', type: 'bar', data: [], backgroundColor: [], borderColor: 'rgba(0, 212, 255, 0.5)', borderWidth: 1, yAxisID: 'yNet', order: 3, barPercentage: 0.8, parsing: false }
            ]
        },
        options: {
            animation: false, responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                decimation: { enabled: false }, // Desactivado para simplificar debugging y performance manual
                tooltip: {
                    enabled: true,
                    position: 'followMouse',
                    backgroundColor: 'rgba(10, 15, 45, 0.7)',
                    titleColor: '#00d4ff',
                    bodyColor: '#ccc',
                    borderColor: 'rgba(0, 212, 255, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    usePointStyle: true,
                    callbacks: {
                        title: ctx => {
                            // Obtenemos el timestamp real usando el índice del punto seleccionado
                            const ts = State.history.time[ctx[0].dataIndex];
                            if (!ts) return '--:--';
                            const d = fromUnix(ts);
                            const time = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                            const date = `${d.getDate().toString().padStart(2, '0')}-${(d.getMonth() + 1).toString().padStart(2, '0')}`;
                            return `${time} 📅 ${date}`;
                        },
                        label: ctx => {
                            const label = ctx.dataset.label || '';
                            const val = ctx.parsed.y != null ? ctx.parsed.y.toFixed(2) : '--';
                            if (label === 'Net Flow') return `${label}: $${val}M`;
                            return `${label}: $${val}${label === 'SPY' ? '' : 'M'}`;
                        },
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
                x: {
                    type: 'linear', // Cambiamos de 'time' a 'linear' [cite: 100]
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        includeBounds: false,
                        align: 'inner',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12,
                        color: '#94a3b8',
                        font: { size: 10 },
                        callback: function (value) {
                            // Convertimos el índice de nuevo a hora legible para el usuario
                            const ts = State.history.time[Math.round(value)];
                            return ts ? new Date(ts).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) : '';
                        },
                    bounds: 'data',    
                    }
                },

                y: { display: true, position: 'left', grid: { color: 'rgba(255, 255, 255, 0.05)' }, title: { display: false } },
                yPrice: { display: true, position: 'right', grid: { drawOnChartArea: false } },
                yNet: { 
                    display: false, 
                    position: 'left',
                    grid: { drawOnChartArea: false },
                    min: -20,
                    max: 80 // Expandido para dar más margen inferior relativo
                }
            }
        }
    });

    // Vincular Scroll
    const scrollInput = document.getElementById('chartScroll');
    if (scrollInput) {
        scrollInput.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            const total = State.history.time.length;
            if (total < 100) return;

            // Definir ventana visible (ej: 300 puntos o 4h)
            const windowSize = Math.min(500, total);
            const endIdx = Math.round((val / 100) * (total - 1));
            const startIdx = Math.max(0, endIdx - windowSize);

            State.frozen.isFrozen = (val < 98); // Congelar si nos movemos del "live"
            State.frozen.start = startIdx;
            State.frozen.end = endIdx;
            
            updateChart();
        });
    }

    return true;
};

const updateChart = () => {
    // 1. Mantener tu validación original
    if (!chart || State.history.time.length === 0) return;

    const w = getWindow();
    const lastIdx = State.history.time.length - 1;

    // 2. AJUSTAR RANGO VISUAL (Sin inventar variables nuevas)
    // Solo limitamos el final para que coincida con el último dato real
    chart.options.scales.x.min = w.start;
    chart.options.scales.x.max = Math.min(w.end, lastIdx);

    // 3. ANOTACIONES (Restaurando tu lógica original de Strike Walls)
    const annotations = {};

    // A. Línea de Cierre Previo (código original)
    if (State.current.prevClose) {
        annotations.prevClose = {
            type: 'line', scaleID: 'yPrice', value: State.current.prevClose,
            borderColor: 'rgba(105, 120, 141, 0.4)', borderDash: [5, 5], borderWidth: 1,
            label: { enabled: true, content: `$${formatPrice(State.current.prevClose)}`, position: 'end', backgroundColor: 'rgba(0,0,0,0.5)', color: '#96adcd', font: { size: 10 } }
        };
    }

    // B. LÍNEA DE SESIÓN (bucle original)
    for (let i = Math.max(1, w.start); i <= w.end; i++) {
        const d1 = fromUnix(State.history.time[i - 1]);
        const d2 = fromUnix(State.history.time[i]);
        if (d1 && d2 && d1.getDate() !== d2.getDate()) {
            annotations[`session_${i}`] = {
                type: 'line', scaleID: 'x', value: i,
                borderColor: 'rgba(0, 212, 255, 0.6)', borderWidth: 2,
                label: { enabled: true, content: 'NEW SESSION', position: 'start', backgroundColor: '#1a1a2e', color: '#00d4ff', font: { size: 10 } }
            };
        }
    }

    // C. STRIKE WALLS (lógica original + el recorte de margen)
    const combinedAnomalies = [...State.anomalies.calls, ...State.anomalies.puts].slice(0, 10);
    combinedAnomalies.forEach((anom, idx) => {
        if (!anom.strike) return;
        const id = `wall_${anom.strike}_${idx}`;
        const isPut = State.anomalies.puts.includes(anom);
        annotations[id] = {
            type: 'line', scaleID: 'yPrice', value: anom.strike,
            xMin: w.start,                     // Empieza en el borde izquierdo
            xMax: Math.min(w.end, lastIdx),    // ✅ TERMINA EN EL MARGEN (Lo que pediste)
            borderColor: isPut ? 'rgba(255, 68, 68, 0.6)' : 'rgba(0, 255, 136, 0.6)',
            borderWidth: 2,
            label: {
                enabled: true, content: `${isPut ? 'PUT' : 'CALL'} $${anom.strike}`,
                position: 'center', backgroundColor: isPut ? 'rgba(52, 1, 1, 0.4)' : 'rgba(1, 45, 1, 0.6)',
                color: '#fff', font: { size: 10, weight: 'bold' }
            }
        };
    });

    // 4. LÓGICA DE ESCALADO ORIGINAL
    if (State.history.spy.length > 0) {
        const visibleSpy = State.history.spy.slice(w.start, w.end + 1).filter(v => v > 0);
        if (visibleSpy.length > 0) {
            const minS = Math.min(...visibleSpy, State.current.prevClose || Infinity);
            const maxS = Math.max(...visibleSpy, State.current.prevClose || 0);
            const pad = (maxS - minS) * 0.15;
            chart.options.scales.yPrice.suggestedMin = minS - pad;
            chart.options.scales.yPrice.suggestedMax = maxS + pad;
        }

        const visibleCalls = State.history.calls.slice(w.start, w.end + 1);
        const visiblePuts = State.history.puts.slice(w.start, w.end + 1);
        const maxFlow = Math.max(...visibleCalls, ...visiblePuts, 1);
        chart.options.scales.y.suggestedMax = maxFlow * 1.2; // Restaurado suggestedMax
    }

    chart.options.plugins.annotation.annotations = annotations;
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
    
    // ==================== REVISIÓN DE ANOMALÍAS (BLOQUES UI) ====================
    anomalies: () => {
        if (!DOM.callsCol || !DOM.putsCol) return;

        const isValidAnomaly = (a) => {
            return a && a.strike != null && a.timestamp != null; // Validación más flexible [cite: 159]
        };

        const createCard = (a, isPut) => {
            const card = document.createElement('div');
            card.className = 'alert-card';
            // Usamos valores por defecto (|| 0) para evitar que falle el renderizado [cite: 161]
            card.innerHTML = `
                <div class="alert-line-1">
                    ${isPut ? '🔴' : '🟢'} ${isPut ? 'PUT' : 'CALL'} $${formatPrice(a.strike)} → $${formatPrice(a.mid_price || 0)}
                </div>
                <div class="alert-line-2">
                    <span class="severity-${(a.severity || 'MED').toLowerCase()}">[${a.severity || 'MED'}]</span>
                    <span class="expected-text">Exp: $${formatPrice(a.expected_price)}</span>
                    <span class="deviation-text">(${Math.abs(a.deviation_percent || 0).toFixed(1)}%)</span>
                </div>
                <div class="alert-footer">
                    <span class="alert-line-3">${formatTime(a.timestamp)}</span>
                </div>
            `;
            return card;
        };

        // Limpiar columnas antes de renderizar 
        DOM.callsCol.innerHTML = '';
        DOM.putsCol.innerHTML = '';

        // Renderizar Calls 
        State.anomalies.calls
            .filter(isValidAnomaly)
            .slice(0, 5)
            .forEach(a => DOM.callsCol.appendChild(createCard(a, false)));

        // Renderizar Puts 
        State.anomalies.puts
            .filter(isValidAnomaly)
            .slice(0, 5)
            .forEach(a => DOM.putsCol.appendChild(createCard(a, true)));
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
            console.log('[SignalR] ✅ Flow recibido:', data);
            if (!chart) return;
            
            let ts = typeof data.timestamp === 'number' ? data.timestamp : new Date(data.timestamp).getTime();
            if (ts < 10000000000) ts *= 1000;
            ts = Math.floor(ts / 1000) * 1000; // Redondear a segundos para consistencia
            
            const spyPrice = (data.spy_price && data.spy_price > 0) ? data.spy_price : null;
            const c = (data.cum_call_flow || 0) / 1e6;
            const p = (data.cum_put_flow || 0) / 1e6;
            const net = c - p;

            // ✅ SEGURIDAD DE TIEMPO
            if (State.history.time.length > 0) {
                const lastTs = State.history.time[State.history.time.length - 1];
                if (ts <= lastTs) ts = lastTs + 1;
            }

            State.history.time.push(ts);
            State.history.calls.push(c);
            State.history.puts.push(p);
            State.history.net.push(net);
            State.history.spy.push(spyPrice);

            // ✅ OPT: Actualización incremental de Datasets (Sin recrear arrays)
            if (chart) {
                chart.data.datasets[0].data.push({ x: ts, y: c });
                chart.data.datasets[1].data.push({ x: ts, y: p });
                chart.data.datasets[2].data.push({ x: ts, y: net });
                chart.data.datasets[3].data.push({ x: ts, y: spyPrice });

                // Momentum instantáneo
                const prevNet = State.history.net.length > 1 ? State.history.net[State.history.net.length - 2] : net;
                const momentum = net - prevNet;
                chart.data.datasets[4].data.push({ x: ts, y: momentum });
                
                // Actualizar color solo del último bar si es necesario (o rebuild masivo si es poco frecuente)
                const lastColor = momentum >= 0 ? 'rgba(0, 255, 136, 0.4)' : 'rgba(255, 68, 68, 0.4)';
                if (Array.isArray(chart.data.datasets[4].backgroundColor)) {
                    chart.data.datasets[4].backgroundColor.push(lastColor);
                }
            }

            // Auto-scroll si no está congelado
            if (!State.frozen.isFrozen) {
                const scrollInput = document.getElementById('chartScroll');
                if (scrollInput) scrollInput.value = 100;
            }

            // Rendimiento: Renderizado con Throttle
            const now = performance.now();
            if (now - lastChartRender >= CONFIG.CHART_THROTTLE_MS) {
                if (pendingChartFrame) cancelAnimationFrame(pendingChartFrame);
                pendingChartFrame = requestAnimationFrame(() => {
                    updateChart();
                    lastChartRender = performance.now();
                    pendingChartFrame = null;
                });
            }
        });

        connection.on('anomalyDetected', data => {
            console.log('[SignalR] 🚨 anomalyDetected:', { type: data.option_type, strike: data.strike });
            const arr = data.option_type === 'PUT' ? State.anomalies.puts : State.anomalies.calls;
            arr.unshift(data);
            if (arr.length > 5) arr.pop();
            updateUI.anomalies();
            // Solo persistimos en localStorage para el panel
            Storage.saveAnomalies({ calls: State.anomalies.calls, puts: State.anomalies.puts });
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

        // ✅ CORRECCIÓN: Inyectamos los puntos al gráfico. 
        // updateChart() por sí solo no dibuja los puntos, solo mueve los ejes.
        if (chart) {
            chart.data.datasets[0].data = State.history.calls.map((v, i) => ({ x: i, y: v }));
            chart.data.datasets[1].data = State.history.puts.map((v, i) => ({ x: i, y: v }));
            chart.data.datasets[2].data = State.history.net.map((v, i) => ({ x: i, y: v }));
            chart.data.datasets[3].data = State.history.spy.map((v, i) => ({ x: i, y: v }));
        }

        updateChart();
        updateUI.metrics();
    }

    // 2. PETICIÓN AL BACKEND (Siempre se ejecuta, no hay 'else')
    // Esto asegura que si el caché es viejo o incompleto, el backend lo actualice.
    if (CONFIG.ENABLE_FLOW_FEATURE) {
        try {
            console.log('[Load] Actualizando datos desde el backend...');
            const data = await fetchWithRetry(ENDPOINTS.FLOW_SNAP);

            if (data?.history) {
                // procesarDatosHistoricos limpia el gráfico y lo rellena de nuevo
                const procesado = procesarDatosHistoricos(data.history);
                console.log('[LoadData] ✅ Flow actualizado del servidor:', procesado);

                if (procesado) {
                    updateChart();
                    updateUI.metrics();
                    updateUI.atm();
                    Storage.saveFlow({ history: State.history });
                }
            }
        } catch (e) {
            console.warn('[Load] Error al pedir el Snap al backend:', e);
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
        if (chart && !State.frozen.isFrozen) {
            updateChart();
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