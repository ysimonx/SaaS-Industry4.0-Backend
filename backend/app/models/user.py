"""
User model for authentication and user management.

Stores user accounts in the main database with password hashing,
tenant associations, and authentication methods.
"""

import bcrypt
from sqlalchemy import Column, String, Boolean, Index
from sqlalchemy.orm import relationship
from typing import List, Optional
import logging

from app.extensions import db
from app.models.base import BaseModel

logger = logging.getLogger(__name__)


class User(BaseModel, db.Model):
    """
    User model for authentication and profile management.

    Stored in the main database. Users can be associated with multiple tenants
    with different roles in each tenant.

    Attributes:
        first_name: User's first name (required, max 100 chars)
        last_name: User's last name (required, max 100 chars)
        email: User's email address (unique, required, indexed, max 255 chars)
        password_hash: Bcrypt hashed password (required, max 255 chars)
        is_active: Whether user account is active (default True)
        tenant_associations: List of UserTenantAssociation objects

    Example:
        >>> user = User(
        ...     first_name='John',
        ...     last_name='Doe',
        ...     email='john.doe@example.com'
        ... )
        >>> user.set_password('secure_password123')
        >>> db.session.add(user)
        >>> db.session.commit()
    """

    __tablename__ = 'users'
    __bind_key__ = None  # Uses default (main) database

    # User profile fields
    first_name = Column(
        String(100),
        nullable=False,
        comment="User's first name"
    )

    last_name = Column(
        String(100),
        nullable=False,
        comment="User's last name"
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User's email address (unique, used for login)"
    )

    password_hash = Column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether user account is active (can login)"
    )

    # Relationships
    # Note: UserTenantAssociation will be created in Task 8
    # tenant_associations = relationship(
    #     'UserTenantAssociation',
    #     back_populates='user',
    #     cascade='all, delete-orphan'
    # )

    # Indexes for performance
    __table_args__ = (
        Index('ix_users_email_active', 'email', 'is_active'),
    )

    def set_password(self, password: str) -> None:
        """
        Hash and set user password using bcrypt.

        Args:
            password: Plain text password to hash (minimum 8 characters)

        Raises:
            ValueError: If password is less than 8 characters

        Example:
            >>> user = User(email='test@example.com', first_name='Test', last_name='User')
            >>> user.set_password('my_secure_password')
        """
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        # Generate salt and hash password with bcrypt
        salt = bcrypt.gensalt()
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, salt)

        # Store as string
        self.password_hash = hashed.decode('utf-8')
        logger.debug(f"Password hashed for user: {self.email}")

    def check_password(self, password: str) -> bool:
        """
        Verify password against stored hash.

        Args:
            password: Plain text password to verify

        Returns:
            True if password matches, False otherwise

        Example:
            >>> user = User.query.filter_by(email='test@example.com').first()
            >>> if user.check_password('my_password'):
            ...     print('Password correct')
        """
        if not password or not self.password_hash:
            return False

        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = self.password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception as e:
            logger.error(f"Error checking password for user {self.email}: {str(e)}")
            return False

    def get_tenants(self) -> List:
        """
        Get list of all tenants this user has access to.

        Returns:
            List of Tenant objects with user's role information

        Note:
            This will be implemented in Task 8 after UserTenantAssociation is created.

        Example:
            >>> user = User.query.get(user_id)
            >>> tenants = user.get_tenants()
            >>> for tenant_info in tenants:
            ...     print(f"Tenant: {tenant_info['tenant'].name}, Role: {tenant_info['role']}")
        """
        # TODO: Implement after UserTenantAssociation model is created
        # from app.models.user_tenant_association import UserTenantAssociation
        # from app.models.tenant import Tenant
        #
        # associations = UserTenantAssociation.query.filter_by(user_id=self.id).all()
        # return [
        #     {
        #         'tenant': assoc.tenant,
        #         'role': assoc.role,
        #         'joined_at': assoc.joined_at
        #     }
        #     for assoc in associations
        # ]
        logger.warning("get_tenants() not yet implemented - requires UserTenantAssociation model")
        return []

    def has_access_to_tenant(self, tenant_id: str) -> bool:
        """
        Check if user has access to a specific tenant.

        Args:
            tenant_id: UUID of tenant to check access for

        Returns:
            True if user is associated with tenant, False otherwise

        Note:
            This will be implemented in Task 8 after UserTenantAssociation is created.

        Example:
            >>> user = User.query.get(user_id)
            >>> if user.has_access_to_tenant(tenant_id):
            ...     print('User has access to this tenant')
        """
        # TODO: Implement after UserTenantAssociation model is created
        # from app.models.user_tenant_association import UserTenantAssociation
        #
        # association = UserTenantAssociation.query.filter_by(
        #     user_id=self.id,
        #     tenant_id=tenant_id
        # ).first()
        #
        # return association is not None
        logger.warning("has_access_to_tenant() not yet implemented - requires UserTenantAssociation model")
        return False

    def get_role_in_tenant(self, tenant_id: str) -> Optional[str]:
        """
        Get user's role in a specific tenant.

        Args:
            tenant_id: UUID of tenant to get role for

        Returns:
            Role string ('admin', 'user', 'viewer') or None if no access

        Note:
            This will be implemented in Task 8 after UserTenantAssociation is created.

        Example:
            >>> user = User.query.get(user_id)
            >>> role = user.get_role_in_tenant(tenant_id)
            >>> if role == 'admin':
            ...     print('User is admin of this tenant')
        """
        # TODO: Implement after UserTenantAssociation model is created
        # from app.models.user_tenant_association import UserTenantAssociation
        #
        # association = UserTenantAssociation.query.filter_by(
        #     user_id=self.id,
        #     tenant_id=tenant_id
        # ).first()
        #
        # return association.role if association else None
        logger.warning("get_role_in_tenant() not yet implemented - requires UserTenantAssociation model")
        return None

    def get_full_name(self) -> str:
        """
        Get user's full name.

        Returns:
            Full name as "First Last"

        Example:
            >>> user = User(first_name='John', last_name='Doe')
            >>> print(user.get_full_name())  # "John Doe"
        """
        return f"{self.first_name} {self.last_name}"

    def to_dict(self, exclude: Optional[list] = None) -> dict:
        """
        Convert user to dictionary, automatically excluding password_hash.

        Args:
            exclude: Additional fields to exclude beyond password_hash

        Returns:
            Dictionary representation of user (without password)

        Example:
            >>> user = User.query.get(user_id)
            >>> user_dict = user.to_dict()
            >>> # password_hash is automatically excluded
        """
        exclude = exclude or []
        # Always exclude password_hash for security
        if 'password_hash' not in exclude:
            exclude.append('password_hash')

        return super().to_dict(exclude=exclude)

    def deactivate(self) -> None:
        """
        Deactivate user account.

        Sets is_active to False, preventing login.
        Soft delete - preserves user data and associations.

        Example:
            >>> user = User.query.get(user_id)
            >>> user.deactivate()
            >>> db.session.commit()
        """
        self.is_active = False
        logger.info(f"User deactivated: {self.email}")

    def activate(self) -> None:
        """
        Reactivate user account.

        Sets is_active to True, allowing login.

        Example:
            >>> user = User.query.get(user_id)
            >>> user.activate()
            >>> db.session.commit()
        """
        self.is_active = True
        logger.info(f"User activated: {self.email}")

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User {self.email} (id={self.id})>"

    @classmethod
    def find_by_email(cls, email: str) -> Optional['User']:
        """
        Find user by email address.

        Args:
            email: Email address to search for

        Returns:
            User object if found, None otherwise

        Example:
            >>> user = User.find_by_email('john.doe@example.com')
            >>> if user:
            ...     print(f'Found user: {user.get_full_name()}')
        """
        return cls.query.filter_by(email=email.lower()).first()

    @classmethod
    def find_active_by_email(cls, email: str) -> Optional['User']:
        """
        Find active user by email address.

        Args:
            email: Email address to search for

        Returns:
            User object if found and active, None otherwise

        Example:
            >>> user = User.find_active_by_email('john.doe@example.com')
            >>> if user:
            ...     print('User found and is active')
        """
        return cls.query.filter_by(email=email.lower(), is_active=True).first()

    def before_insert(self):
        """
        Hook called before inserting new user.

        Normalizes email to lowercase.
        """
        if self.email:
            self.email = self.email.lower()
        logger.info(f"Creating new user: {self.email}")

    def before_update(self):
        """
        Hook called before updating user.

        Normalizes email to lowercase if changed.
        """
        if self.email:
            self.email = self.email.lower()
        logger.debug(f"Updating user: {self.email}")
