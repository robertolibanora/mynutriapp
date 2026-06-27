# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""GoogleSheet: lettura prospect da Google Sheets (read-only)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from integrations.base import IntegrationError, SheetProvider

logger = logging.getLogger(__name__)

_SCOPES_READONLY = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Colonne canoniche A-O (solo lettura; il mapping verso CRM avviene a valle).
_HEADERS = [
    "nome",
    "telefono",
    "email",
    "azienda",
    "zona",
    "note",
    "agent_type",
    "stato",
    "esito",
    "ultimo_call_sid",
    "ultimo_tentativo",
    "prossimo_tentativo_at",
    "tentativi",
    "appuntamento_dt",
    "transcript",
]


def _col_index(col: str) -> int:
    """Lettera colonna → indice 0-based. Es: A→0, Z→25, AA→26."""
    result = 0
    for ch in col.upper().strip():
        if not ("A" <= ch <= "Z"):
            continue
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _col_letter(idx: int) -> str:
    """Indice 0-based → lettera colonna. Es: 0→A, 25→Z, 26→AA."""
    result = ""
    n = idx + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _column_map_uses_letters(column_map: dict[str, str]) -> bool:
    """True se le chiavi del map sono lettere colonna (A, B, AA…)."""
    if not column_map:
        return False
    return all(re.fullmatch(r"[A-Z]+", k.strip().upper()) for k in column_map)


def _parse_credentials(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    s = (raw or "").strip()
    if not s:
        raise IntegrationError("GOOGLE_CREDENTIALS_JSON vuoto")
    if s.startswith("{"):
        return json.loads(s)
    with open(s, encoding="utf-8") as fh:
        return json.load(fh)


class GoogleSheet(SheetProvider):
    """Lettura prospect da Google Sheets (nessuna scrittura sul foglio)."""

    slug = "google_sheets"

    def __init__(
        self,
        credentials: dict[str, Any] | str,
        sheet_id: str,
        sheet_name: str = "Foglio1",
        column_map: dict[str, str] | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        if not sheet_id:
            raise IntegrationError("sheet_id vuoto (env SHEET_ID)")
        creds_dict = _parse_credentials(credentials)
        use_scopes = scopes or _SCOPES_READONLY
        creds = Credentials.from_service_account_info(creds_dict, scopes=use_scopes)
        self._service = build(
            "sheets", "v4", credentials=creds, cache_discovery=False
        )
        self._sheet_id = sheet_id
        self._sheet_name = sheet_name or "Foglio1"
        self._column_map = column_map or {}

    @property
    def spreadsheet_id(self) -> str:
        return self._sheet_id

    @property
    def sheet_name(self) -> str:
        return self._sheet_name

    def _range(self, span: str) -> str:
        # Sempre tra apici: tab tipo "CRM" altrimenti Google interpreta male il range.
        name = (self._sheet_name or "Foglio1").replace("'", "''")
        return f"'{name}'!{span}"

    def list_tab_titles(self) -> list[str]:
        """Nomi dei tab nel file (per validare SHEET_NAME_*)."""
        try:
            meta = (
                self._service.spreadsheets()
                .get(spreadsheetId=self._sheet_id, fields="sheets.properties.title")
                .execute()
            )
        except HttpError as exc:
            logger.warning("sheets list_tab_titles errore: %s", exc)
            return []
        titles: list[str] = []
        for sh in meta.get("sheets") or []:
            props = sh.get("properties") if isinstance(sh, dict) else None
            if isinstance(props, dict):
                t = str(props.get("title") or "").strip()
                if t:
                    titles.append(t)
        return titles

    def health_check(self) -> bool:
        try:
            self._service.spreadsheets().get(spreadsheetId=self._sheet_id).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("sheets health_check fallito: %s", exc)
            return False

    def _read_by_letter_map(self, range_str: str, headers: list[str]) -> list[list[str]]:
        try:
            resp = (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self._sheet_id, range=self._range(range_str))
                .execute()
            )
        except HttpError as exc:
            logger.error("sheets read errore: %s", exc)
            return []
        return resp.get("values", []) or []

    def _read_by_header_map(self, column_map: dict[str, str]) -> list[dict[str, Any]]:
        """Mappa per intestazione riga 1: {'Nome agenzia': 'nome_agenzia', ...}."""
        try:
            header_resp = (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self._sheet_id, range=self._range("1:1"))
                .execute()
            )
        except HttpError as exc:
            logger.error("sheets read header row errore: %s", exc)
            return []

        header_row = (header_resp.get("values") or [[]])[0]
        if not header_row:
            logger.warning("sheets: riga intestazione vuota")
            return []

        norm_headers = [str(h or "").strip() for h in header_row]
        col_for_field: dict[str, int] = {}
        for sheet_label, field_name in column_map.items():
            label = str(sheet_label).strip()
            if not label or not str(field_name).strip():
                continue
            idx = next(
                (
                    i
                    for i, h in enumerate(norm_headers)
                    if h.casefold() == label.casefold()
                ),
                None,
            )
            if idx is None:
                logger.warning(
                    "sheets: intestazione %r non trovata in riga 1", label
                )
                continue
            col_for_field[str(field_name).strip()] = idx

        if not col_for_field:
            return []

        max_col = max(col_for_field.values())
        end_letter = _col_letter(max_col)
        try:
            data_resp = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._sheet_id,
                    range=self._range(f"A2:{end_letter}"),
                )
                .execute()
            )
        except HttpError as exc:
            logger.error("sheets read data errore: %s", exc)
            return []

        rows = data_resp.get("values", []) or []
        out: list[dict[str, Any]] = []
        for row_idx, row in enumerate(rows, start=2):
            data: dict[str, Any] = {"row_index": row_idx}
            for field_name, col_index in col_for_field.items():
                data[field_name] = (
                    row[col_index] if col_index < len(row) else ""
                )
            if not any(
                str(data.get(k) or "").strip()
                for k in ("telefono", "nome", "email", "nome_agenzia")
            ):
                continue
            out.append(data)
        return out

    def read_prospects(self) -> list[dict[str, Any]]:
        """Legge righe dal foglio e mappa le celle su dict (header da column_map o _HEADERS)."""
        if self._column_map and not _column_map_uses_letters(self._column_map):
            return self._read_by_header_map(self._column_map)

        if self._column_map:
            last_col = max(self._column_map.keys(), key=_col_index)
            range_str = f"A2:{last_col}"
            last_idx = _col_index(last_col)
            headers = [
                self._column_map.get(_col_letter(i), f"col_{i}")
                for i in range(last_idx + 1)
            ]
        else:
            range_str = "A2:O"
            headers = _HEADERS

        rows = self._read_by_letter_map(range_str, headers)
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=2):
            data: dict[str, Any] = {"row_index": idx}
            for col_index, header in enumerate(headers):
                data[header] = row[col_index] if col_index < len(row) else ""
            out.append(data)
        return out
