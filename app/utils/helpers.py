"""
Funzioni helper e utility comuni
"""

from datetime import datetime, date
from flask import flash, redirect, url_for, session
from functools import wraps

def normalize_phone(phone: str) -> str:
    """Normalizza un numero di telefono (rimuove spazi, +39, ecc.)."""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if digits.startswith('39') and len(digits) > 10:
        digits = digits[2:]
    return digits

def admin_required(func):
    """Decorator per accesso riservato all'admin"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper

def user_required(func):
    """Decorator per accesso riservato all'utente loggato"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login come paziente", "warning")
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
