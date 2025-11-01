"""
User Schemas for Data Validation and Serialization

This module defines Marshmallow schemas for User model validation and serialization.

Schemas:
- UserSchema: Base schema with all fields
- UserCreateSchema: For user registration (includes password)
- UserUpdateSchema: For profile updates (no password)
- UserResponseSchema: For API responses (excludes sensitive data)
"""

from marshmallow import Schema, fields, validate, validates, ValidationError, post_load
import re


class UserSchema(Schema):
    """
    Base User schema with all fields.

    This is the foundation schema that defines all User model fields.
    Other schemas inherit from this and customize for specific use cases.
    """
    id = fields.UUID(dump_only=True)
    first_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100, error="First name must be between 1 and 100 characters")
    )
    last_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100, error="Last name must be between 1 and 100 characters")
    )
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255, error="Email must not exceed 255 characters")
    )
    password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=8, error="Password must be at least 8 characters")
    )
    is_active = fields.Boolean(load_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    created_by = fields.UUID(dump_only=True)

    @validates('first_name')
    def validate_first_name(self, value):
        """Validate first name is not empty or whitespace only."""
        if not value or not value.strip():
            raise ValidationError("First name cannot be empty or whitespace")

    @validates('last_name')
    def validate_last_name(self, value):
        """Validate last name is not empty or whitespace only."""
        if not value or not value.strip():
            raise ValidationError("Last name cannot be empty or whitespace")

    @validates('password')
    def validate_password(self, value):
        """
        Validate password meets security requirements.

        Requirements:
        - At least 8 characters
        - At least one letter
        - At least one number
        """
        if len(value) < 8:
            raise ValidationError("Password must be at least 8 characters")

        if not re.search(r'[a-zA-Z]', value):
            raise ValidationError("Password must contain at least one letter")

        if not re.search(r'\d', value):
            raise ValidationError("Password must contain at least one number")


class UserCreateSchema(Schema):
    """
    Schema for user registration.

    Used for POST /api/auth/register endpoint.
    Includes password field for initial account creation.
    """
    first_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100, error="First name must be between 1 and 100 characters")
    )
    last_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100, error="Last name must be between 1 and 100 characters")
    )
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255, error="Email must not exceed 255 characters")
    )
    password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=8, error="Password must be at least 8 characters")
    )

    @validates('first_name')
    def validate_first_name(self, value):
        """Validate first name is not empty or whitespace only."""
        if not value or not value.strip():
            raise ValidationError("First name cannot be empty or whitespace")

    @validates('last_name')
    def validate_last_name(self, value):
        """Validate last name is not empty or whitespace only."""
        if not value or not value.strip():
            raise ValidationError("Last name cannot be empty or whitespace")

    @validates('email')
    def validate_email_format(self, value):
        """Additional email validation beyond the Email field validator."""
        # Email field already validates format, this is for additional checks
        if not value or not value.strip():
            raise ValidationError("Email cannot be empty or whitespace")

        # Convert to lowercase for consistency
        return value.lower()

    @validates('password')
    def validate_password(self, value):
        """
        Validate password meets security requirements.

        Requirements:
        - At least 8 characters
        - At least one letter
        - At least one number
        """
        if len(value) < 8:
            raise ValidationError("Password must be at least 8 characters")

        if not re.search(r'[a-zA-Z]', value):
            raise ValidationError("Password must contain at least one letter")

        if not re.search(r'\d', value):
            raise ValidationError("Password must contain at least one number")

    @post_load
    def normalize_data(self, data, **kwargs):
        """Normalize user data before returning."""
        # Strip whitespace from names
        if 'first_name' in data:
            data['first_name'] = data['first_name'].strip()
        if 'last_name' in data:
            data['last_name'] = data['last_name'].strip()
        # Normalize email to lowercase
        if 'email' in data:
            data['email'] = data['email'].lower().strip()
        return data


class UserUpdateSchema(Schema):
    """
    Schema for updating user profile.

    Used for PUT /api/users/me endpoint.
    Excludes password and email (email is immutable after registration).
    All fields are optional for partial updates.
    """
    first_name = fields.Str(
        validate=validate.Length(min=1, max=100, error="First name must be between 1 and 100 characters")
    )
    last_name = fields.Str(
        validate=validate.Length(min=1, max=100, error="Last name must be between 1 and 100 characters")
    )

    @validates('first_name')
    def validate_first_name(self, value):
        """Validate first name is not empty or whitespace only."""
        if value is not None and (not value or not value.strip()):
            raise ValidationError("First name cannot be empty or whitespace")

    @validates('last_name')
    def validate_last_name(self, value):
        """Validate last name is not empty or whitespace only."""
        if value is not None and (not value or not value.strip()):
            raise ValidationError("Last name cannot be empty or whitespace")

    @post_load
    def normalize_data(self, data, **kwargs):
        """Normalize user data before returning."""
        # Strip whitespace from names
        if 'first_name' in data:
            data['first_name'] = data['first_name'].strip()
        if 'last_name' in data:
            data['last_name'] = data['last_name'].strip()
        return data


class UserResponseSchema(Schema):
    """
    Schema for user data in API responses.

    Used for returning user data in API responses.
    Excludes all sensitive data (password_hash, etc.).
    All fields are read-only (dump_only).
    """
    id = fields.UUID(dump_only=True)
    first_name = fields.Str(dump_only=True)
    last_name = fields.Str(dump_only=True)
    email = fields.Email(dump_only=True)
    is_active = fields.Boolean(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class UserLoginSchema(Schema):
    """
    Schema for user login.

    Used for POST /api/auth/login endpoint.
    Simple schema with just email and password.
    """
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255, error="Email must not exceed 255 characters")
    )
    password = fields.Str(
        required=True,
        load_only=True
    )

    @validates('email')
    def validate_email_format(self, value):
        """Validate email is not empty."""
        if not value or not value.strip():
            raise ValidationError("Email cannot be empty or whitespace")

    @validates('password')
    def validate_password_present(self, value):
        """Validate password is provided."""
        if not value:
            raise ValidationError("Password is required")

    @post_load
    def normalize_data(self, data, **kwargs):
        """Normalize login data before returning."""
        # Normalize email to lowercase
        if 'email' in data:
            data['email'] = data['email'].lower().strip()
        return data


# Instantiate schemas for easy import
user_schema = UserSchema()
user_create_schema = UserCreateSchema()
user_update_schema = UserUpdateSchema()
user_response_schema = UserResponseSchema()
user_login_schema = UserLoginSchema()

# For serializing multiple users
users_response_schema = UserResponseSchema(many=True)
