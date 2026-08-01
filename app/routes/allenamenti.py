from flask import Blueprint, render_template, redirect, url_for, flash, session, send_from_directory, abort
from functools import wraps
import os

from app.models.models import Allenamento, Patient
from app.config.config import get_full_path

# Prefisso storico /admin/allenamenti mantenuto per url_for template user
allenamenti_bp = Blueprint('allenamenti', __name__, url_prefix='/admin/allenamenti')


def user_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


@allenamenti_bp.route('/file/<int:allenamento_id>')
def serve_file(allenamento_id):
    allenamento = Allenamento.query.get_or_404(allenamento_id)
    user_id = session.get('user_id')
    if session.get('role') != 'user' or allenamento.patient_id != user_id:
        abort(403)
    file_path = get_full_path(allenamento.pdf_path)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))


@allenamenti_bp.route('/user/')
@user_required
def lista_allenamenti_user():
    from datetime import datetime
    from app.services.workout_service import list_for_patient

    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))

    paziente = Patient.query.get_or_404(user_id)
    allenamenti = list_for_patient(user_id)

    return render_template(
        'user/allenamenti_lista.html',
        paziente=paziente,
        allenamenti=allenamenti,
        now=datetime.now().date(),
    )
