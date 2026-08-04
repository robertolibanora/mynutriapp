from flask import Blueprint, render_template, redirect, url_for, flash, session, send_from_directory, abort
import os
from app.models.models import db, Documento
from app.config.config import get_full_path
from app.utils.tenant import assert_resource_patient_tenant, get_tenant_patient_or_404

# ========================
# BLUEPRINT
# ========================
documenti_bp = Blueprint('documenti', __name__, url_prefix='/documenti')


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
# SERVIRE FILE
# ========================
@documenti_bp.route('/file/<int:documento_id>')
def serve_file(documento_id):
    """Serve un file documento con controllo accessi (solo staff)."""
    documento = Documento.query.get_or_404(documento_id)

    if session.get('role') not in ('admin', 'nutrizionista'):
        abort(403)
    assert_resource_patient_tenant(documento)

    file_path = get_full_path(documento.file_path)
    if os.path.exists(file_path):
        from app.utils.audit import log_audit_event
        log_audit_event('DOWNLOAD', 'documento', documento_id)
        db.session.commit()
        
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return send_from_directory(directory, filename)
    abort(404)


# ========================
# ADMIN: LISTA DOCUMENTI PAZIENTE
# ========================
@documenti_bp.route('/admin/paziente/<int:patient_id>')
@admin_required
def lista_documenti_admin(patient_id):
    """L'admin può vedere tutti i documenti di un paziente specifico"""
    paziente = get_tenant_patient_or_404(patient_id)
    documenti = Documento.query.filter_by(patient_id=patient_id).order_by(Documento.data_upload.desc()).all()
    
    return render_template('admin/documenti_paziente.html', paziente=paziente, documenti=documenti)


# ========================
# ADMIN: ELIMINA DOCUMENTO PAZIENTE
# ========================
@documenti_bp.route('/admin/elimina/<int:documento_id>', methods=['POST'])
@admin_required
def elimina_documento_admin(documento_id):
    """L'admin può eliminare qualsiasi documento del proprio tenant"""
    documento = Documento.query.get_or_404(documento_id)
    assert_resource_patient_tenant(documento)
    paziente_id = documento.patient_id
    
    try:
        # Elimina file fisico
        if documento.file_path and os.path.exists(documento.file_path):
            os.remove(documento.file_path)
        
        db.session.delete(documento)
        db.session.commit()
        flash("Documento eliminato ✅", "success")
    
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")
    
    return redirect(url_for('documenti.lista_documenti_admin', patient_id=paziente_id))

