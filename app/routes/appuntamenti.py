from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from app.models.models import db, Appuntamento, Patient
from app.services.agenda_service import AgendaService


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
            data_appuntamento_str = request.form['data_appuntamento']
            tipo = request.form['tipo']
            note = request.form.get('note')

            data_appuntamento = datetime.strptime(data_appuntamento_str, '%Y-%m-%dT%H:%M')
            if not AgendaService.is_slot_disponibile(data_appuntamento):
                flash("Orario non disponibile o già occupato", "warning")
                return redirect(request.url)

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
    app = Appuntamento.query.get_or_404(id)
    
    stati_validi = ['in_attesa', 'confermato', 'completato', 'annullato']
    if nuovo_stato not in stati_validi:
        flash("Stato non valido", "danger")
        return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))
    
    try:
        vecchio_stato = app.stato
        app.stato = nuovo_stato
        db.session.commit()
        
        # 🔔 INVIO WHATSAPP AUTOMATICO
        from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato
        safe_trigger_appuntamento_stato(app, nuovo_stato)
        
        messaggi = {
            'confermato': 'Appuntamento confermato ✅',
            'completato': 'Appuntamento completato ✅',
            'annullato': 'Appuntamento annullato',
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
    app = Appuntamento.query.get_or_404(id)
    
    try:
        db.session.delete(app)
        db.session.commit()
        flash("Appuntamento eliminato", "success")
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
    from datetime import datetime
    
    user_id = session.get('user_id')

    if request.method == 'POST':
        try:
            data_appuntamento_str = request.form['data_appuntamento']
            tipo = request.form['tipo']
            note = request.form.get('note')
            
            data_appuntamento = datetime.strptime(data_appuntamento_str, '%Y-%m-%d %H:%M:%S')
            if not AgendaService.is_slot_disponibile(data_appuntamento):
                flash("Questo orario non è più disponibile", "warning")
                return redirect(request.url)

            nuovo = Appuntamento(
                patient_id=user_id,
                created_by='user',
                data_appuntamento=data_appuntamento,
                tipo=tipo,
                stato='in_attesa',
                note=note
            )

            db.session.add(nuovo)
            db.session.commit()
            flash("Richiesta di appuntamento inviata", "success")
            return redirect(url_for('appuntamenti.lista_user'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore: {e}", "danger")

    slot_liberi = AgendaService.slot_liberi_per_select()
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