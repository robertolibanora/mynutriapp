from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from app.models.models import db, Appuntamento, Patient
from app.services.agenda_service import AgendaService
from app.utils.tenant import (
    assert_appuntamento_tenant,
    assert_patient_tenant,
    require_tenant,
    tenant_filter_enabled,
)


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
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso non autorizzato", "danger")
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

            uid = require_tenant()
            paziente = Patient.query.get_or_404(patient_id)
            assert_patient_tenant(paziente)

            data_appuntamento = datetime.strptime(data_appuntamento_str, '%Y-%m-%dT%H:%M')
            if not AgendaService.is_slot_disponibile(data_appuntamento, utente_id=uid):
                flash("Orario non disponibile o già occupato", "warning")
                return redirect(request.url)

            nuovo = Appuntamento(
                patient_id=patient_id,
                utente_id=uid,
                created_by='admin',
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
            # Creato già come 'confermato': non aprire il filtro 'Da confermare' (solo in_attesa)
            return redirect(url_for(
                'agenda.agenda_unificata',
                tab='appuntamenti',
                mese=data_appuntamento.strftime('%Y-%m'),
                filtro_giorno=data_appuntamento.strftime('%Y-%m-%d'),
            ))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore: {e}", "danger")

    q = Patient.query
    if tenant_filter_enabled():
        q = q.filter(Patient.nutrizionista_id == require_tenant())
    pazienti = q.order_by(Patient.nome.asc()).all()
    selected_patient_id = request.args.get("patient_id", type=int)
    return render_template(
        "admin/appuntamento_nuovo.html",
        pazienti=pazienti,
        selected_patient_id=selected_patient_id,
    )


# ========================
# ADMIN: CAMBIA STATO APPUNTAMENTO
# ========================
@appuntamenti_bp.route('/admin/cambia_stato/<int:id>/<string:nuovo_stato>', methods=['POST'])
@admin_required
def cambia_stato_admin(id, nuovo_stato):
    """Cambia lo stato di un appuntamento (conferma, completa, annulla)"""
    app = Appuntamento.query.get_or_404(id)
    assert_appuntamento_tenant(app)
    
    stati_validi = ['in_attesa', 'confermato', 'completato', 'annullato']
    if nuovo_stato not in stati_validi:
        flash("Stato non valido", "danger")
        return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))
    
    try:
        app.stato = nuovo_stato
        from app.services.paziente_service import sync_stato_cliente_da_appuntamento
        sync_stato_cliente_da_appuntamento(app, nuovo_stato)
        db.session.commit()
        
        # 🔔 INVIO WHATSAPP AUTOMATICO
        from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato
        safe_trigger_appuntamento_stato(app, nuovo_stato)
        
        messaggi = {
            'confermato': 'Appuntamento confermato ✅ — cliente attivo',
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
    assert_appuntamento_tenant(app)
    
    try:
        db.session.delete(app)
        db.session.commit()
        flash("Appuntamento eliminato", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante eliminazione: {e}", "danger")
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))


# ========================
# ADMIN: VISTA CALENDARIO MENSILE
# ========================
@appuntamenti_bp.route('/admin/calendario')
@admin_required
def calendario_admin():
    """Redirect alla pagina agenda unificata"""
    return redirect(url_for('agenda.agenda_unificata', tab='appuntamenti', filtro='da_confermare'))