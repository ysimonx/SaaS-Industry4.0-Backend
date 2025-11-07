"""
Routes Package - API Blueprints

This package contains all Flask blueprints for the API endpoints.
"""

from app.routes.auth import auth_bp
from app.routes.users import users_bp
from app.routes.tenants import tenants_bp
from app.routes.documents import documents_bp
from app.routes.files import files_bp
from app.routes.kafka_demo import kafka_demo_bp
from app.routes.sso_config import bp as sso_config_bp
from app.routes.sso_auth import bp as sso_auth_bp

__all__ = [
    'auth_bp',
    'users_bp',
    'tenants_bp',
    'documents_bp',
    'files_bp',
    'kafka_demo_bp',
    'sso_config_bp',
    'sso_auth_bp',
]
