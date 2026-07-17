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
from app.services.agenda_service import AgendaService
from app.utils.db_schema import (
    ensure_segretario_removed,
    ensure_agenda_schema,
    ensure_finance_removed,
    ensure_richieste_appuntamento_schema,
)
from datetime import datetime, timedelta

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
    if session.get('role') != 'admin':
        flash("Accesso non autorizzato", "danger")
        return redirect(url_for('auth.login'))

    ensure_finance_removed()
    ensure_segretario_removed()
    ensure_agenda_schema()
    ensure_richieste_appuntamento_schema()

    oggi = datetime.now()
    oggi_data = oggi.date()
    fine_settimana = oggi + timedelta(days=7)

    n_pazienti = Patient.query.count()

    n_appuntamenti_oggi = Appuntamento.query.filter(
        db.func.date(Appuntamento.data_appuntamento) == oggi_data,
        Appuntamento.stato != "annullato",
    ).count()

    n_appuntamenti_settimana = Appuntamento.query.filter(
        Appuntamento.data_appuntamento >= oggi,
        Appuntamento.data_appuntamento <= fine_settimana,
        Appuntamento.stato != "annullato",
    ).count()

    n_diete_pubblicate = DietPlan.query.filter_by(status="published").count()
    n_diete_bozza = DietPlan.query.filter_by(status="draft").count()
    n_diete = n_diete_pubblicate + n_diete_bozza

    # Fallback legacy se non ci sono piani strutturati
    if n_diete == 0:
        n_diete = Dieta.query.filter(
            Dieta.data_inizio <= oggi_data,
            Dieta.data_fine >= oggi_data,
        ).count()

    n_da_confermare = Appuntamento.query.filter(
        Appuntamento.stato == "in_attesa",
        Appuntamento.data_appuntamento >= oggi,
    ).count()

    n_richieste = RichiestaAppuntamento.query.filter_by(stato="in_attesa").count()
    n_da_gestire = n_da_confermare + n_richieste

    n_slot_futuri = len(AgendaService.slot_liberi())

    appuntamenti_oggi = (
        Appuntamento.query.options(joinedload(Appuntamento.patient))
        .filter(
            db.func.date(Appuntamento.data_appuntamento) == oggi_data,
            Appuntamento.stato != "annullato",
        )
        .order_by(Appuntamento.data_appuntamento.asc())
        .all()
    )

    prossimi_appuntamenti = (
        Appuntamento.query.options(joinedload(Appuntamento.patient))
        .filter(
            Appuntamento.data_appuntamento > oggi,
            Appuntamento.data_appuntamento <= fine_settimana,
            Appuntamento.stato != "annullato",
        )
        .order_by(Appuntamento.data_appuntamento.asc())
        .limit(6)
        .all()
    )

    ultime_diete = (
        DietPlan.query.options(joinedload(DietPlan.patient))
        .order_by(DietPlan.updated_at.desc(), DietPlan.created_at.desc())
        .limit(5)
        .all()
    )

    richieste_recenti = (
        RichiestaAppuntamento.query.filter_by(stato="in_attesa")
        .order_by(RichiestaAppuntamento.data_richiesta.asc())
        .limit(4)
        .all()
    )

    return render_template(
        'admin/dashboard.html',
        n_pazienti=n_pazienti,
        n_appuntamenti_oggi=n_appuntamenti_oggi,
        appuntamenti_oggi=appuntamenti_oggi,
        n_diete=n_diete,
        n_diete_pubblicate=n_diete_pubblicate,
        n_diete_bozza=n_diete_bozza,
        n_slot_futuri=n_slot_futuri,
        n_appuntamenti_settimana=n_appuntamenti_settimana,
        n_da_confermare=n_da_confermare,
        n_richieste=n_richieste,
        n_da_gestire=n_da_gestire,
        prossimi_appuntamenti=prossimi_appuntamenti,
        ultime_diete=ultime_diete,
        richieste_recenti=richieste_recenti,
        tipo_labels=_TIPO_LABELS,
        saluto=_saluto(oggi.hour),
        data_oggi=_data_italiana(oggi),
        ora_ora=oggi.strftime("%H:%M"),
        oggi=oggi,
    )


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
