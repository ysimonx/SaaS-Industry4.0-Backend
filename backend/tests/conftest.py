"""
Test Configuration and Fixtures

This module provides pytest fixtures and configuration for the test suite.
Fixtures are reusable test resources that can be injected into test functions.

Key fixtures:
- app: Flask application instance with test configuration
- client: Flask test client for making HTTP requests
- db: Database instance for test isolation
- test_user: Sample user for testing
- test_tenant: Sample tenant for testing
- auth_headers: Authentication headers with JWT token
"""

import pytest
import os
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db as _db
from app.models import User, Tenant, UserTenantAssociation
from flask_jwt_extended import create_access_token


@pytest.fixture(scope='session')
def app():
    """
    Create Flask application for testing.

    Scope: session - created once per test session

    Returns:
        Flask application configured for testing
    """
    # Set test environment
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['TESTING'] = 'True'
    os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/saas_platform_test'

    # Create app with test config
    app = create_app('testing')

    # Establish application context
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def db(app):
    """
    Create database for testing.

    Scope: session - created once per test session

    Creates all tables at session start and drops them at session end.

    Returns:
        SQLAlchemy database instance
    """
    # Create all tables
    _db.create_all()

    yield _db

    # Drop all tables after tests
    _db.session.close()
    _db.drop_all()


@pytest.fixture(scope='function')
def session(db):
    """
    Create a new database session for a test.

    Scope: function - created for each test function

    Provides transaction rollback for test isolation.
    Each test gets a clean database state.

    Returns:
        SQLAlchemy session
    """
    # Start a new transaction
    connection = db.engine.connect()
    transaction = connection.begin()

    # Bind the session to the connection
    session = db.create_scoped_session(
        options={'bind': connection, 'binds': {}}
    )
    db.session = session

    yield session

    # Rollback transaction to clean up
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope='function')
def client(app, session):
    """
    Create Flask test client.

    Scope: function - created for each test function

    Returns:
        Flask test client for making HTTP requests
    """
    return app.test_client()


@pytest.fixture(scope='function')
def test_user(session):
    """
    Create a test user.

    Returns:
        User instance with test data
    """
    user = User(
        first_name='Test',
        last_name='User',
        email='test@example.com',
        is_active=True
    )
    user.set_password('TestPass123')

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


@pytest.fixture(scope='function')
def test_admin_user(session):
    """
    Create a test admin user.

    Returns:
        User instance with admin privileges
    """
    user = User(
        first_name='Admin',
        last_name='User',
        email='admin@example.com',
        is_active=True
    )
    user.set_password('AdminPass123')

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


@pytest.fixture(scope='function')
def test_tenant(session, test_admin_user):
    """
    Create a test tenant with admin user.

    Returns:
        Tuple of (Tenant, UserTenantAssociation)
    """
    tenant = Tenant(name='Test Company')

    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    # Add admin user to tenant
    association = UserTenantAssociation(
        user_id=test_admin_user.id,
        tenant_id=tenant.id,
        role='admin'
    )

    session.add(association)
    session.commit()
    session.refresh(association)

    return tenant, association


@pytest.fixture(scope='function')
def auth_token(app, test_user):
    """
    Generate JWT access token for test user.

    Returns:
        JWT access token string
    """
    with app.app_context():
        token = create_access_token(
            identity=str(test_user.id),
            expires_delta=timedelta(minutes=15)
        )
    return token


@pytest.fixture(scope='function')
def auth_headers(auth_token):
    """
    Generate authentication headers with JWT token.

    Returns:
        Dict with Authorization header
    """
    return {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }


@pytest.fixture(scope='function')
def admin_token(app, test_admin_user):
    """
    Generate JWT access token for admin user.

    Returns:
        JWT access token string
    """
    with app.app_context():
        token = create_access_token(
            identity=str(test_admin_user.id),
            expires_delta=timedelta(minutes=15)
        )
    return token


@pytest.fixture(scope='function')
def admin_headers(admin_token):
    """
    Generate authentication headers for admin user.

    Returns:
        Dict with Authorization header
    """
    return {
        'Authorization': f'Bearer {admin_token}',
        'Content-Type': 'application/json'
    }


# Mock fixtures for external dependencies

@pytest.fixture
def mock_s3_client(mocker):
    """
    Mock S3/MinIO client for testing.

    Returns:
        Mock S3 client object
    """
    mock_client = mocker.Mock()
    mock_client.upload_fileobj.return_value = None
    mock_client.delete_object.return_value = None
    mock_client.generate_presigned_url.return_value = 'https://s3.example.com/presigned-url'

    return mock_client


@pytest.fixture
def mock_kafka_producer(mocker):
    """
    Mock Kafka producer for testing.

    Returns:
        Mock Kafka producer object
    """
    mock_producer = mocker.Mock()
    mock_producer.send.return_value.get.return_value = None

    return mock_producer


@pytest.fixture
def mock_kafka_consumer(mocker):
    """
    Mock Kafka consumer for testing.

    Returns:
        Mock Kafka consumer object
    """
    mock_consumer = mocker.Mock()
    mock_consumer.poll.return_value = {}
    mock_consumer.subscribe.return_value = None

    return mock_consumer


# Helper functions for tests

def create_test_user_dict(
    first_name='John',
    last_name='Doe',
    email='john.doe@example.com',
    password='SecurePass123'
):
    """
    Create user data dictionary for testing.

    Args:
        first_name: User's first name
        last_name: User's last name
        email: User's email
        password: User's password

    Returns:
        Dict with user data
    """
    return {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'password': password
    }


def create_test_tenant_dict(name='Test Corporation'):
    """
    Create tenant data dictionary for testing.

    Args:
        name: Tenant name

    Returns:
        Dict with tenant data
    """
    return {
        'name': name
    }


def assert_success_response(response, status_code=200):
    """
    Assert that API response is successful.

    Args:
        response: Flask response object
        status_code: Expected HTTP status code
    """
    assert response.status_code == status_code
    data = response.get_json()
    assert data is not None
    assert 'success' in data or 'message' in data


def assert_error_response(response, status_code, error_code=None):
    """
    Assert that API response is an error.

    Args:
        response: Flask response object
        status_code: Expected HTTP status code
        error_code: Expected error code (optional)
    """
    assert response.status_code == status_code
    data = response.get_json()
    assert data is not None

    if error_code:
        assert 'error' in data
        assert data['error'] == error_code
