# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Webhook handler Vapi: firma → parse_webhook → dispatch su CRM/dispatcher/tools."""
from __future__ import annotations

import json as _json
import logging
import os as _os
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Optional

from fastapi import APIRouter, HTTPException, Request

from app import dial_guard
from app.config import canonical_agent_key, get_business_timezone
from crm import crud
from crm.base import CRMProvider
from telephony.base import TelephonyProvider
from integrations.sheets.retry_schedule import next_hour_datetime
from telephony.vapi.cost_sync import (
    apply_call_billing,
    extract_end_of_call_metrics,
    schedule_billing_sync,
)
from telephony.vapi.outbound_policy import (
    is_unreachable_sip_ended_reason,
    is_voicemail_ended_reason,
)

logger = logging.getLogger(__name__)


# ----- mapping endedReason Vapi → esiti CRM ---------------------------


# Canonical tags accettati da MirkoCRM.update_outcome (vedi
# _ESITO_TAG_TO_OUTCOME_STATO in crm/crud.py). I tag non canonical
# vengono comunque persistiti come session_outcome.
# Durata minima (s) oltre cui un transcript vuoto è sospetto: probabile dialogo
# reale non arrivato col webhook → tentiamo un refetch da Vapi.
_TRANSCRIPT_REFETCH_MIN_SECONDS = 25

_ENDED_REASON_MAP: dict[str, str] = {
    # nessuna risposta lato cliente
    "customer-did-not-answer": "NON_RISPONDE",
    "no-answer": "NON_RISPONDE",
    "customer-busy": "NON_RISPONDE",
    "customer-did-not-give-microphone-permission": "NON_RISPONDE",
    "voicemail": "NON_RISPONDE",
    # chiusura neutra Vapi → NON_RISPONDE grezzo; resolve_final_call_outcome_tag raffina
    "assistant-ended-call": "NON_RISPONDE",
    "assistant-ended-call-after-message-spoken": "NON_RISPONDE",
    "assistant-said-end-call-phrase": "NON_RISPONDE",
    "customer-ended-call": "NON_RISPONDE",
    "customer-hung-up": "NON_RISPONDE",
    # errori di trasporto / blocco operatore
    "twilio-failed-to-connect-call": "ERRORE",
    "phone-call-provider-blocked-call": "ERRORE",
    "phone-call-provider-error": "ERRORE",
    "error": "ERRORE",
    "exceeded-max-duration": "NON_RISPONDE",
    "silence-timed-out": "NON_RISPONDE",
    "pipeline-error": "ERRORE",
}


def map_ended_reason_to_esito(ended_reason: str) -> str:
    """Vapi endedReason → tag esito grezzo (raffinato da resolve_final_call_outcome_tag)."""
    key = (ended_reason or "").strip().lower()
    mapped = _ENDED_REASON_MAP.get(key)
    if mapped is not None:
        return mapped
    if is_unreachable_sip_ended_reason(ended_reason):
        return "NON_RISPONDE"
    return "NON_RISPONDE"


_QUALIFICA_KEYS = {
    "tipologia_immobile",
    "metratura",
    "zona",
    "via",
    "urgenza_vendita",
    "agenzia_precedente",
    "motivo_no_vendita",
    "ads_source",
    "note_pre_visita",
}


async def _save_call_profile_data(
    provider_call_id: str,
    variable_values: dict,
) -> None:
    """Persiste le variabili di qualifica VAPI nel profilo CRM del cliente."""
    if not variable_values or not provider_call_id:
        return
    row_call = crud.get_call_by_sid(provider_call_id)
    if not row_call or not row_call.get("client_id"):
        return
    client_id = int(row_call["client_id"])
    cli = crud.get_client(client_id) or {}
    ak = canonical_agent_key(str(cli.get("agent_key") or row_call.get("agent_key") or ""))
    try:
        crud.assert_client_agent_scope(client_id, ak, context="save_call_profile")
    except ValueError:
        return
    allowed = (
        _SARA_TRANSCRIPT_KEYS
        if ak == "sara"
        else _QUALIFICA_KEYS
    )
    profile_data = {
        k: str(v).strip()
        for k, v in variable_values.items()
        if k in allowed and str(v or "").strip()
    }
    if ak == "gloria" and "via" in profile_data:
        from app.agencies import get_agency, get_agency_citta, resolve_agency_slug_for_client
        from crm.address_validation import resolve_gloria_via_for_save

        agency_slug = resolve_agency_slug_for_client(
            client_id=client_id,
            agent_key=ak,
        )
        agency_city = get_agency_citta(get_agency(agency_slug))
        resolved_via = await resolve_gloria_via_for_save(
            profile_data["via"],
            zona=profile_data.get("zona") or cli.get("zona"),
            citta=str(cli.get("citta") or agency_city or "").strip() or None,
            existing_via=cli.get("via"),
        )
        if resolved_via:
            profile_data["via"] = resolved_via
        else:
            profile_data.pop("via", None)
    if not profile_data:
        return
    try:
        crud.update_client(client_id, **profile_data)
        logger.info(
            "end-of-call: profilo aggiornato client_id=%s campi=%s",
            client_id,
            list(profile_data.keys()),
        )
    except Exception:
        logger.exception(
            "end-of-call: update_client fallito client_id=%s", client_id
        )


_SARA_TRANSCRIPT_KEYS = frozenset(
    {
        "citta",
        "nome_agenzia",
        "collaboratori_num",
        "obiettivo_vendite",
        "note_call",
    }
)


async def _extract_profile_from_transcript(
    transcript: str,
    agent_key: str,
) -> dict:
    """Estrae dati di qualifica dal transcript con LLM. Ritorna dict o {}."""
    if not transcript or len(transcript.strip()) < 50:
        return {}
    ak = canonical_agent_key(agent_key)
    if ak == "sara":
        return await _extract_sara_profile_from_transcript(transcript)
    if ak != "gloria":
        return {}

    api_key = _os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    prompt = f"""Analizza questa trascrizione di una chiamata immobiliare e
estrai SOLO i dati che il cliente ha esplicitamente menzionato.
Rispondi SOLO con un JSON valido, nessun testo aggiuntivo.
Se un dato non è menzionato, NON includerlo nel JSON.

Campi possibili (usa esattamente questi nomi):
- tipologia_immobile: tipo di immobile (es. "appartamento", "villa", "negozio")
- metratura: dimensione (es. "80mq", "circa 100 metri")
- zona: zona o quartiere dell'immobile
- via: via e numero civico dell'immobile
- urgenza_vendita: da quanto cerca di vendere o urgenza
- agenzia_precedente: agenzie già contattate
- motivo_no_vendita: perché non ha venduto con altri
- note_pre_visita: qualsiasi altra info rilevante

Trascrizione:
{transcript[:3000]}

JSON:"""

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 300,
                },
            )
        if resp.status_code != 200:
            logger.warning(
                "extract_profile: OpenAI status=%s", resp.status_code
            )
            return {}
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # rimuovi eventuali backtick markdown
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return _json.loads(content.strip())
    except Exception as exc:
        logger.warning("extract_profile: fallito (%s)", exc)
        return {}


async def _extract_sara_profile_from_transcript(transcript: str) -> dict:
    """Estrae dati outbound (Sara) dal transcript con LLM."""
    if not transcript or len(transcript.strip()) < 50:
        return {}

    api_key = _os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    prompt = f"""Analizza questa trascrizione di una chiamata outbound per agenzie
immobiliari (Evolution Media) ed estrai SOLO i dati che il cliente ha detto
esplicitamente. Rispondi SOLO con JSON valido, nessun testo aggiuntivo.
Se un dato non è menzionato, NON includerlo.

Campi possibili (nomi esatti):
- citta: città/comune dell'agenzia (es. "Roma", "Milano")
- nome_agenzia: nome commerciale dell'agenzia
- collaboratori_num: numero collaboratori (solo cifra, es. "3")
- obiettivo_vendite: obiettivo fatturato/vendite per l'anno
- note_call: note brevi sulla chiamata o correzioni nome

Trascrizione:
{transcript[:3000]}

JSON:"""

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 300,
                },
            )
        if resp.status_code != 200:
            logger.warning(
                "extract_sara_profile: OpenAI status=%s", resp.status_code
            )
            return {}
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = _json.loads(content.strip())
        if not isinstance(parsed, dict):
            return {}
        return parsed
    except Exception as exc:
        logger.warning("extract_sara_profile: fallito (%s)", exc)
        return {}


# ----- factory router -------------------------------------------------


ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str]]


def _resolve_dispatchers(dispatcher: Any) -> Any:
    """Risolve la sorgente dispatcher: closure → dict[str, CallDispatcher] o singolo."""
    if dispatcher is None:
        return None
    if hasattr(dispatcher, "mark_call_completed"):
        return dispatcher
    if callable(dispatcher):
        try:
            return dispatcher()
        except Exception as exc:  # noqa: BLE001
            logger.warning("vapi webhook: dispatcher closure ha sollevato: %s", exc)
            return None
    return dispatcher


def _resolve_dispatcher_for_agent(
    dispatcher: Any,
    agent_key: str,
    *,
    default_agent_key: str = "gloria",
) -> Any:
    """Da dict di dispatchers (multi-agente) o singolo dispatcher."""
    source = _resolve_dispatchers(dispatcher)
    if source is None:
        return None
    ak = (agent_key or default_agent_key).strip().lower() or default_agent_key
    if isinstance(source, dict):
        resolved = source.get(ak)
        if resolved is None:
            logger.warning(
                "vapi webhook: nessun dispatcher per agent_key=%s (disponibili=%s)",
                ak,
                list(source.keys()),
            )
        return resolved
    return source


def build_webhook_router(
    *,
    provider: TelephonyProvider,
    crm: CRMProvider,
    dispatcher: Any,
    tool_handler: ToolHandler,
    sheet_writers: Mapping[str, Any] | None = None,
) -> APIRouter:
    """Costruisce APIRouter con POST /vapi/webhook.

    `dispatcher` può essere l'oggetto stesso (con `mark_call_completed`) oppure
    una closure no-arg che lo restituisce a runtime (utile con `lifespan`).
    Se manca, il completion viene solo loggato.
    """
    router = APIRouter()

    @router.post("/vapi/webhook")
    async def vapi_webhook(request: Request) -> dict[str, Any]:
        body = await request.body()
        hdrs = dict(request.headers)
        if not provider.verify_signature(hdrs, body):
            logger.warning(
                "vapi webhook: autenticazione fallita (body_len=%s, has_sig=%s, has_secret=%s)",
                len(body),
                any(k.lower() == "x-vapi-signature" for k in hdrs),
                any(k.lower() == "x-vapi-secret" for k in hdrs),
            )
            raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("vapi webhook: body non JSON valido: %s", exc)
            raise HTTPException(status_code=400, detail="invalid JSON") from exc

        event = provider.parse_webhook(payload)
        event_type = str(event.get("type") or "").strip()
        provider_call_id = str(event.get("provider_call_id") or "").strip()

        if event_type == "call-started":
            return await _on_call_started(crm, event, provider_call_id)

        if event_type == "transcript":
            return _on_transcript(crm, event, provider_call_id)

        if event_type == "end-of-call":
            metadata = dict(event.get("metadata") or {})
            agent_key = str(metadata.get("agent_key") or "gloria")
            return await _on_end_of_call(
                crm,
                _resolve_dispatcher_for_agent(dispatcher, agent_key),
                event,
                provider_call_id,
                provider=provider,
                sheet_writers=sheet_writers or {},
            )

        if event_type == "tool-call":
            return await _on_tool_call(tool_handler, event)

        # eventi non gestiti: ack ma niente effetti collaterali
        logger.debug(
            "vapi webhook: evento ignorato type=%s subtype=%s",
            event_type,
            event.get("subtype"),
        )
        return {"ok": True, "ignored": True}

    return router


# ----- handler per tipo evento ----------------------------------------


async def _on_call_started(
    crm: CRMProvider,
    event: Mapping[str, Any],
    provider_call_id: str,
) -> dict[str, Any]:
    if not provider_call_id:
        return {"ok": False, "reason": "missing provider_call_id"}
    metadata: dict[str, Any] = dict(event.get("metadata") or {})
    client_id_raw = metadata.get("client_id")
    agent_key = str(metadata.get("agent_key") or "gloria")
    try:
        client_id = int(client_id_raw) if client_id_raw is not None else None
    except (TypeError, ValueError):
        client_id = None

    if client_id is None:
        logger.warning(
            "vapi call-started: client_id mancante nei metadata (call=%s)",
            provider_call_id,
        )
        return {"ok": False, "reason": "missing client_id in metadata"}

    ak = canonical_agent_key(agent_key)
    try:
        crud.assert_client_agent_scope(client_id, ak, context="call-started")
    except ValueError as exc:
        phone_meta = str(metadata.get("customer_phone") or "").strip()
        alt_id = crud.resolve_outbound_client_id(
            ak,
            client_id=client_id,
            telefono=phone_meta or None,
            create_if_missing=False,
        )
        if alt_id is None:
            logger.warning(
                "vapi call-started: agent mismatch call=%s err=%s",
                provider_call_id,
                exc,
            )
            return {"ok": False, "reason": str(exc)}
        client_id = int(alt_id)
        metadata["client_id"] = client_id

    try:
        crm.create_call(
            client_id=client_id,
            call_id=provider_call_id,
            agent_key=ak,
            metadata=metadata,
        )
        crud.update_call_status(provider_call_id, "in-progress")
        crud.set_client_in_chiamata(
            int(client_id),
            call_sid=provider_call_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi call-started: crm.create_call fallito: %s", exc)
        return {"ok": False, "reason": str(exc)}
    return {"ok": True}


def _on_transcript(
    crm: CRMProvider,
    event: Mapping[str, Any],
    provider_call_id: str,
) -> dict[str, Any]:
    if not provider_call_id:
        return {"ok": False, "reason": "missing provider_call_id"}
    # Persistiamo solo i transcript finali per non inondare il DB con interim.
    if event.get("is_final") is False:
        return {"ok": True, "ignored": "interim"}
    role = str(event.get("role") or "").strip() or "system"
    text = str(event.get("text") or "").strip()
    if not text:
        return {"ok": True, "ignored": "empty text"}
    try:
        crm.add_transcript(provider_call_id, role=role, text=text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi transcript: crm.add_transcript fallito: %s", exc)
        return {"ok": False, "reason": str(exc)}
    if role in ("assistant", "bot"):
        try:
            row = crud.get_call_by_sid(provider_call_id) or {}
            meta = dict(event.get("metadata") or {})
            ak = str(
                meta.get("agent_key")
                or row.get("agent_key")
                or ""
            ).strip().lower()
            if ak == "sara":
                from telephony.vapi.pitch_bridge import on_sara_assistant_transcript

                on_sara_assistant_transcript(provider_call_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("pitch_bridge transcript hook: %s", exc)
    return {"ok": True}


async def _on_end_of_call(
    crm: CRMProvider,
    dispatcher: Any,
    event: Mapping[str, Any],
    provider_call_id: str,
    *,
    provider: TelephonyProvider | None = None,
    sheet_writers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not provider_call_id:
        return {"ok": False, "reason": "missing provider_call_id"}
    # Idempotenza: VAPI può ritrasmettere lo stesso end-of-call. Se la chiamata è
    # già "completed" evita doppio billing, doppio retry e doppi eventi.
    try:
        existing_call = crud.get_call_by_sid_raw(provider_call_id)
        if existing_call and str(existing_call.get("status") or "") == "completed":
            logger.info(
                "end-of-call: evento duplicato ignorato call=%s", provider_call_id[:18]
            )
            return {"ok": True, "duplicate": True}
    except Exception as exc:  # noqa: BLE001
        logger.debug("end-of-call: check idempotenza fallito (procedo): %s", exc)
    try:
        from telephony.vapi.pitch_bridge import unregister_sara_pitch_bridge

        unregister_sara_pitch_bridge(provider_call_id)
    except Exception:  # noqa: BLE001
        pass
    ended_reason = str(event.get("ended_reason") or "").strip()
    metrics = extract_end_of_call_metrics(event)
    duration = metrics.get("duration_seconds")
    if duration is None:
        duration = event.get("duration_seconds")
    duration_int: int | None = None
    if duration is not None:
        try:
            duration_int = max(0, int(duration))
        except (TypeError, ValueError):
            duration_int = None
    vapi_cost = metrics.get("vapi_cost_usd")
    if vapi_cost is None:
        raw_cost = event.get("vapi_cost_usd")
        if raw_cost is not None:
            try:
                vapi_cost = float(raw_cost)
            except (TypeError, ValueError):
                vapi_cost = None
    recording_url = event.get("recording_url") or None
    transcript = str(event.get("transcript") or "")
    summary = str(event.get("summary") or "")
    try:
        crud.update_call_status(
            provider_call_id,
            status="completed",
            duration_seconds=duration_int,
            recording_url=recording_url,
        )
        crud.add_call_event(
            provider_call_id,
            "update_outcome_extra",
            {
                "summary": summary,
                "transcript_len": len(transcript),
                "ended_reason": ended_reason,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi end-of-call: update_call_status iniziale fallito: %s", exc)

    try:
        apply_call_billing(
            provider_call_id,
            duration_seconds=duration_int,
            vapi_cost_usd=vapi_cost,
        )
        if provider is not None:
            schedule_billing_sync(
                provider,
                provider_call_id,
                initial_duration=duration_int,
                initial_vapi_cost=vapi_cost,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi end-of-call: billing fallito: %s", exc)

    if ended_reason:
        try:
            crud.add_call_event(
                provider_call_id,
                "vapi_ended",
                {"ended_reason": ended_reason},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vapi end-of-call: vapi_ended event fallito: %s", exc)

    if is_voicemail_ended_reason(ended_reason):
        try:
            row_vm = crud.get_call_by_sid(provider_call_id)
            phone_vm = str(
                (row_vm or {}).get("cliente_telefono")
                or dict(event.get("metadata") or {}).get("customer_phone")
                or ""
            ).strip()
            ak_vm = canonical_agent_key(
                str(
                    (row_vm or {}).get("agent_key")
                    or dict(event.get("metadata") or {}).get("agent_key")
                    or "gloria"
                )
            )
            if phone_vm:
                tz_vm = get_business_timezone()
                until_vm = next_hour_datetime(
                    datetime.now(tz_vm),
                    tz_vm,
                )
                await dial_guard.mark_voicemail_cooldown(
                    phone_vm, ak_vm, until_at=until_vm
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vapi end-of-call: voicemail cooldown fallito: %s", exc)

    try:
        n = crud.ingest_vapi_transcript_report(
            provider_call_id,
            transcript,
            artifact=dict(event.get("artifact") or {}),
        )
        if n:
            logger.info(
                "vapi end-of-call: ingest transcript call=%s turns=%s",
                provider_call_id,
                n,
            )
        # Fallback: nessun turno ma la durata indica una conversazione reale →
        # ri-scarica il transcript da Vapi per non classificare come NON_RISPONDE.
        if not n and (duration_int or 0) >= _TRANSCRIPT_REFETCH_MIN_SECONDS:
            try:
                recovered = crud.refetch_and_ingest_vapi_transcript(provider_call_id)
                if recovered:
                    logger.info(
                        "vapi end-of-call: transcript recuperato via refetch "
                        "call=%s turns=%s dur=%ss",
                        provider_call_id[:18],
                        recovered,
                        duration_int,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "vapi end-of-call: refetch transcript fallito: %s", exc
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi end-of-call: ingest transcript fallito: %s", exc)

    try:
        payload = dict(event.get("raw") or {})
        variable_values = (
            payload.get("message", {})
            .get("artifact", {})
            .get("variableValues")
            or payload.get("message", {}).get("variableValues")
            or {}
        )
        await _save_call_profile_data(provider_call_id, variable_values)
    except Exception:
        logger.exception("end-of-call: salvataggio profilo fallito (non bloccante)")

    # Qualifica zona post-call (Gloria / immobiliare)
    try:
        row_call = crud.get_call_by_sid(provider_call_id)
        client_id_zone = (
            int(row_call["client_id"])
            if row_call and row_call.get("client_id")
            else None
        )
        if client_id_zone:
            metadata = dict(event.get("metadata") or {})
            agent_key_zone = str(
                metadata.get("agent_key")
                or (crud.get_client(client_id_zone) or {}).get("agent_key")
                or "gloria"
            )
            if agent_key_zone == "gloria":
                crud.apply_zone_target_status(
                    client_id_zone,
                    call_sid=provider_call_id,
                )
    except Exception as exc:
        logger.warning(
            "end-of-call: apply_zone_target_status fallito (non bloccante): %s",
            exc,
        )

    # Fallback: estrai profilo dal transcript se save_profile non ha dati
    try:
        row_call = crud.get_call_by_sid(provider_call_id)
        client_id_for_check = (
            int(row_call["client_id"])
            if row_call and row_call.get("client_id")
            else None
        )
        if client_id_for_check:
            existing = crud.get_client(client_id_for_check)
            agent_key_for_extract = str(
                (existing or {}).get("agent_key")
                or dict(event.get("metadata") or {}).get("agent_key")
                or "gloria"
            )
            ak_extract = canonical_agent_key(agent_key_for_extract)
            needs_extract = False
            if ak_extract == "gloria":
                needs_extract = any(
                    not str((existing or {}).get(k) or "").strip()
                    for k in (
                        "tipologia_immobile",
                        "zona",
                        "metratura",
                        "urgenza_vendita",
                        "via",
                    )
                )
            elif ak_extract == "sara":
                needs_extract = bool(
                    crud.missing_sara_qualification_fields(existing)
                )

            if needs_extract and transcript:
                extracted = await _extract_profile_from_transcript(
                    transcript, agent_key_for_extract
                )
                if extracted:
                    if ak_extract == "sara":
                        saveable = _SARA_TRANSCRIPT_KEYS
                    else:
                        saveable = {
                            "tipologia_immobile",
                            "metratura",
                            "zona",
                            "via",
                            "urgenza_vendita",
                            "agenzia_precedente",
                            "motivo_no_vendita",
                            "note_pre_visita",
                        }
                    to_save = {
                        k: str(v).strip()
                        for k, v in extracted.items()
                        if k in saveable and str(v or "").strip()
                    }
                    if ak_extract == "gloria" and "via" in to_save:
                        from app.agencies import (
                            get_agency,
                            get_agency_citta,
                            resolve_agency_slug_for_client,
                        )
                        from crm.address_validation import resolve_gloria_via_for_save

                        agency_slug = resolve_agency_slug_for_client(
                            client_id=client_id_for_check,
                            agent_key=ak_extract,
                        )
                        agency_city = get_agency_citta(get_agency(agency_slug))
                        resolved_via = await resolve_gloria_via_for_save(
                            to_save["via"],
                            zona=to_save.get("zona") or (existing or {}).get("zona"),
                            citta=str(
                                (existing or {}).get("citta") or agency_city or ""
                            ).strip()
                            or None,
                            existing_via=(existing or {}).get("via"),
                        )
                        if resolved_via:
                            to_save["via"] = resolved_via
                        else:
                            to_save.pop("via", None)
                    if to_save:
                        crud.update_client(client_id_for_check, **to_save)
                        logger.info(
                            "end-of-call: profilo estratto da transcript "
                            "client_id=%s campi=%s",
                            client_id_for_check,
                            list(to_save.keys()),
                        )
                        if ak_extract == "gloria":
                            crud.apply_zone_target_status(
                                client_id_for_check,
                                call_sid=provider_call_id,
                            )
    except Exception as exc:
        logger.warning(
            "end-of-call: extract_profile_from_transcript fallito "
            "(non bloccante): %s",
            exc,
        )

    # Fallback: richiamo concordato (giorno+ora) se schedule_callback non è stato usato in call
    try:
        from app.call_summary import build_transcript_dialogue
        from telephony.vapi.tools import schedule_agreed_callback_if_any

        row_call_cb = crud.get_call_by_sid(provider_call_id)
        metadata_cb = dict(event.get("metadata") or {})
        cid_cb = (
            int(row_call_cb["client_id"])
            if row_call_cb and row_call_cb.get("client_id")
            else None
        )
        if cid_cb:
            ak_cb = canonical_agent_key(
                str(
                    (crud.get_client(cid_cb) or {}).get("agent_key")
                    or metadata_cb.get("agent_key")
                    or "gloria"
                )
            )
            transcript_for_cb = transcript
            if len(str(transcript_for_cb or "").strip()) < 40:
                turns_cb = crud.list_transcript_turns_for_sid(provider_call_id)
                dialogue_cb = build_transcript_dialogue(turns_cb, agent_key=ak_cb)
                if len(dialogue_cb.strip()) >= 40:
                    transcript_for_cb = dialogue_cb
            today_cb = str(metadata_cb.get("today_date") or "").strip()
            if not today_cb:
                from crm.timezone import ROME_TZ
                from datetime import datetime as _dt

                today_cb = _dt.now(ROME_TZ).strftime("%Y-%m-%d")
            if transcript_for_cb:
                await schedule_agreed_callback_if_any(
                    client_id=cid_cb,
                    agent_key=ak_cb,
                    transcript=transcript_for_cb,
                    today_date=today_cb,
                    get_dispatchers=lambda: _resolve_dispatchers(dispatcher),
                    source="end_of_call_transcript",
                )
    except Exception as exc:
        logger.warning(
            "end-of-call: schedule_callback da transcript fallito "
            "(non bloccante): %s",
            exc,
        )

    decision = crud.build_call_outcome_decision(
        provider_call_id, duration_sec=duration_int
    )
    session_tag = decision.get("session_tag")
    esito = decision.get("final_tag") or "NON_RISPONDE"
    decision["ended_reason"] = ended_reason
    logger.info(
        "end-of-call: esito finale call=%s ended_reason=%r session_tag=%r dur=%ss "
        "engagement=%s refusal=%s slot=%s → %s (%s)",
        provider_call_id[:18],
        ended_reason,
        session_tag,
        duration_int,
        decision.get("has_real_engagement"),
        decision.get("explicit_refusal"),
        decision.get("slot_rejection"),
        esito,
        decision.get("reason"),
    )
    try:
        crud.add_call_event(provider_call_id, "outcome_decision", decision)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vapi end-of-call: audit outcome_decision fallito: %s", exc)

    final_esito: str | None = None
    try:
        final_esito = crud.apply_resolved_call_outcome(provider_call_id, esito)
    except Exception as exc:  # noqa: BLE001
        logger.exception("vapi end-of-call: apply_resolved_call_outcome fallito: %s", exc)

    try:
        crud.reconcile_call_outcome_with_session(provider_call_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "vapi end-of-call: reconcile_call_outcome_with_session fallito: %s", exc
        )

    try:
        row_finalize = crud.get_call_by_sid(provider_call_id)
        cid_finalize = (
            int(row_finalize["client_id"])
            if row_finalize and row_finalize.get("client_id") is not None
            else None
        )
        if cid_finalize is not None:
            session_tag = crud.get_call_session_outcome_tag(provider_call_id)
            if crud.esito_tag_blocks_retry(session_tag):
                fallback_stato = (
                    crud.stato_crm_for_esito_tag(session_tag) or "da_richiamare"
                )
            else:
                fallback_stato = (
                    crud.stato_crm_for_esito_tag(final_esito)
                    or crud.stato_crm_for_esito_tag(session_tag)
                    or crud.stato_crm_for_esito_tag(esito)
                    or "da_richiamare"
                )
            crud.finalize_client_stato_after_call(
                cid_finalize,
                fallback_stato=fallback_stato,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "vapi end-of-call: finalize_client_stato_after_call fallito: %s", exc
        )

    retry_esito = final_esito or esito
    if retry_esito in ("NON_RISPONDE", "RICHIAMARE"):
        try:
            row_call_retry = crud.get_call_by_sid(provider_call_id)
            metadata = dict(event.get("metadata") or {})
            agent_key_retry = canonical_agent_key(
                str(
                    (row_call_retry or {}).get("agent_key")
                    or metadata.get("agent_key")
                    or "gloria"
                )
            )
            if row_call_retry and row_call_retry.get("client_id") is not None:
                cid_retry = int(row_call_retry["client_id"])
                if (
                    crud.client_should_schedule_retry(
                        cid_retry,
                        call_sid=provider_call_id,
                    )
                    and not crud.is_precise_callback_pending(cid_retry)
                ):
                    crud.schedule_retry_after_no_answer(
                        cid_retry,
                        agent_key_retry,
                        ended_reason=ended_reason,
                    )
                elif not crud.client_should_schedule_retry(
                    cid_retry,
                    call_sid=provider_call_id,
                ) and not crud.is_precise_callback_pending(cid_retry):
                    # Non cancellare se è già stato programmato un richiamo concordato
                    # (precise callback) durante questo stesso end-of-call.
                    crud.cancel_outbound_queue_for_client(cid_retry)
                    logger.info(
                        "end-of-call: no richiamo client_id=%s (esito/stato terminale)",
                        cid_retry,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "vapi end-of-call: schedule_retry_after_no_answer fallito: %s", exc
            )

    # Persisti l'esito finale PRIMA di summary/sheet (step non bloccanti):
    # così UI e coda riflettono subito la decisione anche se il riassunto AI fallisce.
    try:
        crud.persist_call_completion(
            provider_call_id,
            outcome_tag=final_esito or esito,
            duration_sec=duration_int,
            recording_url=recording_url,
            extra={
                "summary": summary,
                "transcript_len": len(transcript),
                "ended_reason": ended_reason,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "vapi end-of-call: persist_call_completion finale fallito: %s", exc
        )

    mark_done = getattr(dispatcher, "mark_call_completed", None)
    if callable(mark_done):
        try:
            mark_done(provider_call_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "vapi end-of-call: dispatcher.mark_call_completed fallito: %s", exc
            )
    else:
        logger.debug(
            "vapi end-of-call: dispatcher non espone mark_call_completed (call=%s)",
            provider_call_id,
        )

    try:
        from app.call_summary import generate_call_summary

        summary_result = await generate_call_summary(
            provider_call_id,
            sheet_writers=sheet_writers or {},
        )
        if summary_result.get("summary"):
            logger.info(
                "vapi end-of-call: riassunto IT generato call=%s cached=%s "
                "outcome_applied=%s sheet_synced=%s",
                provider_call_id,
                summary_result.get("cached"),
                summary_result.get("outcome_applied"),
                summary_result.get("sheet_synced"),
            )
        elif summary_result.get("reason") not in (None, "not_generated"):
            logger.debug(
                "vapi end-of-call: riassunto IT skip call=%s reason=%s",
                provider_call_id,
                summary_result.get("reason"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "vapi end-of-call: generate_call_summary fallito (non bloccante): %s",
            exc,
        )

    try:
        from integrations.sheets.sync import sync_client_to_sheet

        row_call_sheet = crud.get_call_by_sid(provider_call_id)
        metadata_sheet = dict(event.get("metadata") or {})
        cid_sheet = (
            int(row_call_sheet["client_id"])
            if row_call_sheet and row_call_sheet.get("client_id") is not None
            else None
        )
        if cid_sheet is not None and sheet_writers:
            client_sheet = crud.get_client(cid_sheet) or {}
            ak_sheet = canonical_agent_key(
                str(
                    client_sheet.get("agent_key")
                    or metadata_sheet.get("agent_key")
                    or "gloria"
                )
            )
            if str(client_sheet.get("external_source") or "") == "google_sheet":
                await sync_client_to_sheet(
                    sheet_writers,
                    ak_sheet,
                    cid_sheet,
                    call_row=row_call_sheet,
                )
    except Exception as exc:
        logger.warning(
            "end-of-call: sheet sync fallito (non bloccante): %s", exc
        )

    return {"ok": True, "esito": final_esito or esito}


async def _on_tool_call(
    tool_handler: ToolHandler,
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """Esegue il tool e formatta la risposta nel formato che Vapi si aspetta."""
    tool_calls = list(event.get("tool_calls") or [])
    if not tool_calls:
        tool_call_id = str(event.get("tool_call_id") or "")
        try:
            result = await tool_handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("vapi tool-call: handler ha sollevato %s", exc)
            result = "Errore interno nell'esecuzione del tool."
        if not tool_call_id:
            return {"results": [{"result": result}]}
        return {"results": [{"toolCallId": tool_call_id, "result": result}]}

    results: list[dict[str, str]] = []
    for tc in tool_calls:
        tc_event = dict(event)
        tc_event["tool_name"] = tc.get("tool_name") or event.get("tool_name")
        tc_event["tool_call_id"] = tc.get("tool_call_id") or event.get("tool_call_id")
        tc_event["args"] = tc.get("args") or event.get("args") or {}
        tool_call_id = str(tc_event.get("tool_call_id") or "")
        try:
            result = await tool_handler(tc_event)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "vapi tool-call: handler ha sollevato %s (tool=%s)",
                exc,
                tc_event.get("tool_name"),
            )
            result = "Errore interno nell'esecuzione del tool."
        if tool_call_id:
            results.append({"toolCallId": tool_call_id, "result": result})
        else:
            results.append({"result": result})
    return {"results": results}
