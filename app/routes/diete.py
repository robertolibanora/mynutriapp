from flask import Blueprint, render_template, redirect, url_for, flash, session, send_from_directory, abort
from functools import wraps
import os

from app.models.models import Dieta, Patient
from app.config.config import get_full_path

# Prefisso storico /admin/diete mantenuto per non rompere url_for template user
diete_bp = Blueprint('diete', __name__, url_prefix='/admin/diete')


def user_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


@diete_bp.route('/file/<int:dieta_id>')
def serve_file(dieta_id):
    dieta = Dieta.query.get_or_404(dieta_id)
    user_id = session.get('user_id')
    if session.get('role') != 'user' or dieta.patient_id != user_id:
        abort(403)
    file_path = get_full_path(dieta.pdf_path)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))


@diete_bp.route('/user/')
@user_required
def lista_diete_user():
    from datetime import datetime
    from app.services.diet_service import list_for_patient

    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))

    paziente = Patient.query.get_or_404(user_id)
    listed = list_for_patient(user_id)
    return render_template(
        'user/diete_lista.html',
        paziente=paziente,
        diete=listed["pdf_diete"],
        diet_plans=listed["plans"],
        now=datetime.now().date(),
    )
