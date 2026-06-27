"""Visualizzazione date/orari in fuso Italia (DB: UTC naive)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo('Europe/Rome')


def datetime_as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_rome(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return datetime_as_utc(dt).astimezone(ROME_TZ)


def format_in_rome(dt: datetime | None, fmt: str = '%d/%m/%Y %H:%M') -> str:
    if dt is None:
        return ''
    return to_rome(dt).strftime(fmt)


def utc_iso_z(dt: datetime | None) -> str | None:
    """ISO 8601 in UTC con suffisso Z (chiaro per il client JS)."""
    if dt is None:
        return None
    return datetime_as_utc(dt).isoformat().replace('+00:00', 'Z')
