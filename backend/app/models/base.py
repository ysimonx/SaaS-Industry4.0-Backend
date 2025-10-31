"""
Base model with common fields for all database models.

Provides UUID primary keys, automatic timestamps, and audit trail support.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from typing import Dict, Any, Optional


class BaseModel:
    """
    Abstract base model with common fields for all models.

    Provides:
    - UUID primary key (id)
    - Automatic timestamps (created_at, updated_at)
    - Audit trail (created_by)
    - Serialization helpers (to_dict)
    - String representation (__repr__)

    Usage:
        class User(BaseModel, db.Model):
            __tablename__ = 'users'
            email = Column(String(255), unique=True, nullable=False)
    """

    @declared_attr
    def __tablename__(cls):
        """
        Generate table name from class name if not explicitly set.

        Converts CamelCase to snake_case and pluralizes.
        Override in child class if custom table name needed.
        """
        # This will be overridden in child classes
        return cls.__name__.lower() + 's'

    # Primary key (UUID)
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Unique identifier for the record"
    )

    # Timestamp fields
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Timestamp when record was created (UTC)"
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Timestamp when record was last updated (UTC)"
    )

    # Audit trail - who created this record
    # Nullable to allow self-registration and system-generated records
    created_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID of user who created this record (nullable for self-registration)"
    )

    def to_dict(self, exclude: Optional[list] = None) -> Dict[str, Any]:
        """
        Convert model instance to dictionary for JSON serialization.

        Args:
            exclude: List of field names to exclude from output

        Returns:
            Dictionary representation of the model

        Example:
            >>> user = User(email='test@example.com', first_name='John')
            >>> user.to_dict(exclude=['password_hash'])
            {
                'id': '123e4567-e89b-12d3-a456-426614174000',
                'email': 'test@example.com',
                'first_name': 'John',
                'created_at': '2024-01-01T00:00:00+00:00',
                'updated_at': '2024-01-01T00:00:00+00:00'
            }
        """
        exclude = exclude or []
        result = {}

        # Get all columns from the model
        for column in self.__table__.columns:
            field_name = column.name

            # Skip excluded fields
            if field_name in exclude:
                continue

            value = getattr(self, field_name, None)

            # Convert datetime to ISO format string
            if isinstance(value, datetime):
                result[field_name] = value.isoformat()
            # Convert UUID to string
            elif isinstance(value, uuid.UUID):
                result[field_name] = str(value)
            # Keep other values as-is
            else:
                result[field_name] = value

        return result

    def update_from_dict(self, data: Dict[str, Any], allowed_fields: Optional[list] = None):
        """
        Update model fields from dictionary.

        Only updates fields that exist in the model and are in allowed_fields list.
        Useful for bulk updates from API requests.

        Args:
            data: Dictionary with field names and values
            allowed_fields: List of field names that are allowed to be updated
                          If None, all fields except primary key and timestamps are allowed

        Example:
            >>> user = User.query.get(user_id)
            >>> user.update_from_dict(
            ...     {'first_name': 'Jane', 'email': 'jane@example.com'},
            ...     allowed_fields=['first_name', 'last_name']
            ... )
            >>> db.session.commit()
        """
        # Default allowed fields: all columns except id and timestamps
        if allowed_fields is None:
            forbidden_fields = {'id', 'created_at', 'updated_at', 'created_by'}
            allowed_fields = [
                col.name for col in self.__table__.columns
                if col.name not in forbidden_fields
            ]

        # Update only allowed fields that exist in data
        for field_name, value in data.items():
            if field_name in allowed_fields and hasattr(self, field_name):
                setattr(self, field_name, value)

    def __repr__(self) -> str:
        """
        String representation of the model for debugging.

        Returns:
            String showing model class name and ID

        Example:
            >>> user = User(id='123e4567-e89b-12d3-a456-426614174000')
            >>> repr(user)
            '<User id=123e4567-e89b-12d3-a456-426614174000>'
        """
        return f"<{self.__class__.__name__} id={self.id}>"

    def __str__(self) -> str:
        """
        Human-readable string representation.

        Returns:
            String showing model class name and ID
        """
        return self.__repr__()

    @classmethod
    def get_table_name(cls) -> str:
        """
        Get the table name for this model.

        Returns:
            Table name as string

        Example:
            >>> User.get_table_name()
            'users'
        """
        return cls.__tablename__

    @classmethod
    def get_column_names(cls) -> list:
        """
        Get list of all column names for this model.

        Returns:
            List of column names

        Example:
            >>> User.get_column_names()
            ['id', 'email', 'first_name', 'last_name', 'created_at', 'updated_at']
        """
        return [column.name for column in cls.__table__.columns]

    def before_insert(self):
        """
        Hook called before inserting a new record.

        Override in child classes to add custom logic before insert.
        Called automatically by SQLAlchemy event listeners.
        """
        pass

    def before_update(self):
        """
        Hook called before updating a record.

        Override in child classes to add custom logic before update.
        Called automatically by SQLAlchemy event listeners.
        """
        pass

    def after_insert(self):
        """
        Hook called after inserting a new record.

        Override in child classes to add custom logic after insert.
        Called automatically by SQLAlchemy event listeners.
        """
        pass

    def after_update(self):
        """
        Hook called after updating a record.

        Override in child classes to add custom logic after update.
        Called automatically by SQLAlchemy event listeners.
        """
        pass


# Helper function to register event listeners
def register_base_model_events(db):
    """
    Register SQLAlchemy event listeners for BaseModel lifecycle hooks.

    This should be called during application initialization to enable
    before_insert, before_update, after_insert, after_update hooks.

    Args:
        db: SQLAlchemy database instance

    Example:
        >>> from app import db
        >>> from app.models.base import register_base_model_events
        >>> register_base_model_events(db)
    """
    from sqlalchemy import event

    @event.listens_for(db.session, 'before_flush')
    def receive_before_flush(session, flush_context, instances):
        """Call before_insert and before_update hooks."""
        for instance in session.new:
            if isinstance(instance, BaseModel):
                instance.before_insert()

        for instance in session.dirty:
            if isinstance(instance, BaseModel):
                instance.before_update()

    @event.listens_for(db.session, 'after_flush')
    def receive_after_flush(session, flush_context):
        """Call after_insert and after_update hooks."""
        # Note: We store instances during before_flush to track them
        # This is a simplified version; production code might need more sophistication
        for instance in session.identity_map.values():
            if isinstance(instance, BaseModel):
                # Check if it was recently inserted or updated
                # This is a basic implementation
                if instance in session.new:
                    instance.after_insert()
                elif instance in session.dirty:
                    instance.after_update()
