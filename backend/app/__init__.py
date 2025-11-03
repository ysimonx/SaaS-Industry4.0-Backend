"""
Flask Application Factory for SaaS Multi-Tenant Backend Platform.

This module implements the application factory pattern for creating Flask app instances.
The factory pattern allows for:
- Multiple app instances with different configurations (dev, prod, test)
- Easier testing by creating isolated app instances
- Delayed initialization of extensions
- Better separation of concerns

The create_app() function initializes the Flask application with:
- Configuration loading
- Database and migration setup
- JWT authentication
- CORS configuration
- Blueprint registration for all API routes
- Error handlers
- Logging configuration
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify
from flask.logging import default_handler

from app.config import config, get_config
from app.extensions import db, migrate, jwt, cors


def create_app(config_name=None):
    """
    Application factory function to create and configure Flask app instance.

    This function creates a Flask application instance with the specified configuration.
    It initializes all extensions, registers blueprints, and sets up error handlers.

    Args:
        config_name: Configuration name ('development', 'production', 'testing')
                    If None, uses FLASK_ENV environment variable or defaults to 'development'

    Returns:
        Flask: Configured Flask application instance

    Example:
        # Create development app
        app = create_app('development')

        # Create production app
        app = create_app('production')

        # Create test app
        app = create_app('testing')
    """
    # Create Flask app instance
    app = Flask(__name__)

    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    config_class = config.get(config_name, config['default'])
    app.config.from_object(config_class)

    # Initialize configuration (calls init_app on config class)
    config_class.init_app(app)

    # Initialize Flask extensions
    initialize_extensions(app)

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Configure logging
    configure_logging(app)

    # Register shell context (for flask shell)
    register_shell_context(app)

    # Log startup information
    app.logger.info(f"Flask app created with config: {config_name}")
    app.logger.info(f"Debug mode: {app.config.get('DEBUG')}")
    app.logger.info(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')[:50]}...")

    return app


def initialize_extensions(app):
    """
    Initialize Flask extensions with the app instance.

    Extensions are initialized here after app creation to avoid circular imports.
    This follows the extension initialization pattern recommended by Flask.

    Args:
        app: Flask application instance

    Extensions initialized:
        - SQLAlchemy (db): Database ORM
        - Flask-Migrate (migrate): Database migrations
        - Flask-JWT-Extended (jwt): JWT authentication
        - Flask-CORS (cors): Cross-Origin Resource Sharing
        - TenantDatabaseManager: Multi-tenant database manager
    """
    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize Flask-Migrate for database migrations
    migrate.init_app(app, db)

    # Initialize JWT Manager for authentication
    jwt.init_app(app)

    # Initialize CORS for cross-origin requests
    cors.init_app(
        app,
        origins=app.config.get('CORS_ORIGINS', ['http://localhost:3000']),
        supports_credentials=app.config.get('CORS_ALLOW_CREDENTIALS', True),
        max_age=app.config.get('CORS_MAX_AGE', 3600),
        allow_headers=['Content-Type', 'Authorization'],
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    )

    # Initialize Tenant Database Manager
    from app.utils.database import tenant_db_manager
    tenant_db_manager.init_app(app)

    # Configure JWT callbacks
    configure_jwt(app)

    app.logger.info("Extensions initialized: db, migrate, jwt, cors, tenant_db_manager")


def configure_jwt(app):
    """
    Configure JWT-related callbacks and handlers.

    Sets up callbacks for JWT token handling including:
    - Token expiration handling
    - Invalid token handling
    - Missing token handling
    - Token revocation (if needed)

    Args:
        app: Flask application instance
    """
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Handle expired JWT tokens."""
        return jsonify({
            'error': 'token_expired',
            'message': 'The token has expired. Please log in again.'
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        """Handle invalid JWT tokens."""
        return jsonify({
            'error': 'invalid_token',
            'message': 'Signature verification failed or token is malformed.'
        }), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        """Handle missing JWT tokens."""
        return jsonify({
            'error': 'authorization_required',
            'message': 'Request does not contain a valid access token.'
        }), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        """Handle revoked JWT tokens."""
        return jsonify({
            'error': 'token_revoked',
            'message': 'The token has been revoked.'
        }), 401

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """
        Check if a JWT token has been revoked (is in blacklist).

        This callback is called automatically by Flask-JWT-Extended
        for every request that requires JWT authentication.

        Args:
            jwt_header: JWT header dict
            jwt_payload: JWT payload dict containing 'jti'

        Returns:
            bool: True if token is revoked, False otherwise
        """
        from app.services.auth_service import AuthService
        jti = jwt_payload.get('jti')
        if jti:
            return AuthService.is_token_blacklisted(jti)
        return False


def register_blueprints(app):
    """
    Register Flask blueprints for API routes.

    Blueprints organize the application into modular components.
    Each blueprint handles a specific domain (auth, users, tenants, etc.).

    Args:
        app: Flask application instance

    Blueprints registered:
        - auth: Authentication endpoints (login, register, logout)
        - users: User management endpoints
        - tenants: Tenant management endpoints
        - documents: Document management endpoints
        - files: File management endpoints (if needed)

    Note: Blueprint imports are done inside the function to avoid circular imports.
    """
    # Import blueprints here to avoid circular imports
    # The blueprints will be created in subsequent tasks
    try:
        from app.routes.auth import auth_bp
        app.register_blueprint(auth_bp)
        app.logger.info("Registered blueprint: auth (/api/auth)")
    except ImportError as e:
        app.logger.warning(f"Auth blueprint not found: {e}")

    try:
        from app.routes.users import users_bp
        app.register_blueprint(users_bp)
        app.logger.info("Registered blueprint: users (/api/users)")
    except ImportError as e:
        app.logger.warning(f"Users blueprint not found: {e}")

    try:
        from app.routes.tenants import tenants_bp
        app.register_blueprint(tenants_bp)
        app.logger.info("Registered blueprint: tenants (/api/tenants)")
    except ImportError as e:
        app.logger.warning(f"Tenants blueprint not found: {e}")

    try:
        from app.routes.documents import documents_bp
        app.register_blueprint(documents_bp)
        app.logger.info("Registered blueprint: documents (/api/documents)")
    except ImportError as e:
        app.logger.warning(f"Documents blueprint not found: {e}")

    try:
        from app.routes.files import files_bp
        app.register_blueprint(files_bp)
        app.logger.info("Registered blueprint: files (/api/files)")
    except ImportError as e:
        app.logger.warning(f"Files blueprint not found: {e}")

    try:
        from app.routes.kafka_demo import kafka_demo_bp
        app.register_blueprint(kafka_demo_bp)
        app.logger.info("Registered blueprint: kafka_demo (/api/demo/kafka)")
    except ImportError as e:
        app.logger.warning(f"Kafka demo blueprint not found: {e}")

    # Health check endpoint (no blueprint needed)
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring."""
        return jsonify({
            'status': 'healthy',
            'service': 'SaaS Multi-Tenant Backend',
            'version': '1.0.0'
        }), 200

    @app.route('/')
    def index():
        """Root endpoint with API information."""
        return jsonify({
            'service': 'SaaS Multi-Tenant Backend Platform',
            'version': '1.0.0',
            'status': 'running',
            'endpoints': {
                'health': '/health',
                'auth': '/api/auth',
                'users': '/api/users',
                'tenants': '/api/tenants',
                'documents': '/api/documents',
                'files': '/api/files',
                'kafka_demo': '/api/demo/kafka'
            }
        }), 200


def register_error_handlers(app):
    """
    Register global error handlers for the application.

    Handles common HTTP errors and exceptions with consistent JSON responses.

    Args:
        app: Flask application instance

    Error handlers registered:
        - 400: Bad Request
        - 401: Unauthorized
        - 403: Forbidden
        - 404: Not Found
        - 405: Method Not Allowed
        - 500: Internal Server Error
        - Exception: Catch-all for unhandled exceptions
    """
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors."""
        return jsonify({
            'error': 'bad_request',
            'message': str(error.description) if hasattr(error, 'description') else 'Bad request'
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        """Handle 401 Unauthorized errors."""
        return jsonify({
            'error': 'unauthorized',
            'message': 'Authentication required'
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors."""
        return jsonify({
            'error': 'forbidden',
            'message': 'You do not have permission to access this resource'
        }), 403

    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors."""
        return jsonify({
            'error': 'not_found',
            'message': 'The requested resource was not found'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        return jsonify({
            'error': 'method_not_allowed',
            'message': 'The method is not allowed for this resource'
        }), 405

    @app.errorhandler(500)
    def internal_server_error(error):
        """Handle 500 Internal Server Error."""
        app.logger.error(f"Internal Server Error: {error}")
        return jsonify({
            'error': 'internal_server_error',
            'message': 'An internal server error occurred'
        }), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle all unhandled exceptions."""
        app.logger.error(f"Unhandled exception: {error}", exc_info=True)

        # Return 500 for unhandled exceptions
        return jsonify({
            'error': 'internal_server_error',
            'message': 'An unexpected error occurred'
        }), 500


def configure_logging(app):
    """
    Configure application logging.

    Sets up both console and file logging with rotation.
    Log levels and formats are configured from app.config.

    Args:
        app: Flask application instance

    Configuration:
        - LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        - LOG_FORMAT: Log message format
        - LOG_FILE: Path to log file
        - LOG_MAX_BYTES: Maximum log file size before rotation
        - LOG_BACKUP_COUNT: Number of backup log files to keep
    """
    # Remove default Flask handler
    app.logger.removeHandler(default_handler)

    # Set log level from config
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    app.logger.setLevel(log_level)

    # Create formatters
    formatter = logging.Formatter(
        app.config.get('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    app.logger.addHandler(console_handler)

    # File handler with rotation (only if LOG_FILE is configured)
    log_file = app.config.get('LOG_FILE')
    if log_file:
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=app.config.get('LOG_MAX_BYTES', 10485760),  # 10MB
            backupCount=app.config.get('LOG_BACKUP_COUNT', 5)
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)

    app.logger.info(f"Logging configured: level={log_level}, file={log_file}")


def register_shell_context(app):
    """
    Register shell context for Flask shell.

    Makes common objects available in the Flask shell without imports.
    Useful for debugging and manual database operations.

    Args:
        app: Flask application instance

    Context objects:
        - db: SQLAlchemy database instance
        - User, Tenant, Document, File, UserTenantAssociation: Model classes
    """
    @app.shell_context_processor
    def make_shell_context():
        """Create shell context with commonly used objects."""
        # Import models here to avoid circular imports
        # NOTE: File and Document are NOT imported to prevent them from being
        # registered in main database migrations. They are tenant-database-only models.
        try:
            from app.models.user import User
            from app.models.tenant import Tenant
            from app.models.user_tenant_association import UserTenantAssociation

            return {
                'db': db,
                'User': User,
                'Tenant': Tenant,
                'UserTenantAssociation': UserTenantAssociation
                # 'Document': Document,  # Tenant database only - import separately
                # 'File': File,  # Tenant database only - import separately
            }
        except ImportError as e:
            app.logger.warning(f"Could not import models for shell context: {e}")
            return {'db': db}
