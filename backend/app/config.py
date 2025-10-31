"""
Configuration module for SaaS Multi-Tenant Backend Platform.

Provides environment-specific configurations for Development, Production, and Testing.
Loads settings from environment variables with sensible defaults.
"""

import os
import secrets
from datetime import timedelta
from typing import Dict, Any


class Config:
    """Base configuration class with common settings."""

    # Flask Core Settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)
    FLASK_APP = os.environ.get('FLASK_APP', 'app')
    FLASK_PORT = int(os.environ.get('FLASK_PORT', 4999))

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:postgres@localhost:5432/saas_platform'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.environ.get('DATABASE_POOL_SIZE', 10)),
        'pool_timeout': int(os.environ.get('DATABASE_POOL_TIMEOUT', 30)),
        'pool_recycle': int(os.environ.get('DATABASE_POOL_RECYCLE', 3600)),
        'max_overflow': int(os.environ.get('DATABASE_MAX_OVERFLOW', 20)),
    }

    # Tenant Database Configuration
    TENANT_DATABASE_URL_TEMPLATE = os.environ.get('TENANT_DATABASE_URL_TEMPLATE') or \
        'postgresql://postgres:postgres@localhost:5432/{database_name}'

    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or secrets.token_urlsafe(32)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 900))  # 15 minutes
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 604800))  # 7 days
    )
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_CLIENT_ID = os.environ.get('KAFKA_CLIENT_ID', 'saas-backend')
    KAFKA_GROUP_ID = os.environ.get('KAFKA_GROUP_ID', 'saas-backend-consumer-group')
    KAFKA_AUTO_OFFSET_RESET = os.environ.get('KAFKA_AUTO_OFFSET_RESET', 'earliest')
    KAFKA_ENABLE_AUTO_COMMIT = os.environ.get('KAFKA_ENABLE_AUTO_COMMIT', 'True').lower() == 'true'

    # Kafka Topics
    KAFKA_TOPICS = {
        'tenant_created': os.environ.get('KAFKA_TOPIC_TENANT_CREATED', 'tenant.created'),
        'tenant_deleted': os.environ.get('KAFKA_TOPIC_TENANT_DELETED', 'tenant.deleted'),
        'document_uploaded': os.environ.get('KAFKA_TOPIC_DOCUMENT_UPLOADED', 'document.uploaded'),
        'document_deleted': os.environ.get('KAFKA_TOPIC_DOCUMENT_DELETED', 'document.deleted'),
        'file_process': os.environ.get('KAFKA_TOPIC_FILE_PROCESS', 'file.process'),
        'audit_log': os.environ.get('KAFKA_TOPIC_AUDIT_LOG', 'audit.log'),
    }

    # S3 / Object Storage Configuration
    S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL', 'https://s3.amazonaws.com')
    S3_REGION = os.environ.get('S3_REGION', 'us-east-1')
    S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'saas-platform-files')
    S3_ACCESS_KEY_ID = os.environ.get('S3_ACCESS_KEY_ID')
    S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRET_ACCESS_KEY')
    S3_USE_SSL = os.environ.get('S3_USE_SSL', 'True').lower() == 'true'
    S3_VERIFY_SSL = os.environ.get('S3_VERIFY_SSL', 'True').lower() == 'true'
    S3_SIGNATURE_VERSION = os.environ.get('S3_SIGNATURE_VERSION', 's3v4')

    # File Upload Settings
    MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', 100))
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes
    ALLOWED_FILE_EXTENSIONS = set(
        os.environ.get('ALLOWED_FILE_EXTENSIONS',
                      'pdf,doc,docx,xls,xlsx,ppt,pptx,txt,jpg,jpeg,png,gif').split(',')
    )

    # CORS Configuration
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(',')
    CORS_ALLOW_CREDENTIALS = os.environ.get('CORS_ALLOW_CREDENTIALS', 'True').lower() == 'true'
    CORS_MAX_AGE = int(os.environ.get('CORS_MAX_AGE', 3600))

    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT',
                                '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10485760))  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))

    # Security Settings
    RATE_LIMIT_ENABLED = os.environ.get('RATE_LIMIT_ENABLED', 'True').lower() == 'true'
    RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '100/hour')
    RATE_LIMIT_LOGIN = os.environ.get('RATE_LIMIT_LOGIN', '5/minute')

    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

    # Application Features
    ENABLE_REGISTRATION = os.environ.get('ENABLE_REGISTRATION', 'True').lower() == 'true'
    ENABLE_FILE_DEDUPLICATION = os.environ.get('ENABLE_FILE_DEDUPLICATION', 'True').lower() == 'true'
    ENABLE_KAFKA_EVENTS = os.environ.get('ENABLE_KAFKA_EVENTS', 'True').lower() == 'true'
    ENABLE_AUDIT_LOGGING = os.environ.get('ENABLE_AUDIT_LOGGING', 'True').lower() == 'true'

    # Pagination
    DEFAULT_PAGE_SIZE = int(os.environ.get('DEFAULT_PAGE_SIZE', 20))
    MAX_PAGE_SIZE = int(os.environ.get('MAX_PAGE_SIZE', 100))

    @staticmethod
    def init_app(app):
        """Initialize application with this configuration."""
        pass


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = os.environ.get('SQLALCHEMY_ECHO', 'False').lower() == 'true'

    # More verbose logging in development
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG')

    # Relaxed security for development
    SESSION_COOKIE_SECURE = False

    @classmethod
    def init_app(cls, app):
        """Initialize development-specific settings."""
        Config.init_app(app)

        # Log startup info
        print('=' * 80)
        print('SaaS Multi-Tenant Backend - DEVELOPMENT MODE')
        print(f'Running on port: {cls.FLASK_PORT}')
        print(f'Database: {cls.SQLALCHEMY_DATABASE_URI}')
        print(f'Kafka: {cls.KAFKA_BOOTSTRAP_SERVERS}')
        print(f'S3 Bucket: {cls.S3_BUCKET_NAME}')
        print('=' * 80)


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    TESTING = False
    SQLALCHEMY_ECHO = False

    # Stricter security in production
    SESSION_COOKIE_SECURE = True

    # Require critical environment variables in production
    @classmethod
    def init_app(cls, app):
        """Initialize production-specific settings with validation."""
        Config.init_app(app)

        # Validate critical configuration
        required_vars = [
            'SECRET_KEY',
            'JWT_SECRET_KEY',
            'DATABASE_URL',
            'S3_ACCESS_KEY_ID',
            'S3_SECRET_ACCESS_KEY',
        ]

        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables for production: {', '.join(missing_vars)}"
            )

        # Warn about insecure configurations
        if not cls.SESSION_COOKIE_SECURE:
            app.logger.warning(
                'SESSION_COOKIE_SECURE is False in production! '
                'This is insecure. Enable HTTPS and set SESSION_COOKIE_SECURE=True'
            )


class TestingConfig(Config):
    """Testing environment configuration."""

    TESTING = True
    DEBUG = True

    # Use in-memory SQLite for faster tests
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///:memory:'

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False

    # Fast password hashing for tests
    BCRYPT_LOG_ROUNDS = 4

    # Disable rate limiting in tests
    RATE_LIMIT_ENABLED = False

    # Disable Kafka events in tests by default
    ENABLE_KAFKA_EVENTS = False

    # Use shorter token expiry for faster tests
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=60)  # 1 minute
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=300)  # 5 minutes

    @staticmethod
    def init_app(app):
        """Initialize testing-specific settings."""
        Config.init_app(app)


# Configuration dictionary for easy access
config: Dict[str, Any] = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(config_name: str = None) -> Config:
    """
    Get configuration class by name.

    Args:
        config_name: Name of configuration ('development', 'production', 'testing')
                    If None, uses FLASK_ENV environment variable or 'development'

    Returns:
        Configuration class
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    return config.get(config_name, DevelopmentConfig)
