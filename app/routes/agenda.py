from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date, timedelta
from app.models.models import db, Appuntamento, Patient, SlotDisponibilita
from calendar import monthrange

# ========================
# BLUEPRINT
# ========================
agenda_bp = Blueprint('agenda', __name__, url_prefix='/agenda')

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

# ========================
# AGENDA UNIFICATA
# ========================
@agenda_bp.route('/admin')
@admin_required
def agenda_unificata():
    """Pagina unificata per slot, appuntamenti e calendario"""
    
    # Parametri per il mese e navigazione giorno
    mese_param = request.args.get('mese')
    giorno_param = request.args.get('giorno')
    
    if giorno_param:
        try:
            # Navigazione giorno per giorno
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
    
    # Parametri per filtro giorno
    filtro_giorno_param = request.args.get('filtro_giorno')
    tutti_giorni = request.args.get('tutti_giorni')
    filtro_giorno = None
    
    if filtro_giorno_param:
        try:
            filtro_giorno = datetime.strptime(filtro_giorno_param, '%Y-%m-%d').date()
        except ValueError:
            filtro_giorno = None
    
    oggi = datetime.now()
    
    # Calcola navigazione mensile
    mese_precedente = (mese_corrente - timedelta(days=1)).replace(day=1).strftime('%Y-%m')
    mese_successivo = (mese_corrente + timedelta(days=32)).replace(day=1).strftime('%Y-%m')
    
    # Calcola navigazione giornaliera per la sezione appuntamenti
    giorno_precedente = None
    giorno_successivo = None
    
    if filtro_giorno:
        giorno_target = filtro_giorno
        giorno_precedente = (giorno_target - timedelta(days=1)).strftime('%Y-%m-%d')
        giorno_successivo = (giorno_target + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        # Default: navigazione da oggi
        giorno_precedente = (oggi.date() - timedelta(days=1)).strftime('%Y-%m-%d')
        giorno_successivo = (oggi.date() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Display del mese corrente
    mese_corrente_display = mese_corrente.strftime('%B %Y').replace('January', 'Gennaio').replace('February', 'Febbraio').replace('March', 'Marzo').replace('April', 'Aprile').replace('May', 'Maggio').replace('June', 'Giugno').replace('July', 'Luglio').replace('August', 'Agosto').replace('September', 'Settembre').replace('October', 'Ottobre').replace('November', 'Novembre').replace('December', 'Dicembre')
    
    # Calcola inizio e fine mese
    inizio_mese = mese_corrente
    fine_mese = (mese_corrente + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    # SLOT
    slot_futuri = SlotDisponibilita.query.filter(
        SlotDisponibilita.data_ora >= oggi,
        SlotDisponibilita.data_ora <= fine_mese
    ).order_by(SlotDisponibilita.data_ora.asc()).all()
    
    # APPUNTAMENTI - Gestisce diversi tipi di filtro
    if tutti_giorni:
        # Mostra tutti gli appuntamenti del mese
        query_appuntamenti = Appuntamento.query.filter(
            Appuntamento.data_appuntamento >= inizio_mese,
            Appuntamento.data_appuntamento <= fine_mese + timedelta(days=1)
        )
    elif filtro_giorno:
        # Mostra appuntamenti del giorno specifico
        query_appuntamenti = Appuntamento.query.filter(
            db.func.date(Appuntamento.data_appuntamento) == filtro_giorno
        )
    else:
        # Default: mostra solo gli appuntamenti di oggi
        query_appuntamenti = Appuntamento.query.filter(
            db.func.date(Appuntamento.data_appuntamento) == oggi.date()
        )
    
    appuntamenti = query_appuntamenti.order_by(Appuntamento.data_appuntamento.asc()).all()
    
    # Filtri per statistiche
    appuntamenti_oggi = [a for a in appuntamenti if a.data_appuntamento.date() == oggi.date()]
    appuntamenti_in_attesa = [a for a in appuntamenti if a.stato == 'in_attesa']
    appuntamenti_confermati = [a for a in appuntamenti if a.stato == 'confermato']
    
    # CALENDARIO
    giorni_calendario = []
    
    # Trova il primo lunedì del mese
    primo_giorno = inizio_mese
    while primo_giorno.weekday() != 0:  # 0 = lunedì
        primo_giorno -= timedelta(days=1)
    
    # Genera 42 giorni (6 settimane)
    for i in range(42):
        giorno_data = primo_giorno + timedelta(days=i)
        
        # Appuntamenti del giorno
        appuntamenti_giorno = [a for a in appuntamenti if a.data_appuntamento.date() == giorno_data]
        
        # Slot del giorno
        slot_giorno = [s for s in slot_futuri if s.data_ora.date() == giorno_data and s.attivo]
        
        giorni_calendario.append({
            'data': giorno_data,
            'appuntamenti': appuntamenti_giorno,
            'slot': slot_giorno
        })
    
    
    # Formatta la data per la visualizzazione
    filtro_giorno_display = None
    if filtro_giorno:
        filtro_giorno_display = filtro_giorno.strftime('%d/%m/%Y')
    
    return render_template('admin/agenda_unificata.html',
                         oggi=oggi,
                         mese_corrente=mese_corrente.strftime('%Y-%m'),
                         mese_corrente_display=mese_corrente_display,
                         mese_precedente=mese_precedente,
                         mese_successivo=mese_successivo,
                         filtro_giorno=filtro_giorno_param,
                         filtro_giorno_display=filtro_giorno_display,
                         giorno_precedente=giorno_precedente,
                         giorno_successivo=giorno_successivo,
                         tutti_giorni=tutti_giorni,
                         slot_futuri=slot_futuri,
                         appuntamenti=appuntamenti,
                         appuntamenti_oggi=appuntamenti_oggi,
                         appuntamenti_in_attesa=appuntamenti_in_attesa,
                         appuntamenti_confermati=appuntamenti_confermati,
                         giorni_calendario=giorni_calendario)
