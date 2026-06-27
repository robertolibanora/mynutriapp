"""Estrazione giorno+ora per richiami concordati al telefono."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_WEEKDAY_IT: dict[str, int] = {
    "lunedi": 0,
    "lunedì": 0,
    "martedi": 1,
    "martedì": 1,
    "mercoledi": 2,
    "mercoledì": 2,
    "giovedi": 3,
    "giovedì": 3,
    "venerdi": 4,
    "venerdì": 4,
    "sabato": 5,
    "domenica": 6,
}

_MONTH_IT: dict[str, int] = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
}

_AGENT_SPEAKERS = frozenset(
    {"assistant", "agent", "bot", "gloria", "sara", "system", "agente"}
)

_AFFIRM_RE = re.compile(
    r"^(?:sì|si|va bene|ok|okay|perfetto|d'accordo|certo|proprio|esatto|"
    r"confermo|d accordo)\b",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    r"(?:"
    r"(?:alle|ore)\s+(\d{1,2})(?::(\d{2}))?"
    r"|(\d{1,2}):(\d{2})"
    r")",
    re.IGNORECASE,
)

_RELATIVE_DAY_RE = re.compile(
    r"\b(oggi|domani|dopodomani|"
    r"luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica)\b",
    re.IGNORECASE,
)

_DATE_NUM_RE = re.compile(
    r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b"
)

_DATE_TEXT_RE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_MONTH_IT.keys()) + r")\b",
    re.IGNORECASE,
)

_VAGUE_ONLY_RE = re.compile(
    r"\b(?:pomeriggio|mattina|mattino|sera|stasera|pranzo|"
    r"più tardi|piu tardi|tra un po|non lo so|non saprei|"
    r"non credo|incerto)\b",
    re.IGNORECASE,
)

_SPEAKER_LINE_RE = re.compile(r"^([^:]{1,40}):\s*(.+)$")


def _next_weekday(from_day: date, weekday: int) -> date:
    delta = (weekday - from_day.weekday()) % 7
    if delta == 0:
        delta = 7
    return from_day + timedelta(days=delta)


def _resolve_relative_day(token: str, today: date) -> date | None:
    key = (token or "").strip().lower()
    if key == "oggi":
        return today
    if key == "domani":
        return today + timedelta(days=1)
    if key == "dopodomani":
        return today + timedelta(days=2)
    if key in _WEEKDAY_IT:
        return _next_weekday(today, _WEEKDAY_IT[key])
    return None


def _parse_date_from_text(text: str, today: date) -> date | None:
    chunk = text or ""
    rel = _RELATIVE_DAY_RE.search(chunk)
    if rel:
        resolved = _resolve_relative_day(rel.group(1), today)
        if resolved is not None:
            return resolved

    dm = _DATE_NUM_RE.search(chunk)
    if dm:
        day = int(dm.group(1))
        month = int(dm.group(2))
        year_raw = dm.group(3)
        year = int(year_raw) if year_raw else today.year
        if year_raw and len(year_raw) == 2:
            year = 2000 + year
        try:
            return date(year, month, day)
        except ValueError:
            return None

    dt = _DATE_TEXT_RE.search(chunk)
    if dt:
        day = int(dt.group(1))
        month = _MONTH_IT[dt.group(2).lower()]
        year = today.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate < today - timedelta(days=1):
            candidate = date(year + 1, month, day)
        return candidate
    return None


def _parse_time_from_text(text: str) -> tuple[int, int] | None:
    chunk = text or ""
    if _VAGUE_ONLY_RE.search(chunk) and not _TIME_RE.search(chunk):
        return None
    match = _TIME_RE.search(chunk)
    if not match:
        return None
    if match.group(1) is not None:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
    else:
        hour = int(match.group(3))
        minute = int(match.group(4))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _combine(day: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute), tzinfo=tz)


def _line_parts(line: str) -> tuple[str, str]:
    match = _SPEAKER_LINE_RE.match(line.strip())
    if not match:
        return "", line.strip()
    return match.group(1).strip().lower(), match.group(2).strip()


def _is_agent_speaker(speaker: str) -> bool:
    s = (speaker or "").strip().lower()
    return s in _AGENT_SPEAKERS or s.startswith("sara") or s.startswith("gloria")


def extract_callback_heuristic(
    transcript: str,
    today_date: str,
    tz: ZoneInfo,
) -> datetime | None:
    """Estrae data/ora solo se compaiono giorno e ora numerica espliciti."""
    text = (transcript or "").strip()
    if len(text) < 20:
        return None
    try:
        today = date.fromisoformat(str(today_date)[:10])
    except ValueError:
        today = datetime.now(tz).date()

    lines = [ln for ln in text.splitlines() if ln.strip()]
    candidates: list[datetime] = []

    for idx, line in enumerate(lines):
        speaker, content = _line_parts(line)
        day = _parse_date_from_text(content, today)
        clock = _parse_time_from_text(content)
        if day is not None and clock is not None:
            candidates.append(_combine(day, clock[0], clock[1], tz))
            continue

        if clock is not None:
            context = content
            if day is None and idx > 0:
                _, prev_content = _line_parts(lines[idx - 1])
                context = f"{prev_content} {content}"
            day = _parse_date_from_text(context, today) or today
            if day is not None:
                candidates.append(_combine(day, clock[0], clock[1], tz))

        if _is_agent_speaker(speaker) and clock is not None:
            day = _parse_date_from_text(content, today) or today
            for j in range(idx + 1, min(idx + 4, len(lines))):
                next_speaker, next_content = _line_parts(lines[j])
                if _is_agent_speaker(next_speaker):
                    break
                if _AFFIRM_RE.match(next_content):
                    candidates.append(_combine(day, clock[0], clock[1], tz))
                    break

    if not candidates:
        return None

    now = datetime.now(tz)
    future = [dt for dt in candidates if dt >= now - timedelta(minutes=5)]
    if not future:
        return None
    return min(future)


async def extract_callback_llm(
    transcript: str,
    today_date: str,
) -> str | None:
    """LLM: richiamo concordato solo con giorno + ora espliciti."""
    text = (transcript or "").strip()
    if len(text) < 40:
        return None

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None

    prompt = f"""Analizza la trascrizione di una chiamata telefonica in italiano.
Oggi è {today_date} (fuso orario Italia).

Devi capire se è stato CONCORDATO un richiamo con giorno E ora precisa (con ore e minuti).

Conta come concordato SOLO se:
- L'interlocutore indica giorno E ora numerica ("domani alle 15", "lunedì 22 alle 10:30", "oggi alle 16")
- L'agente propone giorno+ora e l'interlocutore accetta ("sì", "va bene", "ok", "perfetto")

NON estrarre se:
- C'è solo una fascia vaga ("pomeriggio", "mattina", "più tardi") senza ora numerica
- L'interlocutore dice che non sa / non è sicuro dell'orario
- Non c'è un accordo chiaro su quando richiamare

Rispondi SOLO con JSON valido:
- Richiamo concordato con giorno+ora: {{"data_ora": "YYYY-MM-DDTHH:MM:SS"}}
- Altrimenti: {{}}

Trascrizione:
{text[:3500]}

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
                    "max_tokens": 120,
                },
            )
        if resp.status_code != 200:
            return None
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content.strip())
        if not isinstance(parsed, dict):
            return None
        raw = str(parsed.get("data_ora") or "").strip()
        return raw or None
    except Exception as exc:
        logger.warning("extract_callback_llm: fallito (%s)", exc)
        return None


async def resolve_agreed_callback_datetime(
    transcript: str,
    today_date: str,
    tz: ZoneInfo,
) -> datetime | None:
    """Heuristica prima, poi LLM; ritorna datetime locale concordato."""
    from telephony.vapi.tools import parse_callback_datetime

    heuristic = extract_callback_heuristic(transcript, today_date, tz)
    if heuristic is not None:
        return heuristic

    raw = await extract_callback_llm(transcript, today_date)
    if not raw:
        return None
    parsed = parse_callback_datetime(raw)
    if parsed is None:
        return None
    return parsed.astimezone(tz)


def callback_datetime_from_summary(summary: Mapping[str, Any] | None) -> datetime | None:
    """Legge data_ora dal blocco richiamo_concordato del riassunto AI."""
    from telephony.vapi.tools import parse_callback_datetime

    if not summary or not isinstance(summary, dict):
        return None
    block = summary.get("richiamo_concordato")
    if not isinstance(block, dict):
        return None
    raw = str(block.get("data_ora") or "").strip()
    if not raw:
        return None
    return parse_callback_datetime(raw)
