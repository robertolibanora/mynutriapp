"""
Registrazione di tutti i blueprint delle route
"""

def register_blueprints(app):
    """Registra tutti i blueprint dell'applicazione"""
    
    # Importa tutti i blueprint
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .patients import patients_bp
    from .appuntamenti import appuntamenti_bp
    from .agenda import agenda_bp
    from .diete import diete_bp
    from .allenamenti import allenamenti_bp
    from .progressi import progressi_bp
    from .documenti import documenti_bp
    from .slot import slot_bp
    from .whatsapp.broadcast_routes import broadcast_bp
    from .admin_nutrition import admin_nutrition_bp
    from .admin_diets import admin_diets_bp
    from .diete_plans import diete_plans_bp
    from .prenota_public import prenota_public_bp
    
    # Registra i blueprint
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(appuntamenti_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(diete_bp)
    app.register_blueprint(allenamenti_bp)
    app.register_blueprint(progressi_bp)
    app.register_blueprint(documenti_bp)
    app.register_blueprint(slot_bp)
    app.register_blueprint(broadcast_bp)
    app.register_blueprint(admin_nutrition_bp)
    app.register_blueprint(admin_diets_bp)
    app.register_blueprint(diete_plans_bp)
    app.register_blueprint(prenota_public_bp)