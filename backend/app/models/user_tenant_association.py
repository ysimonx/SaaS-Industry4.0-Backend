"""
UserTenantAssociation Model

This module defines the association model between Users and Tenants with role-based access control.
This is a many-to-many relationship table that stores which users belong to which tenants and their roles.

Key features:
- Composite primary key (user_id, tenant_id) prevents duplicate associations
- Role-based access control with three predefined roles: admin, user, viewer
- Automatic timestamp when user joins tenant (joined_at)
- Cascading deletes when user or tenant is removed
- Bidirectional relationships to User and Tenant models

Storage:
- Stored in main database (saas_platform)
- Links users to tenants with their assigned roles
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..extensions import db

logger = logging.getLogger(__name__)


class UserTenantAssociation(db.Model):
    """
    Association model linking Users to Tenants with role-based access control.

    This model implements the many-to-many relationship between Users and Tenants,
    with additional role information for each association.

    Attributes:
        user_id (UUID): Foreign key to users.id (part of composite primary key)
        tenant_id (UUID): Foreign key to tenants.id (part of composite primary key)
        role (str): User's role in the tenant ('admin', 'user', 'viewer')
        joined_at (datetime): UTC timestamp when user was added to tenant

    Relationships:
        user: Reference to User model
        tenant: Reference to Tenant model

    Roles:
        - admin: Full access - can manage tenant, users, and all resources
        - user: Standard access - can create/read/update/delete own resources
        - viewer: Read-only access - can only view resources

    Constraints:
        - Composite primary key (user_id, tenant_id) ensures uniqueness
        - Role must be one of: 'admin', 'user', 'viewer'
        - Cascading delete when user or tenant is removed
    """

    __tablename__ = 'user_tenant_associations'
    # No __bind_key__ needed - uses default (main) database

    # Composite Primary Key
    user_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
        nullable=False
    )
    tenant_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        primary_key=True,
        nullable=False
    )

    # Fields
    role = db.Column(String(50), nullable=False)
    joined_at = db.Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship('User', back_populates='tenant_associations')
    tenant = relationship('Tenant', back_populates='user_associations')

    # Indexes for common queries
    __table_args__ = (
        Index('ix_user_tenant_user_id', 'user_id'),
        Index('ix_user_tenant_tenant_id', 'tenant_id'),
        Index('ix_user_tenant_role', 'role'),
        CheckConstraint(
            "role IN ('admin', 'user', 'viewer')",
            name='valid_role_check'
        ),
    )

    # Valid roles (class constant)
    ROLE_ADMIN = 'admin'
    ROLE_USER = 'user'
    ROLE_VIEWER = 'viewer'
    VALID_ROLES = [ROLE_ADMIN, ROLE_USER, ROLE_VIEWER]

    def __init__(self, **kwargs):
        """
        Initialize a new user-tenant association.

        Args:
            user_id: UUID of the user
            tenant_id: UUID of the tenant
            role: Role to assign ('admin', 'user', or 'viewer')

        Raises:
            ValueError: If role is not valid
        """
        # Validate role before initialization
        if 'role' in kwargs:
            role = kwargs['role']
            if role not in self.VALID_ROLES:
                raise ValueError(
                    f"Invalid role: {role}. Must be one of: {', '.join(self.VALID_ROLES)}"
                )

        super().__init__(**kwargs)
        logger.info(
            f"UserTenantAssociation initialized: user_id={self.user_id}, "
            f"tenant_id={self.tenant_id}, role={self.role}"
        )

    @classmethod
    def create_association(cls, user_id, tenant_id, role):
        """
        Create a new user-tenant association.

        Args:
            user_id (UUID): User's unique identifier
            tenant_id (UUID): Tenant's unique identifier
            role (str): Role to assign ('admin', 'user', or 'viewer')

        Returns:
            UserTenantAssociation: The created association

        Raises:
            ValueError: If role is invalid or association already exists
        """
        # Validate role
        if role not in cls.VALID_ROLES:
            raise ValueError(
                f"Invalid role: {role}. Must be one of: {', '.join(cls.VALID_ROLES)}"
            )

        # Check if association already exists
        existing = cls.query.filter_by(user_id=user_id, tenant_id=tenant_id).first()
        if existing:
            raise ValueError(
                f"Association already exists for user {user_id} and tenant {tenant_id}"
            )

        # Create association
        association = cls(user_id=user_id, tenant_id=tenant_id, role=role)
        db.session.add(association)
        db.session.commit()

        logger.info(
            f"Created association: user_id={user_id}, tenant_id={tenant_id}, role={role}"
        )
        return association

    def update_role(self, new_role: str) -> None:
        """
        Update the user's role in the tenant.

        Args:
            new_role: New role to assign ('admin', 'user', or 'viewer')

        Raises:
            ValueError: If new_role is not valid
        """
        if new_role not in self.VALID_ROLES:
            raise ValueError(
                f"Invalid role: {new_role}. Must be one of: {', '.join(self.VALID_ROLES)}"
            )

        old_role = self.role
        self.role = new_role
        db.session.commit()

        logger.info(
            f"Updated role for user {self.user_id} in tenant {self.tenant_id}: "
            f"{old_role} -> {new_role}"
        )

    def is_admin(self) -> bool:
        """Check if this association has admin role."""
        return self.role == self.ROLE_ADMIN

    def is_user(self) -> bool:
        """Check if this association has user role."""
        return self.role == self.ROLE_USER

    def is_viewer(self) -> bool:
        """Check if this association has viewer role."""
        return self.role == self.ROLE_VIEWER

    def has_permission(self, required_role: str) -> bool:
        """
        Check if this association has at least the required role level.

        Role hierarchy: admin > user > viewer

        Args:
            required_role: Minimum required role

        Returns:
            True if user has sufficient permissions

        Examples:
            - Admin has permission for admin, user, and viewer roles
            - User has permission for user and viewer roles
            - Viewer only has permission for viewer role
        """
        role_hierarchy = {
            self.ROLE_ADMIN: 3,
            self.ROLE_USER: 2,
            self.ROLE_VIEWER: 1
        }

        current_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return current_level >= required_level

    def to_dict(self) -> dict:
        """
        Convert association to dictionary for JSON serialization.

        Returns:
            Dictionary with association details
        """
        return {
            'user_id': str(self.user_id),
            'tenant_id': str(self.tenant_id),
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None
        }

    @classmethod
    def find_by_user_and_tenant(cls, user_id, tenant_id) -> Optional['UserTenantAssociation']:
        """
        Find association by user and tenant IDs.

        Args:
            user_id: User's unique identifier
            tenant_id: Tenant's unique identifier

        Returns:
            UserTenantAssociation if found, None otherwise
        """
        return cls.query.filter_by(user_id=user_id, tenant_id=tenant_id).first()

    @classmethod
    def get_user_tenants(cls, user_id):
        """
        Get all tenants for a specific user with their roles.

        Args:
            user_id: User's unique identifier

        Returns:
            List of UserTenantAssociation objects
        """
        return cls.query.filter_by(user_id=user_id).all()

    @classmethod
    def get_tenant_users(cls, tenant_id):
        """
        Get all users in a specific tenant with their roles.

        Args:
            tenant_id: Tenant's unique identifier

        Returns:
            List of UserTenantAssociation objects
        """
        return cls.query.filter_by(tenant_id=tenant_id).all()

    @classmethod
    def get_tenant_admins(cls, tenant_id):
        """
        Get all admin users for a specific tenant.

        Args:
            tenant_id: Tenant's unique identifier

        Returns:
            List of UserTenantAssociation objects with admin role
        """
        return cls.query.filter_by(tenant_id=tenant_id, role=cls.ROLE_ADMIN).all()

    @classmethod
    def count_tenant_users(cls, tenant_id) -> int:
        """
        Count number of users in a tenant.

        Args:
            tenant_id: Tenant's unique identifier

        Returns:
            Number of users in the tenant
        """
        return cls.query.filter_by(tenant_id=tenant_id).count()

    @classmethod
    def count_user_tenants(cls, user_id) -> int:
        """
        Count number of tenants a user belongs to.

        Args:
            user_id: User's unique identifier

        Returns:
            Number of tenants the user belongs to
        """
        return cls.query.filter_by(user_id=user_id).count()

    @classmethod
    def user_has_access_to_tenant(cls, user_id, tenant_id) -> bool:
        """
        Check if a user has access to a specific tenant.

        Args:
            user_id: User's unique identifier
            tenant_id: Tenant's unique identifier

        Returns:
            True if user has access, False otherwise
        """
        association = cls.find_by_user_and_tenant(user_id, tenant_id)
        return association is not None

    @classmethod
    def get_user_role_in_tenant(cls, user_id, tenant_id) -> Optional[str]:
        """
        Get user's role in a specific tenant.

        Args:
            user_id: User's unique identifier
            tenant_id: Tenant's unique identifier

        Returns:
            Role string ('admin', 'user', 'viewer') or None if no access
        """
        association = cls.find_by_user_and_tenant(user_id, tenant_id)
        return association.role if association else None

    @classmethod
    def remove_association(cls, user_id, tenant_id) -> bool:
        """
        Remove a user-tenant association.

        Args:
            user_id: User's unique identifier
            tenant_id: Tenant's unique identifier

        Returns:
            True if association was removed, False if not found
        """
        association = cls.find_by_user_and_tenant(user_id, tenant_id)
        if association:
            db.session.delete(association)
            db.session.commit()
            logger.info(
                f"Removed association: user_id={user_id}, tenant_id={tenant_id}"
            )
            return True
        else:
            logger.warning(
                f"Association not found: user_id={user_id}, tenant_id={tenant_id}"
            )
            return False

    @classmethod
    def remove_all_user_associations(cls, user_id) -> int:
        """
        Remove all tenant associations for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            Number of associations removed
        """
        count = cls.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        logger.info(f"Removed {count} associations for user {user_id}")
        return count

    @classmethod
    def remove_all_tenant_associations(cls, tenant_id) -> int:
        """
        Remove all user associations for a tenant.

        Args:
            tenant_id: Tenant's unique identifier

        Returns:
            Number of associations removed
        """
        count = cls.query.filter_by(tenant_id=tenant_id).delete()
        db.session.commit()
        logger.info(f"Removed {count} associations for tenant {tenant_id}")
        return count

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<UserTenantAssociation(user_id={self.user_id}, "
            f"tenant_id={self.tenant_id}, role='{self.role}')>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"User {self.user_id} is {self.role} in tenant {self.tenant_id}"
