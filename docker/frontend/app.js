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
    SPY_MARKET_LATEST: `${CONFIG.API}/spymarket/spy_latest`,
    GAMMA_SNAP: `${CONFIG.API}/gamma/gamma_snap`
};

// ==================== ESTADO GLOBAL ====================
const State = {
    history: { time: [], calls: [], puts: [], net: [], spy: [] },
    current: { spy: null, change: null, prevClose: null, atm: { min: null, max: null }, status: 'unknown' },
    anomalies: { calls: [], puts: [] },
    gammaWalls: [],
    market: { isOpen: false, mode: 'snapshot' },
    frozen: { isFrozen: false, start: null, end: null, date: null },
    connection: { isConnected: false, retries: 0 },
    marketEvents: [] // ✅ NUEVO: Almacén para señales de TradingView
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

/**
 * Genera un mapa de tiempo de mercado rígido (Grid).
 * @param {number} endTime - Timestamp Unix (ms) de finalización.
 * @param {number} durationHours - Duración en horas de mercado.
 * @param {number} resolutionSeconds - Resolución en segundos (ej. 15s).
 * @returns {Array<number>} - Array de timestamps (ms) en orden cronológico.
 */
const generateMarketTimeMap = (endTime, durationHours, resolutionSeconds = 15) => {
    const totalSlots = Math.ceil((durationHours * 3600) / resolutionSeconds);
    const grid = [];
    let cursor = new Date(endTime);
    
    // Normalizar cursor al múltiplo más cercano de la resolución para consistencia
    const resMs = resolutionSeconds * 1000;
    cursor = new Date(Math.floor(cursor.getTime() / resMs) * resMs);

    while (grid.length < totalSlots) {
        if (isMarketOpen(toCET(cursor))) {
            grid.push(cursor.getTime());
        }
        
        // Retroceder un slot
        cursor = new Date(cursor.getTime() - resMs);
        
        // Optimización 1: si no es día de trading, saltar al cierre anterior
        if (!isTradingDay(toCET(cursor))) {
            cursor = getLastMarketClose(cursor);
            cursor = new Date(Math.floor(cursor.getTime() / resMs) * resMs);
        }

        // Optimización 2: si es de noche (fuera de horario), saltar al cierre anterior de ese mismo día/día previo
        const currentHours = MARKET_HOURS.getHoursCET(toCET(cursor));
        const hour = toCET(cursor).getHours() + toCET(cursor).getMinutes() / 60;
        if (hour < currentHours.open) {
            cursor = getLastMarketClose(cursor);
            cursor = new Date(Math.floor(cursor.getTime() / resMs) * resMs);
        }
    }

    return grid.reverse(); // Devolver en orden ASC (pasado -> presente)
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
    const totalPoints = State.history.time.length;
    if (totalPoints === 0) return { start: null, end: null };

    // Si está congelado (scroll manual), devolvemos los timestamps de los límites
    if (State.frozen.isFrozen && State.frozen.start !== null) {
        return {
            start: State.history.time[State.frozen.start],
            end: State.history.time[State.frozen.end]
        };
    }

    // Por defecto: Ver los últimos 960 puntos (4 horas si la resolución es 15s)
    const lastIdx = totalPoints - 1;
    const startIdx = Math.max(0, lastIdx - 959);

    return {
        start: State.history.time[startIdx],
        end: State.history.time[lastIdx]
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
* Procesa datos históricos y actualiza State.history usando un Grid Temporal.
* @param {Array} history - Array de snapshots del backend
* @returns {boolean} - true si se procesaron datos
*/
function procesarDatosHistoricos(history) {
    if (!history || history.length === 0) {
        console.warn('[Historic] No hay datos disponibles para sincronizar');
        return false;
    }

    // 1. Definir la ventana de 4h
    let endTs;
    const ahora = toCET();
    
    if (isMarketOpen(ahora)) {
        // En mercado abierto, el ancla es AHORA
        endTs = ahora.getTime();
    } else {
        // En mercado cerrado, el ancla es el último cierre de mercado
        endTs = getLastMarketClose(ahora).getTime();
    }

    // Sincronizar metadatos (ATM/PrevClose) del snapshot
    if (history.length > 0) {
        const lastItem = history[history.length - 1];
        if (lastItem.atm_min && lastItem.atm_max) State.current.atm = { min: lastItem.atm_min, max: lastItem.atm_max };
        if (lastItem.previous_close) State.current.prevClose = lastItem.previous_close;
    }

    // 2. Generar el Grid de 15 segundos para 12 horas (2880 puntos)
    // Esto proporciona "universo" para que el scroll pueda ir hacia atrás
    const timeGrid = generateMarketTimeMap(endTs, 12, 15);
    
    // 3. Crear estructuras temporales para el mapeo
    const gridData = timeGrid.map(ts => ({
        time: ts,
        calls: null,
        puts: null,
        net: null,
        spy: null
    }));

    // 4. Mapear datos del backend al slot más cercano (hacia atrás)
    const resMs = 15000;
    const historyMap = new Map();
    
    history.forEach(item => {
        let ts = typeof item.timestamp === 'number' ? item.timestamp : new Date(item.timestamp).getTime();
        if (ts < 10000000000) ts *= 1000;
        const slotTs = Math.floor(ts / resMs) * resMs;
        historyMap.set(slotTs, item);
    });

    // 5. Rellenar el grid. Si no hay dato, queda como null (gap visual)
    gridData.forEach(slot => {
        const item = historyMap.get(slot.time);
        if (item) {
            slot.calls = (item.cum_call_flow || 0) / 1e6;
            slot.puts = (item.cum_put_flow || 0) / 1e6;
            slot.net = slot.calls - slot.puts;
            slot.spy = (item.spy_price && item.spy_price > 0) ? item.spy_price : null;
        }
    });

    // 6. Actualizar State.history con la estructura rígida del grid
    State.history = {
        time: gridData.map(d => d.time),
        calls: gridData.map(d => d.calls),
        puts: gridData.map(d => d.puts),
        net: gridData.map(d => d.net),
        spy: gridData.map(d => d.spy)
    };

    // 7. Sincronizar datasets del chart
    if (chart) {
        chart.data.labels = State.history.time;
        chart.data.datasets[0].data = State.history.calls;
        chart.data.datasets[1].data = State.history.puts;
        chart.data.datasets[2].data = State.history.net;
        chart.data.datasets[3].data = State.history.spy;
    }

    console.log(`[Sync] Grid de 15s generado: ${State.history.time.length} puntos.`);
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
    const SMOOTH_FACTOR = 0.20; // Ajusta entre 0.05 (muy suave) y 0.3 (rápido)

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
                { label: 'Calls', data: [], borderColor: '#00ff88', backgroundColor: 'rgba(0, 255, 136, 0.15)', fill: true, borderCapStyle: 'round', pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: true, order: 2 },
                { label: 'Puts', data: [], borderColor: '#ff4444', backgroundColor: 'rgba(255, 68, 68, 0.15)', fill: true, borderCapStyle: 'round', pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: true, order: 2 },
                { label: 'Net Flow (NOFA)', data: [], borderColor: '#00d4ff', borderWidth: 2.5, pointStyle: 'circle', tension: 0.1, yAxisID: 'y', spanGaps: true, order: 1 },
                { label: 'SPY', data: [], borderColor: '#ffd700', backgroundColor: '#ffd700', pointStyle: 'circle', borderDash: [2, 2], borderWidth: 1.5, yAxisID: 'yPrice', spanGaps: true, order: 1 }
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
                    type: 'timeseries',
                    grid: { 
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawOnChartArea: true,
                        drawTicks: true
                    },
                    ticks: {
                        source: 'auto', // Cambiar a 'auto' para que Chart.js genere labels limpios
                        align: 'inner',
                        maxRotation: 0,
                        autoSkip: true,
                        color: '#94a3b8',
                        font: { size: 10 },
                        callback: function (value, index, ticks) {
                            // En v3 con source 'auto', ticks[index].value es el timestamp real
                            const ts = ticks[index]?.value;
                            if (!ts) return '';
                            const d = new Date(ts);
                            return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
                        }
                    },
                    time: {
                        unit: 'minute',
                        stepSize: 30, // Forzar visualmente el paso de 30 min
                        displayFormats: {
                            minute: 'HH:mm'
                        }
                    },
                    bounds: 'ticks'
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

    // Vincular Scroll (Lógica de Paneo/Cinta Continua)
    const scrollInput = document.getElementById('chartScroll');
    if (scrollInput) {
        scrollInput.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            const total = State.history.time.length;
            const windowSize = 960; // 4 horas fijas

            if (total <= windowSize) {
                // Si hay menos de 4h, el scroll no hace nada
                State.frozen.isFrozen = false;
                return;
            }

            // Paneo: movemos el inicio de la ventana de 4h sobre el total de datos
            const maxStartIdx = total - windowSize;
            const startIdx = Math.round((val / 100) * maxStartIdx);
            const endIdx = startIdx + windowSize - 1;

            State.frozen.isFrozen = (val < 99); 
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
    if (!w.start) return;

    // 2. AJUSTAR RANGO VISUAL
    chart.options.scales.x.min = w.start;
    chart.options.scales.x.max = w.end;

    // 3. ANOTACIONES
    const annotations = {};

    // A. SEÑALES TRADINGVIEW (NUEVO)
    State.marketEvents.forEach((sig, i) => {
        const ts = sig.timestamp;
        
        // Solo procesar si está en la ventana visible
        if (ts >= w.start && ts <= w.end) {
            // Buscar precio de SPY en ese momento o el más cercano
            // Buscamos el índice en State.history.time más cercano a 'ts'
            const idx = State.history.time.findIndex(t => Math.abs(t - ts) < 16000); // 16s de margen
            
            if (idx !== -1 && State.history.spy[idx]) {
                const spyPrice = State.history.spy[idx];
                const actionLower = sig.action.toLowerCase();
                const isLong = actionLower.includes('long') || actionLower.includes('buy');
                const isExit = actionLower.includes('exit') || actionLower.includes('tp') || actionLower.includes('take');
                
                let color = isLong ? 'rgba(0, 255, 136, 0.9)' : 'rgba(255, 68, 68, 0.9)';
                let label = isLong ? 'BUY' : 'SELL';
                let style = isLong ? 'triangle' : 'rectRot';
                
                if (isExit) {
                    color = 'rgba(0, 212, 255, 0.9)'; // Azul cian para TP
                    label = 'EXIT';
                    style = 'star';
                }

                annotations[`tv_sig_${i}`] = {
                    type: 'point',
                    xValue: ts,
                    yValue: spyPrice,
                    xScaleID: 'x',
                    yScaleID: 'yPrice',
                    backgroundColor: color,
                    borderColor: '#fff',
                    borderWidth: 1,
                    radius: isExit ? 9 : 7,
                    pointStyle: style,
                    rotation: isLong ? 0 : 45,
                    label: {
                        display: true,
                        content: label,
                        backgroundColor: 'rgba(0,0,0,0.6)',
                        color: '#fff',
                        font: { size: 10, weight: 'bold' },
                        yAdjust: isExit ? -25 : (isLong ? -20 : 20),
                        position: 'center'
                    }
                };
            }
        }
    });

    // B. Línea de Cierre Previo
    if (State.current.prevClose) {
        annotations.prevClose = {
            type: 'line', scaleID: 'yPrice', value: State.current.prevClose,
            borderColor: 'rgba(105, 120, 141, 0.4)', borderDash: [5, 5], borderWidth: 1,
            label: { enabled: true, content: `$${formatPrice(State.current.prevClose)}`, position: 'start', backgroundColor: 'rgba(0,0,0,0.5)', color: '#96adcd', font: { size: 10 } }
        };
    }

    // B. LÍNEA DE SESIÓN (bucle original)
    // Buscamos los índices reales para iterar solo sobre los puntos visibles
    const startIdx = State.history.time.indexOf(w.start);
    const endIdx = State.history.time.indexOf(w.end);

    if (startIdx !== -1 && endIdx !== -1) {
        for (let i = Math.max(1, startIdx); i <= endIdx; i++) {
            const d1 = fromUnix(State.history.time[i - 1]);
            const d2 = fromUnix(State.history.time[i]);
            if (d1 && d2 && d1.getDate() !== d2.getDate()) {
                annotations[`session_${i}`] = {
                    type: 'line', scaleID: 'x', value: State.history.time[i],
                    borderColor: 'rgba(0, 212, 255, 0.6)', borderWidth: 2,
                    label: { enabled: true, content: 'NEW SESSION', position: 'start', backgroundColor: '#1a1a2e', color: '#00d4ff', font: { size: 10 } }
                };
            }
        }
    }

    // C. GAMMA WALLS (Top 5 strikes con mayor concentración de gamma)
    const gammaWallsToRender = State.gammaWalls.length > 0 ? State.gammaWalls : [];
    gammaWallsToRender.slice(0, 5).forEach((wall, idx) => {
        if (!wall.strike) return;
        const id = `gamma_wall_${wall.strike}_${idx}`;
        const isCall = wall.type === 'CALL' || wall.type === 'C';  // Acepta ambos formatos
        
        annotations[id] = {
            type: 'line',
            scaleID: 'yPrice',
            value: wall.strike,
            xMin: w.start,
            xMax: w.end,
            borderColor: isCall ? 'rgba(0, 212, 255, 0.6)' : 'rgba(255, 165, 0, 0.6)',  // Cian/Naranja
            borderWidth: 2.5,
            borderDash: [8, 4],  // Línea discontinua
            label: {
                enabled: true,
                content: `🧱 ${wall.strike} (${wall.type})`,  // Muestra P/C como viene del backend
                position: 'end',  // Al final de la línea (derecha)
                backgroundColor: isCall ? 'rgba(0, 80, 120, 0.8)' : 'rgba(120, 60, 0, 0.8)',
                color: '#fff',
                font: { size: 9, weight: 'bold' },
                yAdjust: isCall ? -12 : 12
            }
        };
    });

    // 4. LÓGICA DE ESCALADO AUTOMÁTICO
    if (State.history.spy.length > 0) {
        // Encontrar índices de la ventana visible para escalar los ejes Y
        const startIdx = State.history.time.indexOf(w.start);
        const endIdx = State.history.time.indexOf(w.end);

        if (startIdx !== -1 && endIdx !== -1) {
            const visibleSpy = State.history.spy.slice(startIdx, endIdx + 1).filter(v => v > 0);
            if (visibleSpy.length > 0) {
                const minS = Math.min(...visibleSpy, State.current.prevClose || Infinity);
                const maxS = Math.max(...visibleSpy, State.current.prevClose || 0);
                const pad = (maxS - minS) * 0.15;
                chart.options.scales.yPrice.suggestedMin = minS - pad;
                chart.options.scales.yPrice.suggestedMax = maxS + pad;
            }

            const visibleCalls = State.history.calls.slice(startIdx, endIdx + 1).filter(v => v !== null);
            const visiblePuts = State.history.puts.slice(startIdx, endIdx + 1).filter(v => v !== null);
            const maxFlow = Math.max(...visibleCalls, ...visiblePuts, 1);
            chart.options.scales.y.suggestedMax = maxFlow * 1.2;
        }
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
            DOM.status.textContent = '● ' + (i18n[currentLang]?.statusError || 'ERROR');
            DOM.status.classList.add('disconnected');  // rojo pulse
        }
        else if (!marketOpen) {
            DOM.status.textContent = '● ' + (i18n[currentLang]?.statusDataPaused || 'DATA PAUSED');
            DOM.status.classList.add('data-paused');  // dorado - mercado cerrado
        }
        else if (State.connection.isConnected) {
            DOM.status.textContent = '● ' + (i18n[currentLang]?.statusConnected || 'CONNECTED');
            DOM.status.classList.add('connected');  // verde - todo OK
        }
        else {
            DOM.status.textContent = '● ' + (i18n[currentLang]?.statusConnecting || 'CONNECTING...');
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
            if (!chart || State.frozen.isFrozen) return;
            
            let ts = typeof data.timestamp === 'number' ? data.timestamp : new Date(data.timestamp).getTime();
            if (ts < 10000000000) ts *= 1000;
            
            const resMs = 15000;
            const slotTs = Math.floor(ts / resMs) * resMs;
            
            const spyPrice = (data.spy_price && data.spy_price > 0) ? data.spy_price : null;
            const c = (data.cum_call_flow || 0) / 1e6;
            const p = (data.cum_put_flow || 0) / 1e6;
            const net = c - p;

            const lastIdx = State.history.time.length - 1;
            const lastGridTs = State.history.time[lastIdx];

            if (slotTs === lastGridTs) {
                // Actualizar el slot actual (Rafagas de 2-4s caen aquí)
                State.history.calls[lastIdx] = c;
                State.history.puts[lastIdx] = p;
                State.history.net[lastIdx] = net;
                State.history.spy[lastIdx] = spyPrice;
                
                // Actualizar chart datasets
                chart.data.datasets[0].data[lastIdx] = c;
                chart.data.datasets[1].data[lastIdx] = p;
                chart.data.datasets[2].data[lastIdx] = net;
                chart.data.datasets[3].data[lastIdx] = spyPrice;
            } else if (slotTs > lastGridTs) {
                // Nuevo slot detectado
                const diffMs = slotTs - lastGridTs;
                const gapSlots = Math.floor(diffMs / resMs);

                // Inyectar nulos si hay un gap real de > 15s
                for (let i = 1; i < gapSlots; i++) {
                    const hollowTs = lastGridTs + (i * resMs);
                    // Solo inyectar si el mercado está abierto
                    if (isMarketOpen(toCET(new Date(hollowTs)))) {
                        State.history.time.push(hollowTs);
                        State.history.calls.push(null);
                        State.history.puts.push(null);
                        State.history.net.push(null);
                        State.history.spy.push(null);
                        
                        State.history.time.shift();
                        State.history.calls.shift();
                        State.history.puts.shift();
                        State.history.net.shift();
                        State.history.spy.shift();
                    }
                }

                // Añadir el nuevo slot
                State.history.time.push(slotTs);
                State.history.calls.push(c);
                State.history.puts.push(p);
                State.history.net.push(net);
                State.history.spy.push(spyPrice);

                // Mantener ventana histórica (e.g., 12h = 2880 puntos)
                while (State.history.time.length > 2880) {
                    State.history.time.shift();
                    State.history.calls.shift();
                    State.history.puts.shift();
                    State.history.net.shift();
                    State.history.spy.shift();
                }

                // Sincronizar chart completo para este caso
                chart.data.labels = State.history.time;
                chart.data.datasets[0].data = State.history.calls;
                chart.data.datasets[1].data = State.history.puts;
                chart.data.datasets[2].data = State.history.net;
                chart.data.datasets[3].data = State.history.spy;
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

        connection.on('tvSignal', data => {
            console.log('[SignalR] 🚩 tvSignal:', data);
            
            // Estandarizar timestamp de segundos a milisegundos si es necesario
            let ts = data.timestamp;
            if (ts < 10000000000) ts *= 1000;
            data.timestamp = ts;

            State.marketEvents.push(data);
            
            // Limitar memoria (mantener últimos 100)
            if (State.marketEvents.length > 100) State.marketEvents.shift();

            // Forzar renderizado
            if (chart) updateChart();
        });

        // ✅ PRESSURE UPDATE - Activado
        connection.on('gammaUpdate', data => {
            console.log('[SignalR] 🌡️ gammaUpdate:', data);
            updateGammaMetrics(data);
            
            // Actualizar gamma walls si vienen en el payload
            if (data.gamma_walls && Array.isArray(data.gamma_walls)) {
                State.gammaWalls = data.gamma_walls;
                if (chart && !State.frozen.isFrozen) updateChart();
            }
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
            // Sincronizar con el formato de la escala timeseries
            chart.data.labels = State.history.time;
            chart.data.datasets[0].data = State.history.calls;
            chart.data.datasets[1].data = State.history.puts;
            chart.data.datasets[2].data = State.history.net;
            chart.data.datasets[3].data = State.history.spy;
        }

        updateChart();
        updateUI.metrics();
    }

    // 2. PETICIÓN AL BACKEND (Siempre se ejecuta, no hay 'else')
    // ✅ OPTIMIZACIÓN: Llamadas paralelas con Promise.allSettled
    console.log('[LoadData] 🚀 Iniciando carga paralela de endpoints...');
    
    if (CONFIG.ENABLE_FLOW_FEATURE) {
        try {
            const [flowResult, anomaliesResult, eventsResult, gammaResult] = await Promise.allSettled([
                fetchWithRetry(ENDPOINTS.FLOW_SNAP),
                fetchWithRetry(ENDPOINTS.ANOMALIES_SNAP),
                fetchWithRetry(`${CONFIG.API}/api/market-events?limit=50`),
                fetchWithRetry(ENDPOINTS.GAMMA_SNAP + '?limit=1')
            ]);
            
            // 1️⃣ Procesar FLOW
            if (flowResult.status === 'fulfilled') {
                const data = flowResult.value;
                if (data?.history) {
                    const procesado = procesarDatosHistoricos(data.history);
                    console.log('[Flow] ✅ Actualizado:', procesado);
                    if (procesado) {
                        updateChart();
                        updateUI.metrics();
                        updateUI.atm();
                        Storage.saveFlow({ history: State.history });
                        
                        const scrollInput = document.getElementById('chartScroll');
                        if (scrollInput && State.history.time.length > 0) {
                            scrollInput.value = 100;
                            State.frozen.isFrozen = false;
                            updateChart();
                            console.log('[Flow] 📍 Scroll reseteado');
                        }
                    }
                }
            } else {
                console.warn('[Flow] ❌ Error:', flowResult.reason);
            }
            
            // 2️⃣ Procesar ANOMALIES
            if (anomaliesResult.status === 'fulfilled') {
                const anomaliesData = anomaliesResult.value;
                if (anomaliesData?.anomalies && anomaliesData.anomalies.length > 0) {
                    const calls = anomaliesData.anomalies.filter(a => a.option_type === 'CALL').slice(0, 5);
                    const puts = anomaliesData.anomalies.filter(a => a.option_type === 'PUT').slice(0, 5);
                    if (calls.length > 0 || puts.length > 0) {
                        State.anomalies = { calls, puts };
                        updateUI.anomalies();
                        Storage.saveAnomalies({ calls, puts });
                        console.log(`[Anomalies] ✅ ${calls.length} calls, ${puts.length} puts`);
                    }
                }
            } else {
                console.warn('[Anomalies] ❌ Error:', anomaliesResult.reason);
            }
            
            // 3️⃣ Procesar MARKET EVENTS
            if (eventsResult.status === 'fulfilled') {
                const eventData = eventsResult.value;
                if (eventData?.events) {
                    State.marketEvents = eventData.events.map(e => ({
                        timestamp: typeof e.timestamp === 'string' ? new Date(e.timestamp).getTime() : e.timestamp,
                        action: e.action,
                        price: e.price,
                        type: e.option_type || 'N/A'
                    }));
                    console.log(`[MarketEvents] ✅ ${State.marketEvents.length} señales`);
                    if (chart) updateChart();
                }
            } else {
                console.warn('[MarketEvents] ❌ Error:', eventsResult.reason);
            }
            
            // 4️⃣ Procesar GAMMA WALLS
            if (gammaResult.status === 'fulfilled') {
                const gammaData = gammaResult.value;
                if (gammaData?.gamma_metrics && gammaData.gamma_metrics.length > 0) {
                    const latestGamma = gammaData.gamma_metrics[0];
                    State.gammaWalls = latestGamma.gamma_walls || [];
                    console.log(`[GammaWalls] ✅ ${State.gammaWalls.length} walls`);
                    if (chart) updateChart();
                    updateGammaMetrics(latestGamma);
                }
            } else {
                console.warn('[GammaWalls] ❌ Error:', gammaResult.reason);
            }
            
        } catch (e) {
            console.error('[LoadData] ❌ Error en carga paralela:', e);
        }
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

// ==================== PRESSURE GAUGES (APEXCHARTS) ====================
let gauges = { pressure: null, regime: null, magnet: null };

const initPressureGauges = () => {
    const commonConfig = {
        chart: { type: 'radialBar', height: 200, background: 'transparent', offsetY: -10 },
        plotOptions: {
            radialBar: {
                startAngle: -90,
                endAngle: 90,
                hollow: { size: '65%', background: 'transparent' },
                track: { background: '#1f2937', strokeWidth: '100%' },
                dataLabels: {
                    name: { show: false },
                    value: {
                        fontSize: '28px',
                        fontWeight: 700,
                        color: '#fff',
                        offsetY: 5,
                        formatter: function(val) {
                            return ((val / 100) * 2 - 1).toFixed(2);
                        }
                    }
                }
            }
        },
        stroke: { lineCap: 'round' }
    };

    // Gauge 1: Net Gamma Exposure (-1 to +1)
    gauges.netGex = new ApexCharts(document.querySelector('#gauge-net-gex'), {
        ...commonConfig,
        series: [50], // 0 = neutral
        fill: {
            type: 'gradient',
            gradient: {
                shade: 'dark',
                type: 'horizontal',
                colorStops: [
                    { offset: 0, color: '#ff0064', opacity: 1 },
                    { offset: 50, color: '#888888', opacity: 1 },
                    { offset: 100, color: '#00ff88', opacity: 1 }
                ]
            }
        }
    });

    // Gauge 2: Gamma Regime (-1 = short gamma, +1 = long gamma)
    gauges.regime = new ApexCharts(document.querySelector('#gauge-gamma-regime'), {
        ...commonConfig,
        series: [50],
        fill: {
            type: 'gradient',
            gradient: {
                shade: 'dark',
                type: 'horizontal',
                colorStops: [
                    { offset: 0, color: '#58a6ff', opacity: 1 },
                    { offset: 50, color: '#888888', opacity: 1 },
                    { offset: 100, color: '#ff6464', opacity: 1 }
                ]
            }
        }
    });

    // Gauge 3: Strike Pinning Risk (0 = free, 1 = pinned)
    gauges.pinning = new ApexCharts(document.querySelector('#gauge-pinning'), {
        ...commonConfig,
        series: [25],
        plotOptions: {
            radialBar: {
                ...commonConfig.plotOptions.radialBar,
                dataLabels: {
                    name: { show: false },
                    value: {
                        fontSize: '28px',
                        fontWeight: 700,
                        color: '#fff',
                        offsetY: 5,
                        formatter: function(val) {
                            return (val / 100).toFixed(2);
                        }
                    }
                }
            }
        },
        fill: {
            type: 'gradient',
            gradient: {
                shade: 'dark',
                type: 'horizontal',
                colorStops: [
                    { offset: 0, color: '#00ff88', opacity: 1 },
                    { offset: 50, color: '#888888', opacity: 1 },
                    { offset: 100, color: '#ff0064', opacity: 1 }
                ]
            }
        }
    });

    gauges.netGex.render();
    gauges.regime.render();
    gauges.pinning.render();

    console.log('[Gauges] Inicializados');
};

// ==================== COMPOSITE SENTIMENT CALCULATION ====================
const calculateSentiment = (data) => {
    const { net_gex, gamma_regime, net_flow, pinning_risk, gamma_walls } = data;
    
    // HIGH CONVICTION BULLISH (short gamma + high call flow)
    if (net_gex > 0.5 && gamma_regime < -0.3 && net_flow > 3_000_000) {
        return {
            text: i18n[currentLang]?.signalBullishStrong || 'BULLISH STRONG',
            desc: i18n[currentLang]?.descBullishStrong || 'High call flow + Short gamma regime → Market amplifies upward moves',
            class: 'bullish-strong'
        };
    }
    
    // HIGH CONVICTION BEARISH (short gamma + high put flow)
    if (net_gex < -0.5 && gamma_regime < -0.3 && net_flow < -3_000_000) {
        return {
            text: i18n[currentLang]?.signalBearishStrong || 'BEARISH STRONG',
            desc: i18n[currentLang]?.descBearishStrong || 'High put flow + Short gamma regime → Market amplifies downward moves',
            class: 'bearish-strong'
        };
    }
    
    // PINNING ALERT (supera sentimiento direccional)
    if (pinning_risk > 0.7 && gamma_walls && gamma_walls.length > 0) {
        const topWall = gamma_walls[0];
        const currentPrice = State?.current?.spy || 0;
        const wallTypeKey = (topWall.type === 'C' || topWall.type === 'CALL') ? 'resistance' : 'support';
        const wallType = i18n[currentLang]?.[wallTypeKey] || wallTypeKey;
        
        let desc = '';
        if (currentPrice > 0 && topWall.distance < 0.5) {
            // Precio MUY CERCA (<.50) → Magnetismo activo
            const template = i18n[currentLang]?.descPinningClose || 'Price pinned at {strike} {type} → Active magnetism';
            desc = template.replace('{strike}', topWall.strike).replace('{type}', wallType);
        } else if (currentPrice > 0) {
            // Precio LEJOS → Wall existe pero no está actuando
            const distancePct = ((topWall.distance / currentPrice) * 100).toFixed(2);
            const template = i18n[currentLang]?.descPinningFar || 'Strong {type} at {strike} → {distance} away ({pct}%)';
            desc = template
                .replace('{type}', wallType)
                .replace('{strike}', topWall.strike)
                .replace('{distance}', topWall.distance.toFixed(2))
                .replace('{pct}', distancePct);
        } else {
            // Fallback si no hay precio actual
            const template = i18n[currentLang]?.descPinningFallback || 'High gamma concentration at {strike}';
            desc = template.replace('{strike}', topWall.strike);
        }
        
        return {
            text: i18n[currentLang]?.signalPinningZone || '🧲 PINNING ZONE',
            desc: desc,
            class: 'pinning'
        };
    }
    
    // LONG GAMMA STABILIZATION (dealers contain moves)
    if (gamma_regime > 0.5) {
        return {
            text: i18n[currentLang]?.signalLongGamma || 'LONG GAMMA',
            desc: i18n[currentLang]?.descLongGamma || 'Dealers stabilize price → Expect range-bound behavior',
            class: 'long-gamma'
        };
    }
    
    // MODERATE BULLISH
    if (net_gex > 0.3) {
        return {
            text: i18n[currentLang]?.signalLongBias || 'LONG BIAS',
            desc: i18n[currentLang]?.descLongBias || 'Moderate bullish gamma exposure → Trending conditions',
            class: ''
        };
    }
    
    // MODERATE BEARISH
    if (net_gex < -0.3) {
        return {
            text: i18n[currentLang]?.signalShortBias || 'SHORT BIAS',
            desc: i18n[currentLang]?.descShortBias || 'Moderate bearish gamma exposure → Trending conditions',
            class: 'bearish'
        };
    }
    
    // NEUTRAL (default)
    return {
        text: i18n[currentLang]?.signalNeutral || 'NEUTRAL',
        desc: i18n[currentLang]?.descNeutral || 'Balanced gamma conditions → No clear directional bias',
        class: 'neutral'
    };
};
const updateGammaMetrics = (data) => {
    if (!gauges.netGex || !data) return;
    lastGammaMetrics = data; // Guardar para re-renderizar al cambiar idioma

    // Convert -1/+1 values to 0-100 scale for ApexCharts
    const netGexVal = ((data.net_gex || 0) + 1) / 2 * 100;
    const regimeVal = ((data.gamma_regime || 0) + 1) / 2 * 100;
    const pinningVal = (data.pinning_risk || 0) * 100;

    // Update gauges
    gauges.netGex.updateSeries([netGexVal]);
    gauges.regime.updateSeries([regimeVal]);
    gauges.pinning.updateSeries([pinningVal]);

    // Update badges
    const netGexBadge = document.getElementById('net-gex-badge');
    const regimeBadge = document.getElementById('gamma-regime-badge');
    const pinningBadge = document.getElementById('pinning-badge');

    if (netGexBadge) {
        netGexBadge.className = 'gauge-badge';
        if (data.net_gex > 0.3) {
            netGexBadge.textContent = i18n[currentLang]?.badgeBullish || 'BULLISH';
            netGexBadge.classList.add('bullish');
        } else if (data.net_gex < -0.3) {
            netGexBadge.textContent = i18n[currentLang]?.badgeBearish || 'BEARISH';
            netGexBadge.classList.add('bearish');
        } else {
            netGexBadge.textContent = i18n[currentLang]?.badgeNeutral || 'NEUTRAL';
        }
    }

    if (regimeBadge) {
        regimeBadge.className = 'gauge-badge';
        if (data.gamma_regime < -0.3) {
            regimeBadge.textContent = i18n[currentLang]?.badgeShortGamma || 'SHORT GAMMA';
            regimeBadge.classList.add('short-gamma');
        } else {
            regimeBadge.textContent = i18n[currentLang]?.badgeLongGamma || 'LONG GAMMA';
            regimeBadge.classList.add('long-gamma');
        }
    }

    if (pinningBadge) {
        pinningBadge.className = 'gauge-badge';
        if (data.pinning_risk > 0.7) {
            pinningBadge.textContent = i18n[currentLang]?.badgeHigh || 'HIGH';
            pinningBadge.classList.add('high');
        } else if (data.pinning_risk > 0.4) {
            pinningBadge.textContent = i18n[currentLang]?.badgeMedium || 'MEDIUM';
        } else {
            pinningBadge.textContent = i18n[currentLang]?.badgeLow || 'LOW';
            pinningBadge.classList.add('low');
        }
    }
    
    // Update footers dinámicamente según badges (usando i18n)
    const netGexFooter = document.getElementById('net-gex-footer');
    const regimeFooter = document.getElementById('gamma-regime-footer');
    const pinningFooterEl = document.getElementById('pinning-footer');

    if (netGexFooter && netGexBadge) {
        const footerKeys = {
            'BULLISH': 'footerNetGexBullish',
            'BEARISH': 'footerNetGexBearish',
            'NEUTRAL': 'footerNetGexNeutral',
            'ALCISTA': 'footerNetGexBullish',
            'BAJISTA': 'footerNetGexBearish'
        };
        const key = footerKeys[netGexBadge.textContent] || 'footerNetGexNeutral';
        netGexFooter.textContent = i18n[currentLang]?.[key] || i18n.en[key];
    }

    if (regimeFooter && regimeBadge) {
        const footerKeys = {
            'SHORT GAMMA': 'footerRegimeShort',
            'LONG GAMMA': 'footerRegimeLong',
            'GAMMA CORTO': 'footerRegimeShort',
            'GAMMA LARGO': 'footerRegimeLong'
        };
        const key = footerKeys[regimeBadge.textContent] || 'footerRegimeShort';
        regimeFooter.textContent = i18n[currentLang]?.[key] || i18n.en[key];
    }

    if (pinningFooterEl && pinningBadge) {
        const footerKeys = {
            'HIGH': 'footerPinningHigh',
            'MEDIUM': 'footerPinningMedium',
            'LOW': 'footerPinningLow',
            'ALTO': 'footerPinningHigh',
            'MEDIO': 'footerPinningMedium',
            'BAJO': 'footerPinningLow'
        };
        const key = footerKeys[pinningBadge.textContent] || 'footerPinningLow';
        pinningFooterEl.textContent = i18n[currentLang]?.[key] || i18n.en[key];
    }

    // Update signal banner with Composite Sentiment
    const signalBanner = document.querySelector('.signal-banner');
    const signalText = document.getElementById('signal-text');
    const signalDesc = document.getElementById('signal-desc');

    if (signalBanner && signalText && signalDesc) {
        const sentiment = calculateSentiment(data);
        
        signalBanner.className = 'signal-banner';
        if (sentiment.class) {
            signalBanner.classList.add(sentiment.class);
        }
        
        signalText.textContent = sentiment.text;
        signalDesc.textContent = sentiment.desc;
    }

    // Update gamma walls table
    if (data.gamma_walls && Array.isArray(data.gamma_walls)) {
        const tbody = document.getElementById('gamma-walls-tbody');
        if (tbody) {
            tbody.innerHTML = data.gamma_walls.slice(0, 5).map(s => {
                const typeDisplay = (s.type === 'C' || s.type === 'CALL') ? 'CALL' : 'PUT';
                return `
                <tr>
                    <td>${formatPrice(s.strike)}</td>
                    <td><span class="strike-type-${s.type.toLowerCase()}">${typeDisplay}</span></td>
                    <td style="color: #aaa;">${s.distance > 0 ? '+' : ''}${formatPrice(s.distance)}</td>
                    <td>${s.volume || 0}</td>
                    <td><span style="color: ${s.score > 1000000 ? '#ff6464' : s.score > 500000 ? '#ffa500' : '#888'}; font-weight: 600;">${(s.score / 1000).toFixed(0)}K</span></td>
                </tr>
            `;
            }).join('');
        }
    }
};

// ==================== INICIALIZACIÓN ====================
const start = async () => {
    console.log('[App] Starting...');
    console.log('[App] 💡 TIP: If you see an old version, use Ctrl+F5 to clear browser cache.');
    
    // ===== ACTUALIZAR UI =====
    updateUI.status();
    updateUI.clocks();
    setInterval(updateUI.clocks, 1000);

    initChart();
    initCrosshair();
    initPressureGauges();    await loadData();
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
        // Range info
        monitoredRange: "Monitored Range",
        maxStrike: "Max Strike",
        minStrike: "Min Strike",
        
        // Chart & Alerts
        chartTitle: "📊 Real-Time Signed Premium Flow",
        alertsTitle: "🚨 Detected Anomaly Alerts",
        
        // Confronted View
        confrontedView: "⚡ CONFRONTED VIEW - 7 Strikes Around ATM",
        
        // Table headers
        strike: "Strike",
        type: "Type",
        price: "Price",
        volume: "Volume",
        distance: "Distance",
        score: "Score",
        bidVol: "Bid Vol",
        askVol: "Ask Vol",
        totalVol: "Total Vol",
        
        // Gauge titles
        netGexTitle: "Net Gamma Exposure",
        gammaRegimeTitle: "Gamma Regime",
        pinningRiskTitle: "Pinning Risk",
        gammaWallsTitle: "⚡ Gamma Walls (Top 5)",
        

        // Status banner
        statusError: "ERROR",
        statusDataPaused: "DATA PAUSED",
        statusConnected: "CONNECTED",
        statusConnecting: "CONNECTING...",
        // Gauge badges
        badgeBullish: "BULLISH",
        badgeBearish: "BEARISH",
        badgeNeutral: "NEUTRAL",
        badgeShortGamma: "SHORT GAMMA",
        badgeLongGamma: "LONG GAMMA",
        badgeHigh: "HIGH",
        badgeMedium: "MEDIUM",
        badgeLow: "LOW",
        
        // Gauge footers (dynamic)
        footerNetGexBullish: "Strong call positioning - dealers absorb selling pressure",
        footerNetGexBearish: "Strong put positioning - dealers absorb buying pressure",
        footerNetGexNeutral: "Balanced dealer positioning across strikes",
        footerRegimeShort: "Dealer positioning: short gamma amplifies moves",
        footerRegimeLong: "Dealer positioning: long gamma stabilizes price",
        footerPinningHigh: "High gamma concentration - strong price magnetism",
        footerPinningMedium: "Moderate gamma concentration - some price attraction",
        footerPinningLow: "Price free to move, low gamma concentration",
        
        // Signal banner texts
        signalBullishStrong: "BULLISH STRONG",
        signalBearishStrong: "BEARISH STRONG",
        signalPinningZone: "🧲 PINNING ZONE",
        signalLongGamma: "LONG GAMMA",
        signalLongBias: "LONG BIAS",
        signalShortBias: "SHORT BIAS",
        signalNeutral: "NEUTRAL",
        
        // Signal descriptions
        descBullishStrong: "High call flow + Short gamma regime → Market amplifies upward moves",
        descBearishStrong: "High put flow + Short gamma regime → Market amplifies downward moves",
        descLongGamma: "Dealers stabilize price → Expect range-bound behavior",
        descLongBias: "Moderate bullish gamma exposure → Trending conditions",
        descShortBias: "Moderate bearish gamma exposure → Trending conditions",
        descNeutral: "Balanced gamma conditions → No clear directional bias",
        descPinningClose: "Price pinned at {strike} {type} → Active magnetism",
        descPinningFar: "Strong {type} at {strike} → {distance} away ({pct}%)",
        descPinningFallback: "High gamma concentration at {strike}",
        
        // Wall types
        resistance: "resistance",
        support: "support"
    },
    es: {
        // Range info
        monitoredRange: "Rango Monitoreado",
        maxStrike: "Strike Máximo",
        minStrike: "Strike Mínimo",
        
        // Chart & Alerts
        chartTitle: "📊 Flujo de Primas en Tiempo Real",
        alertsTitle: "🚨 Alertas de Anomalías Detectadas",
        
        // Confronted View
        confrontedView: "⚡ VISTA CONFRONTADA - 7 Strikes Alrededor del ATM",
        
        // Table headers
        strike: "Strike",
        type: "Tipo",
        price: "Precio",
        volume: "Volumen",
        distance: "Distancia",
        score: "Puntuación",
        bidVol: "Vol Bid",
        askVol: "Vol Ask",
        totalVol: "Vol Total",
        
        // Gauge titles
        netGexTitle: "Exposición Gamma Neta",
        gammaRegimeTitle: "Régimen Gamma",
        pinningRiskTitle: "Riesgo de Anclaje",
        gammaWallsTitle: "⚡ Muros Gamma (Top 5)",
        

        // Status banner
        statusError: "ERROR",
        statusDataPaused: "DATOS PAUSADOS",
        statusConnected: "CONECTADO",
        statusConnecting: "CONECTANDO...",
        // Gauge badges
        badgeBullish: "ALCISTA",
        badgeBearish: "BAJISTA",
        badgeNeutral: "NEUTRAL",
        badgeShortGamma: "GAMMA CORTO",
        badgeLongGamma: "GAMMA LARGO",
        badgeHigh: "ALTO",
        badgeMedium: "MEDIO",
        badgeLow: "BAJO",
        
        // Gauge footers (dynamic)
        footerNetGexBullish: "Fuerte posicionamiento en calls - dealers absorben presión vendedora",
        footerNetGexBearish: "Fuerte posicionamiento en puts - dealers absorben presión compradora",
        footerNetGexNeutral: "Posicionamiento equilibrado de dealers entre strikes",
        footerRegimeShort: "Posicionamiento dealer: gamma corto amplifica movimientos",
        footerRegimeLong: "Posicionamiento dealer: gamma largo estabiliza precio",
        footerPinningHigh: "Alta concentración gamma - fuerte magnetismo de precio",
        footerPinningMedium: "Concentración gamma moderada - alguna atracción de precio",
        footerPinningLow: "Precio libre para moverse, baja concentración gamma",
        
        // Signal banner texts
        signalBullishStrong: "ALCISTA FUERTE",
        signalBearishStrong: "BAJISTA FUERTE",
        signalPinningZone: "🧲 ZONA ANCLAJE",
        signalLongGamma: "GAMMA LARGO",
        signalLongBias: "SESGO ALCISTA",
        signalShortBias: "SESGO BAJISTA",
        signalNeutral: "NEUTRAL",
        
        // Signal descriptions
        descBullishStrong: "Alto flujo calls + Régimen gamma corto → Mercado amplifica movimientos alcistas",
        descBearishStrong: "Alto flujo puts + Régimen gamma corto → Mercado amplifica movimientos bajistas",
        descLongGamma: "Dealers estabilizan precio → Esperar comportamiento lateral",
        descLongBias: "Exposición gamma alcista moderada → Condiciones de tendencia",
        descShortBias: "Exposición gamma bajista moderada → Condiciones de tendencia",
        descNeutral: "Condiciones gamma equilibradas → Sin sesgo direccional claro",
        descPinningClose: "Precio anclado en {strike} {type} → Magnetismo activo",
        descPinningFar: "{type} fuerte en {strike} → {distance} de distancia ({pct}%)",
        descPinningFallback: "Alta concentración gamma en {strike}",
        
        // Wall types
        resistance: "resistencia",
        support: "soporte"
    }
};
let currentLang = localStorage.getItem('preferredLanguage') || 'en';
let lastGammaMetrics = null; // Guardar últimos datos para re-render al cambiar idioma

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
    
    // Re-actualizar badges y footers con el nuevo idioma
    const latestData = lastGammaMetrics || State?.current?.gammaMetrics;
    if (latestData) {
        updateGammaMetrics(latestData);
    updateUI.status(); // Re-traducir status banner
    }
};

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();
