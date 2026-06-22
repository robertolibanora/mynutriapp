"""
Avvio Flask in locale per sviluppo.

Uso:
    python run.py

Variabili d'ambiente (opzionali, vedere anche .env):
    FLASK_HOST   default per questo script: 127.0.0.1 (override esplicito consentito)
    FLASK_PORT   default: 9091
    FLASK_DEBUG  default: True
"""
import os

from wsgi import app


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "9091"))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug, host=host, port=port, use_reloader=debug)
