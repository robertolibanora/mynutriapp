"""
NutriApp - Applicazione per la gestione nutrizionale
"""

from flask import Flask
from app.config.config import Config
from app.models.models import db
from app.routes import register_blueprints
import os


def create_app():
    """Factory per creare l'applicazione Flask"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inizializza database
    db.init_app(app)
    
    # Registra blueprint
    register_blueprints(app)

    @app.context_processor
    def inject_static_version():
        """Cache-busting per file statici (evita CSS/JS obsoleti in produzione)."""
        static_root = os.path.join(app.root_path, "static")
        theme_css = os.path.join(static_root, "css", "admin-theme.css")
        try:
            version = str(int(os.path.getmtime(theme_css)))
        except OSError:
            version = "1"
        return {"static_version": version}
    
    return app
