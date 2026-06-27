#   API outbound + lettura chiamate (3 endpoint, niente Twilio / niente WS)
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.call_summary import generate_call_summary
from app.config import canonical_agent_key, outbound_calls_enabled, resolve_dispatcher_key
from crm import crud
from crm.phone import allows_outbound_dial
from crm.models import ChiamaClienteRequest, ChiamaClienteResponse
from telephony.base import TelephonyError

logger = logging.getLogger(__name__)

calls_api_router = APIRouter(tags=["Calls"])


@calls_api_router.get("/calls")
def api_list_calls(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    client_id: int | None = Query(None),
    search: str | None = Query(None, description="Nome cliente, telefono o esito"),
    date_from: str | None = Query(None, description="Data inizio (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Data fine (YYYY-MM-DD)"),
    outcome: str | None = Query(None, description="Filtra per esito chiamata"),
) -> dict[str, Any]:
    try:
        df = crud._parse_call_date_filter(date_from)
        dt = crud._parse_call_date_filter(date_to, end_of_day=True)
        oc = str(outcome).strip() if outcome else None
        items = crud.list_calls(
            limit=limit,
            offset=offset,
            client_id=client_id,
            search=search,
            date_from=df,
            date_to=dt,
            outcome=oc,
        )
        total = crud.count_calls(
            client_id=client_id,
            search=search,
            date_from=df,
            date_to=dt,
            outcome=oc,
        )
        return {"items": items, "total": total}
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET /calls")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@calls_api_router.get("/calls/{call_sid}")
def api_get_call(call_sid: str) -> dict[str, Any]:
    row = crud.get_call_by_sid(call_sid)
    if not row:
        raise HTTPException(status_code=404, detail="Chiamata non trovata")
    return dict(row)


@calls_api_router.get("/calls/{call_sid}/transcript")
def api_get_call_transcript(call_sid: str) -> list[dict[str, Any]]:
    row = crud.get_call_by_sid(call_sid)
    if not row:
        raise HTTPException(status_code=404, detail="Chiamata non trovata")
    return crud.list_transcript_turns_for_sid(call_sid)


@calls_api_router.get("/calls/{call_sid}/summary")
async def api_get_call_summary(
    call_sid: str,
    request: Request,
    force: bool = Query(False, description="Rigenera anche se già salvato"),
    cached_only: bool = Query(
        False,
        description="Restituisce solo il riassunto già salvato, senza generare",
    ),
) -> dict[str, Any]:
    row = crud.get_call_by_sid(call_sid)
    if not row:
        raise HTTPException(status_code=404, detail="Chiamata non trovata")
    sheet_writers = getattr(request.app.state, "sheet_writers", None) or {}
    return await generate_call_summary(
        call_sid,
        force=force,
        cached_only=cached_only,
        sheet_writers=sheet_writers,
    )


@calls_api_router.get("/calls/{call_sid}/events")
def api_get_call_events(call_sid: str) -> list[dict[str, Any]]:
    row = crud.get_call_by_sid(call_sid)
    if not row:
        raise HTTPException(status_code=404, detail="Chiamata non trovata")
    call_id = row.get("id")
    if call_id is None:
        return []
    events = crud.list_call_events(int(call_id))
    out: list[dict[str, Any]] = []
    for ev in events:
        created = ev.get("created_at")
        if hasattr(created, "isoformat"):
            created = created.isoformat(sep=" ", timespec="seconds")
        out.append(
            {
                "id": ev.get("id"),
                "event_type": ev.get("event_type"),
                "payload_json": ev.get("payload_json"),
                "created_at": created,
            }
        )
    return out


@calls_api_router.post("/chiama-cliente", response_model=ChiamaClienteResponse)
async def api_chiama_cliente(
    body: ChiamaClienteRequest,
    request: Request,
) -> ChiamaClienteResponse:
    """Avvia o accoda una chiamata outbound manuale (dashboard).

    - ``sent``: VAPI ha accettato la chiamata (slot libero, risposta immediata).
    - ``queued``: in attesa di slot o altre chiamate in coda.
    """
    try:
        logger.info("chiama-cliente: body=%s", body.model_dump())
        dispatchers: dict[str, Any] = getattr(request.app.state, "dispatchers", None) or {}
        agent_configs: dict[str, Any] = (
            getattr(request.app.state, "agent_configs", None) or {}
        )
        logger.info(
            "chiama-cliente: dispatchers keys=%s",
            list(dispatchers.keys()) if dispatchers else "NONE",
        )

        row = crud.get_client(body.cliente_id)
        if not row:
            raise HTTPException(status_code=404, detail="Cliente non trovato")
        tel = str(row.get("telefono") or "").strip()
        if not tel:
            raise HTTPException(status_code=400, detail="Telefono cliente mancante")
        if not allows_outbound_dial(tel):
            raise HTTPException(
                status_code=400,
                detail="Numero non valido per chiamate outbound (mobile o fisso italiano).",
            )

        if not outbound_calls_enabled():
            raise HTTPException(
                status_code=503,
                detail="Chiamate outbound disabilitate (CHIAMATE_PARTONO=false in .env)",
            )

        try:
            ak = crud.assert_client_agent_scope(
                body.cliente_id,
                body.agent_key,
                context="chiama-cliente",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        logger.info(
            "chiama-cliente: client_id=%s agent_key=%s telefono=%s",
            body.cliente_id,
            ak,
            tel[:6] + "***",
        )
        dispatch_key = resolve_dispatcher_key(ak, dispatchers)
        dispatcher = dispatchers.get(dispatch_key)
        if dispatcher is None:
            logger.error(
                "chiama-cliente: dispatcher assente agent_key=%s dispatch_key=%s",
                ak,
                dispatch_key,
            )
            raise HTTPException(
                status_code=503,
                detail=f"Dispatcher non disponibile per agent_key={ak}",
            )

        queue_id = crud.enqueue_client(body.cliente_id, dispatch_key)
        payload = {
            "id": body.cliente_id,
            "client_id": body.cliente_id,
            "telefono": tel,
            "nome": str(row.get("nome") or ""),
            "manual": True,
            "queue_id": queue_id,
            "extra": {"agent_key": dispatch_key, "queue_id": queue_id},
        }
        try:
            outcome = await dispatcher.dispatch_manual(payload)
        except TelephonyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        status = str(outcome.get("status") or "queued")
        call_sid = outcome.get("call_sid")
        logger.info(
            "chiama-cliente %s client_id=%s agent=%s call_sid=%s",
            status,
            body.cliente_id,
            dispatch_key,
            call_sid,
        )
        return ChiamaClienteResponse(
            status=status,
            client_id=body.cliente_id,
            call_sid=call_sid,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("chiama-cliente ERRORE: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Errore accodamento chiamata: {exc}"
        ) from exc
