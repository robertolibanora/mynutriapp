from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.models.models import (
    Patient,
    Dieta,
    DietPlan,
    Allenamento,
    Progresso,
    Appuntamento,
)
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/user/dashboard')
def user_dashboard():
    if session.get('role') != 'user':
        flash("Effettua il login", "warning")
        return redirect(url_for('auth.login'))

    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))

    paziente = Patient.query.get_or_404(user_id)

    ultima_dieta = Dieta.query.filter_by(patient_id=user_id).order_by(Dieta.created_at.desc()).first()

    ultimo_diet_plan = (
        DietPlan.query.filter_by(patient_id=user_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .first()
    )

    ultimo_allenamento = Allenamento.query.filter_by(patient_id=user_id).order_by(Allenamento.created_at.desc()).first()

    ultimo_progresso = Progresso.query.filter_by(patient_id=user_id).order_by(Progresso.data_check.desc()).first()

    oggi = datetime.now()
    prossimo_appuntamento = Appuntamento.query.filter(
        Appuntamento.patient_id == user_id,
        Appuntamento.data_appuntamento >= oggi
    ).order_by(Appuntamento.data_appuntamento.asc()).first()

    return render_template(
        'user/dashboard.html',
        paziente=paziente,
        ultima_dieta=ultima_dieta,
        ultimo_diet_plan=ultimo_diet_plan,
        ultimo_allenamento=ultimo_allenamento,
        ultimo_progresso=ultimo_progresso,
        prossimo_appuntamento=prossimo_appuntamento
    )
