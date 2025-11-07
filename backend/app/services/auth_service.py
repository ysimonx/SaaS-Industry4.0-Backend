"""
AuthService - Business Logic for Authentication

This service handles all authentication-related business logic including user registration,
login, token management, and logout. It separates business logic from the route handlers
in the auth blueprint.

Key responsibilities:
- User registration with validation and password hashing
- User authentication with email/password verification
- JWT token generation (access and refresh tokens)
- Token refresh logic with blacklist checking
- Logout with token revocation
- User tenant fetching for login response

Architecture:
- Service layer sits between routes (controllers) and models (data layer)
- Handles business logic, validation, and orchestration
- Routes call service methods instead of directly manipulating models
- Services can call other services for complex operations

Token Management:
- Access tokens: 15 minutes expiration (configurable via JWT_ACCESS_TOKEN_EXPIRES)
- Refresh tokens: 7 days expiration (configurable via JWT_REFRESH_TOKEN_EXPIRES)
- Token blacklist: In-memory set for development (use Redis in production)
- JTI (JWT ID) used for token revocation tracking
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from flask import current_app

from app.models.user import User
from app.models.user_tenant_association import UserTenantAssociation
from app.extensions import db, redis_manager

logger = logging.getLogger(__name__)

# In-memory token blacklist fallback for when Redis is not available
TOKEN_BLACKLIST = set()


class AuthService:
    """
    Service class for authentication operations.

    This class provides methods for user registration, authentication, token management,
    and logout. All methods are static since there's no instance state to maintain.
    """

    @staticmethod
    def _add_to_blacklist(jti: str) -> bool:
        """
        Add a token JTI to the blacklist.

        Uses Redis if available, falls back to in-memory set.

        Args:
            jti: JWT ID to blacklist

        Returns:
            bool: True if successfully added
        """
        try:
            redis_client = redis_manager.get_client()
            if redis_client:
                # Use Redis with expiration
                expire_time = current_app.config.get('REDIS_TOKEN_BLACKLIST_EXPIRE', 86400)
                redis_key = f"token_blacklist:{jti}"
                redis_client.setex(redis_key, expire_time, "1")
                logger.debug(f"Token blacklisted in Redis: {jti}")
                return True
            else:
                # Fall back to in-memory
                TOKEN_BLACKLIST.add(jti)
                logger.debug(f"Token blacklisted in memory: {jti}")
                return True
        except Exception as e:
            logger.error(f"Error adding token to blacklist: {e}")
            # Fallback to in-memory
            TOKEN_BLACKLIST.add(jti)
            return True

    @staticmethod
    def _is_token_blacklisted(jti: str) -> bool:
        """
        Check if a token JTI is blacklisted.

        Uses Redis if available, falls back to in-memory set.

        Args:
            jti: JWT ID to check

        Returns:
            bool: True if token is blacklisted
        """
        try:
            redis_client = redis_manager.get_client()
            if redis_client:
                redis_key = f"token_blacklist:{jti}"
                return redis_client.exists(redis_key) > 0
            else:
                return jti in TOKEN_BLACKLIST
        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            # Fallback to in-memory
            return jti in TOKEN_BLACKLIST

    @staticmethod
    def _get_blacklist_size() -> int:
        """
        Get the size of the token blacklist.

        Returns:
            int: Number of blacklisted tokens
        """
        try:
            redis_client = redis_manager.get_client()
            if redis_client:
                # Count all token_blacklist keys in Redis
                keys = redis_client.keys("token_blacklist:*")
                return len(keys)
            else:
                return len(TOKEN_BLACKLIST)
        except Exception as e:
            logger.error(f"Error getting blacklist size: {e}")
            return len(TOKEN_BLACKLIST)

    @staticmethod
    def register(user_data: Dict) -> Tuple[User, Optional[str]]:
        """
        Register a new user account.

        This method handles the complete user registration flow:
        1. Validates that email is unique
        2. Creates new user record
        3. Hashes password using bcrypt (via User.set_password())
        4. Saves user to database
        5. Returns user object

        Args:
            user_data: Dictionary containing user registration data
                Required fields: email, password, first_name, last_name
                Optional fields: is_active (defaults to True)

        Returns:
            Tuple of (User object, error message)
            - If successful: (user, None)
            - If error: (None, error_message)

        Example:
            user, error = AuthService.register({
                'email': 'user@example.com',
                'password': 'SecurePass123',
                'first_name': 'John',
                'last_name': 'Doe'
            })
            if error:
                return bad_request(error)
            return created(user_response_schema.dump(user))

        Business Rules:
            - Email must be unique (case-insensitive)
            - Password must meet security requirements (handled by User model)
            - User is active by default unless specified otherwise
            - created_by is None for self-registration
        """
        try:
            # Check if email already exists (case-insensitive)
            email = user_data['email'].lower()
            existing_user = User.find_by_email(email)

            if existing_user:
                logger.warning(f"Registration failed: Email already exists: {email}")
                return None, 'Email already registered'

            # Create new user
            user = User(
                email=email,
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_active=user_data.get('is_active', True)
            )

            # Hash password (User model handles bcrypt hashing)
            user.set_password(user_data['password'])

            # Save to database
            db.session.add(user)
            db.session.commit()

            logger.info(f"User registered successfully: {user.id} ({email})")
            return user, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            return None, f'Registration failed: {str(e)}'

    @staticmethod
    def authenticate(email: str, password: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Authenticate user with email and password.

        This method handles the complete authentication flow:
        1. Finds user by email (case-insensitive)
        2. Checks if user is active
        3. Verifies password hash
        4. Generates JWT access and refresh tokens
        5. Fetches user's tenants with roles
        6. Returns authentication response with tokens, user, and tenants

        Args:
            email: User's email address
            password: User's plain-text password

        Returns:
            Tuple of (auth_data dict, error message)
            - If successful: (auth_data, None) where auth_data contains:
                - access_token: JWT access token (15 min expiry)
                - refresh_token: JWT refresh token (7 day expiry)
                - user: User object (dict)
                - tenants: List of tenant associations with roles
            - If error: (None, error_message)

        Example:
            auth_data, error = AuthService.authenticate(
                email='user@example.com',
                password='SecurePass123'
            )
            if error:
                return unauthorized(error)
            return success('Login successful', auth_data)

        Business Rules:
            - Email lookup is case-insensitive
            - User must be active (is_active=True)
            - Password must match hashed password
            - Returns user's tenants sorted by joined_at (most recent first)
        """
        try:
            # Find user by email (case-insensitive)
            user = User.find_active_by_email(email.lower())

            if not user:
                logger.warning(f"Authentication failed: User not found or inactive: {email}")
                return None, 'Invalid email or password'

            # Verify password
            if not user.check_password(password):
                logger.warning(f"Authentication failed: Invalid password for: {email}")
                return None, 'Invalid email or password'

            # Generate JWT tokens
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))

            # Fetch user's tenants with roles
            tenants = AuthService._get_user_tenants(user.id)

            # Build response data
            auth_data = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_active': user.is_active,
                    'created_at': user.created_at.isoformat() if user.created_at else None
                },
                'tenants': tenants
            }

            logger.info(f"User authenticated successfully: {user.id} ({email})")
            return auth_data, None

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            return None, f'Authentication failed: {str(e)}'

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate new access token from refresh token.

        This method handles token refresh:
        1. Decodes and validates refresh token
        2. Checks token is not blacklisted
        3. Verifies user still exists and is active
        4. Generates new access token
        5. Returns new access token

        Args:
            refresh_token: JWT refresh token string

        Returns:
            Tuple of (new_access_token, error message)
            - If successful: (access_token, None)
            - If error: (None, error_message)

        Example:
            new_token, error = AuthService.refresh_access_token(refresh_token)
            if error:
                return unauthorized(error)
            return success('Token refreshed', {'access_token': new_token})

        Business Rules:
            - Refresh token must be valid and not expired
            - Token JTI must not be in blacklist
            - User must still exist and be active
            - New access token has same expiry as configured (15 min)
        """
        try:
            # Decode refresh token
            decoded_token = decode_token(refresh_token)
            jti = decoded_token.get('jti')
            user_id = decoded_token.get('sub')

            # Check if token is blacklisted
            if AuthService._is_token_blacklisted(jti):
                logger.warning(f"Refresh failed: Token is blacklisted: {jti}")
                return None, 'Token has been revoked'

            # Verify user still exists and is active
            user = User.query.filter_by(id=user_id, is_active=True).first()
            if not user:
                logger.warning(f"Refresh failed: User not found or inactive: {user_id}")
                return None, 'User not found or inactive'

            # Generate new access token
            new_access_token = create_access_token(identity=user_id)

            logger.info(f"Access token refreshed for user: {user_id}")
            return new_access_token, None

        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}", exc_info=True)
            return None, f'Token refresh failed: {str(e)}'

    @staticmethod
    def logout(jti: str) -> Tuple[bool, Optional[str]]:
        """
        Logout user by blacklisting their token.

        This method handles logout by adding the token's JTI (JWT ID) to the blacklist.
        Once blacklisted, the token cannot be used for authentication or refresh.

        Args:
            jti: JWT ID (unique identifier) from the token

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If error: (False, error_message)

        Example:
            success, error = AuthService.logout(jti='abc-123-def-456')
            if error:
                return server_error(error)
            return success('Logged out successfully')

        Business Rules:
            - JTI is added to in-memory blacklist (development)
            - In production, should use Redis with TTL matching token expiry
            - Token remains blacklisted until it would naturally expire
            - Multiple logout calls for same token are idempotent

        Notes:
            - In-memory blacklist is lost on server restart (development only)
            - Production should use Redis with expiry matching JWT expiry time
            - Blacklist cleanup can be handled by Redis TTL or scheduled job
        """
        try:
            # Add JTI to blacklist
            AuthService._add_to_blacklist(jti)

            logger.info(f"Token blacklisted (logout): {jti}")
            logger.debug(f"Blacklist size: {AuthService._get_blacklist_size()}")

            return True, None

        except Exception as e:
            logger.error(f"Logout error: {str(e)}", exc_info=True)
            return False, f'Logout failed: {str(e)}'

    @staticmethod
    def is_token_blacklisted(jti: str) -> bool:
        """
        Check if token is blacklisted.

        This method is used by JWT callbacks to check if a token has been revoked.

        Args:
            jti: JWT ID to check

        Returns:
            True if token is blacklisted, False otherwise

        Example:
            if AuthService.is_token_blacklisted(jti):
                return unauthorized('Token has been revoked')
        """
        return AuthService._is_token_blacklisted(jti)

    @staticmethod
    def _get_user_tenants(user_id: str) -> List[Dict]:
        """
        Get list of tenants for a user with roles.

        This is a private helper method used by authenticate() to fetch
        user's tenant associations for the login response.

        Args:
            user_id: User's UUID

        Returns:
            List of tenant dictionaries with role information:
            [
                {
                    'id': 'tenant-uuid',
                    'name': 'Tenant Name',
                    'role': 'admin',
                    'joined_at': '2024-01-01T00:00:00Z'
                },
                ...
            ]

        Notes:
            - Returns only active tenants
            - Sorted by joined_at descending (most recent first)
            - Used internally by authenticate() method
        """
        try:
            # Query user-tenant associations
            associations = UserTenantAssociation.query.filter_by(
                user_id=user_id
            ).join(
                UserTenantAssociation.tenant
            ).filter_by(
                is_active=True
            ).order_by(
                UserTenantAssociation.joined_at.desc()
            ).all()

            # Build tenant list
            tenants = []
            for assoc in associations:
                tenants.append({
                    'id': str(assoc.tenant_id),
                    'name': assoc.tenant.name,
                    'role': assoc.role,
                    'joined_at': assoc.joined_at.isoformat() if assoc.joined_at else None
                })

            logger.debug(f"Fetched {len(tenants)} tenants for user: {user_id}")
            return tenants

        except Exception as e:
            logger.error(f"Error fetching user tenants: {str(e)}", exc_info=True)
            return []


# Export service class and blacklist checking function
__all__ = ['AuthService']
