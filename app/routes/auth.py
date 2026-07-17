from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from app.models.models import db, Patient
from app.utils.audit import log_audit_event
from app.utils.helpers import normalize_phone
import os

# ========================
# BLUEPRINT
# ========================
auth_bp = Blueprint('auth', __name__)

# Il limiter verrà applicato tramite decorator

# ========================
# CONFIGURAZIONE ADMIN (DA VARIABILI D'AMBIENTE)
# ========================
ADMIN_PHONE = normalize_phone(os.getenv("ADMIN_PHONE", ""))
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
ADMIN_NAME = os.getenv("ADMIN_NAME", "MyNutriApp")

# Verifica che ADMIN_PASSWORD_HASH sia presente (fail-fast)
if not ADMIN_PASSWORD_HASH:
    raise ValueError("❌ ADMIN_PASSWORD_HASH deve essere definita in .env")
if not ADMIN_PHONE:
    raise ValueError("❌ ADMIN_PHONE deve essere definita in .env")


# ========================
# ROUTE: LOGIN CON RATE LIMITING
# ========================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telefono = normalize_phone(request.form['telefono'])
        password = request.form['password']

        # --- Caso 1: Login ADMIN (con hash, non più in chiaro)
        if ADMIN_PHONE and ADMIN_PASSWORD_HASH:
            if telefono == ADMIN_PHONE and check_password_hash(ADMIN_PASSWORD_HASH, password):
                # Protezione contro session fixation: Flask non supporta session.regenerate()
                # quindi puliamo la sessione esistente e reimpostiamo solo le chiavi necessarie
                session.clear()
                
                # Reimposta solo le chiavi necessarie per l'autenticazione admin
                session['role'] = 'admin'
                session['name'] = ADMIN_NAME
                session.permanent = True  # Session permanente per admin
                session.modified = True  # Forza il salvataggio della sessione
                
                # Audit log
                log_audit_event('LOGIN', 'system', details={'user_type': 'admin'})
                db.session.commit()
                
                flash("Accesso effettuato come Admin", "success")
                return redirect(url_for('dashboard.admin_dashboard'))

        # --- Caso 2: Login USER da database
        user = Patient.query.filter_by(telefono=telefono).first()
        if not user:
            for candidate in Patient.query.filter(Patient.telefono.isnot(None)).all():
                if normalize_phone(candidate.telefono) == telefono:
                    user = candidate
                    break
        if user and check_password_hash(user.password_hash, password):
            stato = getattr(user, "stato_cliente", None) or "attivo"
            if stato != "attivo":
                flash(
                    "Account non ancora attivo. Attendi la conferma del nutrizionista.",
                    "warning",
                )
                return redirect(url_for("auth.login"))

            # Protezione contro session fixation: Flask non supporta session.regenerate()
            # quindi puliamo la sessione esistente e reimpostiamo solo le chiavi necessarie
            session.clear()
            
            # Reimposta solo le chiavi necessarie per l'autenticazione user
            session['role'] = 'user'
            session['user_id'] = user.id
            session['name'] = f"{user.nome} {user.cognome}"
            session.permanent = True
            session.modified = True  # Forza il salvataggio della sessione
            
            # Audit log
            log_audit_event('LOGIN', 'system', details={'user_type': 'user', 'user_id': user.id})
            db.session.commit()
            
            return redirect(url_for('dashboard.user_dashboard'))
        
        # Audit log per tentativo fallito
        log_audit_event('LOGIN_FAILED', 'system', details={'telefono': telefono[:3] + '***'})
        db.session.commit()
        
        flash("Credenziali non valide", "danger")
        return redirect(url_for('auth.login'))

    return render_template('login.html')


# ========================
# ROUTE: LOGOUT
# ========================
@auth_bp.route('/logout')
def logout():
    # Audit log prima di cancellare session
    user_id = session.get('user_id')
    user_role = session.get('role')
    log_audit_event('LOGOUT', 'system', details={'user_type': user_role, 'user_id': user_id})
    db.session.commit()
    
    session.clear()
    return redirect(url_for('auth.login'))