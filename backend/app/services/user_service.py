"""
UserService - Business Logic for User Management

This service handles all user-related business logic including fetching users,
updating user profiles, and retrieving user tenant associations.
It separates business logic from the route handlers in the users blueprint.

Key responsibilities:
- Fetch user by ID or email
- Update user profile information (name, email, status)
- Retrieve user's tenant associations with roles
- Validate user data before updates
- Handle cross-references between main database and tenant databases

Architecture:
- Service layer sits between routes (controllers) and models (data layer)
- Handles business logic, validation, and orchestration
- Routes call service methods instead of directly manipulating models
- Services can call other services for complex operations

User Management:
- Users stored in main database (not tenant-specific)
- Email must be unique (case-insensitive)
- Password updates handled separately (security requirement)
- Tenant associations managed through UserTenantAssociation model
"""

import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.user_tenant_association import UserTenantAssociation
from app.extensions import db

logger = logging.getLogger(__name__)


class UserService:
    """
    Service class for user management operations.

    This class provides methods for fetching users, updating profiles,
    and retrieving tenant associations. All methods are static since
    there's no instance state to maintain.
    """

    @staticmethod
    def get_user_by_id(user_id: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Fetch user by UUID.

        This method retrieves a user record from the main database by their UUID.
        It returns both active and inactive users (caller should check is_active if needed).

        Args:
            user_id: User's UUID string

        Returns:
            Tuple of (User object, error message)
            - If successful: (user, None)
            - If not found: (None, 'User not found')
            - If error: (None, error_message)

        Example:
            user, error = UserService.get_user_by_id('123e4567-e89b-12d3-a456-426614174000')
            if error:
                return not_found(error)
            return success('User retrieved', user_response_schema.dump(user))

        Business Rules:
            - Returns user regardless of is_active status
            - Caller should check user.is_active if needed
            - Returns None if user_id is invalid UUID format
        """
        try:
            # Query user by ID
            user = User.query.filter_by(id=user_id).first()

            if not user:
                logger.warning(f"User not found: {user_id}")
                return None, 'User not found'

            logger.debug(f"User retrieved: {user.id} ({user.email})")
            return user, None

        except Exception as e:
            logger.error(f"Error fetching user by ID {user_id}: {str(e)}", exc_info=True)
            return None, f'Failed to fetch user: {str(e)}'

    @staticmethod
    def get_user_by_email(email: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Fetch user by email address.

        This method retrieves a user record from the main database by their email.
        Email lookup is case-insensitive. Returns both active and inactive users.

        Args:
            email: User's email address

        Returns:
            Tuple of (User object, error message)
            - If successful: (user, None)
            - If not found: (None, 'User not found')
            - If error: (None, error_message)

        Example:
            user, error = UserService.get_user_by_email('john@example.com')
            if error:
                return not_found(error)
            return success('User retrieved', user_response_schema.dump(user))

        Business Rules:
            - Email lookup is case-insensitive (converted to lowercase)
            - Returns user regardless of is_active status
            - Caller should check user.is_active if needed
        """
        try:
            # Normalize email to lowercase for case-insensitive lookup
            email_normalized = email.lower()

            # Query user by email
            user = User.find_by_email(email_normalized)

            if not user:
                logger.warning(f"User not found: {email_normalized}")
                return None, 'User not found'

            logger.debug(f"User retrieved by email: {user.id} ({user.email})")
            return user, None

        except Exception as e:
            logger.error(f"Error fetching user by email {email}: {str(e)}", exc_info=True)
            return None, f'Failed to fetch user: {str(e)}'

    @staticmethod
    def update_user(user_id: str, user_data: Dict) -> Tuple[Optional[User], Optional[str]]:
        """
        Update user profile information.

        This method handles updating user profile fields including:
        - first_name, last_name: User's name
        - email: Must be unique (case-insensitive)
        - is_active: Account active status (admin-only field)

        Password updates are NOT handled here (use separate password change endpoint).

        Args:
            user_id: User's UUID string
            user_data: Dictionary containing fields to update
                Allowed fields: first_name, last_name, email, is_active
                All fields are optional (only provided fields are updated)

        Returns:
            Tuple of (updated User object, error message)
            - If successful: (user, None)
            - If user not found: (None, 'User not found')
            - If email conflict: (None, 'Email already in use')
            - If validation error: (None, error_message)
            - If error: (None, error_message)

        Example:
            user, error = UserService.update_user(
                user_id='123e4567-e89b-12d3-a456-426614174000',
                user_data={
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'email': 'john.doe@example.com'
                }
            )
            if error:
                return bad_request(error)
            return success('User updated', user_response_schema.dump(user))

        Business Rules:
            - Only updates fields present in user_data (partial updates allowed)
            - Email must be unique across all users (case-insensitive)
            - Email is normalized to lowercase before saving
            - Password updates NOT allowed through this method
            - Database transaction rolled back on any error
            - User must exist (no creation through update)

        Security Notes:
            - Caller should validate that requester has permission to update user
            - is_active field should only be updatable by admins
            - Email changes should trigger email verification (future enhancement)
        """
        try:
            # Fetch user
            user = User.query.filter_by(id=user_id).first()

            if not user:
                logger.warning(f"Update failed: User not found: {user_id}")
                return None, 'User not found'

            # Track what fields are being updated (for logging)
            updated_fields = []

            # Update first_name if provided
            if 'first_name' in user_data:
                user.first_name = user_data['first_name']
                updated_fields.append('first_name')

            # Update last_name if provided
            if 'last_name' in user_data:
                user.last_name = user_data['last_name']
                updated_fields.append('last_name')

            # Update email if provided (with uniqueness check)
            if 'email' in user_data:
                new_email = user_data['email'].lower()

                # Check if email is changing
                if new_email != user.email:
                    # Check if new email is already taken
                    existing_user = User.find_by_email(new_email)
                    if existing_user and existing_user.id != user.id:
                        logger.warning(
                            f"Update failed: Email already in use: {new_email} "
                            f"(attempted by user {user_id})"
                        )
                        return None, 'Email already in use'

                    user.email = new_email
                    updated_fields.append('email')

            # Update is_active if provided (admin-only field)
            if 'is_active' in user_data:
                user.is_active = user_data['is_active']
                updated_fields.append('is_active')

            # Commit changes to database
            db.session.commit()

            logger.info(
                f"User updated: {user.id} ({user.email}) - "
                f"Updated fields: {', '.join(updated_fields) if updated_fields else 'none'}"
            )

            return user, None

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Integrity error updating user {user_id}: {str(e)}", exc_info=True)
            return None, 'Email already in use or database constraint violation'

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating user {user_id}: {str(e)}", exc_info=True)
            return None, f'Failed to update user: {str(e)}'

    @staticmethod
    def get_user_tenants(user_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get list of tenants for a user with roles and status.

        This method retrieves all tenant associations for a user, including:
        - Tenant details (id, name, database_name, is_active)
        - User's role in each tenant (admin, member, viewer)
        - Association metadata (joined_at timestamp)

        The results include both active and inactive tenants (caller should filter if needed).

        Args:
            user_id: User's UUID string

        Returns:
            Tuple of (tenant list, error message)
            - If successful: (tenant_list, None) where tenant_list is:
                [
                    {
                        'tenant_id': 'tenant-uuid',
                        'tenant_name': 'Acme Corp',
                        'database_name': 'tenant_acme_corp',
                        'role': 'admin',
                        'joined_at': '2024-01-01T00:00:00Z',
                        'tenant_is_active': True
                    },
                    ...
                ]
            - If user not found: (None, 'User not found')
            - If error: (None, error_message)
            - If user has no tenants: ([], None) - empty list is success

        Example:
            tenants, error = UserService.get_user_tenants('123e4567-e89b-12d3-a456-426614174000')
            if error:
                return not_found(error)
            return success('User tenants retrieved', {'tenants': tenants})

        Business Rules:
            - Returns ALL tenant associations (active and inactive tenants)
            - Sorted by joined_at descending (most recent first)
            - Includes role information for authorization checks
            - Returns empty list if user has no tenant associations (not an error)
            - User must exist (returns error if user_id invalid)

        Architecture Notes:
            - Joins User → UserTenantAssociation → Tenant
            - Query executes in main database (not tenant-specific)
            - Used for user profile pages, authorization checks, and tenant switching
        """
        try:
            # Verify user exists
            user = User.query.filter_by(id=user_id).first()

            if not user:
                logger.warning(f"Get tenants failed: User not found: {user_id}")
                return None, 'User not found'

            # Query user-tenant associations with tenant details
            associations = UserTenantAssociation.query.filter_by(
                user_id=user_id
            ).join(
                UserTenantAssociation.tenant
            ).order_by(
                UserTenantAssociation.joined_at.desc()
            ).all()

            # Build tenant list with role and status information
            tenants = []
            for assoc in associations:
                tenants.append({
                    'tenant_id': str(assoc.tenant_id),
                    'tenant_name': assoc.tenant.name,
                    'database_name': assoc.tenant.database_name,
                    'role': assoc.role,
                    'joined_at': assoc.joined_at.isoformat() if assoc.joined_at else None,
                    'tenant_is_active': assoc.tenant.is_active
                })

            logger.debug(
                f"Retrieved {len(tenants)} tenant associations for user: {user_id} ({user.email})"
            )

            return tenants, None

        except Exception as e:
            logger.error(
                f"Error fetching tenants for user {user_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to fetch user tenants: {str(e)}'


# Export service class
__all__ = ['UserService']
