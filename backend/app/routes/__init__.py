"""
Routes Package - API Blueprints

This package contains all Flask blueprints for the API endpoints.
"""

from app.routes.auth import auth_bp
from app.routes.users import users_bp

__all__ = [
    'auth_bp',
    'users_bp',
]
