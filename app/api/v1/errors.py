"""Errori JSON coerenti per /api/v1."""

from __future__ import annotations

from flask import jsonify


def api_error(message: str, *, code: str, status: int):
    return jsonify({"error": message, "code": code}), status
