"""Wiring centrale AgentMetrics (istanza Mirko): l'unico posto in cui i pezzi si incontrano.

Tutta la configurazione arriva da .env / agent.json. Niente import nascosti,
niente dipendenze fra moduli figli.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv(override=True)


def _configure_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    if not logging.root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        logging.root.setLevel(level)


_configure_logging()

from app.auth_dashboard import (  # noqa: E402
    DashboardAuthMiddleware,
    dashboard_auth_enabled,
    read_session_secret,
)
from app.config import load_agent_config  # noqa: E402
from app import dial_guard  # noqa: E402
from app.dispatcher import CallDispatcher  # noqa: E402
from app.routes.auth import router as auth_router  # noqa: E402
from app.routes.calls import calls_api_router  # noqa: E402
from app.routes.dashboard import router as dashboard_router  # noqa: E402
from app.routes.usage import health_api_router, usage_api_router  # noqa: E402
from app.routes.inbound import router as inbound_router  # noqa: E402
from app.routes.public import router as public_router  # noqa: E402
from app.vapi_circuit_breaker import get_vapi_circuit_breaker  # noqa: E402
from crm.crud import MirkoCRM  # noqa: E402
from integrations.factory import (  # noqa: E402
    _truthy,
    build_calendar,
    build_sheet,
    build_sheet_writer,
    build_slack,
    build_whatsapp,
)
from integrations.sheets.retry_schedule import compute_next_attempt_at  # noqa: E402
from integrations.sheets.poller import SheetPoller  # noqa: E402
from integrations.whatsapp.meet_reminder import MeetReminderScheduler  # noqa: E402
from telephony.vapi.client import VapiProvider  # noqa: E402
from telephony.vapi.tools import build_tool_handler  # noqa: E402
from telephony.vapi.webhooks import build_webhook_router  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singletons (costruiti a module-load, configurazione 100% da .env / agent.json)
# ---------------------------------------------------------------------------

agent_configs: dict[str, dict[str, Any]] = load_agent_config("agent.json")

crm = MirkoCRM(os.environ["DATABASE_URL"])
telephony = VapiProvider(
    os.environ["VAPI_API_KEY"],
    os.getenv("VAPI_WEBHOOK_SECRET"),
)

calendars: dict[str, Any] = {
    key: build_calendar(key) for key in agent_configs
}
whatsapps: dict[str, Any] = {
    key: build_whatsapp(key, agent_configs.get(key)) for key in agent_configs
}
slack_by_agent: dict[str, Any] = {
    key: build_slack(key) for key in agent_configs
}
sheet_writers: dict[str, Any] = {
    key: build_sheet_writer(key) for key in agent_configs
}
slack_notifier = slack_by_agent.get("gloria") or build_slack()

logger.info(
    "AgentMetrics init: agents=%s calendars=%s whatsapps=%s sheet_writers=%s",
    list(agent_configs.keys()),
    {k: "ON" if v else "OFF" for k, v in calendars.items()},
    {k: "ON" if v else "OFF" for k, v in whatsapps.items()},
    {k: "ON" if v else "OFF" for k, v in sheet_writers.items()},
)

# ---------------------------------------------------------------------------
# Lifespan: init DB, reset dispatcher, avvio per agente + SheetPoller opzionale
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    crm.init_db()
    dial_guard.init_dial_guard()

    from app.config import outbound_calls_enabled

    if not outbound_calls_enabled():
        logger.warning(
            "CHIAMATE_PARTONO=false: nessuna chiamata outbound partirà finché non è true"
        )

    dispatchers: dict[str, CallDispatcher] = {}
    poller_tasks: list[Any] = []
    meet_reminder_task: Any = None
    vapi_circuit_breaker = get_vapi_circuit_breaker()

    for key, cfg in agent_configs.items():
        dispatcher = CallDispatcher(
            telephony=telephony,
            crm=crm,
            agent_config=cfg,
            cooldown_s=int(os.getenv("CALL_COOLDOWN_SECONDS", "15")),
            timeout_s=int(os.getenv("ACTIVE_CALL_TIMEOUT_SECONDS", "600")),
            circuit_breaker=vapi_circuit_breaker,
        )
        await dispatcher.start()
        dispatchers[key] = dispatcher

        if _truthy(str(cfg.get("sheet_enabled") or "")):
            sheet_provider = build_sheet(agent_key=key)
            if sheet_provider is not None:
                try:
                    poller = SheetPoller(
                        crm=crm,
                        sheet=sheet_provider,
                        dispatcher=dispatcher,
                        agent_key=key,
                        interval_s=int(os.getenv("SHEET_POLL_INTERVAL_S", "300")),
                        schedule_retry=compute_next_attempt_at,
                    )
                    poller_tasks.append(poller.start())
                    logger.info("SheetPoller avviato agent=%s", key)
                except Exception:  # noqa: BLE001
                    logger.exception("SheetPoller avvio fallito agent=%s", key)

    if whatsapps.get("sara"):
        try:
            meet_scheduler = MeetReminderScheduler(
                whatsapps=whatsapps,
                interval_s=int(os.getenv("MEET_REMINDER_POLL_S", "30")),
            )
            meet_reminder_task = meet_scheduler.start()
            logger.info("MeetReminderScheduler avviato (poll ogni %ss)", os.getenv("MEET_REMINDER_POLL_S", "30"))
        except Exception:  # noqa: BLE001
            logger.exception("MeetReminderScheduler avvio fallito")

    app.state.dispatchers = dispatchers
    app.state.agent_configs = agent_configs
    app.state.crm = crm
    app.state.telephony = telephony
    app.state.slack = slack_notifier
    app.state.slack_by_agent = slack_by_agent
    app.state.sheet_writers = sheet_writers

    try:
        yield
    finally:
        if meet_reminder_task is not None and not meet_reminder_task.done():
            meet_reminder_task.cancel()
        for task in poller_tasks:
            if task is not None and not task.done():
                task.cancel()
        for dispatcher in dispatchers.values():
            await dispatcher.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan, title="AgentMetrics")

if dashboard_auth_enabled():
    app.add_middleware(DashboardAuthMiddleware)
else:
    logger.warning("Auth dashboard non configurata (.env AGENTMETRICS_LOGIN_*)")
session_secret = read_session_secret()
if session_secret:
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

def _get_dispatchers() -> dict[str, CallDispatcher]:
    return getattr(app.state, "dispatchers", None) or {}


tool_handler = build_tool_handler(
    crm=crm,
    calendars=calendars,
    whatsapps=whatsapps,
    slacks=slack_by_agent,
    sheet_writers=sheet_writers,
    get_dispatchers=_get_dispatchers,
)


app.include_router(
    build_webhook_router(
        provider=telephony,
        crm=crm,
        dispatcher=_get_dispatchers,
        tool_handler=tool_handler,
        sheet_writers=sheet_writers,
    )
)

app.include_router(auth_router)
app.include_router(inbound_router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(calls_api_router, prefix="/api")
app.include_router(usage_api_router)
app.include_router(health_api_router)
app.include_router(public_router)


# ---------------------------------------------------------------------------
# Dashboard HTML (templates/dashboard) + statici (static/)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DASHBOARD = _ROOT / "templates" / "dashboard"
_DASHBOARD_INDEX = _TEMPLATES_DASHBOARD / "index.html"
_STATIC_ASSETS = _ROOT / "static" / "assets"
_FAVICON = _ROOT / "static" / "favicon.ico"


if _STATIC_ASSETS.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_STATIC_ASSETS)),
        name="static-assets",
    )

_RESERVED_PATH_PREFIXES = ("api/", "vapi/", "assets/", "favicon", "appointment/", "a/")


def _serve_html(filename: str) -> FileResponse:
    path = _TEMPLATES_DASHBOARD / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Pagina non trovata")
    return FileResponse(path)


@app.get("/favicon.ico", include_in_schema=False)
async def _favicon() -> Any:
    if not _FAVICON.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(_FAVICON, media_type="image/x-icon")


@app.get("/", include_in_schema=False)
async def _dashboard_root() -> Any:
    if not _DASHBOARD_INDEX.is_file():
        raise HTTPException(status_code=503, detail="templates/dashboard non disponibile")
    return FileResponse(_DASHBOARD_INDEX)


@app.get("/overview", include_in_schema=False)
async def _dashboard_overview() -> Any:
    return _serve_html("overview.html")


@app.get("/lead/immobiliare", include_in_schema=False)
async def _dashboard_lead_immobiliare() -> Any:
    return _serve_html("lead-immobiliare.html")


@app.get("/lead/outbound", include_in_schema=False)
async def _dashboard_lead_outbound() -> Any:
    return _serve_html("lead-outbound.html")


@app.get("/lead/{cliente_id:int}", include_in_schema=False)
async def _dashboard_lead_detail(cliente_id: int) -> Any:
    return _serve_html("lead-detail.html")


@app.get("/chiamate", include_in_schema=False)
async def _dashboard_chiamate() -> Any:
    return _serve_html("chiamate.html")


@app.get("/chiamate/{call_sid:path}", include_in_schema=False)
async def _dashboard_chiamata_detail(call_sid: str) -> Any:
    return _serve_html("chiamata-detail.html")


@app.get("/appuntamenti", include_in_schema=False)
async def _dashboard_appuntamenti() -> Any:
    return _serve_html("appuntamenti.html")


@app.get("/calendario", include_in_schema=False)
async def _dashboard_calendario() -> Any:
    return _serve_html("calendario.html")


@app.get("/coda", include_in_schema=False)
async def _dashboard_coda() -> Any:
    return _serve_html("coda.html")


@app.get("/usage", include_in_schema=False)
async def _dashboard_usage() -> Any:
    return _serve_html("usage.html")


@app.get("/{full_path:path}", include_in_schema=False)
async def _dashboard_fallback(full_path: str) -> Any:
    """File .html diretti in templates/dashboard/ o 404."""
    if full_path.startswith(_RESERVED_PATH_PREFIXES) or full_path in ("login", "logout"):
        raise HTTPException(status_code=404)
    if full_path.endswith(".html"):
        name = full_path.rsplit("/", 1)[-1]
        if (_TEMPLATES_DASHBOARD / name).is_file():
            return _serve_html(name)
    raise HTTPException(status_code=404)
