# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""VapiProvider: implementazione del TelephonyProvider per Vapi (PSTN + LLM)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from typing import Any, Mapping, Optional

import httpx

from app.agencies import (
    resolve_agency_name_for_client,
    resolve_agency_appuntamento_con_for_client,
    resolve_agency_titolare_for_client,
)
from app.formatting import format_today_context_it
from crm import crud
from crm.phone import normalize_e164, is_valid_vapi_e164
from telephony.vapi.http import (
    VAPI_DIAL_TIMEOUT,
    VAPI_MAX_DURATION_SECONDS,
    vapi_async_transport,
)
from telephony.vapi.outbound_policy import (
    apply_outbound_call_policy,
    outbound_start_speaking_wait_seconds,
)
from telephony.vapi.pitch_bridge import fetch_control_url, register_sara_pitch_bridge
from telephony.vapi.tools import prefetch_sara_available_days
from telephony.vapi.webhooks import map_ended_reason_to_esito
from telephony.vapi.phone_registry import resolve_phone_number_id
from telephony.base import (
    CallOutcome,
    CallResult,
    TelephonyError,
    TelephonyProvider,
)

logger = logging.getLogger(__name__)

VAPI_BASE_URL = "https://api.vapi.ai"

# Messaggi utente per endedReason comuni (Vapi call logs).
_ENDED_REASON_USER_HINTS: dict[str, str] = {
    "call.start.error-get-transport": (
        "Vapi non riesce ad avviare la linea telefonica (credenziali Telnyx/Twilio "
        "in dashboard Vapi → Credentials, oppure numero non attivo per outbound)."
    ),
    "call.start.error-get-phone-number": (
        "Numero Vapi non trovato o non attivo: verifica VAPI_PHONE_NUMBER_ID_* nel .env "
        "e che il numero esista in dashboard Vapi."
    ),
    "call.in-progress.error-providerfault-outbound-sip-403-forbidden": (
        "Telnyx ha rifiutato la chiamata SIP outbound (403). "
        "Verifica trunk SIP su Telnyx/Vapi e credenziali nel .env."
    ),
}

# Pausa iniziale outbound: SSML nel firstMessage (startSpeakingPlan gestisce solo le risposte).
FIRST_MESSAGE_START_DELAY_S = 0.0


def first_message_with_start_delay(
    message: str,
    *,
    agent_key: str | None = None,
    outbound_initial: bool = False,
) -> str:
    """Restituisce firstMessage; su outbound antepone pausa SSML prima del saluto."""
    text = str(message or "").strip()
    if outbound_initial:
        wait_s = outbound_start_speaking_wait_seconds()
        if wait_s > 0:
            return f'<break time="{wait_s:.1f}s"/>{text}'
    return text


# firstMessage risolto a dial-time (VAPI non sostituisce [nome], usa {{name}} o override)
_FIRST_MESSAGE_BY_AGENT: dict[str, tuple[str, str]] = {
    "gloria": (
        "Ciao {name}, sono Gloria di {agency_name}, piacere! "
        "Ti contatto perché poco fa ci hai inviato una richiesta riguardo alla "
        "vendita del tuo immobile. Hai presente?",
        "Ciao, sono Gloria di {agency_name}, piacere! "
        "Ti contatto perché poco fa ci hai inviato una richiesta riguardo alla "
        "vendita del tuo immobile. Hai presente?",
    ),
    "gloria_richiamo_completo": (
        "Ciao {name}, sono Gloria di {agency_name}. "
        "Ti richiamo come concordato! Abbiamo già tutte le informazioni sul tuo "
        "immobile — hai un paio di minuti per fissare la chiamata con {titolare}?",
        "Ciao, sono Gloria di {agency_name}. "
        "Ti richiamo come concordato! Abbiamo già le informazioni sull'immobile — "
        "hai un paio di minuti per fissare la chiamata con {titolare}?",
    ),
    "gloria_richiamo_parziale": (
        "Ciao {name}, sono Gloria di {agency_name}. "
        "Ti richiamo come concordato! L'altra volta ci siamo interrotti — "
        "ti chiedo solo {missing} e poi fissiamo la chiamata con {titolare}, ok?",
        "Ciao, sono Gloria di {agency_name}. "
        "Ti richiamo come concordato! Ci siamo interrotti l'altra volta — "
        "ti faccio solo le ultime domande veloci e poi fissiamo la chiamata con "
        "{titolare}, ok?",
    ),
    "sara": (
        "Ciao, parlo con {name}? "
        "Sono Sara, l'assistente virtuale di Evolution Media.",
        "Ciao, con chi ho il piacere di parlare? "
        "Sono Sara, l'assistente virtuale di Evolution Media.",
    ),
    "sara_with_agenzia": (
        "Ciao, parlo con {name}? "
        "Sono Sara, l'assistente virtuale di Evolution Media.",
        "Ciao, con chi ho il piacere di parlare? "
        "Sono Sara, l'assistente virtuale di Evolution Media.",
    ),
}


def _customer_display_name(raw: str | None) -> str:
    """Prenome per il saluto (prima parola del nome CRM)."""
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.split()[0]


def _extract_recording_url(
    message: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> str | None:
    """URL registrazione da end-of-call-report VAPI (più chiavi possibili)."""
    candidates: list[Any] = []
    for src in (message, artifact):
        if not isinstance(src, Mapping):
            continue
        for key in (
            "recordingUrl",
            "recording_url",
            "stereoRecordingUrl",
            "stereoUrl",
            "recordingUri",
        ):
            candidates.append(src.get(key))
        rec = src.get("recording")
        if isinstance(rec, Mapping):
            candidates.extend(
                rec.get(k)
                for k in ("url", "recordingUrl", "stereoUrl", "uri")
            )
        recs = src.get("recordings")
        if isinstance(recs, list):
            for item in recs:
                if isinstance(item, Mapping):
                    candidates.extend(
                        item.get(k)
                        for k in ("url", "recordingUrl", "stereoUrl")
                    )
    for val in candidates:
        url = str(val or "").strip()
        if url.startswith("http"):
            return url
    return None


def _assistant_overrides(
    agent_key: str,
    customer_name: str | None,
    *,
    client_row: Mapping[str, Any] | None = None,
    customer_phone: str | None = None,
    prefetched_available_days: str = "",
    prefetched_available_days_tool: str = "",
) -> dict[str, Any]:
    """Override VAPI: variableValues + firstMessage con nome e profilo CRM."""
    ak = str(agent_key or "gloria").strip().lower() or "gloria"
    display = _customer_display_name(customer_name)
    if not display and client_row:
        display = _customer_display_name(
            str(client_row.get("nome") or client_row.get("titolare") or "")
        )
    overrides: dict[str, Any] = {}
    variable_values: dict[str, str] = {}
    if display:
        variable_values["name"] = display
    phone = str(customer_phone or "").strip()
    if not phone and client_row:
        phone = str(client_row.get("telefono") or "").strip()
    if phone:
        variable_values["customer_phone"] = phone
    if ak in ("gloria", "sara"):
        variable_values["today_date"] = format_today_context_it()
    if ak == "sara" and prefetched_available_days:
        variable_values["available_days"] = prefetched_available_days
        if prefetched_available_days_tool:
            variable_values["available_days_tool"] = prefetched_available_days_tool
    client_id: int | None = None
    if client_row and client_row.get("id") is not None:
        try:
            client_id = int(client_row["id"])
        except (TypeError, ValueError):
            client_id = None
    if ak == "gloria":
        if not variable_values.get("agency_name"):
            agency_name = resolve_agency_name_for_client(
                client_id=client_id,
                agent_key=ak,
            )
            if agency_name:
                variable_values["agency_name"] = agency_name
        if not variable_values.get("titolare_agenzia"):
            variable_values["titolare_agenzia"] = (
                resolve_agency_appuntamento_con_for_client(
                    client_id=client_id,
                    agent_key=ak,
                )
            )
        if not variable_values.get("nome_titolare_agenzia"):
            titolare = resolve_agency_titolare_for_client(
                client_id=client_id,
                agent_key=ak,
            )
            if titolare:
                variable_values["nome_titolare_agenzia"] = titolare
    if client_row and ak in ("gloria", "sara"):
        for k, v in crud.build_voice_variable_values(client_row).items():
            if k == "name" and variable_values.get("name"):
                continue
            if k == "telefono" and variable_values.get("customer_phone"):
                continue
            variable_values[k] = v
    if ak == "sara" and prefetched_available_days and display:
        agenzia = (
            str(variable_values.get("nome_agenzia") or "").strip()
            or "la tua agenzia"
        )
        variable_values["pitch_final_block"] = (
            f"questo comporta che il nominativo che porteremo a {display}, "
            f"oltre a conoscere {agenzia} e te, avrà una reale esigenza nel "
            f"vendere l'immobile perché dovrà passare una selezione interna da "
            f"parte nostra, anche perché noi non forniamo contatti ma andremo a "
            f"qualificare internamente il nominativo profilandolo per voi {display}. "
            f"Ti andrebbe di riprendere quel piccolo appuntamento con un nostro consulente?"
        )
    if variable_values:
        overrides["variableValues"] = variable_values
    agency_label = str(
        variable_values.get("agency_name") or "l'agenzia immobiliare"
    ).strip()
    titolare_label = str(
        variable_values.get("titolare_agenzia") or "un consulente"
    ).strip()
    template_key = ak
    if ak == "gloria" and client_row and crud.is_voice_callback_call(client_row):
        if crud.is_gloria_qualification_complete(client_row):
            template_key = "gloria_richiamo_completo"
        else:
            template_key = "gloria_richiamo_parziale"
    elif ak == "sara" and str(variable_values.get("nome_agenzia") or "").strip():
        template_key = "sara_with_agenzia"
    templates = _FIRST_MESSAGE_BY_AGENT.get(template_key) or _FIRST_MESSAGE_BY_AGENT.get(ak)
    if templates:
        with_name, without_name = templates
        fmt: dict[str, str] = {
            "name": display,
            "agency_name": agency_label,
            "nome_agenzia": str(variable_values.get("nome_agenzia") or "").strip(),
            "titolare": titolare_label,
            "missing": str(
                variable_values.get("missing_qualification") or "qualche dettaglio"
            ).strip(),
        }
        overrides["firstMessage"] = first_message_with_start_delay(
            (
                with_name.format(**fmt)
                if display
                else without_name.format(**fmt)
            ),
            agent_key=ak,
            outbound_initial=True,
        )
    return apply_outbound_call_policy(overrides, agent_key=ak)


class VapiProvider(TelephonyProvider):
    """Provider Vapi: POST /call per outbound, parse dei webhook in eventi normalizzati."""

    slug = "vapi"

    def __init__(
        self,
        api_key: str,
        webhook_secret: Optional[str] = None,
        *,
        assistant_id: str = "",
        phone_number_id: str = "",
        base_url: str = VAPI_BASE_URL,
    ) -> None:
        api_key = (api_key or "").strip()
        if not api_key:
            raise TelephonyError("VapiProvider: api_key vuoto")
        self._api_key = api_key
        self._assistant_id = (assistant_id or "").strip()
        self._phone_number_id = (phone_number_id or "").strip()
        self._webhook_secret = (webhook_secret or "").strip() or None
        self._base_url = base_url.rstrip("/")

    async def _verify_outbound_started(
        self,
        call_id: str,
        *,
        headers: Mapping[str, str],
    ) -> None:
        """Attende qualche secondo e fallisce se Vapi termina subito per errore transport."""
        active = frozenset({"queued", "ringing", "in-progress", "forwarding"})
        for _ in range(10):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(
                    timeout=VAPI_DIAL_TIMEOUT,
                    transport=vapi_async_transport(),
                ) as client:
                    resp = await client.get(
                        f"{self._base_url}/call/{call_id}",
                        headers=dict(headers),
                    )
            except httpx.HTTPError as exc:
                logger.warning(
                    "Vapi verify call_id=%s: probe rete fallita: %s", call_id, exc
                )
                return
            if resp.status_code >= 400:
                return
            data: dict[str, Any] = resp.json()
            status = str(data.get("status") or "").strip().lower()
            if status in active:
                return
            if status != "ended":
                continue
            reason = str(data.get("endedReason") or "").strip()
            hint = _ENDED_REASON_USER_HINTS.get(reason, "")
            msg = f"Vapi ha rifiutato la chiamata ({reason or 'ended'})."
            if hint:
                msg = f"{msg} {hint}"
            logger.error(
                "Vapi outbound fallita call_id=%s endedReason=%s phoneNumber=%s",
                call_id,
                reason,
                (data.get("phoneNumber") or {}).get("number"),
            )
            raise TelephonyError(msg)

    # ----- dial -------------------------------------------------------

    async def dial(
        self,
        to_number: str,
        *,
        agent_key: str,
        assistant_id: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> CallResult:
        """POST https://api.vapi.ai/call → CallResult(call_id=resp['id'], raw=resp).

        `assistant_id` / `phone_number_id` / `customer_name` opzionali: se
        non passati, si usano i default del costruttore (o, per il nome,
        `metadata.customer_name`/`metadata.nome`).
        """
        number = normalize_e164(to_number)
        if not number or not is_valid_vapi_e164(number):
            raise TelephonyError(
                f"VapiProvider.dial: numero non valido per Vapi (E.164): {to_number!r} → {number!r}"
            )

        aid = (assistant_id or self._assistant_id or "").strip()
        pnid = (phone_number_id or self._phone_number_id or "").strip()
        if not aid:
            raise TelephonyError("VapiProvider.dial: assistant_id mancante")
        if not pnid:
            raise TelephonyError("VapiProvider.dial: phone_number_id mancante")

        pnid, phone_row = resolve_phone_number_id(self._api_key, pnid)
        if str(phone_row.get("number") or ""):
            logger.debug(
                "Vapi dial: caller-id %s provider=%s",
                phone_row.get("number"),
                phone_row.get("provider"),
            )

        customer: dict[str, Any] = {"number": number}
        meta: dict[str, Any] = dict(metadata or {})
        name = (
            customer_name
            or meta.pop("customer_name", None)
            or meta.get("nome")
        )
        display_name = _customer_display_name(name)
        if display_name:
            customer["name"] = display_name
        # agent_key viaggia nei metadati per il riaggancio in parse_webhook → CRM.
        meta.setdefault("agent_key", agent_key)

        body: dict[str, Any] = {
            "assistantId": aid,
            "phoneNumberId": pnid,
            "customer": customer,
            "metadata": meta,
        }
        client_row: Mapping[str, Any] | None = None
        raw_cid = meta.get("client_id")
        if raw_cid is not None:
            try:
                client_row = crud.get_client(int(raw_cid))
            except (TypeError, ValueError) as exc:
                logger.warning("Vapi dial: client_id non valido %r: %s", raw_cid, exc)
            except Exception as exc:
                logger.warning(
                    "Vapi dial: impossibile caricare client_id=%s: %s",
                    raw_cid,
                    exc,
                )
        prefetched_days = ""
        prefetched_days_tool = ""
        if str(agent_key or "").strip().lower() == "sara":
            try:
                prefetched_days, prefetched_days_tool = (
                    await prefetch_sara_available_days(agent_key)
                )
            except Exception as exc:
                logger.warning(
                    "Vapi dial: prefetch giorni Sara fallito: %s", exc
                )
        overrides = _assistant_overrides(
            agent_key,
            name,
            client_row=client_row,
            customer_phone=number,
            prefetched_available_days=prefetched_days,
            prefetched_available_days_tool=prefetched_days_tool,
        )
        overrides.setdefault("maxDurationSeconds", VAPI_MAX_DURATION_SECONDS)
        body["assistantOverrides"] = overrides
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=VAPI_DIAL_TIMEOUT,
                transport=vapi_async_transport(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/call", json=body, headers=headers
                )
        except httpx.ReadTimeout as exc:
            raise TelephonyError(
                "Vapi non ha risposto entro 120 secondi. "
                "Riprova tra poco o verifica lo stato del servizio Vapi."
            ) from exc
        except httpx.HTTPError as exc:
            raise TelephonyError(f"Vapi /call errore di rete: {exc}") from exc

        if resp.status_code >= 400:
            logger.error(
                "Vapi /call status=%s body=%s", resp.status_code, resp.text[:500]
            )
            detail = resp.text[:300].strip()
            if "upstream connect error" in detail.lower():
                detail = (
                    "Vapi non riesce ad avviare la telefonia (provider upstream). "
                    "Verifica in dashboard Vapi che il numero sia attivo per outbound "
                    "e che Twilio/sip sia configurato correttamente."
                )
            raise TelephonyError(
                f"Vapi /call HTTP {resp.status_code}: {detail}"
            )

        data: dict[str, Any] = resp.json()
        call_id = str(data.get("id") or "").strip()
        if not call_id:
            raise TelephonyError("Vapi /call: 'id' mancante nella risposta")

        await self._verify_outbound_started(call_id, headers=headers)

        if str(agent_key or "").strip().lower() == "sara":
            pitch_block = str(
                (overrides.get("variableValues") or {}).get("pitch_final_block")
                or ""
            ).strip()
            if pitch_block:
                control_url = str(
                    (data.get("monitor") or {}).get("controlUrl") or ""
                ).strip()
                if not control_url:
                    control_url = await fetch_control_url(
                        self._api_key, call_id, base_url=self._base_url
                    )
                if control_url:
                    register_sara_pitch_bridge(call_id, control_url, pitch_block)
                else:
                    logger.warning(
                        "pitch_bridge: controlUrl assente call_id=%s", call_id
                    )

        return CallResult(
            call_id=call_id,
            outcome=CallOutcome.QUEUED,
            to_number=number,
            from_number=str(data.get("phoneNumber", {}).get("number") or ""),
            raw=data,
        )

    async def fetch_call_record(self, call_id: str) -> dict[str, Any]:
        """GET /call/:id — durata e costo finali (dopo end-of-call-report)."""
        cid = (call_id or "").strip()
        if not cid:
            return {}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=VAPI_DIAL_TIMEOUT,
                transport=vapi_async_transport(),
            ) as client:
                resp = await client.get(
                    f"{self._base_url}/call/{cid}",
                    headers=headers,
                )
            if resp.status_code >= 400:
                logger.warning(
                    "Vapi GET /call/%s status=%s", cid, resp.status_code
                )
                return {}
            data: dict[str, Any] = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Vapi GET /call/%s errore: %s", cid, exc)
            return {}

        duration = self._coerce_int(
            data.get("durationSeconds")
            or data.get("duration_seconds")
            or data.get("duration")
        )
        cost_raw = data.get("cost")
        cost_usd: float | None = None
        if cost_raw is not None and cost_raw != "":
            try:
                cost_usd = float(cost_raw)
            except (TypeError, ValueError):
                cost_usd = None
        return {
            "duration_seconds": duration if duration is not None and duration >= 0 else None,
            "vapi_cost_usd": cost_usd,
            "ended_reason": str(data.get("endedReason") or "").strip(),
            "status": str(data.get("status") or "").strip(),
        }

    # ----- parse_webhook ---------------------------------------------

    def parse_webhook(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalizza il payload Vapi in un evento {'type': ..., ...}.

        Tipi gestiti:
          * 'call-started' (da status-update con status='in-progress')
          * 'transcript'
          * 'end-of-call'
          * 'tool-call' (da function-call / tool-calls)
          * 'unknown' per tutto il resto
        """
        message: dict[str, Any] = dict(payload.get("message") or {})
        msg_type = str(message.get("type") or "").strip().lower()
        call = dict(message.get("call") or {})
        provider_call_id = str(call.get("id") or "").strip()
        metadata: dict[str, Any] = dict(call.get("metadata") or {})

        if msg_type in ("status-update", "status_update"):
            status = str(message.get("status") or "").strip().lower()
            if status in ("in-progress", "in_progress", "answered", "started"):
                return {
                    "type": "call-started",
                    "provider_call_id": provider_call_id,
                    "metadata": metadata,
                    "raw": dict(payload),
                }
            if status == "ended":
                ended_reason = str(
                    message.get("endedReason")
                    or message.get("ended_reason")
                    or call.get("endedReason")
                    or ""
                ).strip()
                duration_seconds = self._coerce_int(
                    message.get("durationSeconds")
                    or message.get("duration_seconds")
                    or message.get("duration")
                    or call.get("durationSeconds")
                    or call.get("duration")
                )
                return {
                    "type": "end-of-call",
                    "provider_call_id": provider_call_id,
                    "ended_reason": ended_reason,
                    "duration_seconds": duration_seconds,
                    "transcript": "",
                    "summary": "",
                    "recording_url": None,
                    "artifact": {},
                    "metadata": metadata,
                    "raw": dict(payload),
                }
            return {
                "type": "unknown",
                "provider_call_id": provider_call_id,
                "subtype": f"status-update/{status}",
                "raw": dict(payload),
            }

        if msg_type == "transcript":
            role = str(message.get("role") or "").strip().lower()
            text = str(message.get("transcript") or message.get("text") or "").strip()
            # Vapi a volte aggrega in transcriptType=final|interim
            transcript_type = str(message.get("transcriptType") or "").strip().lower()
            return {
                "type": "transcript",
                "provider_call_id": provider_call_id,
                "role": role,
                "text": text,
                "is_final": transcript_type in ("", "final"),
                "raw": dict(payload),
            }

        if msg_type in ("end-of-call-report", "end_of_call_report", "end-of-call"):
            artifact = dict(message.get("artifact") or {})
            transcript = (
                message.get("transcript")
                or artifact.get("transcript")
                or ""
            )
            summary = message.get("summary") or artifact.get("summary") or ""
            ended_reason = str(
                message.get("endedReason")
                or message.get("ended_reason")
                or call.get("endedReason")
                or ""
            ).strip()
            duration_seconds = self._coerce_int(
                message.get("durationSeconds")
                or message.get("duration_seconds")
                or message.get("duration")
                or call.get("durationSeconds")
                or call.get("duration")
            )
            cost_raw = message.get("cost")
            if cost_raw in (None, "", 0) and call.get("cost") not in (None, "", 0):
                cost_raw = call.get("cost")
            vapi_cost_usd: float | None = None
            if cost_raw not in (None, ""):
                try:
                    vapi_cost_usd = float(cost_raw)
                except (TypeError, ValueError):
                    vapi_cost_usd = None
            recording_url = _extract_recording_url(message, artifact)
            return {
                "type": "end-of-call",
                "provider_call_id": provider_call_id,
                "ended_reason": ended_reason,
                "duration_seconds": duration_seconds,
                "vapi_cost_usd": vapi_cost_usd,
                "transcript": str(transcript or ""),
                "summary": str(summary or ""),
                "recording_url": recording_url,
                "artifact": artifact,
                "call": call,
                "metadata": metadata,
                "raw": dict(payload),
            }

        if msg_type in ("tool-calls", "tool_calls", "function-call", "function_call"):
            # Vapi può inviare uno o più tool_calls in un singolo webhook.
            tool_calls_list = (
                message.get("toolCalls")
                or message.get("toolCallList")
                or message.get("functionCall")  # alias legacy
                or []
            )
            if isinstance(tool_calls_list, dict):
                tool_calls_list = [tool_calls_list]
            tools_out: list[dict[str, Any]] = []
            for tc in tool_calls_list:
                fn = dict(tc.get("function") or {})
                tool_name = str(
                    tc.get("name") or fn.get("name") or ""
                ).strip()
                tool_call_id = str(
                    tc.get("id") or tc.get("toolCallId") or ""
                ).strip()
                args = fn.get("arguments")
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_raw": args}
                if args is None:
                    args = tc.get("arguments") or {}
                tools_out.append(
                    {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "args": dict(args or {}),
                    }
                )
            # Compat: per webhook con singolo tool, espongo i campi al top level.
            single = tools_out[0] if len(tools_out) == 1 else None
            return {
                "type": "tool-call",
                "provider_call_id": provider_call_id,
                "tool_name": (single or {}).get("tool_name", ""),
                "tool_call_id": (single or {}).get("tool_call_id", ""),
                "args": (single or {}).get("args", {}),
                "tool_calls": tools_out,
                "metadata": metadata,
                "raw": dict(payload),
            }

        return {
            "type": "unknown",
            "provider_call_id": provider_call_id,
            "subtype": msg_type or "(empty)",
            "raw": dict(payload),
        }

    # ----- verify_signature -------------------------------------------

    @staticmethod
    def _normalize_vapi_signature(raw: str) -> str:
        provided = (raw or "").strip()
        if "," in provided:
            provided = provided.rsplit(",", 1)[-1].strip()
        if provided.lower().startswith("sha256="):
            provided = provided.split("=", 1)[1].strip()
        return provided

    @staticmethod
    def _webhook_body_hmac_candidates(body: bytes) -> list[bytes]:
        """Varianti del payload usate da VAPI per firmare (raw + JSON.stringify)."""
        candidates: list[bytes] = [body]
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return candidates
        for payload in (
            json.dumps(parsed, ensure_ascii=False),
            json.dumps(parsed, ensure_ascii=True),
            json.dumps(parsed, separators=(",", ":"), ensure_ascii=False),
            json.dumps(parsed, separators=(",", ":"), ensure_ascii=True),
            json.dumps(parsed, sort_keys=True, separators=(",", ":")),
        ):
            encoded = payload.encode("utf-8")
            if encoded not in candidates:
                candidates.append(encoded)
        return candidates

    @staticmethod
    def _digest_matches_signature(digest: str, provided: str) -> bool:
        if hmac.compare_digest(digest, provided):
            return True
        if len(digest) == len(provided):
            return hmac.compare_digest(digest.lower(), provided.lower())
        return False

    def verify_signature(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Autentica webhook VAPI.

        Supporta:
        - Legacy: header ``X-Vapi-Secret`` con token in chiaro (server.headers).
        - Moderno: ``x-vapi-signature`` HMAC-SHA256 del body.

        Se webhook_secret è None ritorna True (verifica disattivata).
        """
        if self._webhook_secret is None:
            return True
        if not body:
            return False

        secret_header = ""
        signature_header = ""
        for k, v in headers.items():
            lk = k.lower()
            if lk == "x-vapi-secret":
                secret_header = (v or "").strip()
            elif lk == "x-vapi-signature":
                signature_header = self._normalize_vapi_signature(v or "")

        if secret_header and hmac.compare_digest(secret_header, self._webhook_secret):
            return True

        if not signature_header:
            return False

        key = self._webhook_secret.encode("utf-8")
        for candidate in self._webhook_body_hmac_candidates(body):
            digest = hmac.new(key, candidate, hashlib.sha256).hexdigest()
            if self._digest_matches_signature(digest, signature_header):
                return True
        return False

    # ----- helpers ----------------------------------------------------

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
