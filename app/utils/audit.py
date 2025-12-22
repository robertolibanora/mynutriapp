"""
Audit logging minimale - solo eventi critici.
Overhead RAM: ~50-100KB per log entry in memoria (poi flush su DB).
"""
from flask import request, session
from app.models.models import db
from datetime import datetime
import json

def log_audit_event(action, resource_type, resource_id=None, details=None):
    """
    Logga evento critico in audit_log.
    
    Args:
        action: 'VIEW', 'CREATE', 'UPDATE', 'DELETE', 'DOWNLOAD', 'LOGIN', 'LOGOUT'
        resource_type: 'patient', 'dieta', 'documento', 'progresso', etc.
        resource_id: ID della risorsa (opzionale)
        details: dict con dettagli aggiuntivi (opzionale)
    """
    try:
        from app.models.models import AuditLog
        
        user_id = session.get('user_id')
        user_role = session.get('role', 'anonymous')
        
        # Estrai IP (gestisce proxy)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # Crea entry audit
        audit_entry = AuditLog(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            user_role=user_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=request.headers.get('User-Agent', '')[:255],  # Limita lunghezza
            details=json.dumps(details) if details else None
        )
        
        db.session.add(audit_entry)
        # NON fare commit qui - lascia al chiamante per performance (batch commit)
        
    except Exception as e:
        # Audit logging non deve mai bloccare l'app
        import logging
        logging.error(f"Errore audit logging: {e}")

def audit_decorator(action, resource_type):
    """
    Decorator per loggare automaticamente accessi a route.
    Uso: @audit_decorator('VIEW', 'patient')
    """
    def decorator(func):
        from functools import wraps
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Estrai resource_id da kwargs se presente
            resource_id = None
            for key in ['patient_id', 'id', 'documento_id', 'dieta_id', 'progresso_id']:
                if key in kwargs:
                    resource_id = kwargs[key]
                    break
            
            # Logga prima dell'esecuzione
            log_audit_event(action, resource_type, resource_id)
            
            # Esegui funzione
            result = func(*args, **kwargs)
            
            # Commit audit dopo esecuzione (se non già fatto)
            try:
                db.session.commit()
            except:
                db.session.rollback()
            
            return result
        return wrapper
    return decorator

