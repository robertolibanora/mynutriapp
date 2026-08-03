from flask import Blueprint, render_template, session, redirect, url_for, flash
from sqlalchemy.orm import joinedload
from app.models.models import (
    db,
    Patient,
    Dieta,
    DietPlan,
    Allenamento,
    Progresso,
    Appuntamento,
    RichiestaAppuntamento,
)
from app.utils.db_schema import (
    ensure_segretario_removed,
    ensure_agenda_schema,
    ensure_finance_removed,
    ensure_richieste_appuntamento_schema,
)
from datetime import datetime, timedelta
from app.utils.tenant import require_tenant

dashboard_bp = Blueprint('dashboard', __name__)

_GIORNI = (
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"
)
_MESI = (
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

_TIPO_LABELS = {
    "allenamento_1to1": "Allenamento 1to1",
    "rinnovo_dieta": "Rinnovo dieta",
    "rinnovo_allenamento": "Rinnovo allenamento",
    "check": "Check",
    "altro": "Altro",
}


def _saluto(ora: int) -> str:
    if ora < 12:
        return "Buongiorno"
    if ora < 18:
        return "Buon pomeriggio"
    return "Buonasera"


def _data_italiana(dt: datetime) -> str:
    return f"{_GIORNI[dt.weekday()]} {dt.day} {_MESI[dt.month]} {dt.year}"


# ============================
# DASHBOARD ADMIN
# ============================
@dashboard_bp.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') not in ('admin', 'nutrizionista'):
        flash("Accesso non autorizzato", "danger")
        return redirect(url_for('auth.login'))

    ensure_finance_removed()
    ensure_segretario_removed()
    ensure_agenda_schema()
    ensure_richieste_appuntamento_schema()

    uid = require_tenant()
    oggi = datetime.now()
    oggi_data = oggi.date()
    fine_settimana = oggi + timedelta(days=7)

    n_appuntamenti_oggi = Appuntamento.query.filter(
        Appuntamento.utente_id == uid,
        db.func.date(Appuntamento.data_appuntamento) == oggi_data,
        Appuntamento.stato != "annullato",
    ).count()

    n_appuntamenti_settimana = Appuntamento.query.filter(
        Appuntamento.utente_id == uid,
        Appuntamento.data_appuntamento >= oggi,
        Appuntamento.data_appuntamento <= fine_settimana,
        Appuntamento.stato != "annullato",
    ).count()

    n_da_confermare = Appuntamento.query.filter(
        Appuntamento.utente_id == uid,
        Appuntamento.stato == "in_attesa",
        Appuntamento.data_appuntamento >= oggi,
    ).count()

    n_richieste = RichiestaAppuntamento.query.filter_by(
        stato="in_attesa", utente_id=uid
    ).count()
    n_da_gestire = n_da_confermare + n_richieste

    appuntamenti_oggi = (
        Appuntamento.query.options(joinedload(Appuntamento.patient))
        .filter(
            Appuntamento.utente_id == uid,
            db.func.date(Appuntamento.data_appuntamento) == oggi_data,
            Appuntamento.stato != "annullato",
        )
        .order_by(Appuntamento.data_appuntamento.asc())
        .all()
    )

    prossimi_appuntamenti = (
        Appuntamento.query.options(joinedload(Appuntamento.patient))
        .filter(
            Appuntamento.utente_id == uid,
            Appuntamento.data_appuntamento > oggi,
            Appuntamento.data_appuntamento <= fine_settimana,
            Appuntamento.stato != "annullato",
        )
        .order_by(Appuntamento.data_appuntamento.asc())
        .limit(6)
        .all()
    )

    richieste_recenti = (
        RichiestaAppuntamento.query.filter_by(stato="in_attesa", utente_id=uid)
        .order_by(RichiestaAppuntamento.data_richiesta.asc())
        .limit(6)
        .all()
    )

    show_onboarding = bool(session.pop("show_onboarding", False))

    from app.services.activity_service import dashboard_todo_preview
    from app.utils.db_schema import ensure_activity_notes_schema

    ensure_activity_notes_schema()
    try:
        todo_items = dashboard_todo_preview(limit=8)
    except Exception:  # noqa: BLE001
        todo_items = []

    pazienti_recenti = (
        Patient.query.filter(Patient.nutrizionista_id == uid)
        .order_by(Patient.data_creazione.desc())
        .limit(5)
        .all()
    )

    return render_template(
        'admin/dashboard.html',
        n_appuntamenti_oggi=n_appuntamenti_oggi,
        appuntamenti_oggi=appuntamenti_oggi,
        n_appuntamenti_settimana=n_appuntamenti_settimana,
        n_da_confermare=n_da_confermare,
        n_richieste=n_richieste,
        n_da_gestire=n_da_gestire,
        prossimi_appuntamenti=prossimi_appuntamenti,
        richieste_recenti=richieste_recenti,
        tipo_labels=_TIPO_LABELS,
        saluto=_saluto(oggi.hour),
        data_oggi=_data_italiana(oggi),
        ora_ora=oggi.strftime("%H:%M"),
        oggi=oggi,
        show_onboarding=show_onboarding,
        todo_items=todo_items,
        pazienti_recenti=pazienti_recenti,
    )


# ============================
# IMPOSTAZIONI NUTRIZIONISTA
# ============================
@dashboard_bp.route("/admin/impostazioni")
def admin_impostazioni():
    if session.get("role") not in ("admin", "nutrizionista"):
        flash("Accesso non autorizzato", "danger")
        return redirect(url_for("auth.login"))

    from app.models.diario import Utente
    from app.services.licensing_service import get_subscription_usage
    from app.utils.tenant import current_utente_id

    uid = current_utente_id()
    if not uid:
        flash("Sessione non valida", "danger")
        return redirect(url_for("auth.login"))

    utente = Utente.query.get(int(uid))
    if utente is None:
        flash("Account non trovato", "danger")
        return redirect(url_for("auth.login"))

    from app.config.config import Config

    usage = get_subscription_usage(int(uid))
    status = (getattr(utente, "subscription_status", None) or "none").strip().lower()
    status_labels = {
        "active": "Attivo",
        "trialing": "In prova",
        "past_due": "Pagamento in ritardo",
        "canceled": "Annullato",
        "unpaid": "Non pagato",
        "incomplete": "Incompleto",
        "incomplete_expired": "Scaduto",
        "none": "Non collegato",
    }
    return render_template(
        "admin/impostazioni.html",
        utente=utente,
        usage=usage,
        subscription_status=status,
        subscription_status_label=status_labels.get(status, status),
        has_stripe_customer=bool(getattr(utente, "stripe_customer_id", None)),
        privacy_policy_version=Config.PRIVACY_POLICY_VERSION,
        patient_retention_days=Config.PATIENT_DATA_RETENTION_DAYS,
        audio_retention_days=Config.AUDIO_RETENTION_DAYS,
        audit_retention_days=Config.AUDIT_LOG_RETENTION_DAYS,
    )


# ============================
# PROFILO USER (alias path pubblico)
# ============================
@dashboard_bp.route('/user/profilo')
def user_profilo():
    """Alias /user/profilo (il blueprint patients ha prefix /admin/pazienti)."""
    from app.routes.patients import profilo_user
    return profilo_user()


# ============================
# DASHBOARD USER
# ============================
@dashboard_bp.route('/user/dashboard')
def user_dashboard():
    if session.get('role') != 'user':
        flash("Effettua il login", "warning")
        return redirect(url_for('auth.login'))

    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))

    paziente = Patient.query.get_or_404(user_id)

    ultima_dieta = Dieta.query.filter_by(patient_id=user_id).order_by(Dieta.created_at.desc()).first()

    ultimo_diet_plan = (
        DietPlan.query.filter_by(patient_id=user_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .first()
    )

    ultimo_allenamento = Allenamento.query.filter_by(patient_id=user_id).order_by(Allenamento.created_at.desc()).first()

    ultimo_progresso = Progresso.query.filter_by(patient_id=user_id).order_by(Progresso.data_check.desc()).first()

    oggi = datetime.now()
    prossimo_appuntamento = Appuntamento.query.filter(
        Appuntamento.patient_id == user_id,
        Appuntamento.data_appuntamento >= oggi
    ).order_by(Appuntamento.data_appuntamento.asc()).first()

    return render_template(
        'user/dashboard.html',
        paziente=paziente,
        ultima_dieta=ultima_dieta,
        ultimo_diet_plan=ultimo_diet_plan,
        ultimo_allenamento=ultimo_allenamento,
        ultimo_progresso=ultimo_progresso,
        prossimo_appuntamento=prossimo_appuntamento
    )
