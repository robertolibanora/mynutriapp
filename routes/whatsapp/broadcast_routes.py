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
from models import Patient

# Blueprint per le routes broadcast
broadcast_bp = Blueprint('broadcast', __name__, url_prefix='/admin/broadcast')

# Decoratore per accesso admin
def admin_required(func):
    """Accesso riservato all'admin"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper

@broadcast_bp.route('/')
@admin_required
def dashboard():
    """Dashboard semplificata per WhatsApp"""
    # Statistiche base
    totale_pazienti = Patient.query.count()
    pazienti_con_telefono = Patient.query.filter(Patient.telefono.isnot(None)).count()
    
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
    """Invia messaggio personalizzato a tutti i pazienti"""
    if request.method == 'POST':
        try:
            messaggio = request.form['messaggio']
            
            if not messaggio.strip():
                flash("Inserisci un messaggio", "danger")
                return render_template('admin/broadcast_nuovo.html')
            
            # Invia a tutti i pazienti
            stats = invia_broadcast_personalizzato(messaggio)
            
            # Messaggio di successo
            flash(f"Messaggio inviato! Inviati: {stats['inviati']}, Errori: {stats['errori']}", "success")
            return redirect(url_for('broadcast.dashboard'))
            
        except Exception as e:
            flash(f"Errore durante l'invio: {e}", "danger")
    
    return render_template('admin/broadcast_nuovo.html')

@broadcast_bp.route('/anteprima', methods=['POST'])
@admin_required
def anteprima_messaggio():
    """Mostra anteprima del messaggio con variabili sostituite"""
    try:
        messaggio = request.form['messaggio']
        
        # Prendi il primo paziente come esempio
        paziente_esempio = Patient.query.filter(Patient.telefono.isnot(None)).first()
        
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
