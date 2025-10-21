from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.utils import secure_filename
import os
from models import db, Documento, Patient
from config import get_upload_folder, get_allowed_extensions, get_full_path, Config

# ========================
# BLUEPRINT
# ========================
documenti_bp = Blueprint('documenti', __name__, url_prefix='/documenti')

# ========================
# CONFIG UPLOAD FILES
# ========================
UPLOAD_FOLDER = get_upload_folder('documenti')
ALLOWED_EXTENSIONS = get_allowed_extensions('documenti')


# ========================
# FUNZIONI UTILI
# ========================
def user_required(func):
    """Permette l'accesso solo agli user (pazienti)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return wrapper


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


def allowed_file(filename):
    """Controlla estensione file"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# SERVIRE FILE
# ========================
@documenti_bp.route('/file/<int:documento_id>')
def serve_file(documento_id):
    """Serve un file documento con controllo accessi"""
    documento = Documento.query.get_or_404(documento_id)
    
    # Controllo accessi
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Solo il proprietario o l'admin possono vedere il file
    if user_role == 'admin' or (user_role == 'user' and documento.patient_id == user_id):
        file_path = get_full_path(documento.file_path)
        if os.path.exists(file_path):
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            return send_from_directory(directory, filename)
        else:
            abort(404)
    else:
        abort(403)


# ========================
# USER: LISTA DOCUMENTI
# ========================
@documenti_bp.route('/user/')
@user_required
def lista_documenti_user():
    """Mostra i documenti del paziente loggato"""
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    paziente = Patient.query.get_or_404(user_id)
    documenti = Documento.query.filter_by(patient_id=user_id).order_by(Documento.data_upload.desc()).all()
    
    return render_template('user/documenti_lista.html', paziente=paziente, documenti=documenti)


# ========================
# USER: UPLOAD NUOVO DOCUMENTO
# ========================
@documenti_bp.route('/user/nuovo', methods=['GET', 'POST'])
@user_required
def nuovo_documento_user():
    """Permette al paziente di caricare un documento"""
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            tipo = request.form['tipo']
            descrizione = request.form.get('descrizione', '').strip()
            
            # --- Gestione file ---
            file = request.files.get('file')
            if not file or file.filename == '':
                flash("Seleziona un file da caricare", "danger")
                return redirect(request.url)
            
            if not allowed_file(file.filename):
                flash("Formato file non valido. Usa PDF, JPG o PNG", "danger")
                return redirect(request.url)
            
            filename = secure_filename(file.filename)
            # Aggiungi timestamp per evitare conflitti
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{user_id}_{timestamp}_{filename}"
            
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)
            
            # --- Crea record Documento ---
            nuovo = Documento(
                patient_id=user_id,
                tipo=tipo,
                file_path=save_path,
                descrizione=descrizione if descrizione else None
            )
            
            db.session.add(nuovo)
            db.session.commit()
            
            flash("Documento caricato con successo ✅", "success")
            return redirect(url_for('documenti.lista_documenti_user'))
        
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante il caricamento: {e}", "danger")
    
    return render_template('user/documento_nuovo.html')


# ========================
# USER: ELIMINA DOCUMENTO
# ========================
@documenti_bp.route('/user/elimina/<int:documento_id>', methods=['POST'])
@user_required
def elimina_documento_user(documento_id):
    """Permette al paziente di eliminare un proprio documento"""
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    documento = Documento.query.get_or_404(documento_id)
    
    # Verifica che il documento appartenga all'utente loggato
    if documento.patient_id != user_id:
        flash("Non puoi eliminare questo documento", "danger")
        return redirect(url_for('documenti.lista_documenti_user'))
    
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
    
    return redirect(url_for('documenti.lista_documenti_user'))


# ========================
# ADMIN: LISTA DOCUMENTI PAZIENTE
# ========================
@documenti_bp.route('/admin/paziente/<int:patient_id>')
@admin_required
def lista_documenti_admin(patient_id):
    """L'admin può vedere tutti i documenti di un paziente specifico"""
    paziente = Patient.query.get_or_404(patient_id)
    documenti = Documento.query.filter_by(patient_id=patient_id).order_by(Documento.data_upload.desc()).all()
    
    return render_template('admin/documenti_paziente.html', paziente=paziente, documenti=documenti)


# ========================
# ADMIN: ELIMINA DOCUMENTO PAZIENTE
# ========================
@documenti_bp.route('/admin/elimina/<int:documento_id>', methods=['POST'])
@admin_required
def elimina_documento_admin(documento_id):
    """L'admin può eliminare qualsiasi documento"""
    documento = Documento.query.get_or_404(documento_id)
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

