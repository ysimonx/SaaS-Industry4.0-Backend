"""
SSO Configuration Schema

Marshmallow schemas for TenantSSOConfig model validation and serialization.
"""

from marshmallow import Schema, fields, validate, validates, ValidationError, post_load
import re


class AutoProvisioningSchema(Schema):
    """
    Schema for auto-provisioning configuration within SSO config metadata.
    """
    enabled = fields.Boolean(required=False, load_default=False)
    default_role = fields.String(
        required=False,
        load_default='viewer',
        validate=validate.OneOf(['admin', 'user', 'viewer'])
    )
    sync_attributes_on_login = fields.Boolean(required=False, load_default=True)
    allowed_email_domains = fields.List(
        fields.String(),
        required=False,
        allow_none=True
    )
    allowed_azure_groups = fields.List(
        fields.String(),
        required=False,
        allow_none=True
    )
    group_role_mapping = fields.Dict(
        keys=fields.String(),
        values=fields.String(validate=validate.OneOf(['admin', 'user', 'viewer'])),
        required=False,
        allow_none=True
    )


class ConfigMetadataSchema(Schema):
    """
    Schema for SSO configuration metadata.
    """
    app_type = fields.String(
        required=False,
        load_default='public',
        validate=validate.Equal('public')
    )
    auto_provisioning = fields.Nested(
        AutoProvisioningSchema,
        required=False,
        allow_none=True
    )


class TenantSSOConfigSchema(Schema):
    """
    Schema for TenantSSOConfig model.
    """
    id = fields.UUID(dump_only=True)
    tenant_id = fields.UUID(required=True)
    provider_type = fields.String(
        required=False,
        load_default='azure_ad',
        validate=validate.OneOf(['azure_ad'])
    )
    provider_tenant_id = fields.String(
        required=True,
        error_messages={'required': 'Azure tenant ID or domain is required'}
    )
    client_id = fields.String(
        required=True,
        error_messages={'required': 'Azure Application (client) ID is required'}
    )
    redirect_uri = fields.String(dump_only=True)
    is_enabled = fields.Boolean(required=False, load_default=False)
    config_metadata = fields.Nested(
        ConfigMetadataSchema,
        required=False,
        allow_none=True
    )
    created_at = fields.DateTime(dump_only=True, format='iso')
    updated_at = fields.DateTime(dump_only=True, format='iso')

    # URLs (only included when requested)
    authority_url = fields.String(dump_only=True)
    authorization_url = fields.String(dump_only=True)
    token_url = fields.String(dump_only=True)
    logout_url = fields.String(dump_only=True)

    @validates('provider_tenant_id')
    def validate_provider_tenant_id(self, value):
        """
        Validate Azure tenant ID format (GUID or domain).
        """
        # Check if it's a valid GUID
        guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        # Check if it's a valid domain
        domain_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$'

        if not (re.match(guid_pattern, value) or re.match(domain_pattern, value)):
            raise ValidationError(
                'Invalid Azure tenant ID format. Must be a GUID or domain (e.g., contoso.onmicrosoft.com)'
            )

    @validates('client_id')
    def validate_client_id(self, value):
        """
        Validate Azure Application (client) ID format.
        """
        # Azure client IDs are usually GUIDs
        guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

        if not re.match(guid_pattern, value):
            raise ValidationError(
                'Invalid client ID format. Must be a valid Azure Application ID (GUID)'
            )

    @post_load
    def ensure_app_type(self, data, **kwargs):
        """
        Ensure app_type is always set to 'public' in config_metadata.
        """
        if 'config_metadata' not in data:
            data['config_metadata'] = {}
        data['config_metadata']['app_type'] = 'public'
        return data


class TenantSSOConfigCreateSchema(TenantSSOConfigSchema):
    """
    Schema for creating a new SSO configuration.
    """
    tenant_id = fields.UUID(required=False)  # Will be taken from URL parameter

    class Meta:
        exclude = ('id', 'redirect_uri', 'created_at', 'updated_at',
                  'authority_url', 'authorization_url', 'token_url', 'logout_url')


class TenantSSOConfigUpdateSchema(Schema):
    """
    Schema for updating an existing SSO configuration.
    """
    client_id = fields.String(required=False)
    provider_tenant_id = fields.String(required=False)
    is_enabled = fields.Boolean(required=False)
    config_metadata = fields.Nested(
        ConfigMetadataSchema,
        required=False,
        allow_none=True
    )

    @validates('provider_tenant_id')
    def validate_provider_tenant_id(self, value):
        """
        Validate Azure tenant ID format if provided.
        """
        if value:
            guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            domain_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$'

            if not (re.match(guid_pattern, value) or re.match(domain_pattern, value)):
                raise ValidationError(
                    'Invalid Azure tenant ID format. Must be a GUID or domain'
                )

    @validates('client_id')
    def validate_client_id(self, value):
        """
        Validate Azure Application (client) ID format if provided.
        """
        if value:
            guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

            if not re.match(guid_pattern, value):
                raise ValidationError(
                    'Invalid client ID format. Must be a valid Azure Application ID (GUID)'
                )


class SSOStatisticsSchema(Schema):
    """
    Schema for SSO usage statistics.
    """
    configuration = fields.Dict(dump_only=True)
    usage = fields.Dict(dump_only=True)
    recent_logins = fields.List(fields.Dict(), dump_only=True)


class SSOAvailabilitySchema(Schema):
    """
    Schema for SSO availability check response.
    """
    available = fields.Boolean(required=True)
    auth_method = fields.String(allow_none=True)
    provider = fields.String(allow_none=True)
    auto_provisioning = fields.Boolean(allow_none=True)
    error = fields.String(allow_none=True)
    message = fields.String(allow_none=True)