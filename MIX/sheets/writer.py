# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""SheetWriter: scrittura celle su Google Sheets (per riga nota)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from integrations.base import IntegrationError
from integrations.sheets.google import _parse_credentials

logger = logging.getLogger(__name__)

_SCOPES_WRITE = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetWriter:
    """Aggiorna celle per `sheet_row` usando intestazioni riga 1 e write_map."""

    def __init__(
        self,
        *,
        sheet_id: str,
        credentials: dict[str, Any] | str,
        sheet_name: str = "Foglio1",
        write_map: dict[str, str],
    ) -> None:
        if not sheet_id:
            raise IntegrationError("sheet_id vuoto")
        if not write_map:
            raise IntegrationError("write_map vuoto")
        creds_dict = _parse_credentials(credentials)
        creds = Credentials.from_service_account_info(
            creds_dict, scopes=_SCOPES_WRITE
        )
        self._service = build(
            "sheets", "v4", credentials=creds, cache_discovery=False
        )
        self._sheet_id = sheet_id
        self._sheet_name = sheet_name or "Foglio1"
        # intestazione foglio (riga 1) → nome campo interno in `updates`
        self._write_map = {
            str(k).strip(): str(v).strip()
            for k, v in write_map.items()
            if str(k).strip() and str(v).strip()
        }
        self._field_to_header: dict[str, str] = {
            field: header for header, field in self._write_map.items()
        }
        self._header_cols: dict[str, int] | None = None

    def _range(self, span: str) -> str:
        name = (self._sheet_name or "Foglio1").replace("'", "''")
        return f"'{name}'!{span}"

    def _load_header_columns(self) -> dict[str, int]:
        if self._header_cols is not None:
            return self._header_cols
        try:
            resp = (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self._sheet_id, range=self._range("1:1"))
                .execute()
            )
        except HttpError as exc:
            logger.error("SheetWriter: lettura intestazioni fallita: %s", exc)
            self._header_cols = {}
            return self._header_cols

        header_row = (resp.get("values") or [[]])[0]
        cols: dict[str, int] = {}
        for idx, cell in enumerate(header_row):
            label = str(cell or "").strip()
            if label:
                cols[label.casefold()] = idx
        self._header_cols = cols
        return cols

    def _col_letter(self, idx: int) -> str:
        result = ""
        n = idx + 1
        while n:
            n, rem = divmod(n - 1, 26)
            result = chr(65 + rem) + result
        return result

    def update_row(self, sheet_row: int, updates: dict[str, Any]) -> bool:
        """Scrive `updates` (chiavi = nomi campo interni) sulla riga `sheet_row`."""
        row_num = int(sheet_row)
        if row_num < 2:
            logger.warning("SheetWriter: sheet_row=%s non valido, skip", sheet_row)
            return False
        if not updates:
            return True

        header_cols = self._load_header_columns()
        if not header_cols:
            logger.warning("SheetWriter: nessuna intestazione in riga 1")
            return False

        data: list[dict[str, Any]] = []
        for field, raw_val in updates.items():
            if raw_val is None:
                continue
            text = str(raw_val).strip()
            if not text:
                continue
            header = self._field_to_header.get(str(field).strip())
            if not header:
                continue
            col_idx = header_cols.get(header.casefold())
            if col_idx is None:
                logger.warning(
                    "SheetWriter: colonna %r non trovata in riga 1", header
                )
                continue
            col_letter = self._col_letter(col_idx)
            data.append(
                {
                    "range": self._range(f"{col_letter}{row_num}"),
                    "values": [[text]],
                }
            )

        if not data:
            logger.debug("SheetWriter: nessun campo da scrivere row=%s", row_num)
            return True

        try:
            self._service.spreadsheets().values().batchUpdate(
                spreadsheetId=self._sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
            logger.info(
                "SheetWriter: aggiornata riga %s campi=%s",
                row_num,
                [d["range"] for d in data],
            )
            return True
        except HttpError as exc:
            logger.error(
                "SheetWriter: batchUpdate fallito row=%s: %s", row_num, exc
            )
            return False
