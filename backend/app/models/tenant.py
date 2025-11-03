"""
Tenant Model

This module defines the Tenant model for the multi-tenant SaaS platform.
Each tenant represents an isolated organization with its own PostgreSQL database.

Key features:
- Stores tenant metadata in the main database
- Each tenant has an isolated PostgreSQL database for Documents/Files
- Automatic database name generation from tenant name
- Database lifecycle management (create, drop)
- User association management via UserTenantAssociation
- Soft delete support (is_active flag)

Storage strategy:
- Tenant metadata: stored in main database (saas_platform)
- Tenant data: stored in isolated database (e.g., tenant_acme_corp_a1b2c3d4)
"""

import re
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Boolean, Index
from sqlalchemy.orm import relationship

from .base import BaseModel
from ..extensions import db
from ..utils.database import tenant_db_manager

logger = logging.getLogger(__name__)


class Tenant(BaseModel, db.Model):
    """
    Tenant model representing an organization in the multi-tenant system.

    Each tenant gets:
    1. A record in the main database (this table)
    2. An isolated PostgreSQL database for their documents and files
    3. At least one admin user (creator)

    Attributes:
        name (str): Human-readable tenant name (e.g., "Acme Corporation")
        database_name (str): PostgreSQL database name (e.g., "tenant_acme_corp_a1b2c3d4")
        is_active (bool): Soft delete flag - False means tenant is deactivated

    Relationships:
        user_associations: Many-to-many with User via UserTenantAssociation

    Inherited from BaseModel:
        id (UUID): Primary key
        created_at (datetime): Creation timestamp (UTC)
        updated_at (datetime): Last update timestamp (UTC)
        created_by (UUID): User who created this tenant
    """

    __tablename__ = 'tenants'
    # No __bind_key__ needed - uses default (main) database

    # Fields
    name = db.Column(String(255), nullable=False)
    database_name = db.Column(String(63), unique=True, nullable=False, index=True)
    is_active = db.Column(Boolean, default=True, nullable=False)

    # Relationships
    user_associations = relationship(
        'UserTenantAssociation',
        back_populates='tenant',
        cascade='all, delete-orphan'
    )

    # Indexes for common queries
    __table_args__ = (
        Index('ix_tenants_name_active', 'name', 'is_active'),
        Index('ix_tenants_database_name', 'database_name', unique=True),
    )

    def __init__(self, **kwargs):
        """
        Initialize a new tenant.

        If database_name is not provided, it will be auto-generated from the name.
        """
        # Auto-generate database_name if not provided
        if 'database_name' not in kwargs and 'name' in kwargs:
            kwargs['database_name'] = self._generate_database_name(kwargs['name'])

        super().__init__(**kwargs)
        logger.info(f"Tenant object initialized: name={self.name}, database_name={self.database_name}")

    @staticmethod
    def _generate_database_name(tenant_name: str) -> str:
        """
        Generate a unique PostgreSQL-compatible database name from tenant name.

        Rules:
        - Prefix with "tenant_"
        - Convert to lowercase
        - Replace spaces and special chars with underscores
        - Keep only alphanumeric and underscores
        - Append short UUID suffix for uniqueness
        - Max length: 63 characters (PostgreSQL limit)

        Args:
            tenant_name: Human-readable tenant name

        Returns:
            PostgreSQL-compatible database name

        Examples:
            "Acme Corporation" -> "tenant_acme_corporation_a1b2c3d4"
            "Test-Co (2024)" -> "tenant_test_co_2024_a1b2c3d4"
        """
        import uuid

        # Convert to lowercase and replace spaces with underscores
        name_slug = tenant_name.lower().strip()

        # Replace special characters with underscores
        name_slug = re.sub(r'[^\w\s-]', '_', name_slug)
        name_slug = re.sub(r'[-\s]+', '_', name_slug)

        # Remove consecutive underscores
        name_slug = re.sub(r'_+', '_', name_slug)

        # Remove leading/trailing underscores
        name_slug = name_slug.strip('_')

        # Generate short UUID suffix (8 chars)
        uuid_suffix = str(uuid.uuid4()).replace('-', '')[:8]

        # Construct database name with prefix
        database_name = f"tenant_{name_slug}_{uuid_suffix}"

        # PostgreSQL max identifier length is 63 characters
        if len(database_name) > 63:
            # Truncate the slug part to fit
            max_slug_length = 63 - len("tenant__") - len(uuid_suffix)
            name_slug = name_slug[:max_slug_length]
            database_name = f"tenant_{name_slug}_{uuid_suffix}"

        logger.debug(f"Generated database name: {tenant_name} -> {database_name}")
        return database_name

    def get_connection_string(self) -> str:
        """
        Generate the PostgreSQL connection string for this tenant's database.

        Returns:
            Connection URL string (e.g., "postgresql://user:pass@host:5432/tenant_db")
        """
        from flask import current_app

        # Get base connection URL from config
        base_url = current_app.config['SQLALCHEMY_DATABASE_URI']

        # Replace database name with tenant database name
        # Format: postgresql://user:pass@host:5432/dbname
        if '/' in base_url:
            base_without_db = base_url.rsplit('/', 1)[0]
            connection_string = f"{base_without_db}/{self.database_name}"
        else:
            logger.error(f"Invalid database URL format: {base_url}")
            raise ValueError("Invalid SQLALCHEMY_DATABASE_URI format")

        return connection_string

    def create_database(self) -> bool:
        """
        Create the isolated PostgreSQL database for this tenant.

        This method:
        1. Creates the PostgreSQL database
        2. Runs migrations to create Document and File tables
        3. Sets up proper permissions

        Returns:
            True if database was created successfully, False otherwise

        Raises:
            Exception: If database creation fails
        """
        logger.info(f"Creating database for tenant {self.id}: {self.database_name}")

        try:
            # Use the TenantDatabaseManager to create the database
            success = tenant_db_manager.create_tenant_database(self.database_name)

            if success:
                logger.info(f"Successfully created database: {self.database_name}")

                # Create Document and File tables in the tenant database
                tenant_db_manager.create_tenant_tables(self.database_name)
                logger.info(f"Successfully created tables in database: {self.database_name}")

                return True
            else:
                logger.error(f"Failed to create database: {self.database_name}")
                return False

        except Exception as e:
            logger.error(f"Error creating database for tenant {self.id}: {str(e)}", exc_info=True)
            raise

    def delete_database(self, confirm: bool = False) -> bool:
        """
        Drop the tenant's PostgreSQL database.

        WARNING: This is a destructive operation that permanently deletes all tenant data.
        Use with extreme caution!

        Args:
            confirm: Must be True to proceed with deletion (safety check)

        Returns:
            True if database was deleted successfully, False otherwise

        Raises:
            ValueError: If confirm is not True
            Exception: If database deletion fails
        """
        if not confirm:
            raise ValueError(
                "Database deletion requires explicit confirmation. "
                "Set confirm=True to proceed with this destructive operation."
            )

        logger.warning(f"DELETING database for tenant {self.id}: {self.database_name}")

        try:
            # Use the TenantDatabaseManager to drop the database
            success = tenant_db_manager.drop_tenant_database(self.database_name)

            if success:
                logger.warning(f"Successfully deleted database: {self.database_name}")
                return True
            else:
                logger.error(f"Failed to delete database: {self.database_name}")
                return False

        except Exception as e:
            logger.error(f"Error deleting database for tenant {self.id}: {str(e)}", exc_info=True)
            raise

    def database_exists(self) -> bool:
        """
        Check if the tenant's database exists.

        Returns:
            True if database exists, False otherwise
        """
        return tenant_db_manager.database_exists(self.database_name)

    def get_users(self) -> List:
        """
        Get all users associated with this tenant.

        Returns:
            List of dictionaries with user objects and their roles:
            [{'user': User, 'role': str, 'joined_at': datetime}, ...]
        """
        return [
            {
                'user': assoc.user,
                'role': assoc.role,
                'joined_at': assoc.joined_at
            }
            for assoc in self.user_associations
        ]

    def get_user_count(self) -> int:
        """
        Get the number of users in this tenant.

        Returns:
            Number of users associated with this tenant
        """
        return len(self.user_associations)

    def deactivate(self) -> None:
        """
        Soft delete this tenant by setting is_active = False.

        This preserves the tenant record and database for audit purposes.
        The database is not dropped.
        """
        logger.info(f"Deactivating tenant {self.id}: {self.name}")
        self.is_active = False
        db.session.commit()

    def activate(self) -> None:
        """
        Reactivate a deactivated tenant.
        """
        logger.info(f"Activating tenant {self.id}: {self.name}")
        self.is_active = True
        db.session.commit()

    def to_dict(self, exclude: List[str] = None, include_stats: bool = False) -> dict:
        """
        Convert tenant to dictionary for JSON serialization.

        Args:
            exclude: List of fields to exclude from output
            include_stats: If True, include user count and database status

        Returns:
            Dictionary representation of the tenant
        """
        data = super().to_dict(exclude=exclude)

        if include_stats:
            data['user_count'] = self.get_user_count()
            data['database_exists'] = self.database_exists()

        return data

    @classmethod
    def find_by_name(cls, name: str) -> Optional['Tenant']:
        """
        Find a tenant by exact name match.

        Args:
            name: Tenant name to search for

        Returns:
            Tenant object if found, None otherwise
        """
        return cls.query.filter_by(name=name).first()

    @classmethod
    def find_active_by_name(cls, name: str) -> Optional['Tenant']:
        """
        Find an active tenant by exact name match.

        Args:
            name: Tenant name to search for

        Returns:
            Active Tenant object if found, None otherwise
        """
        return cls.query.filter_by(name=name, is_active=True).first()

    @classmethod
    def find_by_database_name(cls, database_name: str) -> Optional['Tenant']:
        """
        Find a tenant by database name.

        Args:
            database_name: PostgreSQL database name

        Returns:
            Tenant object if found, None otherwise
        """
        return cls.query.filter_by(database_name=database_name).first()

    @classmethod
    def get_all_active(cls) -> List['Tenant']:
        """
        Get all active tenants.

        Returns:
            List of active Tenant objects
        """
        return cls.query.filter_by(is_active=True).order_by(cls.created_at.desc()).all()

    def before_insert(self) -> None:
        """
        Lifecycle hook called before inserting a new tenant.

        Validates that:
        - Tenant name is not empty
        - Database name is valid and unique
        """
        super().before_insert()

        # Validate name
        if not self.name or not self.name.strip():
            raise ValueError("Tenant name cannot be empty")

        # Validate database name format
        if not re.match(r'^[a-z0-9_]+$', self.database_name):
            raise ValueError(
                f"Invalid database name: {self.database_name}. "
                "Must contain only lowercase letters, numbers, and underscores."
            )

        # Check database name uniqueness
        existing = Tenant.find_by_database_name(self.database_name)
        if existing:
            raise ValueError(f"Database name already exists: {self.database_name}")

        logger.debug(f"Tenant pre-insert validation passed: {self.name}")

    def before_update(self) -> None:
        """
        Lifecycle hook called before updating a tenant.

        Prevents changing the database_name after creation.
        """
        super().before_update()

        # Prevent database name changes
        if db.session.is_modified(self, include_collections=False):
            changes = db.session.dirty
            if self in changes:
                history = db.inspect(self).attrs.database_name.history
                if history.has_changes():
                    raise ValueError(
                        "Cannot change database_name after tenant creation. "
                        "Create a new tenant instead."
                    )

        logger.debug(f"Tenant pre-update validation passed: {self.name}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Tenant(id={self.id}, name='{self.name}', database='{self.database_name}', active={self.is_active})>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "active" if self.is_active else "inactive"
        return f"Tenant '{self.name}' ({status})"
