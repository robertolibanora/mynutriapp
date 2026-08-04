"""Token sicuri monouso (invito paziente, reset password) salvati come hash SHA-256."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from flask import current_app

from app.models.models import AuthSecureToken, db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def _ttl_minutes(purpose: str) -> int:
    if purpose == AuthSecureToken.PURPOSE_PATIENT_INVITE:
        return int(current_app.config.get("INVITE_TOKEN_EXPIRES_MINUTES") or 10080)  # 7g
    return int(current_app.config.get("PASSWORD_RESET_TOKEN_EXPIRES_MINUTES") or 45)


def invalidate_unused_tokens(purpose: str, subject_id: int) -> None:
    now = _utcnow()
    (
        AuthSecureToken.query.filter_by(purpose=purpose, subject_id=subject_id)
        .filter(AuthSecureToken.used_at.is_(None))
        .update({"used_at": now}, synchronize_session=False)
    )


def issue_token(purpose: str, subject_id: int) -> Tuple[str, AuthSecureToken]:
    """Crea un nuovo token (invalida i precedenti non usati dello stesso purpose/subject)."""
    invalidate_unused_tokens(purpose, subject_id)
    raw = generate_raw_token()
    row = AuthSecureToken(
        purpose=purpose,
        subject_id=int(subject_id),
        token_hash=hash_token(raw),
        expires_at=_utcnow() + timedelta(minutes=_ttl_minutes(purpose)),
        used_at=None,
    )
    db.session.add(row)
    db.session.flush()
    return raw, row


def consume_token(purpose: str, raw_token: str) -> Optional[AuthSecureToken]:
    """Valida e marca come usato. Ritorna None se invalido/scaduto/già usato."""
    raw_token = (raw_token or "").strip()
    if not raw_token:
        return None
    row = AuthSecureToken.query.filter_by(
        purpose=purpose, token_hash=hash_token(raw_token)
    ).first()
    if row is None or row.used_at is not None:
        return None
    now = _utcnow()
    if row.expires_at < now:
        return None
    row.used_at = now
    db.session.flush()
    return row


def peek_token(purpose: str, raw_token: str) -> Optional[AuthSecureToken]:
    """Valida senza consumare (per pagine GET di attivazione/reset)."""
    raw_token = (raw_token or "").strip()
    if not raw_token:
        return None
    row = AuthSecureToken.query.filter_by(
        purpose=purpose, token_hash=hash_token(raw_token)
    ).first()
    if row is None or row.used_at is not None:
        return None
    if row.expires_at < _utcnow():
        return None
    return row
