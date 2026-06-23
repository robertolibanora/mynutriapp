from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from app.models.models import db, Appuntamento, Patient


# ========================
# BLUEPRINT
# ========================
appuntamenti_bp = Blueprint('appuntamenti', __name__, url_prefix='/appuntamenti')

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


def user_required(func):
    """Accesso riservato all’utente loggato"""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login come paziente", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


# ========================
# ADMIN: TUTTI GLI APPUNTAMENTI
# ========================
@appuntamenti_bp.route('/admin')
@admin_required
def lista_admin():
    """Redirect alla pagina agenda unificata"""
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))


# ========================
# ADMIN: CREA NUOVO APPUNTAMENTO
# ========================
@appuntamenti_bp.route('/admin/nuovo', methods=['GET', 'POST'])
@admin_required
def nuovo_admin():
    """Crea manualmente un appuntamento"""
    if request.method == 'POST':
        try:
            patient_id = request.form['patient_id']
            data_appuntamento = request.form['data_appuntamento']
            tipo = request.form['tipo']
            note = request.form.get('note')

            nuovo = Appuntamento(
                patient_id=patient_id,
                created_by='Enrico',
                data_appuntamento=data_appuntamento,
                tipo=tipo,
                stato='confermato',
                note=note
            )

            db.session.add(nuovo)
            db.session.commit()
            
            # 🔔 INVIO WHATSAPP AUTOMATICO per nuovo appuntamento
            from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato
            safe_trigger_appuntamento_stato(nuovo, 'confermato')
            
            flash("Appuntamento aggiunto ✅", "success")
            return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore: {e}", "danger")

    pazienti = Patient.query.order_by(Patient.nome.asc()).all()
    return render_template('admin/appuntamento_nuovo.html', pazienti=pazienti)


# ========================
# ADMIN: CAMBIA STATO APPUNTAMENTO
# ========================
@appuntamenti_bp.route('/admin/cambia_stato/<int:id>/<string:nuovo_stato>', methods=['POST'])
@admin_required
def cambia_stato_admin(id, nuovo_stato):
    """Cambia lo stato di un appuntamento (conferma, completa, annulla)"""
    from app.models.models import SlotDisponibilita
    
    app = Appuntamento.query.get_or_404(id)
    
    stati_validi = ['in_attesa', 'confermato', 'completato', 'annullato']
    if nuovo_stato not in stati_validi:
        flash("Stato non valido", "danger")
        return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))
    
    try:
        vecchio_stato = app.stato
        app.stato = nuovo_stato
        
        # Se l'appuntamento viene annullato, riattiva lo slot
        if nuovo_stato == 'annullato' and vecchio_stato in ['in_attesa', 'confermato']:
            slot = SlotDisponibilita.query.filter_by(data_ora=app.data_appuntamento).first()
            if slot:
                slot.attivo = True
        
        db.session.commit()
        
        # 🔔 INVIO WHATSAPP AUTOMATICO
        from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato
        safe_trigger_appuntamento_stato(app, nuovo_stato)
        
        messaggi = {
            'confermato': 'Appuntamento confermato ✅',
            'completato': 'Appuntamento completato ✅',
            'annullato': 'Appuntamento annullato ❌ (slot riattivato)',
            'in_attesa': 'Appuntamento rimesso in attesa ⏳'
        }
        flash(messaggi.get(nuovo_stato, 'Stato aggiornato'), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante aggiornamento: {e}", "danger")
    
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))


# ========================
# ADMIN: ELIMINA APPUNTAMENTO
# ========================
@appuntamenti_bp.route('/admin/elimina/<int:id>', methods=['POST'])
@admin_required
def elimina_admin(id):
    from app.models.models import SlotDisponibilita
    
    app = Appuntamento.query.get_or_404(id)
    data_appuntamento = app.data_appuntamento
    
    try:
        db.session.delete(app)
        
        # Riattiva lo slot se esiste
        slot = SlotDisponibilita.query.filter_by(data_ora=data_appuntamento).first()
        if slot:
            slot.attivo = True
        
        db.session.commit()
        flash("Appuntamento eliminato ✅ (slot riattivato)", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante eliminazione: {e}", "danger")
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))


# ========================
# USER: VISUALIZZA I PROPRI APPUNTAMENTI
# ========================
@appuntamenti_bp.route('/user')
@user_required
def lista_user():
    """Mostra gli appuntamenti del paziente loggato"""
    from datetime import datetime
    
    user_id = session.get('user_id')
    appuntamenti = Appuntamento.query.filter_by(patient_id=user_id).order_by(Appuntamento.data_appuntamento.asc()).all()
    return render_template('user/appuntamenti_lista.html', appuntamenti=appuntamenti, now=datetime.now())


# ========================
# USER: PRENOTA UN APPUNTAMENTO
# ========================
@appuntamenti_bp.route('/user/prenota', methods=['GET', 'POST'])
@user_required
def prenota_user():
    """Il paziente può prenotare scegliendo una data disponibile"""
    from app.models.models import SlotDisponibilita
    from datetime import datetime
    
    user_id = session.get('user_id')

    if request.method == 'POST':
        try:
            data_appuntamento_str = request.form['data_appuntamento']
            tipo = request.form['tipo']
            note = request.form.get('note')
            
            # Converti la stringa in datetime
            data_appuntamento = datetime.strptime(data_appuntamento_str, '%Y-%m-%d %H:%M:%S')

            # Crea l'appuntamento
            nuovo = Appuntamento(
                patient_id=user_id,
                created_by='user',
                data_appuntamento=data_appuntamento,
                tipo=tipo,
                stato='in_attesa',
                note=note
            )

            db.session.add(nuovo)
            
            # Disattiva lo slot corrispondente
            slot = SlotDisponibilita.query.filter_by(data_ora=data_appuntamento).first()
            if slot:
                slot.attivo = False
            
            db.session.commit()
            flash("Richiesta di appuntamento inviata ✅", "success")
            return redirect(url_for('appuntamenti.lista_user'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore: {e}", "danger")

    # Legge slot dal database (solo futuri e attivi)
    oggi = datetime.now()
    slot_db = SlotDisponibilita.query.filter(
        SlotDisponibilita.data_ora >= oggi,
        SlotDisponibilita.attivo == True
    ).order_by(SlotDisponibilita.data_ora.asc()).all()
    
    # Filtra solo slot non già prenotati
    slot_liberi = []
    for slot in slot_db:
        # Verifica se lo slot è già occupato
        appuntamento_esistente = Appuntamento.query.filter_by(
            data_appuntamento=slot.data_ora
        ).first()
        
        if not appuntamento_esistente:
            label = slot.data_ora.strftime('%A %d %B %Y ore %H:%M')
            if slot.note:
                label += f" - {slot.note}"
            slot_liberi.append({
                "data": slot.data_ora.strftime('%Y-%m-%d %H:%M:%S'),
                "label": label,
                "note": slot.note or ""
            })

    return render_template('user/appuntamento_prenota.html', slot_liberi=slot_liberi)

# ========================
# ADMIN: VISTA CALENDARIO MENSILE
# ========================
from datetime import date
import calendar

@appuntamenti_bp.route('/admin/calendario')
@admin_required
def calendario_admin():
    """Redirect alla pagina agenda unificata"""
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))