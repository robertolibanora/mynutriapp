from flask import Flask, redirect, url_for, session, render_template
from app.models.models import db
from app.config.config import Config, get_dynamic_limits, get_login_limit, get_rate_limit_config
from dotenv import load_dotenv
from app.config.config import ensure_upload_dirs
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import pytz
from datetime import datetime

# ===========================================
# ⚙️ CONFIGURAZIONE BASE FLASK + DATABASE
# ===========================================
load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# Configura timezone per l'applicazione
app.config['TIMEZONE'] = pytz.timezone('Europe/Rome')

# Inizializza SQLAlchemy
db.init_app(app)

# 🛡️ Inizializza CSRF Protection
csrf = CSRFProtect(app)

# 🚦 Inizializza Rate Limiter con configurazioni dinamiche
rate_config = get_rate_limit_config()
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=get_dynamic_limits(),
    storage_uri=rate_config['storage_url'],
    enabled=rate_config['enabled']
)

# Inizializza directory di upload
ensure_upload_dirs()

# ===========================================
# 🛡️ SECURITY HEADERS (zero overhead RAM)
# ===========================================
@app.after_request
def set_security_headers(response):
    """Aggiunge security headers a tutte le risposte."""
    # HSTS - Force HTTPS (se configurato)
    if app.config.get('SESSION_COOKIE_SECURE'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # X-Content-Type-Options - Previene MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # X-Frame-Options - Previene clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # X-XSS-Protection - Browser XSS filter
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content-Security-Policy - Base (può essere esteso)
    # Nota: CSP può rompere app se troppo restrittivo, quindi base
    csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:;"
    response.headers['Content-Security-Policy'] = csp
    
    # Referrer-Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Permissions-Policy (ex Feature-Policy)
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    return response

# ===========================================
# 🔀 REGISTRAZIONE ROUTES (via funzione centralizzata)
# ===========================================
# La funzione register_blueprints(app) verrà definita in /app/routes/__init__.py
from app.routes import register_blueprints
register_blueprints(app)

# Rende disponibile csrf_token() in tutte le template
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

# Rende disponibile timezone-aware datetime in tutte le template
@app.template_filter('localize')
def localize_datetime(dt):
    """Converte un datetime UTC al timezone locale (Europe/Rome)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume UTC se non specificato
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(pytz.timezone('Europe/Rome'))

@app.context_processor
def inject_timezone():
    """Inietta funzioni timezone nelle template"""
    def get_local_time():
        """Ritorna l'ora locale corrente"""
        return datetime.now(pytz.timezone('Europe/Rome'))
    return dict(get_local_time=get_local_time, timezone=pytz.timezone('Europe/Rome'))

# 🚦 Applica rate limiting specifico al login con configurazione dinamica
# Decora la view function del login dopo la registrazione delle routes
for rule in app.url_map.iter_rules():
    if rule.endpoint == 'auth.login':
        view_func = app.view_functions[rule.endpoint]
        # Applica limit solo per metodo POST con configurazione dinamica
        app.view_functions[rule.endpoint] = limiter.limit(
            get_login_limit()
        )(view_func)


# ===========================================
# 🔧 ROUTE DEBUG RATE LIMITING
# ===========================================
@app.route('/debug/rate-limit')
def debug_rate_limit():
    """Route per debug delle configurazioni rate limiting"""
    if session.get('role') != 'admin':
        return "Accesso negato", 403
    
    config = get_rate_limit_config()
    return f"""
    <h1>🔍 Rate Limiting Debug</h1>
    <h2>Configurazioni attuali:</h2>
    <ul>
        <li><strong>Enabled:</strong> {config['enabled']}</li>
        <li><strong>Storage URL:</strong> {config['storage_url']}</li>
        <li><strong>Default per day:</strong> {config['default_per_day']}</li>
        <li><strong>Default per hour:</strong> {config['default_per_hour']}</li>
        <li><strong>Login limit:</strong> {config['login_limit']}</li>
        <li><strong>Create limit:</strong> {config['create_limit']}</li>
        <li><strong>Upload limit:</strong> {config['upload_limit']}</li>
    </ul>
    <h2>Limiti dinamici:</h2>
    <ul>
        <li><strong>Dynamic limits:</strong> {get_dynamic_limits()}</li>
        <li><strong>Login limit:</strong> {get_login_limit()}</li>
    </ul>
    <p><a href="/admin/dashboard">← Torna alla dashboard</a></p>
    """

# ===========================================
# 🏥 HEALTH CHECK ENDPOINT
# ===========================================
@app.route('/health')
def health_check():
    """Endpoint per healthcheck Docker/Kubernetes"""
    try:
        # Verifica connessione database
        db.session.execute(db.text('SELECT 1'))
        return "healthy", 200
    except Exception as e:
        return f"unhealthy: {str(e)}", 503

# ===========================================
# 👤 ROUTE PRESENTAZIONE ROBERTO
# ===========================================
@app.route('/presentazione')
def presentazione_roberto():
    """Pagina di presentazione di Roberto Libanora"""
    return render_template('public/presentazione_roberto.html')

# ===========================================
# 🏠 ROUTE PRINCIPALE (redirect intelligente)
# ===========================================
@app.route('/')
def home():
    """
    Redireziona automaticamente l'utente alla dashboard corretta
    in base al ruolo salvato in sessione.
    """
    if 'role' in session:
        if session['role'] == 'admin':
            return redirect(url_for('dashboard.admin_dashboard'))
        elif session['role'] == 'user':
            return redirect(url_for('dashboard.user_dashboard'))
    return redirect(url_for('auth.login'))


# ===========================================
# 🚦 ERROR HANDLER RATE LIMIT
# ===========================================
@app.errorhandler(429)
def ratelimit_handler(e):
    """Handler per errore 429 - Too Many Requests"""
    return render_template('errors/429.html', description=e.description), 429


# ===========================================
# 🗄️ COMANDO CLI: init-db
# Crea tutte le tabelle del database (backup se init.sql non funziona)
# ===========================================
@app.cli.command('init-db')
def init_db_command():
    """Crea tutte le tabelle del database."""
    try:
        # Importa tutti i modelli per assicurarsi che siano registrati
        from app.models.models import (
            Patient, Dieta, Allenamento, Progresso, 
            MisureAntropometriche, ComposizioneCorporea,
            Documento, Appuntamento, Listino, Vendita, SlotDisponibilita
        )
        
        # Crea tutte le tabelle
        db.create_all()
        print("✅ Database inizializzato con successo!")
        print("📋 Tabelle create:")
        for table in db.metadata.tables.keys():
            print(f"   - {table}")
    except Exception as e:
        print(f"❌ Errore durante l'inizializzazione del database: {e}")
        raise


# ===========================================
# 🚀 AVVIO DELL'APPLICAZIONE
# ===========================================
if __name__ == "__main__":
    # Configurazioni Flask da .env
    flask_host = os.getenv("FLASK_HOST", "0.0.0.0")
    flask_port = int(os.getenv("FLASK_PORT", "9091"))
    flask_debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    
    app.run(debug=flask_debug, host=flask_host, port=flask_port)