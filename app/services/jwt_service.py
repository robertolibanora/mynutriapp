"""JWT access/refresh per API mobile /api/v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import jwt
from flask import current_app


class JwtError(Exception):
    """Token assente, malformato, scaduto o di tipo errato."""


def _secret() -> str:
    return current_app.config.get("JWT_SECRET") or current_app.config["SECRET_KEY"]


def _access_expires() -> int:
    return int(current_app.config.get("JWT_ACCESS_EXPIRES", 900))


def _refresh_expires() -> int:
    return int(current_app.config.get("JWT_REFRESH_EXPIRES", 2592000))


def access_expires_seconds() -> int:
    return _access_expires()


def issue_access_token(*, patient_id: int, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(patient_id),
        "role": "user",
        "name": name,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=_access_expires()),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def issue_refresh_token(*, patient_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(patient_id),
        "role": "user",
        "typ": "refresh",
        "iat": now,
        "exp": now + timedelta(seconds=_refresh_expires()),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def issue_token_pair(*, patient_id: int, name: str) -> dict[str, Any]:
    return {
        "access_token": issue_access_token(patient_id=patient_id, name=name),
        "refresh_token": issue_refresh_token(patient_id=patient_id),
        "token_type": "Bearer",
        "expires_in": _access_expires(),
    }


def decode_token(token: str, *, expected_typ: Optional[str] = None) -> dict[str, Any]:
    if not token:
        raise JwtError("Token mancante")
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise JwtError("Token scaduto") from exc
    except jwt.InvalidTokenError as exc:
        raise JwtError("Token non valido") from exc

    if expected_typ and payload.get("typ") != expected_typ:
        raise JwtError("Tipo token non valido")

    role = payload.get("role")
    if role != "user":
        raise JwtError("Ruolo non autorizzato")

    return payload


def patient_id_from_payload(payload: dict[str, Any]) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise JwtError("Subject token non valido") from exc
