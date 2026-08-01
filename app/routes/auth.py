from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.models.models import db
from app.services.auth_service import AuthStatus, authenticate
from app.utils.audit import log_audit_event
from app.utils.helpers import normalize_phone
import os

# ========================
# BLUEPRINT
# ========================
auth_bp = Blueprint('auth', __name__)

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
        telefono = request.form.get('telefono', '')
        password = request.form.get('password', '')
        result = authenticate(telefono, password)

        if result.status == AuthStatus.OK_ADMIN:
            session.clear()
            session['role'] = 'admin'
            session['name'] = result.admin_name or ADMIN_NAME
            try:
                from app.services.utente_service import ensure_admin_utente

                session['utente_id'] = ensure_admin_utente(
                    telefono=ADMIN_PHONE,
                    admin_name=ADMIN_NAME,
                )
            except Exception as exc:  # noqa: BLE001
                current_app.logger.warning(
                    "Impossibile collegare utente_id alla sessione admin: %s", exc
                )
            session.permanent = True
            session.modified = True

            log_audit_event('LOGIN', 'system', details={'user_type': 'admin'})
            db.session.commit()

            flash("Accesso effettuato come Admin", "success")
            return redirect(url_for('dashboard.admin_dashboard'))

        if result.status == AuthStatus.INACTIVE:
            flash(
                "Account non ancora attivo. Attendi la conferma del nutrizionista.",
                "warning",
            )
            return redirect(url_for("auth.login"))

        if result.status == AuthStatus.OK_USER and result.patient is not None:
            user = result.patient
            session.clear()
            session['role'] = 'user'
            session['user_id'] = user.id
            session['name'] = f"{user.nome} {user.cognome}"
            session.permanent = True
            session.modified = True

            log_audit_event('LOGIN', 'system', details={'user_type': 'user', 'user_id': user.id})
            db.session.commit()

            return redirect(url_for('dashboard.user_dashboard'))

        telefono_n = result.telefono_normalized or normalize_phone(telefono)
        log_audit_event(
            'LOGIN_FAILED',
            'system',
            details={'telefono': (telefono_n[:3] + '***') if telefono_n else '***'},
        )
        db.session.commit()

        flash("Credenziali non valide", "danger")
        return redirect(url_for('auth.login'))

    return render_template('login.html')


# ========================
# ROUTE: LOGOUT
# ========================
@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    user_role = session.get('role')
    log_audit_event('LOGOUT', 'system', details={'user_type': user_role, 'user_id': user_id})
    db.session.commit()

    session.clear()
    return redirect(url_for('auth.login'))
