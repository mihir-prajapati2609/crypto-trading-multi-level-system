from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import asyncio
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Global state for dashboard
DASHBOARD_STATE = {
    "is_running": False,
    "trading_mode": "paper",
    "regime": "ACTIVE",
    "garch_vol": 0.0,
    "anomaly_detected": False,
    "balances": {"total_usd": 0.0, "free_usd": 0.0, "real_fetched": False},
    "daily_pnl": 0.0,
    "watchlist_size": 0,
    "errors": [],
    "recent_trades": [],
    "top_coins": [],
    "cumulative_pnl": [],
    "analytics": {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "avg_win_usd": 0.0,
        "avg_loss_usd": 0.0,
        "risk_reward_ratio": 0.0,
        "total_fees_paid": 0.0,
        "total_net_pnl": 0.0,
        "expectancy_per_trade": 0.0,
        "max_drawdown_usd": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
    },
    "equity_curve": [],
    "strategy_breakdown": [],
    "strategy_metrics": {
        "cross_exchange": {"current_max_spread": 0.0, "target_spread": 0.30},
        "funding_rate":   {"current_max_rate": 0.0,   "target_rate": 0.05},
        "triangular":     {"current_max_profit": 0.0,  "target_profit": 0.20},
        "ai_momentum":    {"current_max_prob": 0.0,    "target_prob": 80.0},
        "momentum_rotation": {
            "active_slots": "0/5",
            "top_momentum_score": 0.0,
            "total_rotations": 0,
            "current_holdings": [],
            "target_slots": 5
        },
        "rsi_mean_reversion": {
            "active_positions": 0,
            "max_positions": 2
        },
    },
    "event_intelligence": {},
}

app = FastAPI(title="Crypto Arbitrage Bot Dashboard")

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount Event Intelligence static files and router
ei_static_dir = Path(__file__).parent.parent / "event_intelligence" / "dashboard_ext" / "static"
if ei_static_dir.exists():
    app.mount("/events/static", StaticFiles(directory=ei_static_dir), name="ei_static")

try:
    from event_intelligence.dashboard_ext.routes import router as ei_router
    app.include_router(ei_router)
except ImportError:
    pass

# Templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_dir)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

# ── Page Routes ────────────────────────────────────────────────────────────────

@app.get("/")
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/account")
async def get_account(request: Request):
    return templates.TemplateResponse(request=request, name="account.html")

@app.get("/opportunities")
async def get_opportunities(request: Request):
    return templates.TemplateResponse(request=request, name="opportunities.html")

# ── API: Core Status ───────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    return JSONResponse(content=DASHBOARD_STATE)

@app.get("/api/trades")
async def get_trades():
    return JSONResponse(content=DASHBOARD_STATE["recent_trades"])

@app.get("/api/pnl/cumulative")
async def get_cumulative_pnl():
    return JSONResponse(content=DASHBOARD_STATE["cumulative_pnl"])

@app.get("/api/coins")
async def get_coins():
    return JSONResponse(content=DASHBOARD_STATE["top_coins"])

@app.get("/api/opportunities")
async def get_opportunities_data():
    return JSONResponse(content=DASHBOARD_STATE.get("opportunities", []))

# ── API: Analytics ─────────────────────────────────────────────────────────────

@app.get("/api/analytics")
async def get_analytics():
    """Full analytics summary: win rate, profit factor, R:R, drawdown, Sharpe."""
    return JSONResponse(content=DASHBOARD_STATE["analytics"])

@app.get("/api/equity_curve")
async def get_equity_curve():
    """Equity curve time series for the chart."""
    return JSONResponse(content=DASHBOARD_STATE["equity_curve"])

@app.get("/api/strategy_breakdown")
async def get_strategy_breakdown():
    """Per-strategy performance breakdown."""
    return JSONResponse(content=DASHBOARD_STATE["strategy_breakdown"])

@app.get("/api/balance")
async def get_balance():
    """Real/paper balance summary."""
    return JSONResponse(content=DASHBOARD_STATE["balances"])

# ── API: Controls ──────────────────────────────────────────────────────────────

@app.post("/api/mock-trade")
async def mock_trade():
    import time, random
    if DASHBOARD_STATE["top_coins"]:
        coin = random.choice(DASHBOARD_STATE["top_coins"])["symbol"]
        DASHBOARD_STATE["recent_trades"].insert(0, {
            "timestamp": time.time(),
            "symbol": coin,
            "strategy": "MOCK_BLAST",
            "status": "CLOSED",
            "net_profit_usd": random.uniform(-5.0, 15.0)
        })
        return {"status": "mock trade added", "symbol": coin}
    return {"status": "no coins"}

@app.post("/api/killswitch")
async def trigger_killswitch():
    DASHBOARD_STATE["is_running"] = False
    DASHBOARD_STATE["errors"].append("Kill switch activated via dashboard.")
    await manager.broadcast(json.dumps({"type": "killswitch", "status": "activated"}))
    return {"status": "paused"}

@app.post("/api/resume")
async def resume_trading():
    DASHBOARD_STATE["is_running"] = True
    await manager.broadcast(json.dumps({"type": "status", "is_running": True}))
    return {"status": "resumed"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.send_text(json.dumps({"type": "update", "state": DASHBOARD_STATE}))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
