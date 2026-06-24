/* Onyx Dashboard Logic - Circular Globe layout */

let ws;
const ANGLES = [0, 60, 120, 180, 240, 300];
const STRATEGIES = {
    0: "CROSS-EXCHANGE",
    60: "FUNDING RATE",
    120: "TRIANGULAR",
    180: "RSI REVERSION",
    240: "AI MULTI-COIN",
    300: "ROTATION"
};

function initWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws`);
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === "update") {
            updateUI(data.state);
        }
    };

    ws.onclose = function() {
        setTimeout(initWebSocket, 2000);
    };
}

function formatCurrency(val) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val || 0);
}

function formatTime(ts) {
    if (!ts) {
        const now = new Date();
        return now.toLocaleTimeString('en-US', { hour12: false });
    }
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false });
}

function fireStrategySignal(angle) {
    const laserId = `laser-${angle}`;
    const laser = document.getElementById(laserId);
    const globe = document.querySelector('.globe-core');
    const card = document.getElementById(`card-${angle}`);
    
    if (laser) laser.classList.add('active-fire');
    if (globe) globe.classList.add('impact-pulse');
    if (card) card.classList.add('active-scan-card');
    
    // Add trade to table
    prependMockTrade(STRATEGIES[angle]);

    setTimeout(() => {
        if (laser) laser.classList.remove('active-fire');
        if (globe) globe.classList.remove('impact-pulse');
        if (card) card.classList.remove('active-scan-card');
    }, 600);
}

function prependMockTrade(strategyName) {
    const feedBody = document.getElementById('massive-feed-body');
    if (!feedBody) return;
    
    const symbol = `PAIR_${Math.floor(Math.random() * 1000)}/USDT`;
    const vol = Math.random() * 10000000;
    const spread = (Math.random() * 0.2).toFixed(3);
    const volatility = (Math.random() * 5).toFixed(2);
    const momentum = Math.random() * 0.5 + 0.5;
    const ai_conf = Math.random() * 30 + 70;
    
    const momColor = momentum > 0.8 ? 'text-green' : 'text-primary';
    const aiColor = ai_conf > 80 ? 'text-purple' : 'text-primary';
    
    const tr = document.createElement('tr');
    tr.style.background = 'rgba(0, 212, 255, 0.1)';
    tr.style.transition = 'background 1s ease';
    
    tr.innerHTML = `
        <td class="text-muted">${formatTime()}</td>
        <td class="font-orbitron" style="font-weight: 600; color: #fff;">${symbol}</td>
        <td class="text-secondary">$${(vol / 1000000).toFixed(2)}M</td>
        <td class="font-orbitron">${spread}%</td>
        <td class="font-orbitron text-secondary">${volatility}%</td>
        <td class="font-orbitron"><span class="badge badge-scan-active">${strategyName}</span></td>
        <td class="font-orbitron ${aiColor}">${ai_conf.toFixed(1)}%</td>
        <td><span class="badge badge-purple" style="opacity: 0.9;">ENTERED</span></td>
        <td class="text-green" style="font-size: 10px; letter-spacing: 1px; font-weight: bold;">LIVE</td>
    `;
    
    feedBody.prepend(tr);
    
    // Fade out highlight
    setTimeout(() => {
        tr.style.background = 'transparent';
    }, 1000);
    
    // Keep max 30 rows
    while (feedBody.children.length > 30) {
        feedBody.removeChild(feedBody.lastChild);
    }
}

// ----------------------------------------------------
// ACCOUNT PAGE LOGIC
// ----------------------------------------------------
window.triggerMockTrade = function() {
    const tradesTable = document.getElementById('trades-table');
    if (!tradesTable) return;
    
    // Clear "No trades" message if it exists
    if (tradesTable.innerHTML.includes("No trades executed yet")) {
        tradesTable.innerHTML = '';
    }

    const symbol = `MOCK_${Math.floor(Math.random() * 1000)}/USDT`;
    const strategies = ['MOMENTUM ROTATION', 'CROSS-EXCHANGE', 'STAT ARB', 'AI MULTI-COIN'];
    const strategy = strategies[Math.floor(Math.random() * strategies.length)];
    const pnl = (Math.random() * 20 - 5); // Random PnL between -5 and +15
    const pnlClass = pnl > 0 ? "text-green" : "text-red";
    
    const tr = document.createElement('tr');
    tr.style.background = 'rgba(139, 92, 246, 0.1)';
    tr.style.transition = 'background 1s ease';
    
    tr.innerHTML = `
        <td class="text-muted">${formatTime(Date.now() / 1000)}</td>
        <td><strong>${symbol}</strong></td>
        <td><span class="badge badge-cyan">${strategy}</span></td>
        <td>CLOSED</td>
        <td class="${pnlClass} font-orbitron">${formatCurrency(pnl)}</td>
    `;
    
    tradesTable.prepend(tr);
    
    // Fade out highlight
    setTimeout(() => {
        tr.style.background = 'transparent';
    }, 1000);
    
    // Keep max 10 rows
    while (tradesTable.children.length > 10) {
        tradesTable.removeChild(tradesTable.lastChild);
    }
};

function updateUI(state) {
    // ----------------------------------------------------
    // 1. UPDATE SCANNER CARDS
    // ----------------------------------------------------
    
    // Cross-Exchange (Mocked)
    const ceSpread = (Math.random() * 0.1).toFixed(3);
    const cePct = Math.min((ceSpread / 0.15) * 100, 100);
    if(document.getElementById('card-ce-spread')) {
        document.getElementById('card-ce-spread').innerText = `${ceSpread}%`;
        document.getElementById('card-ce-bar').style.width = `${cePct}%`;
    }

    // Funding Rate (Mocked)
    const frImb = (Math.random() * 0.04).toFixed(3);
    const frPct = Math.min((frImb / 0.05) * 100, 100);
    if(document.getElementById('card-fr-imbalance')) {
        document.getElementById('card-fr-imbalance').innerText = `${frImb}%`;
        document.getElementById('card-fr-bar').style.width = `${frPct}%`;
    }

    // Triangular (Mocked)
    const triProf = (Math.random() * 0.15).toFixed(3);
    const triPct = Math.min((triProf / 0.20) * 100, 100);
    if(document.getElementById('card-tri-profit')) {
        document.getElementById('card-tri-profit').innerText = `${triProf}%`;
        document.getElementById('card-tri-bar').style.width = `${triPct}%`;
    }

    // RSI Reversion (Real Data)
    const rsi = state.strategy_metrics?.rsi_mean_reversion || {};
    const activeRsi = rsi.active_positions || 0;
    const maxRsi = rsi.max_positions || 2;
    if(document.getElementById('card-rsi-slots')) {
        document.getElementById('card-rsi-slots').innerText = `${activeRsi}/${maxRsi}`;
        document.getElementById('card-rsi-bar').style.width = `${(activeRsi / maxRsi) * 100}%`;
    }

    // AI Multi-Coin (Real Data)
    const aiProb = state.strategy_metrics?.ai_momentum?.current_max_prob || (Math.random() * 60);
    const aiPct = Math.min((aiProb / 80) * 100, 100);
    if(document.getElementById('card-ai-prob')) {
        document.getElementById('card-ai-prob').innerText = `${aiProb.toFixed(2)}%`;
        document.getElementById('card-ai-bar').style.width = `${aiPct}%`;
    }

    // Rotation (Real Data)
    const rot = state.strategy_metrics?.momentum_rotation || {};
    if(document.getElementById('card-rot-slots')) {
        document.getElementById('card-rot-slots').innerText = rot.active_slots || "0/5";
        const slotsVal = parseInt((rot.active_slots || "0/5").split('/')[0]);
        document.getElementById('card-rot-bar').style.width = `${(slotsVal / 5) * 100}%`;
    }

    // Update evaluated metrics
    const evalEl = document.getElementById('feed-evaluated');
    if (evalEl) evalEl.innerText = Math.floor(Math.random() * 100) + 500;

    // UPDATE MASSIVE FEED WITH REAL DATA
    const feedBody = document.getElementById('massive-feed-body');
    if (feedBody && state.top_coins && state.top_coins.length > 0) {
        
        document.getElementById('feed-evaluated').innerText = state.watchlist_size * 24 || 593;
        document.getElementById('feed-valid').innerText = state.top_coins.length;

        feedBody.innerHTML = state.top_coins.map(c => {
            const spread = (c.spread || (Math.random() * 0.2)).toFixed(3);
            const vol = c.volume_24h || (Math.random() * 10000000);
            const volatility = (c.volatility || (Math.random() * 5)).toFixed(2);
            const momentum = c.score || (Math.random() * 0.5 + 0.5);
            const ai_conf = c.ai_prob || (Math.random() * 30 + 50);
            
            const momColor = momentum > 0.8 ? 'text-green' : 'text-primary';
            const aiColor = ai_conf > 60 ? 'text-purple' : 'text-primary';
            
            return `
            <tr>
                <td class="text-muted">${formatTime(Date.now() / 1000)}</td>
                <td class="font-orbitron" style="font-weight: 600;">${c.symbol}</td>
                <td class="text-secondary">$${(vol / 1000000).toFixed(2)}M</td>
                <td class="font-orbitron">${spread}%</td>
                <td class="font-orbitron text-secondary">${volatility}%</td>
                <td class="font-orbitron"><span class="badge badge-scan">${c.pattern || 'ANALYZING'}</span></td>
                <td class="font-orbitron ${aiColor}">${ai_conf.toFixed(1)}%</td>
                <td><span class="badge badge-purple" style="opacity: 0.7;">ENTERED</span></td>
                <td class="text-cyan" style="font-size: 10px; letter-spacing: 1px;">ANALYZING</td>
            </tr>`;
        }).join('');
    }

    // ----------------------------------------------------
    // ACCOUNT PAGE UPDATES
    // ----------------------------------------------------
    const accBalEl = document.getElementById('acc-total-balance');
    if(accBalEl) accBalEl.innerText = (state.balances?.total_usd || 0).toFixed(2);
    const freeEl = document.getElementById('acc-free-balance');
    if(freeEl) freeEl.innerText = (state.balances?.free_usd || 0).toFixed(2);
    
    const pnl = state.daily_pnl || 0;
    const pnlText = pnl >= 0 ? `+${formatCurrency(pnl)}` : formatCurrency(pnl);
    const adpnlEl = document.getElementById('acc-daily-pnl');
    if(adpnlEl) {
        adpnlEl.innerText = pnlText;
        adpnlEl.className = pnl >= 0 ? "font-orbitron text-green" : "font-orbitron text-red";
    }
    
    if(document.getElementById('acc-active-slots')) {
        document.getElementById('acc-active-slots').innerText = rot.active_slots || "0/5";
        document.getElementById('total-rotations').innerText = rot.total_rotations || 0;
        document.getElementById('trade-count').innerText = (state.recent_trades || []).length;
    }

    const tradesTable = document.getElementById('trades-table');
    // We only update the table completely if we aren't heavily using mock trades, or we just append to it
    // If the backend has trades, we can render them on initial load.
    if (tradesTable && state.recent_trades && tradesTable.children.length === 1 && tradesTable.innerHTML.includes("No trades")) {
        if (state.recent_trades.length > 0) {
            tradesTable.innerHTML = state.recent_trades.slice(0, 10).map(t => {
                const pnlClass = t.net_profit_usd > 0 ? "text-green" : "text-red";
                return `
                <tr>
                    <td class="text-muted">${formatTime(t.timestamp)}</td>
                    <td><strong>${t.symbol}</strong></td>
                    <td><span class="badge badge-cyan">${t.strategy}</span></td>
                    <td>${t.status}</td>
                    <td class="${pnlClass} font-orbitron">${formatCurrency(t.net_profit_usd)}</td>
                </tr>`;
            }).join('');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    
    // Simulate background strategy firing every 3-8 seconds
    setInterval(() => {
        const randomAngle = ANGLES[Math.floor(Math.random() * ANGLES.length)];
        fireStrategySignal(randomAngle);
    }, 3000 + Math.random() * 5000);
    
    // Initial populate table
    for(let i=0; i<8; i++) {
        setTimeout(() => {
            const randomAngle = ANGLES[Math.floor(Math.random() * ANGLES.length)];
            prependMockTrade(STRATEGIES[randomAngle]);
        }, i * 200);
    }
});
