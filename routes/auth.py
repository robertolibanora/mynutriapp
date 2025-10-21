from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.security import check_password_hash
from models import db, Patient
import os

# ========================
# BLUEPRINT
# ========================
auth_bp = Blueprint('auth', __name__)

# Il limiter verrà applicato tramite decorator

# ========================
# CONFIGURAZIONE ADMIN (DA VARIABILI D'AMBIENTE)
# ========================
ADMIN_PHONE = os.getenv("ADMIN_PHONE")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")  # Password in chiaro da .env (sicuro perché .env è locale)
ADMIN_NAME = os.getenv("ADMIN_NAME", "MyNutriApp")


# ========================
# ROUTE: LOGIN CON RATE LIMITING
# ========================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        telefono = request.form['telefono']
        password = request.form['password']

        # --- Caso 1: Login ADMIN da variabili d'ambiente
        if ADMIN_PHONE and ADMIN_PASSWORD and telefono == ADMIN_PHONE and password == ADMIN_PASSWORD:
            session['role'] = 'admin'
            session['name'] = ADMIN_NAME
            flash("Accesso effettuato come Admin", "success")
            return redirect(url_for('dashboard.admin_dashboard'))

        # --- Caso 2: Login USER da database
        user = Patient.query.filter_by(telefono=telefono).first()
        if user and check_password_hash(user.password_hash, password):
            session['role'] = 'user'
            session['user_id'] = user.id
            session['name'] = f"{user.nome} {user.cognome}"
            return redirect(url_for('dashboard.user_dashboard'))
        flash("Credenziali non valide", "danger")
        return redirect(url_for('auth.login'))

    return render_template('login.html')


# ========================
# ROUTE: LOGOUT
# ========================
@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))