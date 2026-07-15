from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.models.models import db, Patient, Dieta, Allenamento, Progresso, Appuntamento, Listino, Vendita, SegretarioConfig
from app.services.agenda_service import AgendaService
from app.services import call_forwarding_service
from app.utils.db_schema import ensure_segretario_deviazione_schema, ensure_agenda_schema
from datetime import datetime, date, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

# ============================
# DASHBOARD ADMIN
# ============================
@dashboard_bp.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash("Accesso non autorizzato", "danger")
        return redirect(url_for('auth.login'))

    ensure_segretario_deviazione_schema()
    ensure_agenda_schema()
    
    # Calcola statistiche
    oggi = datetime.now()
    oggi_data = oggi.date()
    inizio_mese = oggi_data.replace(day=1)
    fine_mese = (inizio_mese + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    # Statistiche principali
    n_pazienti = Patient.query.count()
    n_appuntamenti_oggi = Appuntamento.query.filter(
        db.func.date(Appuntamento.data_appuntamento) == oggi_data
    ).count()
    
    n_diete_attive = Dieta.query.filter(
        Dieta.data_inizio <= oggi_data,
        Dieta.data_fine >= oggi_data
    ).count()
    
    # Entrate del mese corrente
    entrate_mese = db.session.query(db.func.sum(Vendita.importo_finale)).filter(
        db.func.date(Vendita.data_acquisto) >= inizio_mese,
        db.func.date(Vendita.data_acquisto) <= fine_mese
    ).scalar() or 0
    
    # Statistiche aggiuntive
    n_slot_futuri = len(AgendaService.slot_liberi())
    
    n_appuntamenti_settimana = Appuntamento.query.filter(
        Appuntamento.data_appuntamento >= oggi,
        Appuntamento.data_appuntamento <= oggi + timedelta(days=7)
    ).count()
    
    appuntamenti_oggi = Appuntamento.query.filter(
        db.func.date(Appuntamento.data_appuntamento) == oggi_data
    ).order_by(Appuntamento.data_appuntamento.asc()).all()

    # Prodotti più venduti questo mese
    prodotti_top = db.session.query(
        Listino.nome_prodotto,
        db.func.count(Vendita.id).label('vendite_count'),
        db.func.sum(Vendita.importo_finale).label('totale_importo')
    ).join(Vendita).filter(
        db.func.date(Vendita.data_acquisto) >= inizio_mese,
        db.func.date(Vendita.data_acquisto) <= fine_mese
    ).group_by(Listino.id, Listino.nome_prodotto).order_by(
        db.func.count(Vendita.id).desc()
    ).limit(3).all()

    segretario_cfg = SegretarioConfig.query.first()
    deviazione_attiva = bool(segretario_cfg and segretario_cfg.deviazione_attiva)
    deviazione = call_forwarding_service.status_info(deviazione_attiva)
    if segretario_cfg:
        deviazione["aggiornata_at"] = segretario_cfg.deviazione_aggiornata_at

    return render_template('admin/dashboard.html',
                         n_pazienti=n_pazienti,
                         n_appuntamenti_oggi=n_appuntamenti_oggi,
                         appuntamenti_oggi=appuntamenti_oggi,
                         totale_mese=int(entrate_mese),
                         n_slot_futuri=n_slot_futuri,
                         n_appuntamenti_settimana=n_appuntamenti_settimana,
                         prodotti_top=prodotti_top,
                         deviazione=deviazione,
                         oggi=oggi)

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
    
    # Recupera dati paziente
    paziente = Patient.query.get_or_404(user_id)
    
    # Ultima dieta (PDF legacy)
    ultima_dieta = Dieta.query.filter_by(patient_id=user_id).order_by(Dieta.created_at.desc()).first()

    # Ultimo piano alimentare strutturato (nuovo flusso)
    from app.models.models import DietPlan
    ultimo_diet_plan = (
        DietPlan.query.filter_by(patient_id=user_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .first()
    )
    
    # Ultimo allenamento
    ultimo_allenamento = Allenamento.query.filter_by(patient_id=user_id).order_by(Allenamento.created_at.desc()).first()
    
    # Peso più recente
    ultimo_progresso = Progresso.query.filter_by(patient_id=user_id).order_by(Progresso.data_check.desc()).first()
    
    # Prossimo appuntamento
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