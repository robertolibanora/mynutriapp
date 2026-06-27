"""Sincronizzazione CRM → Google Sheet (write-back post-chiamata)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Mapping

from app.call_summary import summary_text_for_sheet
from app.config import canonical_agent_key
from crm import crud
from crm.timezone import ROME_TZ

logger = logging.getLogger(__name__)

# Valori dropdown «Esito chiamata» / «Status» nel foglio (allineati al CRM).
_SHEET_DA_RICHIAMARE = "Da richiamare"

_ESITO_TAG_TO_SHEET: dict[str, str] = {
    "APPUNTAMENTO": "Appuntamento",
    "RICHIAMARE": _SHEET_DA_RICHIAMARE,
    "NON_RISPONDE": _SHEET_DA_RICHIAMARE,
    "NON_INTERESSATO": "Non interessato",
    "NUMERO_ERRATO": "Annullato",
    "NON_IN_TARGET": "Fuori zona",
    "ANNULLATO": _SHEET_DA_RICHIAMARE,
    "ERRORE": "Annullato",
}

_STATO_TO_ESITO_SHEET: dict[str, str] = {
    "non_in_target": "Fuori zona",
    "da_richiamare": _SHEET_DA_RICHIAMARE,
    "richiamare": _SHEET_DA_RICHIAMARE,
    "appuntamento_fissato": "Appuntamento",
    "appuntamento": "Appuntamento",
    "non_interessato": "Non interessato",
    "max_tentativi": _SHEET_DA_RICHIAMARE,
    "numero_errato": "Annullato",
    "chiamato": _SHEET_DA_RICHIAMARE,
    "in_chiamata": "In Chiamata",
    "in_coda": "In coda",
}


def format_stato_for_sheet(stato: str | None) -> str:
    """Retro-compat: alias di esito_chiamata."""
    return format_esito_chiamata({"stato": stato})


def format_esito_chiamata(
    client: Mapping[str, Any],
    *,
    call: Mapping[str, Any] | None = None,
) -> str:
    stato = str(client.get("stato") or "").strip().lower()
    if stato in _STATO_TO_ESITO_SHEET:
        mapped = _STATO_TO_ESITO_SHEET[stato]
        if mapped or stato == "da_chiamare":
            if mapped:
                return mapped

    tag = str(client.get("ultimo_esito") or "").strip().upper().replace("-", "_")
    if tag in _ESITO_TAG_TO_SHEET:
        return _ESITO_TAG_TO_SHEET[tag]

    if call:
        outcome = str(call.get("outcome") or "").strip().lower()
        if outcome == "appointment_set":
            return "Appuntamento"
        if outcome == "not_in_target":
            return "Fuori zona"
        if outcome in ("no_answer", "callback_requested"):
            return _SHEET_DA_RICHIAMARE
        if outcome == "not_interested":
            return "Non interessato"
        if outcome in ("cancelled_or_neutral",):
            return _SHEET_DA_RICHIAMARE
        if outcome == "wrong_number":
            return "Annullato"

    return ""


def format_date_it(value: Any) -> str:
    """Data in formato foglio: DD/MM/YYYY."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ROME_TZ)
        else:
            dt = dt.astimezone(ROME_TZ)
        return dt.strftime("%d/%m/%Y")

    raw = str(value).strip()
    if not raw:
        return ""

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19], fmt).replace(tzinfo=ROME_TZ)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return raw[:10]
    return raw[:10]


def format_ora_appuntamento_sheet(time_value: str) -> str:
    """Ora appuntamento descrittiva come nel foglio (es. «nel pomeriggio»)."""
    raw = str(time_value or "").strip()
    if not raw:
        return ""

    lower = raw.lower()
    if any(
        phrase in lower
        for phrase in (
            "mattin",
            "pomerigg",
            "sera",
            "pranzo",
            "maggio",
            "giugno",
            "aprile",
            "metà",
        )
    ):
        return raw

    hhmm = raw[:5] if len(raw) >= 5 and raw[2:3] == ":" else ""
    if not hhmm:
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 4:
            hhmm = f"{digits[:2]}:{digits[2:4]}"
    if not hhmm:
        return raw

    try:
        hour = int(hhmm.split(":", 1)[0])
    except ValueError:
        return raw

    if 9 <= hour < 12:
        fascia = "in mattinata"
    elif 12 <= hour < 14:
        fascia = "a pranzo"
    elif 14 <= hour < 18:
        fascia = "nel pomeriggio"
    elif hour >= 18:
        fascia = "in serata"
    else:
        fascia = f"alle {hhmm}"

    if fascia.startswith("alle"):
        return fascia
    return f"{fascia} (ore {hhmm})"


def _parse_event_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _call_outcome_label(call: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    tag = str(payload.get("esito_gpt") or "").strip().upper().replace("-", "_")
    if tag in _ESITO_TAG_TO_SHEET:
        return _ESITO_TAG_TO_SHEET[tag]
    label = str(call.get("outcome_label") or "").strip()
    if label:
        return label
    outcome = str(call.get("outcome") or "").strip().lower()
    mapping = {
        "appointment_set": "Appuntamento",
        "callback_requested": _SHEET_DA_RICHIAMARE,
        "no_answer": _SHEET_DA_RICHIAMARE,
        "not_interested": "Non interessato",
        "not_in_target": "Fuori zona",
        "wrong_number": "Annullato",
        "cancelled_or_neutral": _SHEET_DA_RICHIAMARE,
    }
    return mapping.get(outcome, outcome.replace("_", " ").title() if outcome else "Chiamata")


_TAG_PRIORITY: dict[str, int] = {
    "APPUNTAMENTO": 100,
    "NON_IN_TARGET": 90,
    "NON_INTERESSATO": 85,
    "RICHIAMARE": 80,
    "NON_RISPONDE": 80,
    "NUMERO_ERRATO": 70,
    "ANNULLATO": 20,
    "ERRORE": 10,
}


def collect_call_notes_history(client_id: int) -> list[str]:
    """Righe cronologiche «[data ora] Esito: nota» per ogni chiamata del prospect."""
    lines: list[str] = []
    client = crud.get_client(int(client_id)) or {}
    client_stato = str(client.get("stato") or "").strip().lower()
    calls = crud.list_calls(client_id=int(client_id), limit=100)
    for call in reversed(calls):
        call_pk = call.get("call_db_id") or call.get("id")
        if call_pk is None:
            continue
        when = crud.format_call_note_timestamp(call.get("started_at"))
        tags: list[str] = []
        note_parts: list[str] = []

        call_sid = str(call.get("call_sid") or "").strip()
        ai_note = summary_text_for_sheet(
            crud.get_call_ai_summary(call_sid) if call_sid else None
        )
        if ai_note and ai_note not in note_parts:
            note_parts.append(ai_note)

        for ev in crud.list_call_events(int(call_pk)):
            payload = _parse_event_payload(ev.get("payload_json"))
            et = str(ev.get("event_type") or "").strip()
            if et == "session_outcome":
                tag = str(payload.get("esito_gpt") or "").strip().upper().replace("-", "_")
                if tag:
                    tags.append(tag)
                note = str(payload.get("note_sessione") or "").strip()
                if note and note not in note_parts and note not in ai_note:
                    note_parts.append(note)

        esito_label = _call_outcome_label(call, {})
        if tags:
            best_tag = max(tags, key=lambda t: _TAG_PRIORITY.get(t, 0))
            if (
                client_stato == "appuntamento_fissato"
                and "APPUNTAMENTO" in tags
            ):
                best_tag = "APPUNTAMENTO"
            esito_label = _ESITO_TAG_TO_SHEET.get(
                best_tag, best_tag.replace("_", " ").title()
            )

        body = "; ".join(note_parts).strip()
        if body or esito_label:
            if body:
                lines.append(f"[{when}] {esito_label}: {body}")
            else:
                lines.append(f"[{when}] {esito_label}")

    return lines


def _legacy_note_fragments(client: Mapping[str, Any], history: list[str]) -> list[str]:
    """Frammenti già in note_pre_visita non presenti nello storico chiamate."""
    legacy = str(client.get("note_pre_visita") or "").strip()
    if not legacy:
        return []
    history_blob = "\n".join(history)
    out: list[str] = []
    for chunk in re.split(r"[\n;]+", legacy):
        text = chunk.strip()
        if not text:
            continue
        if text in history_blob:
            continue
        if any(text in line for line in history):
            continue
        if text not in out:
            out.append(text)
    return out


def build_note_pre_visita_sheet(
    client: Mapping[str, Any],
    *,
    call: Mapping[str, Any] | None = None,
) -> str:
    """Note leggibili per il foglio: qualifica + storico di tutte le chiamate."""
    blocks: list[str] = []

    qualifica: list[str] = []
    for label, key in (
        ("Tipologia", "tipologia_immobile"),
        ("Metratura", "metratura"),
        ("Zona", "zona"),
        ("Urgenza vendita", "urgenza_vendita"),
        ("Via", "via"),
        ("Agenzia precedente", "agenzia_precedente"),
    ):
        val = str(client.get(key) or "").strip()
        if val:
            qualifica.append(f"{label}: {val}")
    if qualifica:
        blocks.append(" · ".join(qualifica))

    cid = client.get("id")
    history: list[str] = []
    if cid is not None:
        history = collect_call_notes_history(int(cid))
    if history:
        blocks.extend(history)

    for fragment in _legacy_note_fragments(client, history):
        blocks.append(fragment)

    note_call = str(client.get("note_call") or "").strip()
    if note_call and note_call not in "\n".join(blocks):
        blocks.append(note_call)

    if call:
        call_sid = str(call.get("call_sid") or "").strip()
        summary = summary_text_for_sheet(
            crud.get_call_ai_summary(call_sid) if call_sid else None
        )
        if summary and summary not in "\n".join(blocks):
            when = crud.format_call_note_timestamp(call.get("started_at"))
            label = _call_outcome_label(call, {})
            blocks.append(f"[{when}] {label}: {summary}")

    return "\n".join(blocks).strip()


def _appointment_times_for_client(client_id: int) -> tuple[str, str]:
    """Ultimo appuntamento confermato → (data ISO, ora HH:MM)."""
    from crm.database import get_conn

    conn = get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT start_time
                FROM appointments
                WHERE client_id = %s AND status = 'confirmed'
                ORDER BY start_time DESC
                LIMIT 1
                """,
                (int(client_id),),
            )
            row = cur.fetchone()
        finally:
            cur.close()
    finally:
        conn.close()
    if not row or not row[0]:
        return "", ""
    start = row[0]
    if isinstance(start, datetime):
        if start.tzinfo is None:
            start = start.replace(tzinfo=ROME_TZ)
        else:
            start = start.astimezone(ROME_TZ)
        return start.strftime("%Y-%m-%d"), start.strftime("%H:%M")
    text = str(start).strip()
    if len(text) >= 16:
        return text[:10], text[11:16]
    if len(text) >= 10:
        return text[:10], ""
    return "", ""


def build_client_sheet_updates(
    client: Mapping[str, Any],
    *,
    call: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Campi interni da scrivere sul foglio (chiavi = SHEET_WRITE_MAP values)."""
    updates: dict[str, Any] = {}

    esito = format_esito_chiamata(client, call=call)
    if esito:
        updates["esito_chiamata"] = esito
        updates["stato"] = esito

    contatto = client.get("ultimo_contatto_at")
    if contatto:
        updates["data_contatto"] = format_date_it(contatto)

    setter = str(client.get("setter") or "").strip()
    if setter:
        updates["setter"] = setter
    elif esito:
        updates["setter"] = "Gloria"

    call_sid = str(client.get("ultimo_call_sid") or "").strip()
    if call_sid:
        updates["id_chiamata"] = call_sid

    for field in (
        "zona",
        "tipologia_immobile",
        "metratura",
        "urgenza_vendita",
        "closer_assegnato",
        "closer_nome",
    ):
        val = client.get(field)
        if val is None or not str(val).strip():
            continue
        key = "closer_assegnato" if field == "closer_nome" else field
        updates[key] = str(val).strip()

    note = build_note_pre_visita_sheet(client, call=call)
    if note:
        updates["note_pre_visita"] = note

    data_appt = str(
        client.get("data_appuntamento") or client.get("pi_data_appuntamento") or ""
    ).strip()
    ora_appt = str(
        client.get("ora_appuntamento") or client.get("pi_ora_appuntamento") or ""
    ).strip()
    if not data_appt or not ora_appt:
        cid = client.get("id")
        if cid is not None:
            db_date, db_time = _appointment_times_for_client(int(cid))
            data_appt = data_appt or db_date
            ora_appt = ora_appt or db_time

    if data_appt:
        updates["data_appuntamento"] = format_date_it(data_appt)
    if ora_appt:
        updates["ora_appuntamento"] = format_ora_appuntamento_sheet(ora_appt)

    if call:
        rec = str(call.get("recording_url") or "").strip()
        if rec:
            updates["link_recording"] = rec

    if extra:
        for key, val in extra.items():
            if val is None:
                continue
            text = str(val).strip()
            if not text:
                continue
            if key == "data_appuntamento":
                updates[key] = format_date_it(text)
            elif key == "ora_appuntamento":
                updates[key] = format_ora_appuntamento_sheet(text)
            elif key == "stato":
                updates["esito_chiamata"] = text
                updates["stato"] = text
            else:
                updates[str(key)] = text

    return updates


async def sync_terminal_outcome_to_sheet(
    call_sid: str,
    *,
    sheet_writers: Mapping[str, Any] | None = None,
) -> bool:
    """Write-back su foglio dopo esito terminale applicato dal riassunto AI."""
    cs = (call_sid or "").strip()
    if not cs:
        return False
    row_call = crud.get_call_by_sid(cs)
    if not row_call or row_call.get("client_id") is None:
        return False
    client_id = int(row_call["client_id"])
    client = crud.get_client(client_id) or {}
    if str(client.get("external_source") or "") != "google_sheet":
        return False
    ak = canonical_agent_key(
        str(row_call.get("agent_key") or client.get("agent_key") or "gloria")
    )
    ok = await sync_client_to_sheet(
        sheet_writers or {},
        ak,
        client_id,
        call_row=row_call,
    )
    if ok:
        logger.info(
            "sheet sync esito terminale: call=%s client_id=%s esito=%s",
            cs[:18],
            client_id,
            format_esito_chiamata(client, call=row_call),
        )
    return ok


async def sync_client_to_sheet(
    sheet_writers: Mapping[str, Any],
    agent_key: str,
    client_id: int,
    *,
    extra_updates: Mapping[str, Any] | None = None,
    call_row: Mapping[str, Any] | None = None,
) -> bool:
    """Scrive la riga foglio collegata al client (se external_sheet_row presente)."""
    ak = canonical_agent_key(agent_key)
    row = crud.get_client(int(client_id)) or {}
    client_tab = str(row.get("external_sheet_tab") or "").strip()
    from integrations.factory import build_sheet_writer

    writer = build_sheet_writer(
        ak, reload_env=True, sheet_name=client_tab or None
    )
    if writer is None:
        writer = sheet_writers.get(ak)
    if writer is None:
        return False
    sheet_row = row.get("external_sheet_row")
    if sheet_row is None:
        logger.debug(
            "sheet sync skip: client_id=%s senza external_sheet_row",
            client_id,
        )
        return False
    try:
        sheet_row_i = int(sheet_row)
    except (TypeError, ValueError):
        logger.warning(
            "sheet sync skip: client_id=%s external_sheet_row=%r non valido",
            client_id,
            sheet_row,
        )
        return False

    if call_row is None:
        call_sid = str(row.get("ultimo_call_sid") or "").strip()
        if call_sid:
            call_row = crud.get_call_by_sid(call_sid)

    updates = build_client_sheet_updates(
        row, call=call_row, extra=extra_updates
    )
    if not updates:
        logger.debug("sheet sync skip: client_id=%s nessun campo da scrivere", client_id)
        return True

    ok = await asyncio.to_thread(writer.update_row, sheet_row_i, updates)
    if not ok:
        logger.warning(
            "sheet sync fallito client_id=%s row=%s campi=%s",
            client_id,
            sheet_row_i,
            list(updates.keys()),
        )
    return ok


async def export_clients_to_sheet(
    agent_key: str,
    *,
    sheet_id: str | None = None,
    client_ids: list[int] | None = None,
    writers: Mapping[str, Any] | None = None,
) -> tuple[int, int, list[str]]:
    """Esporta tutti i client collegati al foglio (DB → Sheet).

    Ritorna (ok_count, total, errori).
    """
    ak = canonical_agent_key(agent_key)
    writer = (writers or {}).get(ak)
    if writer is None:
        from integrations.factory import build_sheet_writer

        writer = build_sheet_writer(ak)
    if writer is None:
        raise RuntimeError(
            f"SheetWriter non configurato per {ak}: "
            "verifica SHEET_WRITE_MAP, GOOGLE_CREDENTIALS_JSON, SHEET_ID"
        )

    writers_map = {ak: writer}
    sid = (sheet_id or "").strip()
    if not sid:
        import os

        sid = os.getenv(f"SHEET_ID_{ak.upper()}", "").strip()

    if client_ids:
        clients = []
        for cid in client_ids:
            row = crud.get_client(int(cid))
            if row:
                clients.append(row)
    else:
        clients = crud.list_clients(agent_key=ak, external_sheet_id=sid or None)
        if sid:
            clients = [
                c
                for c in clients
                if str(c.get("external_sheet_id") or "") == sid
            ]

    ok_n = 0
    errors: list[str] = []
    for c in clients:
        cid = c.get("id")
        if cid is None:
            continue
        sheet_row = c.get("external_sheet_row")
        if sheet_row is None:
            errors.append(f"client #{cid}: senza external_sheet_row")
            continue
        nome = str(c.get("nome") or f"#{cid}")
        if await sync_client_to_sheet(writers_map, ak, int(cid)):
            ok_n += 1
            logger.info(
                "export_sheet: OK client_id=%s row=%s nome=%r",
                cid,
                sheet_row,
                nome,
            )
        else:
            errors.append(f"client #{cid} riga {sheet_row}: scrittura fallita")

    return ok_n, len(clients), errors
