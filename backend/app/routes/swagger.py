"""
Swagger UI Blueprint for API Documentation

This module provides a Flask blueprint that serves the Swagger UI interface
for the OpenAPI specification file (swagger.yaml).

The Swagger UI allows developers to:
- Browse all API endpoints
- View request/response schemas
- Test API endpoints directly from the browser
- Download the OpenAPI specification

Routes:
    - /api/docs: Swagger UI interface
    - /api/docs/swagger.yaml: Raw OpenAPI specification file
"""

import os
from flask import Blueprint, send_from_directory
from flask_swagger_ui import get_swaggerui_blueprint

# Swagger UI configuration
SWAGGER_URL = '/api/docs'  # URL for Swagger UI
API_URL = '/api/docs/swagger.yaml'  # URL to access the swagger.yaml file

# Create Swagger UI blueprint
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "SaaS Multi-Tenant Backend Platform API",
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 1,
        'docExpansion': 'list',
        'filter': True,
        'displayRequestDuration': True,
        'tryItOutEnabled': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'deepLinking': True,
        'showExtensions': True,
        'showCommonExtensions': True,
    }
)

# Create a separate blueprint for serving the swagger.yaml file
swagger_file_bp = Blueprint('swagger_file', __name__)


@swagger_file_bp.route('/api/docs/swagger.yaml')
def serve_swagger_file():
    """
    Serve the swagger.yaml file.

    The file is located in /app (Docker) or backend folder (development).

    Returns:
        File: The swagger.yaml file with appropriate MIME type
    """
    # In Docker container with volume mount: /app/swagger.yaml (backend/swagger.yaml on host)
    # In development: backend/swagger.yaml
    app_dir = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        '..', '..'
    ))

    return send_from_directory(
        app_dir,
        'swagger.yaml',
        mimetype='text/yaml'
    )
