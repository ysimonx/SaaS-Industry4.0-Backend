"""
Authentication Blueprint for SaaS Multi-Tenant Platform.

This module handles all authentication-related endpoints:
- User registration
- User login
- Token refresh
- User logout

Security features:
- Password hashing with bcrypt
- JWT tokens (15min access, 7 day refresh)
- Token blacklist for logout
- Rate limiting protection (future enhancement)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from marshmallow import ValidationError
from datetime import timedelta

from app.extensions import db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation
from app.schemas.user_schema import (
    user_create_schema,
    user_login_schema,
    user_response_schema
)
from app.schemas.tenant_schema import tenant_response_schema
from app.services.auth_service import AuthService


# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user account.

    POST /api/auth/register

    Request Body:
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "password": "SecurePass123"
        }

    Response (201):
        {
            "message": "User registered successfully",
            "user": {
                "id": "uuid",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "is_active": true,
                "created_at": "2024-01-01T00:00:00Z"
            }
        }

    Errors:
        - 400: Validation error (invalid data, weak password)
        - 409: Email already exists
        - 500: Database error

    Security:
        - Password must be at least 8 characters
        - Password must contain at least one letter and one number
        - Email is normalized to lowercase
        - Password is hashed with bcrypt before storage
    """
    try:
        # Validate request data
        data = user_create_schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({
            'error': 'validation_error',
            'message': 'Invalid user data provided',
            'details': err.messages
        }), 400

    # Check if user already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({
            'error': 'email_exists',
            'message': 'A user with this email already exists'
        }), 409

    try:
        # Create new user
        new_user = User(
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email']
        )
        # Set password (this will hash it automatically via the model's setter)
        new_user.set_password(data['password'])

        # Save to database
        db.session.add(new_user)
        db.session.commit()

        # Serialize user for response
        user_data = user_response_schema.dump(new_user)

        return jsonify({
            'message': 'User registered successfully',
            'user': user_data
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'registration_failed',
            'message': 'Failed to register user. Please try again.'
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user and generate JWT tokens.

    POST /api/auth/login

    Request Body:
        {
            "email": "john.doe@example.com",
            "password": "SecurePass123"
        }

    Response (200):
        {
            "message": "Login successful",
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "user": {
                "id": "uuid",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "is_active": true
            },
            "tenants": [
                {
                    "id": "tenant-uuid",
                    "name": "Acme Corp",
                    "subdomain": "acme",
                    "role": "admin"
                }
            ]
        }

    Errors:
        - 400: Validation error (missing email or password)
        - 401: Invalid credentials
        - 403: Account is inactive
        - 500: Server error

    Security:
        - Password is verified using bcrypt
        - Access token expires in 15 minutes
        - Refresh token expires in 7 days
        - Returns user's tenant memberships with roles
    """
    try:
        # Validate request data
        data = user_login_schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({
            'error': 'validation_error',
            'message': 'Invalid login data provided',
            'details': err.messages
        }), 400

    # Find user by email
    user = User.query.filter_by(email=data['email']).first()

    # Verify user exists and password is correct
    if not user or not user.check_password(data['password']):
        return jsonify({
            'error': 'invalid_credentials',
            'message': 'Invalid email or password'
        }), 401

    # Check if user account is active
    if not user.is_active:
        return jsonify({
            'error': 'account_inactive',
            'message': 'Your account has been deactivated. Please contact support.'
        }), 403

    try:
        # Create JWT tokens
        # Access token expires in 15 minutes
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(minutes=15)
        )

        # Refresh token expires in 7 days
        refresh_token = create_refresh_token(
            identity=str(user.id),
            expires_delta=timedelta(days=7)
        )

        # Get user's tenant memberships with roles
        tenant_associations = UserTenantAssociation.query.filter_by(user_id=user.id).all()

        tenants_data = []
        for assoc in tenant_associations:
            tenant = Tenant.query.get(assoc.tenant_id)
            if tenant:
                tenants_data.append({
                    'id': str(tenant.id),
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'role': assoc.role
                })

        # Serialize user data
        user_data = user_response_schema.dump(user)

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user_data,
            'tenants': tenants_data
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'login_failed',
            'message': 'Login failed. Please try again.'
        }), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Generate a new access token using a refresh token.

    POST /api/auth/refresh

    Headers:
        Authorization: Bearer <refresh_token>

    Response (200):
        {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }

    Errors:
        - 401: Missing or invalid refresh token
        - 401: Refresh token expired
        - 401: Refresh token revoked
        - 404: User not found
        - 500: Server error

    Security:
        - Requires valid refresh token
        - New access token expires in 15 minutes
        - Verifies user still exists and is active
    """
    try:
        # Get user ID from refresh token
        current_user_id = get_jwt_identity()

        # Verify user still exists and is active
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({
                'error': 'user_not_found',
                'message': 'User account not found'
            }), 404

        if not user.is_active:
            return jsonify({
                'error': 'account_inactive',
                'message': 'Your account has been deactivated'
            }), 403

        # Create new access token
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(minutes=15)
        )

        return jsonify({
            'access_token': access_token
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'token_refresh_failed',
            'message': 'Failed to refresh token. Please log in again.'
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user by blacklisting the current access token.

    POST /api/auth/logout

    Headers:
        Authorization: Bearer <access_token>

    Response (200):
        {
            "message": "Logged out successfully"
        }

    Errors:
        - 401: Missing or invalid access token
        - 500: Server error

    Security:
        - Adds token JTI to blacklist
        - Blacklisted tokens cannot be used for authentication
        - Client should also delete stored tokens

    Note:
        For production, implement token blacklist using:
        - Redis (for distributed systems)
        - Database table (for persistence)
        - Token revocation list (for compliance)

        Current implementation uses in-memory set (dev only).
    """
    try:
        # Get JWT ID (jti) from current token
        jti = get_jwt()['jti']

        # Add token to blacklist via AuthService
        success, error = AuthService.logout(jti)

        if not success:
            return jsonify({
                'error': 'logout_failed',
                'message': error or 'Failed to logout. Please try again.'
            }), 500

        return jsonify({
            'message': 'Logged out successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'logout_failed',
            'message': 'Failed to logout. Please try again.'
        }), 500


# Health check endpoint for auth service
@auth_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint for authentication service.

    GET /api/auth/health

    Response (200):
        {
            "status": "healthy",
            "service": "authentication",
            "endpoints": [...]
        }
    """
    return jsonify({
        'status': 'healthy',
        'service': 'authentication',
        'endpoints': {
            'register': '/api/auth/register (POST)',
            'login': '/api/auth/login (POST)',
            'refresh': '/api/auth/refresh (POST)',
            'logout': '/api/auth/logout (POST)'
        }
    }), 200
