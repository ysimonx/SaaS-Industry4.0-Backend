"""
User Azure Identity Schema

Marshmallow schemas for UserAzureIdentity model validation and serialization.
"""

from marshmallow import Schema, fields, validate, validates, ValidationError
import re


class UserAzureIdentitySchema(Schema):
    """
    Schema for UserAzureIdentity model.
    """
    id = fields.UUID(dump_only=True)
    user_id = fields.UUID(required=True)
    tenant_id = fields.UUID(required=True)

    # Azure AD identifiers
    azure_object_id = fields.String(
        required=True,
        error_messages={'required': 'Azure Object ID is required'}
    )
    azure_tenant_id = fields.String(
        required=True,
        error_messages={'required': 'Azure Tenant ID is required'}
    )
    azure_upn = fields.String(allow_none=True)
    azure_display_name = fields.String(allow_none=True)

    # Token expiration info (never expose actual tokens)
    token_expires_at = fields.DateTime(dump_only=True, format='iso', allow_none=True)
    refresh_token_expires_at = fields.DateTime(dump_only=True, format='iso', allow_none=True)

    # Status fields
    last_sync = fields.DateTime(dump_only=True, format='iso')
    created_at = fields.DateTime(dump_only=True, format='iso')
    updated_at = fields.DateTime(dump_only=True, format='iso')

    # Computed fields
    access_token_expired = fields.Boolean(dump_only=True)
    refresh_token_expired = fields.Boolean(dump_only=True)
    needs_refresh = fields.Boolean(dump_only=True)

    @validates('azure_object_id')
    def validate_azure_object_id(self, value):
        """
        Validate Azure Object ID format (should be a GUID).
        """
        guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

        if not re.match(guid_pattern, value):
            raise ValidationError('Invalid Azure Object ID format. Must be a GUID.')

    @validates('azure_tenant_id')
    def validate_azure_tenant_id(self, value):
        """
        Validate Azure Tenant ID format (GUID).
        """
        guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

        if not re.match(guid_pattern, value):
            raise ValidationError('Invalid Azure Tenant ID format. Must be a GUID.')

    @validates('azure_upn')
    def validate_azure_upn(self, value):
        """
        Validate UPN format if provided.
        """
        if value:
            # Basic email validation
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, value):
                raise ValidationError('Invalid UPN format. Must be a valid email address.')


class UserAzureIdentityCreateSchema(UserAzureIdentitySchema):
    """
    Schema for creating a new Azure identity (usually done automatically during SSO).
    """
    class Meta:
        exclude = ('id', 'created_at', 'updated_at', 'token_expires_at',
                  'refresh_token_expires_at', 'access_token_expired',
                  'refresh_token_expired', 'needs_refresh')


class UserAzureIdentityUpdateSchema(Schema):
    """
    Schema for updating an existing Azure identity.
    """
    azure_upn = fields.String(allow_none=True)
    azure_display_name = fields.String(allow_none=True)

    @validates('azure_upn')
    def validate_azure_upn(self, value):
        """
        Validate UPN format if provided.
        """
        if value:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, value):
                raise ValidationError('Invalid UPN format. Must be a valid email address.')


class UserAzureIdentityListSchema(Schema):
    """
    Schema for listing user's Azure identities.
    """
    tenant_id = fields.UUID(required=True)
    tenant_name = fields.String(dump_only=True)
    azure_tenant_id = fields.String(required=True)
    azure_object_id = fields.String(required=True)
    azure_upn = fields.String(allow_none=True)
    last_sync = fields.DateTime(format='iso', allow_none=True)
    token_expired = fields.Boolean(dump_only=True)


class AzureTokenRefreshRequestSchema(Schema):
    """
    Schema for Azure token refresh request.
    """
    tenant_id = fields.UUID(
        required=True,
        error_messages={'required': 'Tenant ID is required for token refresh'}
    )


class AzureTokenRefreshResponseSchema(Schema):
    """
    Schema for Azure token refresh response.
    """
    access_token = fields.String(required=True)
    expires_in = fields.Integer(required=True)