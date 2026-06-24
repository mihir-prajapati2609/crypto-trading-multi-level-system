/* AI Terminal Javascript Logic */

const POLL_INTERVAL = 2000;

function formatTime(ts) {
    if (!ts) return '--:--:--';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false });
}

function formatPnl(val) {
    if (val === undefined || val === null) return '$0.00';
    const sign = val >= 0 ? '+' : '';
    return `${sign}$${val.toFixed(4)}`;
}

function renderEventFeed(events) {
    const feed = document.getElementById('event-feed');
    if (!events || events.length === 0) {
        feed.innerHTML = '<div class="term-empty">AWAITING_DATA_STREAM...</div>';
        return;
    }

    feed.innerHTML = events.map(e => {
        const sentScore = e.sentiment_score || 50;
        const trend = sentScore >= 60 ? 'bull' : sentScore <= 40 ? 'bear' : 'neut';
        
        const src = e.url ? `<a href="${e.url}" target="_blank" style="color: var(--neon-cyan); text-decoration: none;">[${e.source}]</a>` : `[${e.source}]`;

        return `
        <div class="ticker-item ${trend}">
            <div class="tick-meta">
                <span>${formatTime(e.timestamp)}</span>
                <span>${src}</span>
                <span class="${trend === 'bull' ? 'text-neon-green' : trend === 'bear' ? 'text-neon-red' : ''}">SNT:${sentScore.toFixed(0)}</span>
                <span style="color: var(--neon-cyan);">${e.category.toUpperCase()}</span>
            </div>
            <div class="tick-body" style="font-weight: 700; color: #fff;">> ${e.title}</div>
            ${e.body ? `<div class="tick-body" style="font-size: 11px;">${e.body}</div>` : ''}
            <div class="tick-hash">HASH: ${e.content_hash ? e.content_hash.substring(0, 16) : 'N/A'}</div>
        </div>`;
    }).join('');
}

function renderScoreCards(scores) {
    const tbody = document.querySelector('#score-cards');
    if (!scores || scores.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="term-empty">NO_SIGNALS</td></tr>';
        return;
    }

    tbody.innerHTML = scores.map(s => {
        const act = (s.trade_action || 'SKIP').toUpperCase();
        const actClass = act === 'BUY' ? 'buy' : act === 'SELL' ? 'sell' : '';
        const confColor = s.ai_confidence > 70 ? 'text-neon-green' : 'text-norm';

        return `
        <tr>
            <td style="font-weight: 700;">${s.coin || '??'}</td>
            <td><span class="badge-act ${actClass}">${act}</span></td>
            <td class="${confColor}">${(s.ai_confidence || 0).toFixed(0)}%</td>
            <td>${(s.current_volume || 'norm').substring(0, 4).toUpperCase()}</td>
            <td>${(s.source_reliability || 0).toFixed(0)}%</td>
        </tr>`;
    }).join('');
}

function renderTradeHistory(trades) {
    const tbody = document.getElementById('ei-trades-body');
    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="term-empty">NO_EXECUTIONS</td></tr>';
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const pnl = t.net_pnl_usd || 0;
        const pnlColor = pnl > 0 ? 'text-neon-green' : pnl < 0 ? 'text-neon-red' : '';
        const act = (t.side || 'BUY').toUpperCase();
        const actClass = act === 'BUY' ? 'buy' : 'sell';

        return `
        <tr>
            <td style="color: var(--text-dim);">${formatTime(t.timestamp)}</td>
            <td style="font-weight: 700;">${t.coin || t.symbol}</td>
            <td><span class="badge-act ${actClass}">${act}</span></td>
            <td class="${pnlColor}">${formatPnl(pnl)}</td>
        </tr>`;
    }).join('');
}

function updateDashboard(data) {
    if (!data) return;

    document.getElementById('ei-mode').textContent = (data.mode || 'OBSERVE').toUpperCase();
    document.getElementById('ei-status').textContent = data.is_running ? 'ONLINE' : 'OFFLINE';
    document.getElementById('sources-active').textContent = `${data.sources_active || 0}/${data.sources_total || 9}`;
    
    const fng = data.fear_greed_index || 50;
    const fngEl = document.getElementById('fear-greed');
    fngEl.textContent = fng;
    fngEl.className = `term-val ${fng > 60 ? 'text-neon-green' : fng < 40 ? 'text-neon-red' : ''}`;
    
    let emoji = fng <= 20 ? '😱' : fng <= 35 ? '😰' : fng <= 50 ? '😐' : fng <= 65 ? '😊' : fng <= 80 ? '😄' : '🤑';
    document.getElementById('fng-emoji').textContent = emoji;

    document.getElementById('open-trades').textContent = `${data.open_trades || 0}/${(data.risk_status || {}).max_open_trades || 5}`;
    
    const pnl = data.pnl_today || 0;
    const pnlEl = document.getElementById('today-pnl');
    pnlEl.textContent = formatPnl(pnl);
    pnlEl.className = `term-val ${pnl > 0 ? 'text-neon-green' : pnl < 0 ? 'text-neon-red' : ''}`;
    
    document.getElementById('win-rate').textContent = `${(data.win_rate || 0).toFixed(0)}%`;

    renderEventFeed(data.recent_events);
    renderScoreCards(data.recent_scores);
    renderTradeHistory(data.recent_trades);
}

async function poll() {
    try {
        const resp = await fetch('/events/api/status');
        if (resp.ok) {
            const data = await resp.json();
            updateDashboard(data);
        }
    } catch (e) {
        console.debug('SYS_ERR:', e);
    }
    setTimeout(poll, POLL_INTERVAL);
}

document.addEventListener('DOMContentLoaded', () => {
    poll();
});
