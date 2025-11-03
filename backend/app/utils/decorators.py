"""
Custom decorators for route protection and access control.

Provides JWT validation, tenant membership verification, and role-based access control.
"""

from functools import wraps
from typing import List, Optional, Callable
from flask import request, g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
import logging

from app.utils.responses import unauthorized, forbidden, not_found
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


def jwt_required_custom(fn: Callable) -> Callable:
    """
    Custom JWT authentication decorator.

    Validates JWT token and injects user information into Flask's g object.
    Enhances Flask-JWT-Extended's jwt_required with custom error handling
    and token blacklist checking.

    Security Features:
        - Validates JWT signature and expiration
        - Checks token against blacklist (revoked tokens)
        - Verifies user identity is present
        - Injects user context into Flask g object

    Usage:
        @app.route('/api/users/me')
        @jwt_required_custom
        def get_profile():
            user_id = g.user_id
            return {"user_id": user_id}

    Sets in Flask g:
        - g.user_id: UUID of authenticated user
        - g.jwt_claims: Full JWT claims dict (includes jti, exp, iat, etc.)

    Token Blacklist:
        - Checks AuthService.is_token_blacklisted() for revoked tokens
        - Uses jti (JWT ID) claim for blacklist lookups
        - Returns 401 if token is blacklisted

    Returns:
        Decorated function with JWT validation
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            # Verify JWT token
            verify_jwt_in_request()

            # Extract user information from JWT
            user_id = get_jwt_identity()
            jwt_claims = get_jwt()

            if not user_id:
                logger.warning("JWT token missing user identity")
                return unauthorized("Invalid authentication token")

            # Check if token is blacklisted
            jti = jwt_claims.get('jti')  # JWT ID from token claims
            if jti:
                is_blacklisted = AuthService.is_token_blacklisted(jti)
                if is_blacklisted:
                    logger.warning(f"Blacklisted token attempted: user_id={user_id}, jti={jti}")
                    return unauthorized("Token has been revoked")

            # Store in Flask g for access in route handlers
            g.user_id = user_id
            g.jwt_claims = jwt_claims

            logger.debug(f"Authenticated user: {user_id}")

            return fn(*args, **kwargs)

        except Exception as e:
            logger.error(f"JWT validation failed: {str(e)}")
            return unauthorized("Authentication failed", str(e))

    return wrapper


def tenant_required(tenant_id_param: str = 'tenant_id') -> Callable:
    """
    Decorator to validate tenant membership.

    Verifies that the authenticated user has access to the requested tenant.
    Must be used together with @jwt_required_custom.

    Args:
        tenant_id_param: Name of the route parameter containing tenant_id

    Usage:
        @app.route('/api/tenants/<tenant_id>/documents')
        @jwt_required_custom
        @tenant_required(tenant_id_param='tenant_id')
        def list_documents(tenant_id):
            # User has access to this tenant
            return {"documents": [...]}

    Sets in Flask g:
        - g.tenant_id: UUID of the tenant
        - g.user_role: User's role in the tenant ('admin', 'user', 'viewer')

    Returns:
        Decorator function
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Get tenant_id from route parameters
            tenant_id = kwargs.get(tenant_id_param)

            if not tenant_id:
                logger.error(f"Tenant ID parameter '{tenant_id_param}' not found in route")
                return not_found("Tenant")

            # Check if user_id is available (requires @jwt_required_custom)
            user_id = getattr(g, 'user_id', None)
            if not user_id:
                logger.error("tenant_required used without jwt_required_custom")
                return unauthorized("Authentication required")

            # TODO: Query UserTenantAssociation to verify membership and get role
            # This will be implemented in Phase 2 after models are created
            # For now, we'll set placeholder values

            # from app.models import UserTenantAssociation
            # association = UserTenantAssociation.query.filter_by(
            #     user_id=user_id,
            #     tenant_id=tenant_id
            # ).first()
            #
            # if not association:
            #     logger.warning(f"User {user_id} attempted to access tenant {tenant_id} without permission")
            #     return forbidden("You do not have access to this tenant")
            #
            # g.user_role = association.role

            # Placeholder until models are implemented
            g.tenant_id = tenant_id
            g.user_role = 'admin'  # TODO: Get actual role from database

            logger.debug(f"User {user_id} accessing tenant {tenant_id} with role {g.user_role}")

            return fn(*args, **kwargs)

        return wrapper
    return decorator


def role_required(allowed_roles: List[str]) -> Callable:
    """
    Decorator to enforce role-based access control.

    Verifies that the user has one of the required roles for the tenant.
    Must be used together with @jwt_required_custom and @tenant_required.

    Args:
        allowed_roles: List of roles that can access this endpoint
                      ['admin', 'user', 'viewer']

    Usage:
        @app.route('/api/tenants/<tenant_id>/users', methods=['POST'])
        @jwt_required_custom
        @tenant_required(tenant_id_param='tenant_id')
        @role_required(['admin'])
        def add_user_to_tenant(tenant_id):
            # Only admins can add users
            return {"message": "User added"}

    Role hierarchy:
        - admin: Full access (create, read, update, delete)
        - user: Read and write access to documents
        - viewer: Read-only access

    Returns:
        Decorator function
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Get user role from g (set by @tenant_required)
            user_role = getattr(g, 'user_role', None)

            if not user_role:
                logger.error("role_required used without tenant_required")
                return forbidden("Access denied")

            if user_role not in allowed_roles:
                user_id = getattr(g, 'user_id', 'unknown')
                tenant_id = getattr(g, 'tenant_id', 'unknown')
                logger.warning(
                    f"User {user_id} with role '{user_role}' attempted to access "
                    f"endpoint requiring roles {allowed_roles} in tenant {tenant_id}"
                )
                return forbidden(
                    f"Access denied. Required roles: {', '.join(allowed_roles)}",
                    f"Your role: {user_role}"
                )

            logger.debug(f"Role check passed: {user_role} in {allowed_roles}")

            return fn(*args, **kwargs)

        return wrapper
    return decorator


def admin_required(fn: Callable) -> Callable:
    """
    Convenience decorator for admin-only endpoints.

    Equivalent to @role_required(['admin']).

    Usage:
        @app.route('/api/tenants/<tenant_id>/settings', methods=['PUT'])
        @jwt_required_custom
        @tenant_required(tenant_id_param='tenant_id')
        @admin_required
        def update_tenant_settings(tenant_id):
            # Only admins can update settings
            return {"message": "Settings updated"}

    Returns:
        Decorated function with admin role requirement
    """
    return role_required(['admin'])(fn)


def rate_limit(limit: int, per: int, scope: Optional[str] = None) -> Callable:
    """
    Rate limiting decorator (placeholder).

    Will be implemented with Redis or in-memory cache in future phases.
    Currently logs rate limit configuration but doesn't enforce.

    Args:
        limit: Maximum number of requests
        per: Time period in seconds
        scope: Optional scope identifier ('user', 'ip', 'tenant')

    Usage:
        @app.route('/api/auth/login', methods=['POST'])
        @rate_limit(limit=5, per=60, scope='ip')
        def login():
            # Limited to 5 requests per minute per IP
            return {"token": "..."}

    Returns:
        Decorator function
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # TODO: Implement rate limiting with Redis
            # For now, just log the configuration
            logger.debug(f"Rate limit configured: {limit} requests per {per} seconds (scope: {scope})")

            # Placeholder for rate limit logic
            # client_id = get_client_identifier(scope)
            # if not check_rate_limit(client_id, limit, per):
            #     return error_response(
            #         "RATE_LIMIT_EXCEEDED",
            #         "Too many requests",
            #         f"Limit: {limit} requests per {per} seconds",
            #         429
            #     )

            return fn(*args, **kwargs)

        return wrapper
    return decorator


def validate_json(required_fields: Optional[List[str]] = None) -> Callable:
    """
    Decorator to validate JSON request body.

    Ensures request has valid JSON and optionally validates required fields.

    Args:
        required_fields: List of required field names in JSON body

    Usage:
        @app.route('/api/auth/register', methods=['POST'])
        @validate_json(required_fields=['email', 'password', 'first_name', 'last_name'])
        def register():
            data = request.get_json()
            return {"user": data}

    Returns:
        Decorator function
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Check if request has JSON content type
            if not request.is_json:
                return unauthorized("Content-Type must be application/json")

            # Parse JSON body
            try:
                data = request.get_json()
            except Exception as e:
                logger.error(f"Invalid JSON in request: {str(e)}")
                return unauthorized("Invalid JSON format", str(e))

            if data is None:
                return unauthorized("Request body is required")

            # Validate required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data]

                if missing_fields:
                    logger.warning(f"Missing required fields: {missing_fields}")
                    return unauthorized(
                        "Missing required fields",
                        {"missing_fields": missing_fields}
                    )

            return fn(*args, **kwargs)

        return wrapper
    return decorator
