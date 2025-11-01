"""
Flask Application Entry Point

This script serves as the main entry point for running the Flask application.
It creates an app instance using the application factory pattern and runs
the development server.

Usage:
    Development: python run.py
    Production: gunicorn -w 4 -b 0.0.0.0:4999 "run:app"
    Flask CLI: flask --app run db migrate
"""

import os
from app import create_app

# Create app instance using factory
# Environment can be set via FLASK_ENV environment variable
config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    # Run development server
    # Port is configured in app.config (default 4999)
    port = app.config.get('FLASK_PORT', 4999)
    debug = app.config.get('DEBUG', True)

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
