// UI Element Selectors
const statusText = document.getElementById('status-text');
const statusIndicator = document.getElementById('status-indicator');
const btnToggleBot = document.getElementById('btn-toggle-bot');

const portfolioValue = document.getElementById('portfolio-value');
const portfolioCash = document.getElementById('portfolio-cash');
const portfolioUpdated = document.getElementById('portfolio-updated');

const positionsTbody = document.getElementById('positions-tbody');
const pendingOrdersTbody = document.getElementById('pending-orders-tbody');
const tradesTbody = document.getElementById('trades-tbody');
const taxTbody = document.getElementById('tax-tbody');

const consoleLogs = document.getElementById('console-logs');

const taxNetGain = document.getElementById('tax-net-gain');
const taxDividends = document.getElementById('tax-dividends');
const taxWithholdings = document.getElementById('tax-withholdings');

const configForm = document.getElementById('config-form');

// Form Input Selectors
const inputKeyId = document.getElementById('alpaca-key-id');
const inputSecretKey = document.getElementById('alpaca-secret-key');
const selectEnv = document.getElementById('alpaca-env');
const selectOrderType = document.getElementById('order-type');
const inputSymbols = document.getElementById('trading-symbols');
const selectScan = document.getElementById('dynamic-scan');
const selectScanIndex = document.getElementById('dynamic-scan-index');
const inputLimit = document.getElementById('dynamic-limit');
const inputBuyThresh = document.getElementById('buy-threshold');
const inputSellThresh = document.getElementById('sell-threshold');
const inputRefresh = document.getElementById('refresh-secs');
const inputReanalyze = document.getElementById('reanalyze-mins');
const inputMaxPos = document.getElementById('max-pos-pct');
const inputDailyLoss = document.getElementById('daily-loss-pct');

// State holding
let botRunningState = 'stopped';
let pollingInterval = null;
let balanceChart = null;
let rawHistoryData = [];
let activeChartRange = 'all';

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    // Tabs Navigation Trigger
    const tabs = document.querySelectorAll('.tab-link');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab-link').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            const contentId = tab.dataset.tab;
            const contentEl = document.getElementById(contentId);
            if (contentEl) contentEl.classList.add('active');
        });
    });

    initBalanceChart();
    loadConfig();
    updateDashboard();
    
    // Poll data every 5 seconds
    setInterval(updateDashboard, 5000);
    // Poll logs every 2 seconds
    setInterval(pollLogs, 2000);
    
    // Add event listeners
    btnToggleBot.addEventListener('click', toggleBotState);
    configForm.addEventListener('submit', saveConfig);
});

// Fetch active config and pre-fill form
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        if (!res.ok) throw new Error("Failed to fetch configuration");
        const config = await res.json();
        
        inputKeyId.value = config.ALPACA_API_KEY_ID || '';
        inputSecretKey.value = config.ALPACA_SECRET_KEY || '';
        selectEnv.value = config.ALPACA_ENV || 'paper';
        selectOrderType.value = config.ORDER_TYPE || 'market';
        inputSymbols.value = config.DEFAULT_TRADING_SYMBOLS || '';
        selectScan.value = config.DYNAMIC_SCAN || 'False';
        selectScanIndex.value = config.DYNAMIC_SCAN_INDEX || 'SP500';
        inputLimit.value = config.DYNAMIC_STOCK_LIMIT || '15';
        inputBuyThresh.value = config.BUY_THRESHOLD || '0.25';
        inputSellThresh.value = config.SELL_THRESHOLD || '-0.25';
        inputRefresh.value = config.PORTFOLIO_REFRESH_SECS || '15';
        inputReanalyze.value = config.REANALYZE_INTERVAL_MINS || '60';
        inputMaxPos.value = config.MAX_POSITION_SIZE_PCT || '0.10';
        inputDailyLoss.value = config.DAILY_LOSS_LIMIT_PCT || '0.02';
        
    } catch (err) {
        appendLog(`[ERROR Web] No se pudo cargar la configuración: ${err.message}`, 'error-log');
    }
}

// Save config handler
async function saveConfig(e) {
    e.preventDefault();
    
    const configData = {
        ALPACA_API_KEY_ID: inputKeyId.value.trim(),
        ALPACA_SECRET_KEY: inputSecretKey.value.trim(),
        ALPACA_ENV: selectEnv.value,
        ORDER_TYPE: selectOrderType.value,
        DEFAULT_TRADING_SYMBOLS: inputSymbols.value.trim(),
        DYNAMIC_SCAN: selectScan.value,
        DYNAMIC_SCAN_INDEX: selectScanIndex.value,
        DYNAMIC_STOCK_LIMIT: inputLimit.value,
        BUY_THRESHOLD: inputBuyThresh.value,
        SELL_THRESHOLD: inputSellThresh.value,
        PORTFOLIO_REFRESH_SECS: inputRefresh.value,
        REANALYZE_INTERVAL_MINS: inputReanalyze.value,
        MAX_POSITION_SIZE_PCT: inputMaxPos.value,
        DAILY_LOSS_LIMIT_PCT: inputDailyLoss.value
    };
    
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        const resData = await res.json();
        if (res.ok) {
            alert('Configuración guardada correctamente.');
            appendLog(`[Sistema] Configuración del archivo .env guardada correctamente.`, 'success-log');
        } else {
            alert(`Error al guardar: ${resData.message}`);
        }
    } catch (err) {
        alert(`Error al guardar configuración: ${err.message}`);
    }
}

// Start / Stop Bot Handler
async function toggleBotState() {
    const action = botRunningState === 'running' ? 'stop' : 'start';
    
    btnToggleBot.disabled = true;
    btnToggleBot.innerText = action === 'start' ? 'Iniciando...' : 'Deteniendo...';
    
    try {
        const res = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        
        const data = await res.json();
        if (res.ok) {
            appendLog(`[Sistema] Bot cambiado de estado a: ${action.toUpperCase()}`, 'success-log');
            updateDashboardState(action === 'start' ? 'running' : 'stopped');
        } else {
            alert(`Error: ${data.message}`);
            // Revert state button text
            updateDashboardState(botRunningState);
        }
    } catch (err) {
        alert(`Error de red al alternar el bot: ${err.message}`);
        updateDashboardState(botRunningState);
    } finally {
        btnToggleBot.disabled = false;
    }
}

// Sync UI Status Lights
function updateDashboardState(status) {
    botRunningState = status;
    
    if (status === 'running') {
        statusIndicator.className = 'status-indicator running';
        statusText.innerText = 'Ejecutando';
        btnToggleBot.className = 'btn btn-primary stop';
        btnToggleBot.innerText = 'Detener Bot';
    } else {
        statusIndicator.className = 'status-indicator stopped';
        statusText.innerText = 'Detenido';
        btnToggleBot.className = 'btn btn-primary start';
        btnToggleBot.innerText = 'Iniciar Bot';
    }
}

// Fetch dashboard state & updates
async function updateDashboard() {
    try {
        // 1. Fetch Status & Portfolio Values
        const resStatus = await fetch('/api/status');
        if (resStatus.ok) {
            const data = await resStatus.json();
            updateDashboardState(data.bot_status);
            
            const port = data.portfolio;
            portfolioValue.innerText = `$${parseFloat(port.portfolio_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            portfolioCash.innerText = `$${parseFloat(port.cash || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            
            if (port.timestamp) {
                const dt = new Date(port.timestamp);
                portfolioUpdated.innerText = dt.toLocaleTimeString();
            } else {
                portfolioUpdated.innerText = 'Sin datos';
            }
            
            // Build Positions Table
            renderPositions(port.positions || {});
        }
        
        // 1b. Fetch Portfolio History & Returns
        try {
            const resHist = await fetch('/api/portfolio_history');
            if (resHist.ok) {
                const histData = await resHist.json();
                
                // Update raw history data for plotting
                rawHistoryData = histData.history || [];
                renderChartData();
                
                // Update Daily Return Box
                const dailyVal = histData.daily.difference;
                const dailyPct = histData.daily.percentage;
                const dailyEl = document.getElementById('portfolio-daily-return');
                if (dailyEl) {
                    const sign = dailyVal >= 0 ? '+' : '';
                    dailyEl.innerText = `${sign}$${dailyVal.toFixed(2)} (${sign}${dailyPct.toFixed(2)}%)`;
                    dailyEl.className = 'stat-value ' + (dailyVal > 0 ? 'success-log' : (dailyVal < 0 ? 'error-log' : ''));
                }
                
                // Update Global Return Box
                const globalVal = histData.global.difference;
                const globalPct = histData.global.percentage;
                const globalEl = document.getElementById('portfolio-global-return');
                if (globalEl) {
                    const sign = globalVal >= 0 ? '+' : '';
                    globalEl.innerText = `${sign}$${globalVal.toFixed(2)} (${sign}${globalPct.toFixed(2)}%)`;
                    globalEl.className = 'stat-value ' + (globalVal > 0 ? 'success-log' : (globalVal < 0 ? 'error-log' : ''));
                }
            }
        } catch (err) {
            console.error("Portfolio history sync error:", err);
        }
        
        // 2. Fetch Trades Log
        const resTrades = await fetch('/api/trades');
        if (resTrades.ok) {
            const trades = await resTrades.json();
            renderTrades(trades);
        }
        
        // 2a. Fetch Active/Pending Orders
        try {
            const resActiveOrders = await fetch('/api/active_orders');
            if (resActiveOrders.ok) {
                const activeOrders = await resActiveOrders.json();
                renderPendingOrders(activeOrders);
            }
        } catch (err) {
            console.error("Active orders sync error:", err);
        }
        
        // 2b. Fetch Live Broker Orders
        try {
            const resLiveOrders = await fetch('/api/alpaca_orders');
            if (resLiveOrders.ok) {
                const liveOrders = await resLiveOrders.json();
                renderLiveOrders(liveOrders);
            }
        } catch (err) {
            console.error("Live orders sync error:", err);
        }
        
        // 2c. Fetch Strategy Analysis State
        try {
            await updateAnalysisDashboard();
        } catch (err) {
            console.error("Analysis dashboard refresh error:", err);
        }
        
        // 3. Fetch Tax Report
        const resTax = await fetch('/api/tax');
        if (resTax.ok) {
            const tax = await resTax.json();
            renderTaxReport(tax);
        }
        
    } catch (err) {
        console.error("Dashboard synchronization error:", err);
    }
}

// Render Positions Table
function renderPositions(positions) {
    const symbols = Object.keys(positions);
    if (symbols.length === 0) {
        positionsTbody.innerHTML = `<tr><td colspan="5" class="empty-state">No hay posiciones abiertas</td></tr>`;
        return;
    }
    
    positionsTbody.innerHTML = '';
    symbols.forEach(sym => {
        const pos = positions[sym];
        const totalVal = pos.qty * pos.current_price;
        const profitLoss = totalVal - (pos.qty * pos.avg_entry_price);
        const plClass = profitLoss >= 0 ? 'success-log' : 'error-log';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${sym}</strong></td>
            <td>${pos.qty}</td>
            <td>$${formatPrice(pos.avg_entry_price)}</td>
            <td>$${formatPrice(pos.current_price)}</td>
            <td>
                $${formatPrice(totalVal)}
                <span class="${plClass}" style="font-size: 0.75rem; margin-left: 0.5rem; font-weight: bold;">
                    ${profitLoss >= 0 ? '+' : ''}$${formatPrice(profitLoss)}
                </span>
            </td>
        `;
        positionsTbody.appendChild(row);
    });
}

// Render Trades Table
function renderTrades(trades) {
    if (trades.length === 0) {
        tradesTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No hay operaciones registradas</td></tr>`;
        return;
    }
    
    tradesTbody.innerHTML = '';
    trades.forEach(trade => {
        const sideClass = trade.side === 'buy' ? 'success-log' : 'error-log';
        const date = new Date(trade.timestamp).toLocaleString();
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-size: 0.75rem; color: var(--text-secondary);">${date}</td>
            <td><strong>${trade.symbol}</strong></td>
            <td><span class="${sideClass}" style="text-transform: uppercase; font-weight: bold;">${trade.side}</span></td>
            <td>${parseFloat(trade.qty).toFixed(4)}</td>
            <td>${formatPrice(trade.price_eur)} €</td>
            <td>${formatPrice(trade.commission_eur)} €</td>
            <td><strong>${formatPrice(trade.total_eur)} €</strong></td>
        `;
        tradesTbody.appendChild(row);
    });
}

// Render Live Broker Orders Table
function renderLiveOrders(orders) {
    const liveOrdersTbody = document.getElementById('live-orders-tbody');
    if (!liveOrdersTbody) return;
    
    if (orders.length === 0) {
        liveOrdersTbody.innerHTML = `<tr><td colspan="6" class="empty-state">No hay órdenes registradas en Alpaca/Simulador</td></tr>`;
        return;
    }
    
    liveOrdersTbody.innerHTML = '';
    orders.forEach(order => {
        let statusClass = 'system-log';
        if (order.status === 'filled') statusClass = 'success-log';
        else if (order.status === 'canceled' || order.status === 'rejected') statusClass = 'error-log';
        else if (order.status === 'new' || order.status === 'submitted' || order.status === 'accepted') statusClass = 'info-log';
        
        const sideClass = order.side === 'buy' ? 'success-log' : 'error-log';
        const date = order.created_at ? new Date(order.created_at).toLocaleString() : 'N/A';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-size: 0.75rem; color: var(--text-secondary);">${date}</td>
            <td><strong>${order.symbol}</strong></td>
            <td><span class="${sideClass}" style="text-transform: uppercase; font-weight: bold;">${order.side}</span></td>
            <td>${parseFloat(order.qty).toFixed(4)}</td>
            <td>$${formatPrice(order.price)}</td>
            <td><span class="${statusClass}" style="text-transform: uppercase; font-weight: bold;">${order.status}</span></td>
        `;
        liveOrdersTbody.appendChild(row);
    });
}

// Render Pending/Active Orders Table
function renderPendingOrders(orders) {
    if (!pendingOrdersTbody) return;
    
    if (orders.length === 0) {
        pendingOrdersTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No hay órdenes activas o pendientes</td></tr>`;
        return;
    }
    
    pendingOrdersTbody.innerHTML = '';
    orders.forEach(order => {
        let statusClass = 'system-log';
        if (order.status === 'partially_filled') statusClass = 'warning-log';
        else if (order.status === 'new' || order.status === 'submitted' || order.status === 'accepted' || order.status === 'open') statusClass = 'info-log';
        
        const sideClass = order.side === 'buy' ? 'success-log' : 'error-log';
        const date = order.created_at ? new Date(order.created_at).toLocaleString() : 'N/A';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-size: 0.75rem; color: var(--text-secondary);">${date}</td>
            <td><strong>${order.symbol}</strong></td>
            <td><span class="${sideClass}" style="text-transform: uppercase; font-weight: bold;">${order.side}</span></td>
            <td>${parseFloat(order.qty).toFixed(4)}</td>
            <td>${parseFloat(order.filled_qty || 0.0).toFixed(4)}</td>
            <td>$${formatPrice(order.price)}</td>
            <td><span class="${statusClass}" style="text-transform: uppercase; font-weight: bold;">${order.status}</span></td>
        `;
        pendingOrdersTbody.appendChild(row);
    });
}

// Fetch latest strategy analysis evaluations
async function updateAnalysisDashboard() {
    try {
        const res = await fetch('/api/analysis');
        if (res.ok) {
            const data = await res.json();
            
            // Update decision rules headers
            const buyEl = document.getElementById('analysis-buy-threshold');
            const sellEl = document.getElementById('analysis-sell-threshold');
            const updatedEl = document.getElementById('analysis-updated');
            
            if (buyEl) buyEl.innerText = `>= ${parseFloat(data.buy_threshold || 0.25).toFixed(2)}`;
            if (sellEl) sellEl.innerText = `<= ${parseFloat(data.sell_threshold || -0.25).toFixed(2)}`;
            
            if (updatedEl) {
                if (data.timestamp) {
                    const dt = new Date(data.timestamp);
                    updatedEl.innerText = dt.toLocaleString();
                } else {
                    updatedEl.innerText = 'Nunca';
                }
            }
            
            renderAnalysis(data.evaluations || {});
        }
    } catch (err) {
        console.error("Analysis synchronization error:", err);
    }
}

// Render Analysis Table
function renderAnalysis(evaluations) {
    const analysisTbody = document.getElementById('analysis-tbody');
    if (!analysisTbody) return;
    
    const symbols = Object.keys(evaluations);
    if (symbols.length === 0) {
        analysisTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No hay análisis disponibles. Activa el bot para recopilar métricas.</td></tr>`;
        return;
    }
    
    analysisTbody.innerHTML = '';
    symbols.forEach(sym => {
        const ev = evaluations[sym];
        const details = ev.details || {};
        
        // Formulate Sub-Metrics detail labels
        const ta_inds = details.technical_indicators || {};
        const rsiVal = ta_inds.rsi !== undefined ? parseFloat(ta_inds.rsi).toFixed(1) : 'N/A';
        const macdSig = ta_inds.macd_signal || 'N/A';
        
        const fund_mets = details.fundamental_metrics || {};
        const peVal = fund_mets.pe_ratio !== undefined ? parseFloat(fund_mets.pe_ratio).toFixed(1) : 'N/A';
        const dyVal = fund_mets.dividend_yield !== undefined ? `${(parseFloat(fund_mets.dividend_yield)*100).toFixed(1)}%` : 'N/A';
        
        const artCount = details.article_count || 0;
        
        // CSS coloring for recommendation action
        let actionClass = 'neutral-log';
        if (ev.action === 'BUY') actionClass = 'success-log';
        else if (ev.action === 'SELL') actionClass = 'error-log';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${sym}</strong></td>
            <td>$${formatPrice(ev.latest_price)}</td>
            <td>
                <div style="font-weight: bold; color: var(--text-accent);">${parseFloat(details.technical_score || 0).toFixed(2)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">RSI: ${rsiVal} | MACD: ${macdSig}</div>
            </td>
            <td>
                <div style="font-weight: bold; color: var(--text-accent);">${parseFloat(details.fundamental_score || 0).toFixed(2)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">P/E: ${peVal} | Div: ${dyVal}</div>
            </td>
            <td>
                <div style="font-weight: bold; color: var(--text-accent);">${parseFloat(details.sentiment_score || 0).toFixed(2)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">Artículos: ${artCount}</div>
            </td>
            <td><strong>${parseFloat(ev.score || 0).toFixed(2)}</strong></td>
            <td><span class="${actionClass}" style="text-transform: uppercase; font-weight: 800; font-size: 0.9rem;">${ev.action}</span></td>
        `;
        analysisTbody.appendChild(row);
    });
}

// Render Spanish Tax compliance
function renderTaxReport(tax) {
    const summary = tax.summary || {};
    const events = tax.events || [];
    
    const netGains = summary.net_capital_gain_loss_eur || 0;
    taxNetGain.innerText = `${netGains >= 0 ? '+' : ''}${netGains.toFixed(2)} €`;
    taxNetGain.className = `tax-val ${netGains >= 0 ? 'profit' : 'loss'}`;
    
    taxDividends.innerText = `${(summary.total_dividends_received_eur || 0).toFixed(2)} €`;
    taxWithholdings.innerText = `${(summary.total_withholding_tax_paid_eur || 0).toFixed(2)} €`;
    
    if (events.length === 0) {
        taxTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No hay ganancias o pérdidas registradas en FIFO</td></tr>`;
        return;
    }
    
    taxTbody.innerHTML = '';
    events.forEach(ev => {
        const signClass = ev.gain_loss >= 0 ? 'success-log' : 'error-log';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${ev.symbol}</strong></td>
            <td>${ev.buy_date}</td>
            <td>${ev.sell_date}</td>
            <td>${ev.qty.toFixed(4)}</td>
            <td>${ev.acquisition_val.toFixed(2)} €</td>
            <td>${ev.sale_val.toFixed(2)} €</td>
            <td><strong class="${signClass}">${ev.gain_loss >= 0 ? '+' : ''}${ev.gain_loss.toFixed(2)} €</strong></td>
        `;
        taxTbody.appendChild(row);
    });
}

// Poll output logs
async function pollLogs() {
    try {
        const res = await fetch('/api/logs');
        if (res.ok) {
            const logs = await res.json();
            
            // Re-render logs in box
            consoleLogs.innerHTML = '';
            logs.forEach(line => {
                let logClass = 'system-log';
                if (line.includes('INFO')) logClass = 'info-log';
                if (line.includes('WARNING')) logClass = 'warning-log';
                if (line.includes('ERROR') || line.includes('critical')) logClass = 'error-log';
                if (line.includes('Filled') || line.includes('Starting') || line.includes('Finished')) logClass = 'success-log';
                
                const div = document.createElement('div');
                div.className = logClass;
                div.innerText = line.trim();
                consoleLogs.appendChild(div);
            });
            
            // Autoscroll logs box
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
        }
    } catch (err) {
        console.error("Logs sync error:", err);
    }
}

// Manual append helper for immediate feedback
function appendLog(text, logClass = 'system-log') {
    const div = document.createElement('div');
    div.className = logClass;
    div.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
    consoleLogs.appendChild(div);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

// Dynamic price formatting helper based on magnitude and original precision
function formatPrice(val) {
    if (val === undefined || val === null || val === '') return '0.00';
    const num = parseFloat(val);
    if (isNaN(num)) return '0.00';
    if (num === 0) return '0.00';
    
    const str = typeof val === 'string' ? val.trim() : num.toString();
    let rawDecimals = 0;
    const dotIdx = str.indexOf('.');
    if (dotIdx !== -1) {
        if (str.includes('e') || str.includes('E')) {
            const match = str.match(/[eE]([-+]?\d+)/);
            const exp = match ? parseInt(match[1]) : 0;
            if (exp < 0) {
                const coeff = str.split(/[eE]/)[0];
                const coeffDot = coeff.indexOf('.');
                const coeffDec = coeffDot !== -1 ? coeff.length - coeffDot - 1 : 0;
                rawDecimals = Math.abs(exp) + coeffDec;
            }
        } else {
            const cleanStr = str.replace(/[^0-9.]/g, '');
            const cleanDotIdx = cleanStr.indexOf('.');
            if (cleanDotIdx !== -1) {
                rawDecimals = cleanStr.length - cleanDotIdx - 1;
            }
        }
    }
    
    let minDec = 2;
    if (Math.abs(num) < 1) {
        minDec = Math.max(2, Math.min(rawDecimals, 8));
    }
    const maxDec = Math.max(minDec, Math.min(rawDecimals, 8));
    
    return num.toLocaleString(undefined, {
        minimumFractionDigits: minDec,
        maximumFractionDigits: maxDec
    });
}

// Initialize Balance Chart
function initBalanceChart() {
    const ctx = document.getElementById('balance-chart');
    if (!ctx) return;
    
    // Create chart
    balanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Valor de Cartera (USD)',
                data: [],
                borderColor: '#00f0ff',
                borderWidth: 2,
                pointRadius: 1,
                pointHoverRadius: 4,
                backgroundColor: (context) => {
                    const chart = context.chart;
                    const {ctx, chartArea} = chart;
                    if (!chartArea) return null;
                    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                    gradient.addColorStop(0, 'rgba(0, 240, 255, 0.25)');
                    gradient.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
                    return gradient;
                },
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(11, 15, 25, 0.85)',
                    titleColor: '#fff',
                    bodyColor: '#00f0ff',
                    borderColor: 'rgba(0, 240, 255, 0.2)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: 'rgba(255, 255, 255, 0.4)', maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.4)',
                        callback: (value) => `$${value.toLocaleString()}`
                    }
                }
            }
        }
    });

    // Event listeners for filters
    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => {
                b.classList.remove('active');
                b.style.background = '';
                b.style.color = '';
            });
            btn.classList.add('active');
            btn.style.background = 'rgba(0, 240, 255, 0.1)';
            btn.style.color = 'var(--text-accent)';
            
            activeChartRange = btn.dataset.range;
            renderChartData();
        });
    });
}

// Render Chart Data
function renderChartData() {
    if (!balanceChart || rawHistoryData.length === 0) return;
    
    const now = new Date();
    let filtered = [...rawHistoryData];
    
    if (activeChartRange === '1d') {
        const oneDayAgo = now.getTime() - (24 * 60 * 60 * 1000);
        filtered = rawHistoryData.filter(p => new Date(p.timestamp).getTime() >= oneDayAgo);
    } else if (activeChartRange === '1y') {
        const oneYearAgo = now.getTime() - (365 * 24 * 60 * 60 * 1000);
        filtered = rawHistoryData.filter(p => new Date(p.timestamp).getTime() >= oneYearAgo);
    }
    
    // Sort chronologically
    filtered.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    
    // Extract labels and values
    const labels = filtered.map(p => {
        const dt = new Date(p.timestamp);
        if (activeChartRange === '1d') {
            return dt.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        } else {
            return dt.toLocaleDateString([], {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'});
        }
    });
    const values = filtered.map(p => p.portfolio_value);
    
    balanceChart.data.labels = labels;
    balanceChart.data.datasets[0].data = values;
    balanceChart.update();
}
