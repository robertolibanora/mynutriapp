"""
NutriApp - Applicazione per la gestione nutrizionale
"""

from flask import Flask
from app.config.config import Config
from app.models.models import db
from app.routes import register_blueprints

def create_app():
    """Factory per creare l'applicazione Flask"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inizializza database
    db.init_app(app)
    
    # Registra blueprint
    register_blueprints(app)
    
    return app
