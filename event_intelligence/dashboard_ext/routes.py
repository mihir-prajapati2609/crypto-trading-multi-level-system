"""
Event Intelligence — Dashboard API Routes

FastAPI router with event intelligence endpoints.
Included in the main dashboard app via app.include_router().
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["event_intelligence"])

# Templates directory for event intelligence pages
templates_dir = Path(__file__).parent / "templates"
main_templates_dir = Path(__file__).parent.parent.parent / "dashboard" / "templates"
templates = Jinja2Templates(directory=[str(templates_dir), str(main_templates_dir)])


def get_ei_state(request: Request) -> dict:
    """Get event intelligence state from the shared dashboard state."""
    # Import here to avoid circular imports
    from dashboard.app import DASHBOARD_STATE
    return DASHBOARD_STATE.get("event_intelligence", {})


@router.get("/", response_class=HTMLResponse)
async def event_intelligence_page(request: Request):
    """Serve the Event Intelligence dashboard page."""
    return templates.TemplateResponse(
        request=request,
        name="event_intelligence.html",
    )


@router.get("/api/status")
async def get_status(request: Request):
    """Get event intelligence engine status."""
    return JSONResponse(content=get_ei_state(request))


@router.get("/api/recent")
async def get_recent_events(request: Request):
    """Get recent events."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("recent_events", []))


@router.get("/api/scores")
async def get_recent_scores(request: Request):
    """Get recent score cards."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("recent_scores", []))


@router.get("/api/trades")
async def get_event_trades(request: Request):
    """Get event-driven trade history."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("recent_trades", []))


@router.get("/api/agents")
async def get_agent_performance(request: Request):
    """Get agent performance stats."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("agent_performance", []))


@router.get("/api/sources")
async def get_source_reliability(request: Request):
    """Get source reliability stats."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("source_reliabilities", []))


@router.get("/api/risk")
async def get_risk_status(request: Request):
    """Get risk management status."""
    state = get_ei_state(request)
    return JSONResponse(content=state.get("risk_status", {}))
