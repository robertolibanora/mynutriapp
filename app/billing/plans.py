"""Configurazione centralizzata dei piani e dei limiti.

Nessun limite numerico deve essere hardcodato fuori da questo modulo.
Estendibile: aggiungere chiavi in ``limits`` (es. collaborators, ai_credits).
"""

from __future__ import annotations

import os
from typing import Any, Optional

PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "starter": {"active_patients": 20},
    "professional": {"active_patients": 50},
    "studio": {"active_patients": 100},
    "enterprise": {"active_patients": None},  # illimitato
}

VALID_PLANS = frozenset(PLAN_LIMITS.keys())
DEFAULT_PLAN = "starter"

# Piani acquistabili online via Stripe Checkout (Enterprise escluso).
PURCHASABLE_PLANS = frozenset({"starter", "professional", "studio"})

_PRICE_ENV_KEYS = {
    "starter": "STRIPE_PRICE_STARTER",
    "professional": "STRIPE_PRICE_PROFESSIONAL",
    "studio": "STRIPE_PRICE_STUDIO",
}


def normalize_plan(plan: Optional[str]) -> str:
    """Ritorna un piano valido; fallback a starter."""
    key = (plan or "").strip().lower()
    if key in VALID_PLANS:
        return key
    return DEFAULT_PLAN


def get_patient_limit(plan: Optional[str]) -> Optional[int]:
    """Limite pazienti attivi per piano. ``None`` = illimitato."""
    limits = PLAN_LIMITS[normalize_plan(plan)]
    value = limits.get("active_patients")
    if value is None:
        return None
    return int(value)


def get_limit(plan: Optional[str], limit_key: str) -> Optional[int]:
    """Limite generico per chiave (estendibile). ``None`` = illimitato o assente."""
    limits = PLAN_LIMITS[normalize_plan(plan)]
    value = limits.get(limit_key)
    if value is None:
        return None
    return int(value)


def stripe_price_id_for_plan(plan: str) -> Optional[str]:
    """Price ID Stripe dal piano (env). Enterprise / sconosciuto → None."""
    key = normalize_plan(plan)
    env_name = _PRICE_ENV_KEYS.get(key)
    if not env_name:
        return None
    value = (os.getenv(env_name) or "").strip()
    return value or None


def plan_from_stripe_price_id(price_id: Optional[str]) -> Optional[str]:
    """Risolve il piano dal Price ID Stripe (env)."""
    if not price_id:
        return None
    needle = price_id.strip()
    for plan, env_name in _PRICE_ENV_KEYS.items():
        configured = (os.getenv(env_name) or "").strip()
        if configured and configured == needle:
            return plan
    return None
