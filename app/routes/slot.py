from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, time

from app.models.models import db
from app.services.agenda_service import AgendaService, GIORNI_SETTIMANA
from app.utils.db_schema import ensure_agenda_schema

# ========================
# BLUEPRINT
# ========================
slot_bp = Blueprint('slot', __name__, url_prefix='/admin/slot')


@slot_bp.before_request
def _ensure_schema():
    ensure_agenda_schema()


# ========================
# FUNZIONI UTILI
# ========================
def admin_required(func):
    """Permette l'accesso solo all'admin (Enrico)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return wrapper


# ========================
# REDIRECT LEGACY
# ========================
@slot_bp.route('/')
@admin_required
def lista_slot():
    return redirect(url_for('slot.orari_settimanali'))


@slot_bp.route('/nuovo')
@admin_required
def nuovo_slot():
    return redirect(url_for('slot.orari_settimanali'))


@slot_bp.route('/genera')
@admin_required
def genera_slot():
    return redirect(url_for('slot.orari_settimanali'))


# ========================
# ORARI SETTIMANALI (slot ordinari)
# ========================
@slot_bp.route('/settimanali', methods=['GET', 'POST'])
@admin_required
def orari_settimanali():
    """Configura gli orari ricorrenti della settimana lavorativa."""
    if request.method == 'POST':
        action = request.form.get('action', 'aggiungi')
        try:
            if action == 'aggiungi':
                giorno = int(request.form['giorno_settimana'])
                ora_str = request.form['ora']
                note = (request.form.get('note') or '').strip() or None
                ora = datetime.strptime(ora_str, '%H:%M').time()
                AgendaService.aggiungi_orario(giorno, ora, note=note)
                flash("Orario aggiunto", "success")
            elif action == 'elimina':
                AgendaService.rimuovi_orario(int(request.form['orario_id']))
                flash("Orario rimosso", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"Errore: {exc}", "danger")
        return redirect(url_for('slot.orari_settimanali'))

    orari_per_giorno = AgendaService.get_orari_per_giorno()
    return render_template(
        'admin/orari_settimanali.html',
        giorni=GIORNI_SETTIMANA,
        orari_per_giorno=orari_per_giorno,
    )


# ========================
# ECCEZIONI (ferie / chiusure)
# ========================
@slot_bp.route('/eccezione', methods=['GET', 'POST'])
@admin_required
def eccezione_agenda():
    """Blocca uno o più giorni (ferie, festività, occasioni speciali)."""
    if request.method == 'POST':
        try:
            data_inizio = datetime.strptime(request.form['data_inizio'], '%Y-%m-%d').date()
            data_fine = datetime.strptime(request.form['data_fine'], '%Y-%m-%d').date()
            note = (request.form.get('note') or '').strip() or None
            AgendaService.aggiungi_eccezione(data_inizio, data_fine, note=note)
            flash("Periodo di chiusura registrato", "success")
            return redirect(url_for('agenda.agenda_unificata'))
        except Exception as exc:
            db.session.rollback()
            flash(f"Errore: {exc}", "danger")

    eccezioni = AgendaService.get_eccezioni(future_only=True)
    return render_template('admin/eccezione_agenda.html', eccezioni=eccezioni)


@slot_bp.route('/eccezione/<int:eccezione_id>/elimina', methods=['POST'])
@admin_required
def elimina_eccezione(eccezione_id):
    try:
        AgendaService.rimuovi_eccezione(eccezione_id)
        flash("Eccezione rimossa", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")
    return redirect(url_for('slot.eccezione_agenda'))
