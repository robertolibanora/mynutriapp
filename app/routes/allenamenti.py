from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.utils import secure_filename
import os
from datetime import date
from app.models.models import db, Allenamento, Patient
from app.config.config import get_upload_folder, get_allowed_extensions, get_full_path

# ========================
# BLUEPRINT
# ========================
allenamenti_bp = Blueprint('allenamenti', __name__, url_prefix='/admin/allenamenti')

# ========================
# CONFIG UPLOAD FILES
# ========================
UPLOAD_FOLDER = get_upload_folder('allenamenti')
ALLOWED_EXTENSIONS = get_allowed_extensions('allenamenti')


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


def allowed_file(filename):
    """Controlla estensione file"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# SERVIRE FILE ALLENAMENTO
# ========================
@allenamenti_bp.route('/file/<int:allenamento_id>')
def serve_file(allenamento_id):
    """Serve un file allenamento con controllo accessi"""
    allenamento = Allenamento.query.get_or_404(allenamento_id)
    
    # Controllo accessi
    user_role = session.get('role')
    user_id = session.get('user_id')
    
    # Admin può vedere tutto, user può vedere solo i propri allenamenti
    if user_role == 'admin' or (user_role == 'user' and allenamento.patient_id == user_id):
        file_path = get_full_path(allenamento.pdf_path)
        if os.path.exists(file_path):
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            return send_from_directory(directory, filename)
        else:
            abort(404)
    else:
        abort(403)


# ========================
# LISTA ALLENAMENTI DI UN PAZIENTE
# ========================
@allenamenti_bp.route('/paziente/<int:patient_id>')
@admin_required
def allenamenti_paziente(patient_id):
    """Mostra solo gli allenamenti di un singolo paziente"""
    paziente = Patient.query.get_or_404(patient_id)
    today = date.today()
    return render_template('admin/allenamenti_paziente.html', paziente=paziente, allenamenti=paziente.allenamenti, today=today)


# ========================
# CREA NUOVO ALLENAMENTO
# ========================
@allenamenti_bp.route('/nuovo/<int:patient_id>', methods=['GET', 'POST'])
@admin_required
def nuovo_allenamento(patient_id):
    paziente = Patient.query.get_or_404(patient_id)

    if request.method == 'POST':
        try:
            data_inizio = request.form['data_inizio']
            data_fine = request.form['data_fine']
            note = request.form.get('note')

            # --- Upload PDF ---
            file = request.files['pdf']
            if not file or not allowed_file(file.filename):
                flash("Carica un file PDF valido", "danger")
                return redirect(request.url)

            filename = secure_filename(file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)

            # --- Crea record ---
            nuovo = Allenamento(
                patient_id=patient_id,
                data_inizio=data_inizio,
                data_fine=data_fine,
                pdf_path=save_path,
                note=note
            )

            db.session.add(nuovo)
            db.session.commit()
            
            # 🔔 INVIO WHATSAPP AUTOMATICO
            from app.routes.whatsapp.triggers import safe_trigger_nuovo_allenamento
            safe_trigger_nuovo_allenamento(paziente, nuovo)
            
            flash("Nuovo piano di allenamento caricato ✅", "success")
            return redirect(url_for('allenamenti.allenamenti_paziente', patient_id=patient_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante il caricamento: {e}", "danger")

    return render_template('admin/allenamento_nuovo.html', paziente=paziente)


# ========================
# ELIMINA ALLENAMENTO
# ========================
@allenamenti_bp.route('/elimina/<int:allenamento_id>', methods=['POST'])
@admin_required
def elimina_allenamento(allenamento_id):
    allenamento = Allenamento.query.get_or_404(allenamento_id)
    patient_id = allenamento.patient_id

    try:
        # 🔥 Elimina file PDF se presente
        if allenamento.pdf_path and os.path.exists(allenamento.pdf_path):
            os.remove(allenamento.pdf_path)

        db.session.delete(allenamento)
        db.session.commit()
        flash("Allenamento eliminato ✅", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")

    return redirect(url_for('allenamenti.allenamenti_paziente', patient_id=patient_id))


# ========================
# LISTA ALLENAMENTI USER (i propri allenamenti)
# ========================
@allenamenti_bp.route('/user/')
@user_required
def lista_allenamenti_user():
    """Mostra gli allenamenti del paziente loggato"""
    from datetime import datetime
    
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    paziente = Patient.query.get_or_404(user_id)
    allenamenti = Allenamento.query.filter_by(patient_id=user_id).order_by(Allenamento.created_at.desc()).all()
    
    return render_template('user/allenamenti_lista.html', paziente=paziente, allenamenti=allenamenti, now=datetime.now().date())