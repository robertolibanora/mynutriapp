from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import db
from app.services.auth_service import AuthStatus, authenticate
from app.services.password_reset_service import (
    GENERIC_OK_MESSAGE,
    PasswordResetError,
    request_utente_reset,
    reset_utente_password,
)
from app.services.patient_invite_service import (
    PatientInviteError,
    activate_account,
)
from app.services import secure_token_service as tokens
from app.models.models import AuthSecureToken
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
        return redirect(url_for('super_admin.dashboard'))
    # Nutrizionista → UI admin tenant
    return redirect(url_for('dashboard.admin_dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telefono = request.form.get('telefono', '')
        password = request.form.get('password', '')
        email = request.form.get('email', '')
        result = authenticate(telefono, password, email=email)

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

        if result.status == AuthStatus.AMBIGUOUS:
            flash(
                "Questo telefono è associato a più professionisti. "
                "Inserisci anche l'email per accedere.",
                "warning",
            )
            return redirect(url_for("auth.login"))

        if result.status == AuthStatus.OK_USER and result.patient is not None:
            flash(
                "L'area paziente è disponibile solo dall'app mobile.",
                "warning",
            )
            return redirect(url_for("auth.login"))

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


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Recupero password area professionisti (messaggio generico)."""
    if request.method == 'POST':
        email = request.form.get('email', '')
        msg = request_utente_reset(email)
        flash(msg, "success")
        return redirect(url_for('auth.forgot_password'))
    return render_template('auth/forgot_password.html')


def _patient_deep_link_page(*, kind: str, token: str):
    """Pagina HTTPS fallback: prova ad aprire l'app, altrimenti form web."""
    from app.services.password_reset_service import reset_app_url, reset_patient_password
    from app.services.patient_invite_service import activation_app_url

    if kind == "activate":
        purpose = AuthSecureToken.PURPOSE_PATIENT_INVITE
        app_url = activation_app_url(token)
        invalid = tokens.peek_token(purpose, token) is None
        if request.method == "POST" and not invalid:
            try:
                activate_account(
                    token,
                    request.form.get("password") or "",
                    request.form.get("password_confirm") or "",
                )
                db.session.commit()
                flash("Account attivato. Accedi dall'app MyNutriApp.", "success")
                return redirect(url_for("auth.login"))
            except PatientInviteError as exc:
                db.session.rollback()
                flash(exc.message, "danger")
        return render_template(
            "auth/deep_link_fallback.html",
            kind="activate",
            token=token,
            app_url=app_url,
            invalid=invalid,
        )

    # reset paziente
    purpose = AuthSecureToken.PURPOSE_PATIENT_RESET
    app_url = reset_app_url(token)
    invalid = tokens.peek_token(purpose, token) is None
    if request.method == "POST" and not invalid:
        try:
            reset_patient_password(
                token,
                request.form.get("password") or "",
                request.form.get("password_confirm") or "",
            )
            flash("Password aggiornata. Accedi dall'app mobile.", "success")
            return redirect(url_for("auth.login"))
        except PasswordResetError as exc:
            flash(exc.message, "danger")
    return render_template(
        "auth/deep_link_fallback.html",
        kind="reset",
        token=token,
        app_url=app_url,
        invalid=invalid,
    )


@auth_bp.route("/activate-account", methods=["GET", "POST"])
def activate_account_query():
    """Deep-link HTTPS: /activate-account?token=... (app o fallback web)."""
    token = (request.args.get("token") or request.form.get("token") or "").strip()
    if not token:
        flash("Link di attivazione non valido.", "danger")
        return render_template(
            "auth/deep_link_fallback.html",
            kind="activate",
            token="",
            app_url="",
            invalid=True,
        ), 400
    return _patient_deep_link_page(kind="activate", token=token)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password_query():
    """Deep-link HTTPS paziente: /reset-password?token=..."""
    token = (request.args.get("token") or request.form.get("token") or "").strip()
    if not token:
        # Senza query → form forgot staff (compat)
        return redirect(url_for("auth.forgot_password"))
    # Se è token staff (path legacy usa /reset-password/<token>), qui gestiamo pazienti
    peek_staff = tokens.peek_token(AuthSecureToken.PURPOSE_UTENTE_RESET, token)
    if peek_staff is not None:
        return reset_password_token(token)
    return _patient_deep_link_page(kind="reset", token=token)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_token(token: str):
    """Reset password nutrizionista/super_admin (o paziente via path legacy)."""
    peek = tokens.peek_token(AuthSecureToken.PURPOSE_UTENTE_RESET, token)
    peek_patient = None
    if peek is None:
        peek_patient = tokens.peek_token(AuthSecureToken.PURPOSE_PATIENT_RESET, token)

    if peek is None and peek_patient is None:
        flash("Link non valido o scaduto.", "danger")
        return redirect(url_for('auth.login'))

    if peek_patient is not None and peek is None:
        return _patient_deep_link_page(kind="reset", token=token)

    if request.method == 'POST':
        try:
            reset_utente_password(
                token,
                request.form.get('password') or '',
                request.form.get('password_confirm') or '',
            )
            session.clear()
            flash("Password aggiornata. Accedi con la nuova password.", "success")
            return redirect(url_for('auth.login'))
        except PasswordResetError as exc:
            flash(exc.message, "danger")

    return render_template('auth/reset_password.html', token=token, for_patient=False)


@auth_bp.route('/attiva-account/<token>', methods=['GET', 'POST'])
def attiva_account(token: str):
    """Compat path legacy → stesso flusso deep-link."""
    return _patient_deep_link_page(kind="activate", token=token)
