from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from functools import wraps

from app.models.models import db, Appuntamento
from app.services.agenda_service import AgendaService

appuntamenti_bp = Blueprint('appuntamenti', __name__, url_prefix='/appuntamenti')


def user_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login come paziente", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


@appuntamenti_bp.route('/user')
@user_required
def lista_user():
    from app.services.appointment_service import list_for_patient

    user_id = session.get('user_id')
    appuntamenti = list_for_patient(user_id)
    return render_template('user/appuntamenti_lista.html', appuntamenti=appuntamenti, now=datetime.now())


@appuntamenti_bp.route('/user/prenota', methods=['GET', 'POST'])
@user_required
def prenota_user():
    user_id = session.get('user_id')

    if request.method == 'POST':
        try:
            data_appuntamento_str = request.form['data_appuntamento']
            tipo = request.form['tipo']
            note = request.form.get('note')

            data_appuntamento = datetime.strptime(data_appuntamento_str, '%Y-%m-%d %H:%M:%S')
            if not AgendaService.is_slot_disponibile(data_appuntamento):
                flash("Questo orario non è più disponibile", "warning")
                return redirect(request.url)

            nuovo = Appuntamento(
                patient_id=user_id,
                created_by='user',
                data_appuntamento=data_appuntamento,
                tipo=tipo,
                stato='in_attesa',
                note=note
            )

            db.session.add(nuovo)
            db.session.commit()
            flash("Richiesta di appuntamento inviata", "success")
            return redirect(url_for('appuntamenti.lista_user'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore: {e}", "danger")

    slot_liberi = AgendaService.slot_liberi_per_select()
    return render_template('user/appuntamento_prenota.html', slot_liberi=slot_liberi)
