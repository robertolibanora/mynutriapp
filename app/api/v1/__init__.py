"""Blueprint API v1 — url_prefix=/api/v1."""

from flask import Blueprint

from app.api.v1.appointments_routes import register_appointments_routes
from app.api.v1.auth_routes import register_auth_routes
from app.api.v1.diets_routes import register_diets_routes
from app.api.v1.documents_routes import register_documents_routes
from app.api.v1.me_routes import register_me_routes
from app.api.v1.progress_routes import register_progress_routes
from app.api.v1.subscription_routes import register_subscription_routes
from app.api.v1.workouts_routes import register_workouts_routes

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
register_auth_routes(api_v1_bp)
register_me_routes(api_v1_bp)
register_appointments_routes(api_v1_bp)
register_diets_routes(api_v1_bp)
register_progress_routes(api_v1_bp)
register_workouts_routes(api_v1_bp)
register_documents_routes(api_v1_bp)
register_subscription_routes(api_v1_bp)
