from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.utils import secure_filename
import os
from datetime import date
from app.models.models import db, Dieta, Patient
from app.config.config import get_upload_folder, get_allowed_extensions, get_full_path

# ========================
# BLUEPRINT
# ========================
diete_bp = Blueprint('diete', __name__, url_prefix='/admin/diete')

# ========================
# CONFIG UPLOAD FILES
# ========================
UPLOAD_FOLDER = get_upload_folder('diete')
ALLOWED_EXTENSIONS = get_allowed_extensions('diete')


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
# SERVIRE FILE DIETA
# ========================
@diete_bp.route('/file/<int:dieta_id>')
def serve_file(dieta_id):
    """Serve un file dieta con controllo accessi"""
    dieta = Dieta.query.get_or_404(dieta_id)
    
    # Controllo accessi
    user_role = session.get('role')
    user_id = session.get('user_id')
    
    # Admin può vedere tutto, user può vedere solo le proprie diete
    if user_role == 'admin' or (user_role == 'user' and dieta.patient_id == user_id):
        file_path = get_full_path(dieta.pdf_path)
        if os.path.exists(file_path):
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            return send_from_directory(directory, filename)
        else:
            abort(404)
    else:
        abort(403)


# ========================
# LISTA DIETE DI UN PAZIENTE
# ========================
@diete_bp.route('/paziente/<int:patient_id>')
@admin_required
def diete_paziente(patient_id):
    """Mostra solo le diete di un singolo paziente"""
    paziente = Patient.query.get_or_404(patient_id)
    today = date.today()
    return render_template('admin/diete_paziente.html', paziente=paziente, diete=paziente.diete, today=today)


# ========================
# CREA NUOVA DIETA
# ========================
@diete_bp.route('/nuova/<int:patient_id>', methods=['GET', 'POST'])
@admin_required
def nuova_dieta(patient_id):
    paziente = Patient.query.get_or_404(patient_id)

    if request.method == 'POST':
        try:
            # --- Estrai dati dal form ---
            data_inizio = request.form['data_inizio']
            data_fine = request.form['data_fine']
            kcal = request.form['kcal']
            carbo = request.form.get('carbo')
            proteine = request.form.get('proteine')
            grassi = request.form.get('grassi')
            note = request.form.get('note')

            # --- Gestione file PDF ---
            file = request.files['pdf']
            if not file or not allowed_file(file.filename):
                flash("Carica un file PDF valido", "danger")
                return redirect(request.url)

            filename = secure_filename(file.filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(save_path)

            # --- Crea nuovo record Dieta ---
            nuova = Dieta(
                patient_id=patient_id,
                data_inizio=data_inizio,
                data_fine=data_fine,
                pdf_path=save_path,
                kcal=kcal,
                carbo=carbo if carbo else None,
                proteine=proteine if proteine else None,
                grassi=grassi if grassi else None,
                note=note
            )

            db.session.add(nuova)
            db.session.commit()

            # 🔔 INVIO WHATSAPP AUTOMATICO
            from app.routes.whatsapp.triggers import safe_trigger_nuova_dieta
            safe_trigger_nuova_dieta(paziente, nuova)

            flash("Nuova dieta caricata con successo ✅", "success")
            return redirect(url_for('diete.diete_paziente', patient_id=patient_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante il caricamento: {e}", "danger")

    return render_template('admin/dieta_nuova.html', paziente=paziente)


# ========================
# ELIMINA DIETA
# ========================
@diete_bp.route('/elimina/<int:dieta_id>', methods=['POST'])
@admin_required
def elimina_dieta(dieta_id):
    dieta = Dieta.query.get_or_404(dieta_id)
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


# ========================
# LISTA DIETE USER (le proprie diete)
# ========================
@diete_bp.route('/user/')
@user_required
def lista_diete_user():
    """Mostra le diete del paziente loggato"""
    from datetime import datetime
    
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    paziente = Patient.query.get_or_404(user_id)
    diete = Dieta.query.filter_by(patient_id=user_id).order_by(Dieta.created_at.desc()).all()

    # Piani alimentari strutturati (nuovo flusso)
    from app.models.models import DietPlan
    diet_plans = (
        DietPlan.query.filter_by(patient_id=user_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .all()
    )

    return render_template(
        'user/diete_lista.html',
        paziente=paziente,
        diete=diete,
        diet_plans=diet_plans,
        now=datetime.now().date(),
    )