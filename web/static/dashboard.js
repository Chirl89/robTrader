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
const btnCopyConsole = document.getElementById('btn-copy-console');

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
const inputHistDays = document.getElementById('historical-days');

// State holding
let botRunningState = 'stopped';
let pollingInterval = null;
let balanceChart = null;
let rawHistoryData = [];
let activeChartRange = 'all';
let latestEvaluations = {};

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
    if (btnCopyConsole) {
        btnCopyConsole.addEventListener('click', copyConsoleLogs);
    }

    // Modal Tab Trigger
    const modalTabs = document.querySelectorAll('.modal-tab-link');
    modalTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            switchModalTab(tab.dataset.modalTab);
        });
    });

    // Close Modal Button and Overlay Dismiss
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalOverlay = document.getElementById('analysis-detail-modal');
    if (modalCloseBtn && modalOverlay) {
        const closeModal = () => {
            modalOverlay.classList.remove('active');
        };
        modalCloseBtn.addEventListener('click', closeModal);
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                closeModal();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modalOverlay.classList.contains('active')) {
                closeModal();
            }
        });
    }
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
        inputHistDays.value = config.HISTORICAL_DAYS || '120';
        
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
        HISTORICAL_DAYS: inputHistDays.value,
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
            <td>
                <strong>${sym}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px;" title="${pos.name || ''}">${pos.name || ''}</div>
            </td>
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
            <td>
                <strong>${trade.symbol}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${trade.name || ''}">${trade.name || ''}</div>
            </td>
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
            <td>
                <strong>${order.symbol}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${order.name || ''}">${order.name || ''}</div>
            </td>
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
            <td>
                <strong>${order.symbol}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${order.name || ''}">${order.name || ''}</div>
            </td>
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
            
            latestEvaluations = data.evaluations || {};
            renderAnalysis(latestEvaluations);
        }
    } catch (err) {
        console.error("Analysis synchronization error:", err);
    }
}

function formatScore(val) {
    if (val === undefined || val === null || val === '' || isNaN(parseFloat(val))) return 'ND';
    return parseFloat(val).toFixed(2);
}

function formatVolume(val) {
    if (val === undefined || val === null || val === '' || isNaN(parseFloat(val))) return 'N/A';
    return parseFloat(val).toLocaleString();
}

function formatMarketCap(val) {
    if (val === undefined || val === null || val === '' || isNaN(parseFloat(val))) return 'N/A';
    const num = parseFloat(val);
    if (num >= 1e12) return `${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
    return num.toLocaleString();
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
        const rsiVal = ta_inds.rsi !== undefined && ta_inds.rsi !== null && !isNaN(parseFloat(ta_inds.rsi)) ? parseFloat(ta_inds.rsi).toFixed(1) : 'N/A';
        const macdSig = ta_inds.macd_signal !== undefined && ta_inds.macd_signal !== null ? ta_inds.macd_signal : 'N/A';
        
        const fund_mets = details.fundamental_metrics || {};
        const peVal = fund_mets.pe_ratio !== undefined && fund_mets.pe_ratio !== null && !isNaN(parseFloat(fund_mets.pe_ratio)) ? parseFloat(fund_mets.pe_ratio).toFixed(1) : 'N/A';
        const dyVal = fund_mets.dividend_yield !== undefined && fund_mets.dividend_yield !== null && !isNaN(parseFloat(fund_mets.dividend_yield)) ? `${(parseFloat(fund_mets.dividend_yield)*100).toFixed(1)}%` : 'N/A';
        
        const artCount = details.article_count || 0;
        
        // CSS coloring for recommendation action
        let actionClass = 'neutral-log';
        if (ev.action === 'BUY') actionClass = 'success-log';
        else if (ev.action === 'SELL') actionClass = 'error-log';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <strong>${sym}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px;" title="${ev.name || ''}">${ev.name || ''}</div>
            </td>
            <td>$${formatPrice(ev.latest_price)}</td>
            <td class="clickable-score" onclick="openAnalysisModal('${sym}', 'modal-tech')" title="Hacer clic para ver detalles técnicos">
                <div style="font-weight: bold; color: var(--text-accent);">${formatScore(details.technical_score)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">RSI: ${rsiVal} | MACD: ${macdSig}</div>
            </td>
            <td class="clickable-score" onclick="openAnalysisModal('${sym}', 'modal-fund')" title="Hacer clic para ver detalles fundamentales">
                <div style="font-weight: bold; color: var(--text-accent);">${formatScore(details.fundamental_score)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">P/E: ${peVal} | Div: ${dyVal}</div>
            </td>
            <td class="clickable-score" onclick="openAnalysisModal('${sym}', 'modal-sentiment')" title="Hacer clic para ver noticias y sentimiento">
                <div style="font-weight: bold; color: var(--text-accent);">${formatScore(details.sentiment_score)}</div>
                <div style="font-size: 0.7rem; color: var(--text-secondary);">Artículos: ${artCount}</div>
            </td>
            <td><strong>${formatScore(ev.score)}</strong></td>
            <td><span class="${actionClass}" style="text-transform: uppercase; font-weight: 800; font-size: 0.9rem;">${ev.action}</span></td>
        `;
        analysisTbody.appendChild(row);
    });
}

// Open Modal with analysis details
function openAnalysisModal(symbol, defaultTab) {
    const ev = latestEvaluations[symbol];
    if (!ev) return;
    
    // Set Header titles
    document.getElementById('modal-asset-title').innerText = `${symbol} - ${ev.name || ''}`;
    document.getElementById('modal-asset-subtitle').innerText = `Detalles del análisis y métricas del algoritmo de decisión`;
    
    const details = ev.details || {};
    
    // 1. Technical Tab
    const techScore = details.technical_score;
    const modalTechScoreEl = document.getElementById('modal-tech-score');
    modalTechScoreEl.innerText = formatScore(techScore);
    
    const techInterpretationEl = document.getElementById('modal-tech-interpretation');
    techInterpretationEl.className = 'interpretation-badge';
    if (techScore === undefined || techScore === null) {
        techInterpretationEl.classList.add('badge-neutral');
        techInterpretationEl.innerText = 'ND (Sin datos)';
    } else if (techScore >= 0.25) {
        techInterpretationEl.classList.add('badge-bullish');
        techInterpretationEl.innerText = 'Alcista';
    } else if (techScore <= -0.25) {
        techInterpretationEl.classList.add('badge-bearish');
        techInterpretationEl.innerText = 'Bajista';
    } else {
        techInterpretationEl.classList.add('badge-neutral');
        techInterpretationEl.innerText = 'Neutral';
    }
    
    // Technical table indicators
    const ta_inds = details.technical_indicators || {};
    const techTbody = document.getElementById('modal-tech-tbody');
    techTbody.innerHTML = '';
    
    if (Object.keys(ta_inds).length === 0) {
        techTbody.innerHTML = `<tr><td colspan="3" class="empty-state">No hay indicadores técnicos disponibles para esta ejecución.</td></tr>`;
    } else {
        const indicatorsToRender = [
            {
                name: 'RSI (14 días)',
                val: ta_inds.rsi !== undefined && ta_inds.rsi !== null && !isNaN(parseFloat(ta_inds.rsi)) ? parseFloat(ta_inds.rsi).toFixed(2) : 'N/A',
                cond: getRsiInterpretation(ta_inds.rsi)
            },
            {
                name: 'MACD Histograma',
                val: ta_inds.macd_hist !== undefined && ta_inds.macd_hist !== null && !isNaN(parseFloat(ta_inds.macd_hist)) ? parseFloat(ta_inds.macd_hist).toFixed(4) : 'N/A',
                cond: getMacdInterpretation(ta_inds.macd_hist)
            },
            {
                name: 'Cruce de Medias (EMA 10 vs SMA 50)',
                val: `EMA10: ${ta_inds.ema_10 !== undefined && ta_inds.ema_10 !== null && !isNaN(parseFloat(ta_inds.ema_10)) ? parseFloat(ta_inds.ema_10).toFixed(2) : 'N/A'} / SMA50: ${ta_inds.sma_50 !== undefined && ta_inds.sma_50 !== null && !isNaN(parseFloat(ta_inds.sma_50)) ? parseFloat(ta_inds.sma_50).toFixed(2) : 'N/A'}`,
                cond: getMaInterpretation(ta_inds.ema_10, ta_inds.sma_50)
            },
            {
                name: 'Bandas de Bollinger',
                val: `Cierre: ${ta_inds.close !== undefined && ta_inds.close !== null && !isNaN(parseFloat(ta_inds.close)) ? parseFloat(ta_inds.close).toFixed(2) : 'N/A'} (Banda Inf: ${ta_inds.bb_lower !== undefined && ta_inds.bb_lower !== null && !isNaN(parseFloat(ta_inds.bb_lower)) ? parseFloat(ta_inds.bb_lower).toFixed(2) : 'N/A'} / Sup: ${ta_inds.bb_upper !== undefined && ta_inds.bb_upper !== null && !isNaN(parseFloat(ta_inds.bb_upper)) ? parseFloat(ta_inds.bb_upper).toFixed(2) : 'N/A'})`,
                cond: getBbInterpretation(ta_inds.close, ta_inds.bb_lower, ta_inds.bb_upper)
            }
        ];
        
        indicatorsToRender.forEach(ind => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${ind.name}</strong></td>
                <td>${ind.val}</td>
                <td>${ind.cond}</td>
            `;
            techTbody.appendChild(tr);
        });
    }
    
    // 2. Fundamental Tab
    const fundScore = details.fundamental_score;
    const modalFundScoreEl = document.getElementById('modal-fund-score');
    modalFundScoreEl.innerText = formatScore(fundScore);
    
    const fundInterpretationEl = document.getElementById('modal-fund-interpretation');
    if (fundInterpretationEl) {
        fundInterpretationEl.className = 'interpretation-badge';
        if (fundScore === undefined || fundScore === null) {
            fundInterpretationEl.classList.add('badge-neutral');
            fundInterpretationEl.innerText = 'ND (No Aplicable)';
        } else if (fundScore >= 0.4) {
            fundInterpretationEl.classList.add('badge-bullish');
            fundInterpretationEl.innerText = fundScore >= 0.6 ? 'Fuerte Compra' : 'Compra / Infravalorado';
        } else if (fundScore <= -0.4) {
            fundInterpretationEl.classList.add('badge-bearish');
            fundInterpretationEl.innerText = fundScore <= -0.6 ? 'Fuerte Venta' : 'Venta / Sobrevalorado';
        } else {
            fundInterpretationEl.classList.add('badge-neutral');
            fundInterpretationEl.innerText = 'Neutral';
        }
    }
    
    const fund_mets = details.fundamental_metrics || {};
    const fundTbody = document.getElementById('modal-fund-tbody');
    fundTbody.innerHTML = '';
    
    const hasCorporate = !(
        fund_mets.pe_ratio === undefined && 
        fund_mets.debt_to_equity === undefined && 
        fund_mets.revenue_growth === undefined && 
        fund_mets.profit_margins === undefined
    );
    
    if (!hasCorporate || Object.keys(fund_mets).length === 0) {
        fundTbody.innerHTML = `<tr><td colspan="3" class="empty-state">Métricas corporativas no aplicables a este tipo de activo.</td></tr>`;
    } else {
        const pe = fund_mets.pe_ratio;
        const de = fund_mets.debt_to_equity;
        const growth = fund_mets.revenue_growth;
        const margins = fund_mets.profit_margins;
        const divYield = fund_mets.dividend_yield;
        
        const fundamentalsToRender = [
            {
                name: 'Relación P/E (Precio/Beneficio)',
                val: pe !== undefined && pe !== null && !isNaN(parseFloat(pe)) ? parseFloat(pe).toFixed(2) : 'N/A',
                cond: getPeInterpretation(pe)
            },
            {
                name: 'Deuda sobre Patrimonio (D/E)',
                val: de !== undefined && de !== null && !isNaN(parseFloat(de)) ? `${parseFloat(de).toFixed(2)}%` : 'N/A',
                cond: getDeInterpretation(de)
            },
            {
                name: 'Crecimiento de Ingresos (Anual)',
                val: growth !== undefined && growth !== null && !isNaN(parseFloat(growth)) ? `${(parseFloat(growth)*100).toFixed(2)}%` : 'N/A',
                cond: getGrowthInterpretation(growth)
            },
            {
                name: 'Margen de Beneficio',
                val: margins !== undefined && margins !== null && !isNaN(parseFloat(margins)) ? `${(parseFloat(margins)*100).toFixed(2)}%` : 'N/A',
                cond: getMarginsInterpretation(margins)
            },
            {
                name: 'Rentabilidad por Dividendo (Yield)',
                val: divYield !== undefined && divYield !== null && !isNaN(parseFloat(divYield)) ? `${(parseFloat(divYield)*100).toFixed(2)}%` : 'N/A',
                cond: (divYield !== undefined && divYield !== null && !isNaN(parseFloat(divYield)) && parseFloat(divYield) > 0) ? 'Paga dividendos de forma regular' : 'No paga dividendos'
            }
        ];
        
        fundamentalsToRender.forEach(f => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${f.name}</strong></td>
                <td>${f.val}</td>
                <td>${f.cond}</td>
            `;
            fundTbody.appendChild(tr);
        });
    }
    
    // Render the General / Market Metrics
    const marketTbody = document.getElementById('modal-market-tbody');
    marketTbody.innerHTML = '';
    
    const marketMetricsToRender = [
        {
            name: 'Precio de Cierre Anterior',
            val: fund_mets.previous_close !== undefined && fund_mets.previous_close !== null ? `$${formatPrice(fund_mets.previous_close)}` : 'N/A'
        },
        {
            name: 'Promedio Móvil 50 Días',
            val: fund_mets.fifty_day_average !== undefined && fund_mets.fifty_day_average !== null ? `$${formatPrice(fund_mets.fifty_day_average)}` : 'N/A'
        },
        {
            name: 'Promedio Móvil 200 Días',
            val: fund_mets.two_hundred_day_average !== undefined && fund_mets.two_hundred_day_average !== null ? `$${formatPrice(fund_mets.two_hundred_day_average)}` : 'N/A'
        },
        {
            name: 'Rango de 52 Semanas',
            val: (fund_mets.fifty_two_week_low !== undefined && fund_mets.fifty_two_week_low !== null && fund_mets.fifty_two_week_high !== undefined && fund_mets.fifty_two_week_high !== null) 
                 ? `$${formatPrice(fund_mets.fifty_two_week_low)} - $${formatPrice(fund_mets.fifty_two_week_high)}` 
                 : 'N/A'
        },
        {
            name: 'Volumen Diario',
            val: fund_mets.volume !== undefined && fund_mets.volume !== null ? formatVolume(fund_mets.volume) : 'N/A'
        },
        {
            name: 'Capitalización de Mercado',
            val: fund_mets.market_cap !== undefined && fund_mets.market_cap !== null ? `$${formatMarketCap(fund_mets.market_cap)}` : 'N/A'
        }
    ];
    
    marketMetricsToRender.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${m.name}</strong></td>
            <td>${m.val}</td>
        `;
        marketTbody.appendChild(tr);
    });
    
    // 3. Sentiment Tab
    const sentScore = details.sentiment_score;
    const modalSentScoreEl = document.getElementById('modal-sent-score');
    modalSentScoreEl.innerText = formatScore(sentScore);
    
    const sentInterpretationEl = document.getElementById('modal-sent-interpretation');
    sentInterpretationEl.className = 'interpretation-badge';
    if (sentScore >= 0.15) {
        sentInterpretationEl.classList.add('badge-bullish');
        sentInterpretationEl.innerText = 'Optimista (Bullish)';
    } else if (sentScore <= -0.15) {
        sentInterpretationEl.classList.add('badge-bearish');
        sentInterpretationEl.innerText = 'Pesimista (Bearish)';
    } else {
        sentInterpretationEl.classList.add('badge-neutral');
        sentInterpretationEl.innerText = 'Neutral / Sin Sesgo';
    }
    
    // Render articles
    const newsListEl = document.getElementById('modal-news-list');
    newsListEl.innerHTML = '';
    
    const articles = details.news_articles || [];
    if (articles.length === 0) {
        newsListEl.innerHTML = `<div class="empty-state" style="padding: 1.5rem; text-align: center; border: 1px dashed var(--border-color); border-radius: 8px;">No se registraron artículos en esta ejecución o no hay noticias recientes disponibles.</div>`;
    } else {
        articles.forEach(art => {
            const card = document.createElement('div');
            card.className = 'news-card';
            
            let sentimentText = 'Neutral';
            let sentimentDotClass = 'neutral';
            if (art.sentiment_score >= 0.15) {
                sentimentText = 'Alcista';
                sentimentDotClass = 'positive';
            } else if (art.sentiment_score <= -0.15) {
                sentimentText = 'Bajista';
                sentimentDotClass = 'negative';
            }
            
            const linkHref = art.url ? `href="${art.url}" target="_blank"` : '';
            const externalIcon = art.url ? ' <span style="font-size: 0.8rem; color: var(--text-accent);">↗</span>' : '';
            
            card.innerHTML = `
                <a ${linkHref} class="news-card-title-link" ${!art.url ? 'style="cursor: default; pointer-events: none;"' : ''}>
                    ${art.title || 'Sin Título'}${externalIcon}
                </a>
                <div class="news-card-footer">
                    <div>
                        <span class="sentiment-dot ${sentimentDotClass}"></span>
                        <span>Sentimiento del Artículo: <strong>${art.sentiment_score >= 0 ? '+' : ''}${parseFloat(art.sentiment_score).toFixed(2)}</strong> (${sentimentText})</span>
                    </div>
                    ${art.url ? `<span style="color: var(--text-accent); font-size: 0.8rem;">Abrir noticia</span>` : `<span style="color: var(--text-secondary); font-style: italic; font-size: 0.8rem;">Enlace no disponible</span>`}
                </div>
            `;
            newsListEl.appendChild(card);
        });
    }
    
    // Show Modal
    const modalEl = document.getElementById('analysis-detail-modal');
    modalEl.classList.add('active');
    
    // Switch to specified tab
    switchModalTab(defaultTab || 'modal-tech');
}

// Switch Modal Tab
function switchModalTab(tabId) {
    document.querySelectorAll('.modal-tab-link').forEach(btn => {
        if (btn.dataset.modalTab === tabId) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    document.querySelectorAll('.modal-tab-content').forEach(content => {
        if (content.id === tabId) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });
}

// Expose openAnalysisModal globally for onclick handlers
window.openAnalysisModal = openAnalysisModal;

// Interpretations helpers for technical indicators and fundamentals
function getRsiInterpretation(rsi) {
    if (rsi === undefined || rsi === null || isNaN(rsi)) return 'Sin datos';
    if (rsi < 30) return '<strong class="success-log">Sobreventa (Rebote Alcista)</strong>';
    if (rsi > 70) return '<strong class="error-log">Sobrecompra (Riesgo Bajista)</strong>';
    if (rsi >= 30 && rsi <= 45) return 'Moderadamente sobrevendido / Estabilizando';
    if (rsi >= 55 && rsi <= 70) return 'Moderadamente sobrecomprado';
    return 'Rango neutral';
}

function getMacdInterpretation(macd_hist) {
    if (macd_hist === undefined || macd_hist === null || isNaN(macd_hist)) return 'Sin datos';
    if (macd_hist > 0) return '<strong class="success-log">Alcista (Histograma > 0)</strong>';
    return '<strong class="error-log">Bajista (Histograma < 0)</strong>';
}

function getMaInterpretation(ema, sma) {
    if (ema === undefined || sma === undefined || isNaN(ema) || isNaN(sma)) return 'Sin datos';
    if (ema > sma) return '<strong class="success-log">Alcista (EMA 10 > SMA 50)</strong>';
    return '<strong class="error-log">Bajista (EMA 10 < SMA 50)</strong>';
}

function getBbInterpretation(close, lower, upper) {
    if (close === undefined || lower === undefined || upper === undefined || isNaN(close) || isNaN(lower) || isNaN(upper)) return 'Sin datos';
    if (close < lower) return '<strong class="success-log">Banda Inferior Superada (Sobrevendido)</strong>';
    if (close > upper) return '<strong class="error-log">Banda Superior Superada (Sobrecomprado)</strong>';
    return 'Dentro de rangos normalizados';
}

function getPeInterpretation(pe) {
    if (pe === undefined || pe === null || isNaN(pe)) return 'Sin datos';
    if (pe < 0) return '<strong class="error-log">Negativo (Compañía en Pérdidas)</strong>';
    if (pe <= 15) return '<strong class="success-log">Bajo (Excelente Valor/Undervalued)</strong>';
    if (pe <= 25) return 'Moderado (Valoración Razonable)';
    if (pe <= 40) return 'Elevado (Crecimiento Esperado)';
    return '<strong class="error-log">Muy Alto (Especulativo/Sobrevalorado)</strong>';
}

function getDeInterpretation(de) {
    if (de === undefined || de === null || isNaN(de)) return 'Sin datos';
    if (de <= 50) return '<strong class="success-log">Muy Seguro (Deuda Baja)</strong>';
    if (de <= 100) return 'Moderado (Apalancamiento Normal)';
    if (de <= 200) return '<strong class="warning-log">Alto Apalancamiento</strong>';
    return '<strong class="error-log">Muy Alto (Riesgo de Solvencia)</strong>';
}

function getGrowthInterpretation(growth) {
    if (growth === undefined || growth === null || isNaN(growth)) return 'Sin datos';
    if (growth > 0.20) return '<strong class="success-log">Fuerte Crecimiento (>20%)</strong>';
    if (growth >= 0.05) return 'Crecimiento Estable (Sano)';
    if (growth >= -0.05) return 'Crecimiento Plano / Estancado';
    return '<strong class="error-log">Contracción (Negocio en Declive)</strong>';
}

function getMarginsInterpretation(margins) {
    if (margins === undefined || margins === null || isNaN(margins)) return 'Sin datos';
    if (margins > 0.20) return '<strong class="success-log">Alta Rentabilidad (>20%)</strong>';
    if (margins >= 0.08) return 'Rentabilidad Estable';
    if (margins > 0) return 'Margen Muy Ajustado';
    return '<strong class="error-log">Margen Negativo (Pérdidas Operativas)</strong>';
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
            <td>
                <strong>${ev.symbol}</strong>
                <div style="font-size: 0.7rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${ev.name || ''}">${ev.name || ''}</div>
            </td>
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

// Fallback helper to copy text in non-secure HTTP contexts
function copyTextFallback(text) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.top = "0";
    textArea.style.left = "0";
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (!successful) {
            throw new Error("execCommand copy returned false");
        }
    } catch (err) {
        console.error("Fallback copy failed:", err);
        throw err;
    } finally {
        document.body.removeChild(textArea);
    }
}

// Copy console logs to clipboard
async function copyConsoleLogs() {
    try {
        const text = consoleLogs.innerText || "";
        
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            copyTextFallback(text);
        }
        
        const originalText = btnCopyConsole.innerText;
        btnCopyConsole.innerText = '¡Copiado!';
        const originalBg = btnCopyConsole.style.background;
        btnCopyConsole.style.background = '#28a745'; // Success green
        btnCopyConsole.disabled = true;
        
        setTimeout(() => {
            btnCopyConsole.innerText = originalText;
            btnCopyConsole.style.background = originalBg;
            btnCopyConsole.disabled = false;
        }, 2000);
    } catch (err) {
        console.error("Error al copiar la consola:", err);
        alert("No se pudo copiar el contenido de la consola.");
    }
}
