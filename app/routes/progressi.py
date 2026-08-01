from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps

from app.models.models import db, Progresso

progressi_bp = Blueprint('progressi', __name__, url_prefix='/progressi')


def user_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login come paziente", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


@progressi_bp.route('/user')
@user_required
def lista_progressi_user():
    from app.services.progress_service import list_for_patient

    user_id = session.get('user_id')
    progressi = list_for_patient(user_id)
    return render_template('user/progressi_lista.html', progressi=progressi)


@progressi_bp.route('/user/dettaglio/<int:progresso_id>')
@user_required
def dettaglio_check_user(progresso_id):
    user_id = session.get('user_id')
    progresso = Progresso.query.get_or_404(progresso_id)

    if progresso.patient_id != user_id:
        flash("Non hai accesso a questo check", "danger")
        return redirect(url_for('progressi.lista_progressi_user'))

    paziente = progresso.patient
    misure_antropometriche = None
    composizione_corporea = None

    if progresso.tipo_check == 'nutrizionista':
        misure_antropometriche = progresso.misure_antropometriche_rel[0] if progresso.misure_antropometriche_rel else None
        composizione_corporea = progresso.composizione_corporea_rel[0] if progresso.composizione_corporea_rel else None

    return render_template(
        'user/dettaglio_check.html',
        progresso=progresso,
        paziente=paziente,
        misure_antropometriche=misure_antropometriche,
        composizione_corporea=composizione_corporea,
    )


@progressi_bp.route('/user/nuovo', methods=['GET', 'POST'])
@user_required
def nuovo_progresso_user():
    user_id = session.get('user_id')

    if request.method == 'POST':
        from app.services.progress_service import (
            ProgressValidationError,
            create_for_patient,
        )

        try:
            create_for_patient(
                user_id,
                peso_settimanale=request.form.get('peso_settimanale'),
                frequenza_allenamenti=request.form.get('frequenza_allenamenti'),
                aderenza=request.form.get('aderenza'),
            )
            flash("Check inviato ✅", "success")
            return redirect(url_for('progressi.lista_progressi_user'))
        except ProgressValidationError as e:
            flash(str(e), "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'invio: {e}", "danger")

    return render_template('user/progresso_nuovo.html')
