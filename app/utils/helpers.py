"""
Funzioni helper e utility comuni
"""

import re
import unicodedata
from datetime import datetime, date
from flask import flash, redirect, url_for, session
from functools import wraps

# Segmenti riservati per /prenota/<studio_slug>
RESERVED_PUBLIC_SLUGS = frozenset(
    {
        "admin",
        "api",
        "activate-account",
        "attiva",
        "attiva-account",
        "billing",
        "forgot-password",
        "health",
        "login",
        "logout",
        "reset-password",
        "static",
        "super",
        "webhook",
        "prenota",
        "appuntamenti",
        "nuovo",
        "ok",
    }
)

# Alias legacy
RESERVED_STUDIO_SLUGS = RESERVED_PUBLIC_SLUGS

STUDIO_SLUG_MIN_LENGTH = 3
STUDIO_SLUG_MAX_LENGTH = 80


def slugify_public_name(value: str, *, max_length: int = STUDIO_SLUG_MAX_LENGTH) -> str:
    """Normalizza un nome studio/nutrizionista in slug URL-safe (a-z0-9-)."""
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if max_length > 0:
        text = text[:max_length].rstrip("-")
    return text


def slugify_studio_name(value: str, *, max_length: int = STUDIO_SLUG_MAX_LENGTH) -> str:
    """Alias di slugify_public_name (nome canonico studio_slug)."""
    return slugify_public_name(value, max_length=max_length)


def validate_studio_slug_base(slug: str) -> str | None:
    """Valida lo slug base. Ritorna messaggio errore o None se ok."""
    if not slug:
        return "Nome nutrizionista / studio obbligatorio"
    if len(slug) < STUDIO_SLUG_MIN_LENGTH:
        return f"Nome studio troppo corto (minimo {STUDIO_SLUG_MIN_LENGTH} caratteri)"
    if len(slug) > STUDIO_SLUG_MAX_LENGTH:
        return f"Nome studio troppo lungo (massimo {STUDIO_SLUG_MAX_LENGTH} caratteri)"
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return "Lo slug può contenere solo lettere, numeri e trattini"
    if slug in RESERVED_STUDIO_SLUGS:
        return "Questo nome non è disponibile, scegline un altro"
    return None


def allocate_unique_studio_slug(
    nome_studio: str,
    *,
    exclude_utente_id: int | None = None,
    max_length: int = STUDIO_SLUG_MAX_LENGTH,
) -> str:
    """Genera uno studio_slug univoco; in caso di collisione aggiunge -2, -3, …"""
    from app.models.diario import Utente

    base = slugify_studio_name(nome_studio, max_length=max_length)
    err = validate_studio_slug_base(base)
    if err:
        raise ValueError(err)

    def _taken(candidate: str) -> bool:
        q = Utente.query.filter(Utente.public_slug == candidate)
        if exclude_utente_id is not None:
            q = q.filter(Utente.id != exclude_utente_id)
        return q.first() is not None

    if not _taken(base):
        return base

    n = 2
    while n < 10000:
        suffix = f"-{n}"
        stem = base[: max(1, max_length - len(suffix))].rstrip("-")
        candidate = f"{stem}{suffix}"
        if candidate not in RESERVED_STUDIO_SLUGS and not _taken(candidate):
            return candidate
        n += 1
    raise ValueError("Impossibile generare uno slug univoco, scegli un altro nome")


def normalize_phone(phone: str) -> str:
    """Normalizza un numero di telefono (rimuove spazi, +39, ecc.)."""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if digits.startswith('39') and len(digits) > 10:
        digits = digits[2:]
    return digits


def format_phone_whatsapp(phone: str) -> str:
    """Formato internazionale per API WhatsApp (solo cifre, es. 393401234567)."""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if not digits:
        return ''
    if len(digits) == 10 and digits.startswith('3'):
        return f'39{digits}'
    return digits

def admin_required(func):
    """Decorator per accesso riservato all'admin"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper

def format_date(date_obj, format_str='%d/%m/%Y'):
    """Formatta una data"""
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime(format_str) if date_obj else ''

def format_datetime(datetime_obj, format_str='%d/%m/%Y %H:%M'):
    """Formatta un datetime"""
    if isinstance(datetime_obj, str):
        return datetime_obj
    return datetime_obj.strftime(format_str) if datetime_obj else ''

def is_today(date_obj):
    """Verifica se una data è oggi"""
    if not date_obj:
        return False
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    return date_obj == date.today()

def is_past(date_obj):
    """Verifica se una data è nel passato"""
    if not date_obj:
        return False
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    return date_obj < date.today()

def safe_float(value, default=0.0):
    """
    Converte un valore in float in modo sicuro.
    Gestisce stringhe vuote, None e valori non numerici.
    
    Args:
        value: Il valore da convertire
        default: Valore di default se la conversione fallisce
    
    Returns:
        float: Il valore convertito o il default
    """
    if value is None or value == '':
        return default
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
