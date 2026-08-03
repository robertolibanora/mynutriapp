"""
Routes per gestione WhatsApp semplificata
Solo gestione trigger e invio messaggi personalizzati
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from .broadcast import (
    invia_broadcast_personalizzato,
    sostituisci_variabili,
    load_trigger_templates,
    save_trigger_templates
)
from .triggers import (
    TRIGGERS_ENABLED,
    enable_trigger,
    disable_trigger,
    print_trigger_status
)
from app.models.models import Patient
from app.utils.tenant import patients_query_for_tenant

# Blueprint per le routes broadcast
broadcast_bp = Blueprint('broadcast', __name__, url_prefix='/admin/broadcast')

# Decoratore per accesso admin
def admin_required(func):
    """Accesso riservato all'admin"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper

@broadcast_bp.route('/')
@admin_required
def dashboard():
    """Dashboard semplificata per WhatsApp"""
    # Statistiche base (solo tenant corrente)
    q = patients_query_for_tenant()
    totale_pazienti = q.count()
    pazienti_con_telefono = q.filter(Patient.telefono.isnot(None)).count()
    
    # Stato trigger
    trigger_stats = {
        'appuntamenti': TRIGGERS_ENABLED['appuntamenti'],
        'diete': TRIGGERS_ENABLED['diete'],
        'allenamenti': TRIGGERS_ENABLED['allenamenti'],
        'scadenze': TRIGGERS_ENABLED['scadenze']
    }
    
    stats = {
        'totale_pazienti': totale_pazienti,
        'con_telefono': pazienti_con_telefono,
        'trigger_stats': trigger_stats
    }
    
    templates = load_trigger_templates()
    return render_template('admin/broadcast_dashboard.html', stats=stats, trigger_templates=templates)

@broadcast_bp.route('/config', methods=['GET', 'POST'])
@admin_required
def config_templates():
    """Schermata di configurazione dei messaggi per i trigger automatici."""
    templates = load_trigger_templates()
    if request.method == 'POST':
        try:
            # Recupera i valori dal form
            templates['appuntamenti'] = request.form.get('tpl_appuntamenti', templates['appuntamenti'])
            templates['diete'] = request.form.get('tpl_diete', templates['diete'])
            templates['allenamenti'] = request.form.get('tpl_allenamenti', templates['allenamenti'])
            templates['scadenze'] = request.form.get('tpl_scadenze', templates['scadenze'])
            if save_trigger_templates(templates):
                flash('Template salvati correttamente', 'success')
                return redirect(url_for('broadcast.config_templates'))
            else:
                flash('Errore nel salvataggio dei template', 'danger')
        except Exception as e:
            flash(f'Errore: {e}', 'danger')
    return render_template('admin/broadcast_config.html', templates=templates)

@broadcast_bp.route('/nuovo', methods=['GET', 'POST'])
@admin_required
def nuovo_broadcast():
    """Invia messaggio personalizzato a tutti i pazienti o a uno solo."""
    from app.utils.tenant import assert_patient_tenant
    from app.routes.whatsapp.broadcast import sostituisci_variabili
    from app.routes.whatsapp.sender import invia_whatsapp

    selected_patient_id = request.args.get('patient_id', type=int) or request.form.get('patient_id', type=int)
    selected_patient = None
    if selected_patient_id:
        selected_patient = Patient.query.get(selected_patient_id)
        if selected_patient:
            try:
                assert_patient_tenant(selected_patient)
            except Exception:
                selected_patient = None
                selected_patient_id = None

    if request.method == 'POST':
        try:
            messaggio = request.form['messaggio']

            if not messaggio.strip():
                flash("Inserisci un messaggio", "danger")
                return render_template(
                    'admin/broadcast_nuovo.html',
                    selected_patient=selected_patient,
                    selected_patient_id=selected_patient_id,
                )

            if selected_patient and selected_patient.telefono:
                testo = sostituisci_variabili(messaggio, selected_patient)
                ok = invia_whatsapp(selected_patient.telefono, testo)
                if ok:
                    flash(f"Messaggio inviato a {selected_patient.nome} {selected_patient.cognome}", "success")
                else:
                    flash("Invio non riuscito", "danger")
                return redirect(url_for('patients.dettaglio_paziente', patient_id=selected_patient.id, tab='messaggi'))

            stats = invia_broadcast_personalizzato(messaggio)
            flash(f"Messaggio inviato! Inviati: {stats['inviati']}, Errori: {stats['errori']}", "success")
            return redirect(url_for('broadcast.dashboard'))

        except Exception as e:
            flash(f"Errore durante l'invio: {e}", "danger")

    return render_template(
        'admin/broadcast_nuovo.html',
        selected_patient=selected_patient,
        selected_patient_id=selected_patient_id,
    )

@broadcast_bp.route('/anteprima', methods=['POST'])
@admin_required
def anteprima_messaggio():
    """Mostra anteprima del messaggio con variabili sostituite"""
    try:
        messaggio = request.form['messaggio']
        
        # Prendi il primo paziente del tenant come esempio
        paziente_esempio = patients_query_for_tenant().filter(
            Patient.telefono.isnot(None)
        ).first()
        
        if not paziente_esempio:
            return jsonify({'errore': 'Nessun paziente trovato per l\'anteprima'})
        
        # Sostituisci variabili
        messaggio_anteprima = sostituisci_variabili(messaggio, paziente_esempio)
        
        return jsonify({
            'successo': True,
            'messaggio': messaggio_anteprima,
            'paziente_esempio': f"{paziente_esempio.nome} {paziente_esempio.cognome}"
        })
        
    except Exception as e:
        return jsonify({'errore': str(e)})

@broadcast_bp.route('/trigger/<trigger_name>/toggle', methods=['POST'])
@admin_required
def toggle_trigger(trigger_name):
    """Abilita/disabilita un trigger specifico"""
    try:
        if trigger_name in TRIGGERS_ENABLED:
            # Toggle dello stato
            TRIGGERS_ENABLED[trigger_name] = not TRIGGERS_ENABLED[trigger_name]
            stato = "abilitato" if TRIGGERS_ENABLED[trigger_name] else "disabilitato"
            flash(f"Trigger '{trigger_name}' {stato}", "success")
        else:
            flash(f"Trigger '{trigger_name}' non trovato", "danger")
    except Exception as e:
        flash(f"Errore: {e}", "danger")
    
    return redirect(url_for('broadcast.dashboard'))
