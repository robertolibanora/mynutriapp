"""
Registrazione blueprint — staging multi-tenant.
Paziente + API mobile + super admin (creazione utenti) + dashboard nutrizionista.
"""

def register_blueprints(app):
    """Registra i blueprint dell'applicazione."""

    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .patients import patients_bp
    from .appuntamenti import appuntamenti_bp
    from .diete import diete_bp
    from .allenamenti import allenamenti_bp
    from .progressi import progressi_bp
    from .documenti import documenti_bp
    from .diete_plans import diete_plans_bp
    from .prenota_public import prenota_public_bp
    from .super_admin import super_admin_bp
    from .nutri_dashboard import nutri_dashboard_bp
    from .billing import billing_bp
    from .landing import landing_bp
    from app.api.v1 import api_v1_bp

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(appuntamenti_bp)
    app.register_blueprint(diete_bp)
    app.register_blueprint(allenamenti_bp)
    app.register_blueprint(progressi_bp)
    app.register_blueprint(documenti_bp)
    app.register_blueprint(diete_plans_bp)
    app.register_blueprint(prenota_public_bp)
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(nutri_dashboard_bp)
    app.register_blueprint(billing_bp)
