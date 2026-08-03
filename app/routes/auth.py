from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import db
from app.services.auth_service import AuthStatus, authenticate
from app.utils.audit import log_audit_event
from app.utils.helpers import normalize_phone
import os

auth_bp = Blueprint('auth', __name__)

# Bootstrap seed ancora richiede ADMIN_* in .env
ADMIN_PHONE = normalize_phone(os.getenv("ADMIN_PHONE", ""))
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

if not ADMIN_PASSWORD_HASH:
    raise ValueError("❌ ADMIN_PASSWORD_HASH deve essere definita in .env (seed super_admin)")
if not ADMIN_PHONE:
    raise ValueError("❌ ADMIN_PHONE deve essere definita in .env (seed super_admin)")


def _login_as_patient(user, *, via: str = "web"):
    session.clear()
    session['role'] = 'user'
    session['user_id'] = user.id
    session['name'] = f"{user.nome} {user.cognome}".strip()
    session.permanent = True
    session.modified = True

    log_audit_event(
        'LOGIN',
        'system',
        details={'user_type': 'user', 'user_id': user.id, 'via': via},
    )
    db.session.commit()
    return redirect(url_for('dashboard.user_dashboard'))


def establish_utente_session(utente, role: str, *, via: str) -> None:
    """Imposta la sessione web per super_admin / nutrizionista (senza redirect)."""
    session.clear()
    session['role'] = role
    session['utente_id'] = utente.id
    session['name'] = f"{utente.nome} {utente.cognome}".strip()
    session.permanent = True
    session.modified = True

    log_audit_event(
        'LOGIN',
        'system',
        details={'user_type': role, 'utente_id': utente.id, 'via': via},
    )
    db.session.commit()


def _login_as_utente(utente, role: str, *, via: str):
    establish_utente_session(utente, role, via=via)

    if role == 'super_admin':
        return redirect(url_for('super_admin.lista_utenti'))
    # Nutrizionista → UI admin tenant
    return redirect(url_for('dashboard.admin_dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telefono = request.form.get('telefono', '')
        password = request.form.get('password', '')
        result = authenticate(telefono, password)

        if result.status in (AuthStatus.OK_SUPER_ADMIN, AuthStatus.OK_ADMIN) and result.utente:
            flash("Accesso super admin", "success")
            return _login_as_utente(result.utente, 'super_admin', via='web')

        if result.status == AuthStatus.OK_NUTRIZIONISTA and result.utente:
            flash("Accesso effettuato", "success")
            return _login_as_utente(result.utente, 'nutrizionista', via='web')

        if result.status == AuthStatus.INACTIVE:
            flash(
                "Account non ancora attivo.",
                "warning",
            )
            return redirect(url_for("auth.login"))

        if result.status == AuthStatus.OK_USER and result.patient is not None:
            return _login_as_patient(result.patient, via="web")

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


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id') or session.get('utente_id')
    user_role = session.get('role')
    log_audit_event('LOGOUT', 'system', details={'user_type': user_role, 'user_id': user_id})
    db.session.commit()

    session.clear()
    return redirect(url_for('auth.login'))
