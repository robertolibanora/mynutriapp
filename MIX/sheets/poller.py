# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""SheetPoller agnostico: legge dal SheetProvider, upserta nel CRMProvider, enqueue.

Riceve via __init__ un `CRMProvider` e un `SheetProvider`: usa solo i metodi
dell'ABC (no import di crud specifici). Tutta la logica di scheduling è
opzionale e iniettabile via `schedule_retry`.
"""
from __future__ import annotations

import asyncio
import logging
import time as time_mod
from datetime import datetime, time
from typing import Any, Callable, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import business_hours_time_window, get_business_timezone, get_max_attempts
from crm import crud
from crm.base import CRMProvider
from crm.phone import allows_outbound_dial
from integrations.base import SheetProvider
from integrations.sheets.retry_schedule import get_daily_call_limit, next_day_first_slot

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 300

# Solo questi stati possono essere accodati dal poller (lead nuovi dal foglio).
_ELIGIBLE_STATI = frozenset({"", "da_chiamare", "da_richiamare", "richiamare"})


ScheduleRetryFn = Callable[[int, datetime, ZoneInfo, int], Optional[datetime]]


def _get_zoneinfo(name: str) -> ZoneInfo:
    n = (name or "").strip()
    if not n:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(n)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":", 1)
    return time(int(h), int(m))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class SheetPoller:
    """Poll periodico: SheetProvider → CRMProvider.upsert_from_sheet_row → CRMProvider.enqueue."""

    def __init__(
        self,
        *,
        crm: CRMProvider,
        sheet: SheetProvider,
        dispatcher: Optional[Any] = None,
        agent_key: Optional[str] = None,
        time_window: tuple[str, str] | None = None,
        timezone_name: str | None = None,
        max_attempts: int | None = None,
        poll_interval_s: int = _POLL_INTERVAL_S,
        interval_s: Optional[int] = None,
        max_enqueue_per_tick: int = 20,
        schedule_retry: Optional[ScheduleRetryFn] = None,
    ) -> None:
        if not isinstance(crm, CRMProvider):
            raise TypeError("SheetPoller.crm deve essere un CRMProvider")
        if not isinstance(sheet, SheetProvider):
            raise TypeError("SheetPoller.sheet deve essere un SheetProvider")
        self._crm = crm
        self._sheet = sheet
        self._dispatcher = dispatcher
        # agent_key: esplicito > dispatcher.agent_key > error
        ak = (agent_key or "").strip()
        if not ak and dispatcher is not None:
            ak = str(getattr(dispatcher, "agent_key", "") or "").strip()
        if not ak:
            raise ValueError("SheetPoller: agent_key non determinabile (passalo esplicitamente o via dispatcher)")
        self._agent_key = ak
        tw = time_window or business_hours_time_window()
        self._tz = (
            get_business_timezone()
            if timezone_name is None
            else _get_zoneinfo(timezone_name)
        )
        self._start = _parse_hhmm(tw[0])
        self._end = _parse_hhmm(tw[1])
        self._max_attempts = max(
            1,
            int(max_attempts if max_attempts is not None else get_max_attempts(ak)),
        )
        # `interval_s` è un alias retro-compat di `poll_interval_s`.
        eff_interval = interval_s if interval_s is not None else poll_interval_s
        self._poll_interval = max(1, int(eff_interval))
        self._max_enqueue_per_tick = max(1, int(max_enqueue_per_tick))
        self._schedule_retry = schedule_retry
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._last_window_pause_log: float = 0.0

    def start(self) -> asyncio.Task[None]:
        """Fire-and-forget: lancia run() come asyncio.Task. Ritorna il task."""
        if self._task is not None and not self._task.done():
            return self._task
        self._stop.clear()
        self._task = asyncio.create_task(self.run(), name="sheet-poller")
        return self._task

    def stop(self) -> None:
        self._stop.set()

    # ----- internals -------------------------------------------------

    def _within_window(self) -> bool:
        now_local = datetime.now(self._tz).time()
        return self._start <= now_local <= self._end

    def _enrich_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Aggiunge metadati (agent_key, sheet id/row/tab)."""
        sheet_id = getattr(self._sheet, "spreadsheet_id", "") or ""
        sheet_tab = str(getattr(self._sheet, "sheet_name", "") or "").strip()
        enriched: dict[str, Any] = dict(row)
        enriched.setdefault("agent_key", self._agent_key)
        enriched["external_source"] = "google_sheet"
        enriched["external_sheet_id"] = sheet_id
        enriched["external_sheet_row"] = _safe_int(row.get("row_index"), 0)
        enriched["external_sheet_tab"] = sheet_tab
        return enriched

    def _refresh_sheet_provider(self) -> bool:
        """Rilegge .env + SHEET_NAME_* a ogni tick → import solo da quel tab."""
        from integrations.factory import build_sheet

        fresh = build_sheet(agent_key=self._agent_key, reload_env=True)
        if fresh is None:
            return False
        tab = str(getattr(fresh, "sheet_name", "") or "").strip()
        try:
            titles = list(getattr(fresh, "list_tab_titles", lambda: [])())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SheetPoller: impossibile elencare tab agent=%s: %s",
                self._agent_key,
                exc,
            )
            titles = []
        from integrations.factory import resolve_sheet_tab_name

        resolved = resolve_sheet_tab_name(tab, titles) if titles else tab
        if titles and not resolved:
            logger.error(
                "SheetPoller: SHEET_NAME_%s=%r NON esiste nel file Google. "
                "Tab disponibili: %s — import sospeso.",
                self._agent_key.upper(),
                tab,
                titles,
            )
            return False
        if resolved and resolved != getattr(fresh, "sheet_name", ""):
            fresh._sheet_name = resolved
            tab = resolved
        self._sheet = fresh
        if titles:
            logger.info(
                "SheetPoller agent=%s import SOLO tab=%r range=%s",
                self._agent_key,
                tab,
                getattr(fresh, "_range", lambda s: "?")("1:1"),
            )
        return True

    def _is_eligible(self, status: Optional[str]) -> bool:
        if crud.client_stato_blocks_outbound(status):
            return False
        s = str(status or "").strip().lower().replace(" ", "_")
        return s in _ELIGIBLE_STATI

    def _scheduled_at_for(
        self,
        tentativi: int,
        *,
        client_stato: str | None = None,
    ) -> Optional[datetime]:
        # Primo contatto (tentativi=0) o lead ancora "da_chiamare" sul foglio: chiamata immediata.
        stato = str(client_stato or "").strip().lower().replace(" ", "_")
        if tentativi <= 0 or stato == "da_chiamare":
            return None
        if self._schedule_retry is None:
            return None
        return self._schedule_retry(
            tentativi, datetime.now(self._tz), self._tz, self._max_attempts
        )

    def _should_enqueue(
        self,
        client_id: int,
        tentativi: int,
        *,
        client_stato: str | None = None,
    ) -> tuple[bool, Optional[datetime]]:
        """True se il lead può essere accodato ora; altrimenti next_attempt_at."""
        if tentativi >= self._max_attempts:
            crud.apply_max_tentativi_if_exhausted(int(client_id), self._agent_key)
            return False, None

        if self._agent_key == "gloria":
            if crud.is_location_out_of_target_for_client(int(client_id)):
                client_row = crud.get_client(int(client_id))
                zona = (client_row or {}).get("zona")
                crud.update_client(int(client_id), stato="non_in_target")
                logger.info(
                    "SheetPoller fuori zona agent=%s client_id=%s zona=%r → non_in_target",
                    self._agent_key,
                    client_id,
                    zona,
                )
                return False, None

        calls_today = crud.count_calls_today(int(client_id))
        daily_limit = get_daily_call_limit(int(client_id), self._tz)
        if calls_today >= daily_limit:
            return False, next_day_first_slot(self._tz)

        return True, self._scheduled_at_for(tentativi, client_stato=client_stato)

    async def _handle_existing_queue(self, client: Any) -> bool:
        """Gestisce coda già presente: recovery dialing stale + wake dispatcher se pronta."""
        if client.id is None:
            return False
        client_id = int(client.id)
        await asyncio.to_thread(crud.recover_stale_dialing_queue, client_id)
        row = await asyncio.to_thread(crud.get_active_queue_row, client_id)
        if not row:
            return False
        if crud.is_queue_row_ready_for_dial(row):
            if self._dispatcher is not None:
                try:
                    await self._dispatcher.enqueue(client)
                    logger.info(
                        "SheetPoller wake dispatcher client_id=%s queue_id=%s (coda pronta)",
                        client_id,
                        row.get("id"),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "SheetPoller dispatcher wake errore client_id=%s",
                        client_id,
                    )
        else:
            logger.info(
                "SheetPoller skip client_id=%s: coda attiva status=%s next=%s (non pronta)",
                client_id,
                row.get("status"),
                row.get("next_attempt_at"),
            )
        return True

    def _log_window_pause(self) -> None:
        now_ts = time_mod.monotonic()
        if now_ts - self._last_window_pause_log < 1800:
            return
        self._last_window_pause_log = now_ts
        logger.info(
            "SheetPoller in pausa agent=%s: fuori finestra %s-%s (%s). "
            "Il task è attivo ma non importa dal foglio finché non si rientra in fascia.",
            self._agent_key,
            self._start.strftime("%H:%M"),
            self._end.strftime("%H:%M"),
            self._tz.key,
        )

    async def _tick(self) -> None:
        if not self._within_window():
            self._log_window_pause()
            return

        if not await asyncio.to_thread(self._refresh_sheet_provider):
            logger.warning(
                "SheetPoller: foglio non disponibile agent=%s", self._agent_key
            )
            return

        tab = str(getattr(self._sheet, "sheet_name", "") or "")
        rows = await asyncio.to_thread(self._sheet.read_prospects)
        # Riga più recente per prima: stesso telefono su più righe → vince l'ultima aggiunta.
        rows = sorted(
            rows,
            key=lambda r: _safe_int(r.get("row_index"), 0),
            reverse=True,
        )
        logger.info(
            "SheetPoller tick agent=%s tab=%r righe=%s",
            self._agent_key,
            tab,
            len(rows),
        )
        enqueued = 0

        for row in rows:
            if self._stop.is_set():
                return
            if enqueued >= self._max_enqueue_per_tick:
                break

            tel = str(row.get("telefono") or "").strip()
            if not tel:
                continue

            enriched = self._enrich_row(row)

            try:
                client, created = await asyncio.to_thread(
                    self._crm.upsert_from_sheet_row, enriched
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "SheetPoller upsert errore agent=%s row=%s: %s",
                    self._agent_key,
                    row.get("row_index"),
                    exc,
                )
                continue

            if client is None or client.id is None:
                continue

            if not self._is_eligible(client.status):
                logger.debug(
                    "SheetPoller skip client_id=%s status=%s",
                    client.id,
                    client.status,
                )
                continue

            client_tel = str(
                getattr(client, "phone", None) or tel or ""
            ).strip()
            if not allows_outbound_dial(client_tel):
                logger.debug(
                    "SheetPoller skip enqueue client_id=%s: telefono non valido per outbound IT",
                    client.id,
                )
                continue

            if await self._handle_existing_queue(client):
                continue

            tentativi = _safe_int((client.extra or {}).get("tentativi"), 0)
            should_enqueue, scheduled_at = await asyncio.to_thread(
                self._should_enqueue,
                int(client.id),
                tentativi,
                client_stato=client.status,
            )
            if not should_enqueue:
                if scheduled_at is not None:
                    try:
                        await asyncio.to_thread(
                            self._crm.enqueue,
                            int(client.id),
                            agent_key=self._agent_key,
                            scheduled_at=scheduled_at,
                            priority=0,
                        )
                        logger.info(
                            "SheetPoller cap giornaliero/max agent=%s client_id=%s "
                            "→ next_attempt_at=%s",
                            self._agent_key,
                            client.id,
                            scheduled_at.isoformat(),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "SheetPoller reschedule errore agent=%s client_id=%s: %s",
                            self._agent_key,
                            client.id,
                            exc,
                        )
                elif tentativi >= self._max_attempts:
                    await asyncio.to_thread(
                        crud.apply_max_tentativi_if_exhausted,
                        int(client.id),
                        self._agent_key,
                    )
                    logger.info(
                        "SheetPoller max attempts reached agent=%s client_id=%s tentativi=%s",
                        self._agent_key,
                        client.id,
                        tentativi,
                    )
                continue

            try:
                await asyncio.to_thread(
                    self._crm.enqueue,
                    int(client.id),
                    agent_key=self._agent_key,
                    scheduled_at=scheduled_at,
                    priority=0,
                )
                enqueued += 1
                if created:
                    logger.debug(
                        "SheetPoller enqueue nuovo client_id=%s", client.id
                    )
                else:
                    logger.info(
                        "SheetPoller enqueue client_id=%s (già in CRM, stato=%s)",
                        client.id,
                        client.status,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "SheetPoller enqueue errore agent=%s client_id=%s: %s",
                    self._agent_key,
                    client.id,
                    exc,
                )
                continue

            # Notifica il dispatcher: se "ready ora" (no scheduled_at o passato),
            # mette subito il client in coda asyncio.
            if self._dispatcher is not None and scheduled_at is None:
                try:
                    await self._dispatcher.enqueue(client)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "SheetPoller dispatcher.enqueue errore client_id=%s",
                        client.id,
                    )

    async def run(self) -> None:
        """Loop principale (asyncio task)."""
        logger.info(
            "SheetPoller avviato: agent=%s window=%s-%s tz=%s",
            self._agent_key,
            self._start.strftime("%H:%M"),
            self._end.strftime("%H:%M"),
            self._tz.key,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.error("SheetPoller tick errore: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                continue
        logger.info("SheetPoller terminato: agent=%s", self._agent_key)
