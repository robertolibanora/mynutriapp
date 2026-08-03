"""
Registrazione blueprint — staging multi-tenant.
Paziente + API mobile + admin nutrizionista + super admin.
"""

def register_blueprints(app):
    """Registra i blueprint dell'applicazione."""

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
    from .consultations_audio import consultations_audio_bp
    from .diario_ui import diario_ui_bp
    from .patients_diary_api import patients_diary_api_bp
    from .super_admin import super_admin_bp
    from .billing import billing_bp
    from .landing import landing_bp
    from .mobile_web import mobile_web_bp
    from app.api.v1 import api_v1_bp

    app.register_blueprint(landing_bp)
    app.register_blueprint(mobile_web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_v1_bp)
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
    app.register_blueprint(consultations_audio_bp)
    app.register_blueprint(diario_ui_bp)
    app.register_blueprint(patients_diary_api_bp)
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(billing_bp)
