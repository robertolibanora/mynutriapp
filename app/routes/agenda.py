from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date, timedelta

from app.models.models import db, Appuntamento, RichiestaAppuntamento
from app.services.agenda_service import AgendaService
from app.utils.db_schema import ensure_agenda_schema, ensure_richieste_appuntamento_schema

# ========================
# BLUEPRINT
# ========================
agenda_bp = Blueprint('agenda', __name__, url_prefix='/agenda')


@agenda_bp.before_request
def _ensure_schema():
    ensure_agenda_schema()
    ensure_richieste_appuntamento_schema()


# ========================
# DECORATORI
# ========================
def admin_required(func):
    """Accesso riservato all'admin"""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


_MESI_IT = {
    'January': 'Gennaio', 'February': 'Febbraio', 'March': 'Marzo', 'April': 'Aprile',
    'May': 'Maggio', 'June': 'Giugno', 'July': 'Luglio', 'August': 'Agosto',
    'September': 'Settembre', 'October': 'Ottobre', 'November': 'Novembre', 'December': 'Dicembre',
}


def _mese_display(mese_corrente: date) -> str:
    text = mese_corrente.strftime('%B %Y')
    for en, it in _MESI_IT.items():
        text = text.replace(en, it)
    return text


# ========================
# AGENDA UNIFICATA
# ========================
@agenda_bp.route('/admin')
@admin_required
def agenda_unificata():
    """Calendario, disponibilità e appuntamenti."""
    mese_param = request.args.get('mese')
    giorno_param = request.args.get('giorno')
    tab = request.args.get('tab', 'calendario')

    if giorno_param:
        try:
            giorno_target = datetime.strptime(giorno_param, '%Y-%m-%d').date()
            mese_corrente = giorno_target.replace(day=1)
        except ValueError:
            mese_corrente = date.today().replace(day=1)
    elif mese_param:
        try:
            mese_corrente = datetime.strptime(mese_param, '%Y-%m').date()
        except ValueError:
            mese_corrente = date.today().replace(day=1)
    else:
        mese_corrente = date.today().replace(day=1)

    filtro_giorno_param = request.args.get('filtro_giorno')
    tutti_giorni = request.args.get('tutti_giorni')
    filtro_vista = request.args.get('filtro', 'da_confermare')
    filtro_giorno = None

    if filtro_giorno_param:
        try:
            filtro_giorno = datetime.strptime(filtro_giorno_param, '%Y-%m-%d').date()
            filtro_vista = 'giorno'
        except ValueError:
            filtro_giorno = None

    if tutti_giorni:
        filtro_vista = 'mese'

    oggi = datetime.now()
    mese_precedente = (mese_corrente - timedelta(days=1)).replace(day=1).strftime('%Y-%m')
    mese_successivo = (mese_corrente + timedelta(days=32)).replace(day=1).strftime('%Y-%m')
    mese_corrente_display = _mese_display(mese_corrente)

    giorno_precedente = None
    giorno_successivo = None
    if filtro_giorno:
        giorno_precedente = (filtro_giorno - timedelta(days=1)).strftime('%Y-%m-%d')
        giorno_successivo = (filtro_giorno + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        giorno_precedente = (oggi.date() - timedelta(days=1)).strftime('%Y-%m-%d')
        giorno_successivo = (oggi.date() + timedelta(days=1)).strftime('%Y-%m-%d')

    inizio_mese = mese_corrente
    fine_mese = (mese_corrente + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    inizio_dt = datetime.combine(inizio_mese, datetime.min.time())
    fine_dt = datetime.combine(fine_mese, datetime.max.time())

    slot_mese = AgendaService.genera_slot(inizio_dt, fine_dt)
    slot_liberi_mese = [s for s in slot_mese if not s.occupato and s.data_ora >= oggi]

    appuntamenti_mese = Appuntamento.query.filter(
        Appuntamento.data_appuntamento >= inizio_dt,
        Appuntamento.data_appuntamento < fine_dt + timedelta(days=1),
        Appuntamento.stato != 'annullato',
    ).order_by(Appuntamento.data_appuntamento.asc()).all()

    appuntamenti_oggi = [
        a for a in appuntamenti_mese if a.data_appuntamento.date() == oggi.date()
    ]
    appuntamenti_in_attesa = Appuntamento.query.filter(
        Appuntamento.stato == 'in_attesa',
        Appuntamento.data_appuntamento >= oggi.replace(hour=0, minute=0, second=0, microsecond=0),
    ).order_by(Appuntamento.data_appuntamento.asc()).all()
    appuntamenti_confermati = [a for a in appuntamenti_oggi if a.stato == 'confermato']

    richieste_in_attesa = (
        RichiestaAppuntamento.query.filter_by(stato='in_attesa')
        .order_by(RichiestaAppuntamento.data_richiesta.asc())
        .all()
    )

    if filtro_vista == 'giorno' and filtro_giorno:
        appuntamenti = [a for a in appuntamenti_mese if a.data_appuntamento.date() == filtro_giorno]
        vista_appuntamenti = filtro_giorno.strftime('%d/%m/%Y')
    elif filtro_vista == 'mese':
        appuntamenti = appuntamenti_mese
        vista_appuntamenti = mese_corrente_display
    elif filtro_vista == 'oggi':
        appuntamenti = appuntamenti_oggi
        vista_appuntamenti = 'Oggi'
    else:
        appuntamenti = appuntamenti_in_attesa
        vista_appuntamenti = 'Da confermare'

    eccezioni = AgendaService.get_eccezioni(future_only=True)
    orari_settimanali = AgendaService.get_orari_settimanali()

    giorni_calendario = []
    primo_giorno = inizio_mese
    while primo_giorno.weekday() != 0:
        primo_giorno -= timedelta(days=1)

    for i in range(42):
        giorno_data = primo_giorno + timedelta(days=i)
        appuntamenti_giorno = [
            a for a in appuntamenti_mese if a.data_appuntamento.date() == giorno_data
        ]
        slot_giorno = [
            s for s in slot_mese
            if s.data_ora.date() == giorno_data and not s.occupato and s.data_ora >= oggi
        ]
        chiuso = AgendaService.is_giorno_chiuso(giorno_data, eccezioni)

        giorni_calendario.append({
            'data': giorno_data,
            'nel_mese': giorno_data.month == mese_corrente.month,
            'chiuso': chiuso,
            'appuntamenti': appuntamenti_giorno,
            'slot': slot_giorno,
        })

    filtro_giorno_display = filtro_giorno.strftime('%d/%m/%Y') if filtro_giorno else None

    return render_template(
        'admin/agenda_unificata.html',
        oggi=oggi,
        tab=tab,
        mese_corrente=mese_corrente.strftime('%Y-%m'),
        mese_corrente_display=mese_corrente_display,
        mese_precedente=mese_precedente,
        mese_successivo=mese_successivo,
        filtro_giorno=filtro_giorno_param,
        filtro_giorno_display=filtro_giorno_display,
        filtro_vista=filtro_vista,
        vista_appuntamenti=vista_appuntamenti,
        giorno_precedente=giorno_precedente,
        giorno_successivo=giorno_successivo,
        tutti_giorni=tutti_giorni,
        slot_liberi_count=len(slot_liberi_mese),
        orari_settimanali_count=len(orari_settimanali),
        eccezioni=eccezioni,
        appuntamenti=appuntamenti,
        appuntamenti_oggi=appuntamenti_oggi,
        appuntamenti_in_attesa=appuntamenti_in_attesa,
        appuntamenti_confermati=appuntamenti_confermati,
        richieste_in_attesa=richieste_in_attesa,
        giorni_calendario=giorni_calendario,
    )
