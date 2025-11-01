"""
Routes Package - API Blueprints

This package contains all Flask blueprints for the API endpoints.
"""

from app.routes.auth import auth_bp
from app.routes.users import users_bp
from app.routes.tenants import tenants_bp
from app.routes.documents import documents_bp
from app.routes.files import files_bp

__all__ = [
    'auth_bp',
    'users_bp',
    'tenants_bp',
    'documents_bp',
    'files_bp',
]
