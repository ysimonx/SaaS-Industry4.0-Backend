#!/usr/bin/env python
"""
Celery Worker Entry Point

This module serves as the entry point for Celery workers, ensuring
proper Flask application context initialization.
"""

import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from app.config import get_config
from app.extensions import db, migrate, jwt, cors, redis_manager
from app.celery_app import create_celery_app

# Create minimal Flask app for Celery workers (no routes needed)
def create_celery_flask_app():
    """Create a minimal Flask app for Celery workers with just extensions."""
    app = Flask(__name__)

    # Load configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(get_config(config_name))

    # Initialize only the extensions Celery tasks need
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    redis_manager.init_app(app)

    return app

# Create Flask app for Celery context
flask_app = create_celery_flask_app()

# Create Celery app with Flask context
celery = create_celery_app(flask_app)

if __name__ == '__main__':
    celery.start()