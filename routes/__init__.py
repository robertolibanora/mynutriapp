from routes.auth import auth_bp
from routes.appuntamenti import appuntamenti_bp
from routes.allenamenti import allenamenti_bp
from routes.diete import diete_bp
from routes.progressi import progressi_bp
from routes.vendite import vendite_bp
from routes.patients import patients_bp
from routes.dashboard import dashboard_bp
from routes.documenti import documenti_bp
from routes.slot import slot_bp
from routes.listino import listino_bp
from routes.agenda import agenda_bp
from routes.whatsapp.broadcast_routes import broadcast_bp

def register_routes(app):
    """Registra tutti i blueprint delle routes"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(appuntamenti_bp)
    app.register_blueprint(allenamenti_bp)
    app.register_blueprint(diete_bp)
    app.register_blueprint(progressi_bp)
    app.register_blueprint(vendite_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documenti_bp)
    app.register_blueprint(slot_bp)
    app.register_blueprint(listino_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(broadcast_bp)
