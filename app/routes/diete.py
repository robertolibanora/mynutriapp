from flask import Blueprint, render_template, redirect, url_for, flash, session, send_from_directory, abort
import os
from datetime import date
from app.models.models import db, Dieta
from app.config.config import get_full_path
from app.utils.tenant import assert_resource_patient_tenant, get_tenant_patient_or_404

# ========================
# BLUEPRINT
# ========================
diete_bp = Blueprint('diete', __name__, url_prefix='/admin/diete')


# ========================
# FUNZIONI UTILI
# ========================
def admin_required(func):
    """Permette l'accesso solo all'admin (Enrico)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


# ========================
# SERVIRE FILE DIETA
# ========================
@diete_bp.route('/file/<int:dieta_id>')
def serve_file(dieta_id):
    """Serve un file dieta con controllo accessi (solo staff)."""
    dieta = Dieta.query.get_or_404(dieta_id)

    if session.get('role') not in ('admin', 'nutrizionista'):
        abort(403)
    assert_resource_patient_tenant(dieta)

    file_path = get_full_path(dieta.pdf_path)
    if os.path.exists(file_path):
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return send_from_directory(directory, filename)
    abort(404)


# ========================
# LISTA DIETE DI UN PAZIENTE
# ========================
@diete_bp.route('/paziente/<int:patient_id>')
@admin_required
def diete_paziente(patient_id):
    """Mostra solo le diete di un singolo paziente"""
    paziente = get_tenant_patient_or_404(patient_id)
    today = date.today()
    return render_template('admin/diete_paziente.html', paziente=paziente, diete=paziente.diete, today=today)


# ========================
# CREA NUOVA DIETA (legacy PDF) → redirect al piano strutturato
# ========================
@diete_bp.route('/nuova/<int:patient_id>', methods=['GET', 'POST'])
@admin_required
def nuova_dieta(patient_id):
    """Endpoint legacy rimosso: reindirizza al flusso diet-plans."""
    get_tenant_patient_or_404(patient_id)
    return redirect(
        url_for('diete_plans.new_diet_plan_standalone', patient_id=patient_id)
    )


# ========================
# ELIMINA DIETA
# ========================
@diete_bp.route('/elimina/<int:dieta_id>', methods=['POST'])
@admin_required
def elimina_dieta(dieta_id):
    dieta = Dieta.query.get_or_404(dieta_id)
    assert_resource_patient_tenant(dieta)
    patient_id = dieta.patient_id

    try:
        # 🔥 Rimuove file PDF se esiste
        if dieta.pdf_path and os.path.exists(dieta.pdf_path):
            os.remove(dieta.pdf_path)

        db.session.delete(dieta)
        db.session.commit()
        flash("Dieta eliminata ✅", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")

    return redirect(url_for('diete.diete_paziente', patient_id=patient_id))