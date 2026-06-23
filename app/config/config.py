import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Carica variabili da .env
load_dotenv()


def _get_required_env(key: str, description: str = None) -> str:
    """Ottiene una variabile d'ambiente obbligatoria. Fallisce se mancante."""
    value = os.getenv(key)
    if not value:
        msg = f"❌ {key} deve essere definita in .env"
        if description:
            msg += f" ({description})"
        raise ValueError(msg)
    return value


def _get_bool_env(key: str, default: bool = False) -> bool:
    """Ottiene una variabile d'ambiente booleana."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def test_redis_connection(redis_url: str) -> bool:
    """Testa la connessione a Redis. Ritorna True se connesso, False altrimenti."""
    try:
        import redis
        if redis_url.startswith("redis://"):
            url_without_protocol = redis_url.replace("redis://", "")
            url_parts = url_without_protocol.split("/")
            
            auth_and_host = url_parts[0]
            if "@" in auth_and_host:
                password_part, host_port = auth_and_host.split("@", 1)
                password = password_part.lstrip(":") if password_part.startswith(":") else None
            else:
                password = None
                host_port = auth_and_host
            
            host = host_port.split(":")[0]
            port = int(host_port.split(":")[1]) if ":" in host_port else 6379
            db = int(url_parts[1]) if len(url_parts) > 1 else 0
            
            r = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_connect_timeout=1
            )
            r.ping()
            return True
    except Exception:
        return False
    return False


def get_rate_limit_storage() -> str:
    """Ritorna lo storage URL per rate limiting. Fallback a memory:// se Redis non disponibile."""
    storage_url = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    
    if storage_url.startswith("redis://"):
        if test_redis_connection(storage_url):
            return storage_url
        else:
            return "memory://"
    
    return storage_url


class Config:
    # ========================================
    # 🗄️ DATABASE (costruito da variabili separate)
    # ========================================
    DB_HOST = _get_required_env("DB_HOST", "host MySQL")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = _get_required_env("DB_NAME", "nome database")
    DB_USER = _get_required_env("DB_USER", "utente MySQL")
    DB_PASSWORD = _get_required_env("DB_PASSWORD", "password MySQL")
    
    # Costruisce SQLALCHEMY_DATABASE_URI manualmente
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = _get_bool_env("DB_TRACK_MODIFICATIONS", False)
    
    # ========================================
    # 🔐 SECRET KEY (obbligatoria)
    # ========================================
    SECRET_KEY = _get_required_env("SECRET_KEY", "chiave segreta Flask")
    
    # ========================================
    # 🔐 CRITTOGRAFIA DATI SANITARI (obbligatoria)
    # ========================================
    ENCRYPTION_KEY = _get_required_env("ENCRYPTION_KEY", "chiave Fernet per crittografia dati sanitari")
    
    # ========================================
    # 🍪 SESSION CONFIGURATION (dati sanitari)
    # ========================================
    # Default: Secure solo con FLASK_ENV=production. Su http://localhost
    # SESSION_COOKIE_SECURE=True impedisce al browser di usare il cookie → CSRF/sessione KO.
    _SESSION_COOKIE_SECURE_DEFAULT = os.getenv("FLASK_ENV", "").lower() == "production"
    SESSION_COOKIE_SECURE = _get_bool_env("SESSION_COOKIE_SECURE", _SESSION_COOKIE_SECURE_DEFAULT)
    SESSION_COOKIE_HTTPONLY = _get_bool_env("SESSION_COOKIE_HTTPONLY", True)
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME", "7200"))
    SESSION_REFRESH_EACH_REQUEST = _get_bool_env("SESSION_REFRESH_EACH_REQUEST", True)
    SESSION_PROTECTION = os.getenv("SESSION_PROTECTION", "strong")
    
    # ========================================
    # 🛡️ CSRF PROTECTION
    # ========================================
    WTF_CSRF_ENABLED = _get_bool_env("WTF_CSRF_ENABLED", True)
    WTF_CSRF_TIME_LIMIT = int(os.getenv("WTF_CSRF_TIME_LIMIT", "3600"))
    
    # ========================================
    # 🚦 RATE LIMITING (Redis con fallback)
    # ========================================
    RATELIMIT_ENABLED = _get_bool_env("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URL = get_rate_limit_storage()
    RATELIMIT_DEFAULT_PER_DAY = os.getenv("RATELIMIT_DEFAULT_PER_DAY", "5000")
    RATELIMIT_DEFAULT_PER_HOUR = os.getenv("RATELIMIT_DEFAULT_PER_HOUR", "200")
    RATELIMIT_LOGIN_LIMIT = os.getenv("RATELIMIT_LOGIN_LIMIT", "20 per 15 minutes")
    RATELIMIT_CREATE_LIMIT = os.getenv("RATELIMIT_CREATE_LIMIT", "100 per hour")
    RATELIMIT_UPLOAD_LIMIT = os.getenv("RATELIMIT_UPLOAD_LIMIT", "50 per hour")
    
    # ========================================
    # 🔴 REDIS CONFIGURATION
    # ========================================
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    
    # ========================================
    # 📁 UPLOAD CONFIGURATION
    # ========================================
    BASE_DIR = Path(__file__).resolve().parents[2]
    UPLOAD_ROOT = os.environ.get('UPLOAD_ROOT', str(BASE_DIR / 'static' / 'uploads'))
    
    UPLOAD_FOLDERS = {
        'documenti': os.path.join(UPLOAD_ROOT, 'documenti'),
        'diete': os.path.join(UPLOAD_ROOT, 'diete'),
        'allenamenti': os.path.join(UPLOAD_ROOT, 'allenamenti')
    }
    
    ALLOWED_EXTENSIONS = {
        'documenti': {'pdf', 'jpg', 'jpeg', 'png'},
        'diete': {'pdf'},
        'allenamenti': {'pdf'}
    }
    
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10)) * 1024 * 1024
    
    # ========================================
    # 🧾 AUDIT LOG
    # ========================================
    AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "730"))
    
    # ========================================
    # 📱 WHATSAPP - Evolution API (opzionale)
    # ========================================
    WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "False").lower() in ("true", "1", "yes")
    WHATSAPP_FROM_NAME = os.getenv("WHATSAPP_FROM_NAME", "MyNutriApp")
    EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
    EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
    EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")


# ========================================
# 📁 UPLOAD HELPER FUNCTIONS
# ========================================

def get_upload_folder(file_type: str) -> str:
    """Restituisce la directory di upload per un tipo di file"""
    return Config.UPLOAD_FOLDERS.get(file_type, Config.UPLOAD_FOLDERS['documenti'])


def get_allowed_extensions(file_type: str) -> set:
    """Restituisce le estensioni permesse per un tipo di file"""
    return Config.ALLOWED_EXTENSIONS.get(file_type, Config.ALLOWED_EXTENSIONS['documenti'])


def ensure_upload_dirs():
    """Crea tutte le directory di upload se non esistono"""
    for folder_path in Config.UPLOAD_FOLDERS.values():
        os.makedirs(folder_path, exist_ok=True)


def get_relative_path(full_path: str) -> str:
    """Converte un percorso assoluto in relativo per il database"""
    if full_path.startswith(Config.UPLOAD_ROOT):
        return os.path.relpath(full_path, Config.BASE_DIR)
    return full_path


def get_full_path(relative_path: str) -> str:
    """Converte un percorso relativo in assoluto"""
    if not os.path.isabs(relative_path):
        abs_path = os.path.join(Config.BASE_DIR, relative_path)
        if os.path.exists(abs_path):
            return abs_path
    else:
        if os.path.exists(relative_path):
            return relative_path

    try:
        legacy_prefix = os.path.join('app', 'config', 'static', 'uploads')
        if legacy_prefix in relative_path:
            after = relative_path.split(legacy_prefix, 1)[-1].lstrip(os.sep)
            candidate = os.path.join(str(Config.BASE_DIR), 'static', 'uploads', after)
            if os.path.exists(candidate):
                return candidate

        uploads_marker = os.path.join('static', 'uploads')
        if uploads_marker in relative_path:
            after = relative_path.split(uploads_marker, 1)[-1].lstrip(os.sep)
            candidate = os.path.join(str(Config.BASE_DIR), 'static', 'uploads', after)
            if os.path.exists(candidate):
                return candidate

        basename = os.path.basename(relative_path)
        for folder in Config.UPLOAD_FOLDERS.values():
            candidate = os.path.join(folder, basename)
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass

    return os.path.join(Config.BASE_DIR, relative_path) if not os.path.isabs(relative_path) else relative_path


# ========================================
# 🚦 RATE LIMITING DYNAMIC FUNCTIONS
# ========================================

def get_rate_limit_config() -> dict:
    """Ritorna la configurazione rate limiting aggiornata da .env"""
    return {
        'enabled': _get_bool_env("RATELIMIT_ENABLED", True),
        'storage_url': get_rate_limit_storage(),
        'default_per_day': os.getenv("RATELIMIT_DEFAULT_PER_DAY", "5000"),
        'default_per_hour': os.getenv("RATELIMIT_DEFAULT_PER_HOUR", "200"),
        'login_limit': os.getenv("RATELIMIT_LOGIN_LIMIT", "20 per 15 minutes"),
        'create_limit': os.getenv("RATELIMIT_CREATE_LIMIT", "100 per hour"),
        'upload_limit': os.getenv("RATELIMIT_UPLOAD_LIMIT", "50 per hour")
    }


def get_dynamic_limits() -> list:
    """Ritorna i limiti dinamici per il limiter"""
    config = get_rate_limit_config()
    return [
        f"{config['default_per_day']} per day",
        f"{config['default_per_hour']} per hour"
    ]


def get_login_limit() -> str:
    """Ritorna il limite specifico per il login"""
    config = get_rate_limit_config()
    return config['login_limit']
