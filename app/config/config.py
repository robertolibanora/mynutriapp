import os
from pathlib import Path
from dotenv import load_dotenv

# Carica variabili da .env se presente (non forza override delle env già settate fuori)
load_dotenv()

# Database URL di default - ora completamente configurabile via .env


def test_redis_connection(redis_url):
    """
    Testa la connessione a Redis.
    Ritorna True se connesso, False altrimenti.
    """
    try:
        import redis
        # Estrai parametri dall'URL
        if redis_url.startswith("redis://"):
            # Parse dell'URL: redis://[password@]host:port/db
            url_parts = redis_url.replace("redis://", "").split("/")
            host_port = url_parts[0].split("@")[-1]  # Rimuovi eventuale password
            host = host_port.split(":")[0]
            port = int(host_port.split(":")[1]) if ":" in host_port else 6379
            db = int(url_parts[1]) if len(url_parts) > 1 else 0
            
            # Tenta connessione
            r = redis.Redis(host=host, port=port, db=db, socket_connect_timeout=1)
            r.ping()
            return True
    except Exception as e:
        print(f"⚠️  Redis non disponibile ({e}), uso memory:// come fallback")
        return False
    return False


def get_rate_limit_storage():
    """
    Ritorna lo storage URL per rate limiting.
    Prova prima Redis, se non disponibile usa memory://
    """
    storage_url = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    
    # Se è configurato Redis, testa la connessione
    if storage_url.startswith("redis://"):
        if test_redis_connection(storage_url):
            print(f"✅ Redis connesso: {storage_url}")
            return storage_url
        else:
            print("⚠️  Fallback a memory:// per rate limiting")
            return "memory://"
    
    # Altrimenti usa il valore configurato (memory:// o altro)
    return storage_url

class Config:
    # ========================================
    # 🗄️ DATABASE
    # ========================================
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/enrico?charset=utf8mb4")
    SQLALCHEMY_TRACK_MODIFICATIONS = os.getenv("DB_TRACK_MODIFICATIONS", "False").lower() == "true"
    
    # ========================================
    # 🔐 SECRET KEY
    # ========================================
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("❌ SECRET_KEY deve essere definita in .env!")
    
    # ========================================
    # 🍪 SESSION CONFIGURATION
    # ========================================
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME", "86400"))
    
    # 🛡️ CSRF Protection
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "True").lower() == "true"
    WTF_CSRF_TIME_LIMIT = None if os.getenv("WTF_CSRF_TIME_LIMIT") == "None" else (int(os.getenv("WTF_CSRF_TIME_LIMIT", "3600")) if os.getenv("WTF_CSRF_TIME_LIMIT") else None)
    
    # 🚦 Rate Limiting con Redis fallback
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "True").lower() == "true"
    RATELIMIT_STORAGE_URL = get_rate_limit_storage()  # Auto-fallback a memory:// se Redis non disponibile
    RATELIMIT_DEFAULT_PER_DAY = os.getenv("RATELIMIT_DEFAULT_PER_DAY", "200")
    RATELIMIT_DEFAULT_PER_HOUR = os.getenv("RATELIMIT_DEFAULT_PER_HOUR", "50")
    RATELIMIT_LOGIN_LIMIT = os.getenv("RATELIMIT_LOGIN_LIMIT", "5 per 15 minutes")
    RATELIMIT_CREATE_LIMIT = os.getenv("RATELIMIT_CREATE_LIMIT", "20 per hour")
    RATELIMIT_UPLOAD_LIMIT = os.getenv("RATELIMIT_UPLOAD_LIMIT", "10 per hour")
    
    # 🔴 Redis (opzionale)
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    
    # 📱 WhatsApp Business API Configuration (Semplificato)
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    
    # ========================================
    # 📁 UPLOAD CONFIGURATION
    # ========================================
    
    # Directory base per upload (può essere sovrascritta da env vars)
    # Directory base del progetto (root), non la cartella config
    BASE_DIR = Path(__file__).resolve().parents[2]
    UPLOAD_ROOT = os.environ.get('UPLOAD_ROOT', str(BASE_DIR / 'static' / 'uploads'))
    
    # Directory specifiche per tipo di file
    UPLOAD_FOLDERS = {
        'documenti': os.path.join(UPLOAD_ROOT, 'documenti'),
        'diete': os.path.join(UPLOAD_ROOT, 'diete'),
        'allenamenti': os.path.join(UPLOAD_ROOT, 'allenamenti')
    }
    
    # Estensioni permesse per tipo
    ALLOWED_EXTENSIONS = {
        'documenti': {'pdf', 'jpg', 'jpeg', 'png'},
        'diete': {'pdf'},
        'allenamenti': {'pdf'}
    }
    
    # Dimensione massima file (in MB)
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10)) * 1024 * 1024  # 10MB default


# ========================================
# 📁 UPLOAD HELPER FUNCTIONS
# ========================================

def get_upload_folder(file_type):
    """Restituisce la directory di upload per un tipo di file"""
    return Config.UPLOAD_FOLDERS.get(file_type, Config.UPLOAD_FOLDERS['documenti'])

def get_allowed_extensions(file_type):
    """Restituisce le estensioni permesse per un tipo di file"""
    return Config.ALLOWED_EXTENSIONS.get(file_type, Config.ALLOWED_EXTENSIONS['documenti'])

def ensure_upload_dirs():
    """Crea tutte le directory di upload se non esistono"""
    for folder_path in Config.UPLOAD_FOLDERS.values():
        os.makedirs(folder_path, exist_ok=True)

def get_relative_path(full_path):
    """Converte un percorso assoluto in relativo per il database"""
    if full_path.startswith(Config.UPLOAD_ROOT):
        return os.path.relpath(full_path, Config.BASE_DIR)
    return full_path

def get_full_path(relative_path):
    """Converte un percorso relativo in assoluto"""
    # 1) Se è relativo, rende assoluto rispetto alla root progetto
    if not os.path.isabs(relative_path):
        abs_path = os.path.join(Config.BASE_DIR, relative_path)
        if os.path.exists(abs_path):
            return abs_path
    else:
        # 2) Se è assoluto e già esiste, restituiscilo
        if os.path.exists(relative_path):
            return relative_path

    # 3) Compatibilità retroattiva: corregge vecchi percorsi salvati con BASE_DIR errata
    try:
        # Caso: vecchio prefisso 'app/config/static/uploads/...'
        legacy_prefix = os.path.join('app', 'config', 'static', 'uploads')
        if legacy_prefix in relative_path:
            # Prende la parte dopo '.../static/uploads/' e la ricompone sotto la root corretta
            after = relative_path.split(legacy_prefix, 1)[-1].lstrip(os.sep)
            candidate = os.path.join(str(Config.BASE_DIR), 'static', 'uploads', after)
            if os.path.exists(candidate):
                return candidate

        # Caso: percorso contiene 'static/uploads' ma con prefisso non corretto
        uploads_marker = os.path.join('static', 'uploads')
        if uploads_marker in relative_path:
            after = relative_path.split(uploads_marker, 1)[-1].lstrip(os.sep)
            candidate = os.path.join(str(Config.BASE_DIR), 'static', 'uploads', after)
            if os.path.exists(candidate):
                return candidate

        # 4) Ultimo tentativo: cerca per basename nelle cartelle note
        basename = os.path.basename(relative_path)
        for folder in Config.UPLOAD_FOLDERS.values():
            candidate = os.path.join(folder, basename)
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass

    # Fallback: ritorna percorso risolto rispetto alla root, anche se non esiste
    return os.path.join(Config.BASE_DIR, relative_path) if not os.path.isabs(relative_path) else relative_path


# ========================================
# 🚦 RATE LIMITING DYNAMIC FUNCTIONS
# ========================================

def get_rate_limit_config():
    """Ritorna la configurazione rate limiting aggiornata da .env"""
    return {
        'enabled': os.getenv("RATELIMIT_ENABLED", "True").lower() == "true",
        'storage_url': get_rate_limit_storage(),
        'default_per_day': os.getenv("RATELIMIT_DEFAULT_PER_DAY", "200"),
        'default_per_hour': os.getenv("RATELIMIT_DEFAULT_PER_HOUR", "50"),
        'login_limit': os.getenv("RATELIMIT_LOGIN_LIMIT", "5 per 15 minutes"),
        'create_limit': os.getenv("RATELIMIT_CREATE_LIMIT", "20 per hour"),
        'upload_limit': os.getenv("RATELIMIT_UPLOAD_LIMIT", "10 per hour")
    }

def get_dynamic_limits():
    """Ritorna i limiti dinamici per il limiter"""
    config = get_rate_limit_config()
    return [
        f"{config['default_per_day']} per day",
        f"{config['default_per_hour']} per hour"
    ]

def get_login_limit():
    """Ritorna il limite specifico per il login"""
    config = get_rate_limit_config()
    return config['login_limit']