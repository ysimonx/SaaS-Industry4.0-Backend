"""
SSO Configuration Routes

This module provides API endpoints for managing tenant SSO configurations.
Only tenant admins can manage SSO settings for their tenant.
"""

import logging
from flask import Blueprint, request, jsonify, current_app, g

from app.models import Tenant, TenantSSOConfig
from app.services.tenant_sso_config_service import TenantSSOConfigService
from app.utils.decorators import jwt_required_custom, tenant_required, role_required
from app.extensions import db

logger = logging.getLogger(__name__)

bp = Blueprint('sso_config', __name__, url_prefix='/api/tenants')


@bp.route('/<string:tenant_id>/sso/config', methods=['GET'])
@jwt_required_custom
@tenant_required()
@role_required(['admin', 'user'])
def get_sso_config(tenant_id):
    """
    Get SSO configuration for a tenant.

    Returns:
        SSO configuration or 404 if not found
    """
    try:
        include_stats = request.args.get('include_stats', 'false').lower() == 'true'
        config = TenantSSOConfigService.get_sso_config(tenant_id, include_stats=include_stats)

        if not config:
            return jsonify({'error': 'No SSO configuration found'}), 404

        return jsonify(config), 200

    except Exception as e:
        logger.error(f"Error getting SSO config: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config', methods=['POST'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def create_sso_config(tenant_id):
    """
    Create SSO configuration for a tenant.

    Request body:
        {
            "client_id": "azure-app-client-id",
            "provider_tenant_id": "azure-tenant-id-or-domain",
            "enable": false,
            "config_metadata": {
                "auto_provisioning": {
                    "enabled": false,
                    "default_role": "viewer",
                    "allowed_email_domains": ["@company.com"]
                }
            }
        }

    Returns:
        Created SSO configuration
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['client_id', 'provider_tenant_id']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400

        # Create SSO configuration
        sso_config = TenantSSOConfigService.create_sso_config(
            tenant_id=tenant_id,
            client_id=data['client_id'],
            provider_tenant_id=data['provider_tenant_id'],
            config_metadata=data.get('config_metadata'),
            enable=data.get('enable', False)
        )

        return jsonify(sso_config.to_dict(include_urls=True)), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating SSO config: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config', methods=['PUT'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def update_sso_config(tenant_id):
    """
    Update SSO configuration for a tenant.

    Request body:
        {
            "client_id": "new-client-id",
            "provider_tenant_id": "new-tenant-id",
            "is_enabled": true,
            "config_metadata": {...}
        }

    Returns:
        Updated SSO configuration
    """
    try:
        data = request.get_json()

        # Update SSO configuration
        sso_config = TenantSSOConfigService.update_sso_config(
            tenant_id=tenant_id,
            updates=data
        )

        return jsonify(sso_config.to_dict(include_urls=True)), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error updating SSO config: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config', methods=['DELETE'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def delete_sso_config(tenant_id):
    """
    Delete SSO configuration for a tenant.

    Query params:
        force: Force deletion even if users have Azure identities

    Returns:
        Success message
    """
    try:
        force = request.args.get('force', 'false').lower() == 'true'

        success = TenantSSOConfigService.delete_sso_config(
            tenant_id=tenant_id,
            force=force
        )

        if success:
            return jsonify({'message': 'SSO configuration deleted successfully'}), 200
        else:
            return jsonify({'error': 'Failed to delete SSO configuration'}), 500

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error deleting SSO config: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config/enable', methods=['POST'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def enable_sso(tenant_id):
    """
    Enable SSO for a tenant.

    Request body:
        {
            "auth_method": "both"  // or "sso"
        }

    Returns:
        Updated SSO configuration
    """
    try:
        data = request.get_json()
        auth_method = data.get('auth_method', 'both')

        sso_config = TenantSSOConfigService.enable_sso(
            tenant_id=tenant_id,
            auth_method=auth_method
        )

        return jsonify(sso_config.to_dict(include_urls=True)), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error enabling SSO: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config/disable', methods=['POST'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def disable_sso(tenant_id):
    """
    Disable SSO for a tenant.

    Request body:
        {
            "keep_azure_identities": true
        }

    Returns:
        Updated SSO configuration
    """
    try:
        data = request.get_json() or {}
        keep_azure_identities = data.get('keep_azure_identities', True)

        sso_config = TenantSSOConfigService.disable_sso(
            tenant_id=tenant_id,
            keep_azure_identities=keep_azure_identities
        )

        return jsonify(sso_config.to_dict()), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error disabling SSO: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config/validate', methods=['GET'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def validate_sso_config(tenant_id):
    """
    Validate SSO configuration and test Azure AD connectivity.

    Returns:
        Validation result with Azure AD endpoints
    """
    try:
        validation_result = TenantSSOConfigService.validate_sso_config(tenant_id)
        return jsonify(validation_result), 200

    except Exception as e:
        logger.error(f"Error validating SSO config: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/config/auto-provisioning', methods=['PUT'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def update_auto_provisioning(tenant_id):
    """
    Update auto-provisioning settings for a tenant.

    Request body:
        {
            "enabled": true,
            "default_role": "viewer",
            "sync_attributes_on_login": true,
            "allowed_email_domains": ["@company.com"],
            "allowed_azure_groups": ["All-Employees"],
            "group_role_mapping": {
                "IT-Admins": "admin",
                "Developers": "user"
            }
        }

    Returns:
        Updated SSO configuration
    """
    try:
        data = request.get_json()

        sso_config = TenantSSOConfigService.update_auto_provisioning(
            tenant_id=tenant_id,
            auto_provisioning_config=data
        )

        return jsonify(sso_config.to_dict()), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error updating auto-provisioning: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/<string:tenant_id>/sso/statistics', methods=['GET'])
@jwt_required_custom
@tenant_required()
@role_required(['admin'])
def get_sso_statistics(tenant_id):
    """
    Get detailed SSO usage statistics for a tenant.

    Returns:
        SSO usage statistics
    """
    try:
        stats = TenantSSOConfigService.get_sso_statistics(tenant_id)
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error getting SSO statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/sso/configs', methods=['GET'])
@jwt_required_custom
def get_all_sso_configs():
    """
    Get all SSO configurations (super admin only).

    Query params:
        only_enabled: Only return enabled configurations

    Returns:
        List of SSO configurations
    """
    try:
        # Check if user is super admin (you may need to implement this)
        current_user_id = g.user_id
        # TODO: Implement super admin check
        # if not is_super_admin(current_user_id):
        #     return jsonify({'error': 'Unauthorized'}), 403

        only_enabled = request.args.get('only_enabled', 'false').lower() == 'true'
        configs = TenantSSOConfigService.get_all_sso_configs(only_enabled=only_enabled)

        return jsonify({'configurations': configs}), 200

    except Exception as e:
        logger.error(f"Error getting all SSO configs: {str(e)}")
        return jsonify({'error': str(e)}), 500