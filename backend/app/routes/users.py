"""
Users Blueprint - User Profile Management Routes

This module provides REST API endpoints for user profile operations:
- GET /api/users/me - Get current user profile
- PUT /api/users/me - Update current user profile
- GET /api/users/me/tenants - Get user's tenants with roles

All endpoints require JWT authentication.
"""

import logging
from flask import Blueprint, request, g
from marshmallow import ValidationError

from app.extensions import db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation
from app.models.user_azure_identity import UserAzureIdentity
from app.schemas.user_schema import user_update_schema, user_response_schema
from app.schemas.tenant_schema import tenants_response_schema
from app.utils.responses import ok, bad_request, not_found, internal_error
from app.utils.decorators import jwt_required_custom

logger = logging.getLogger(__name__)

# Create blueprint
users_bp = Blueprint('users', __name__, url_prefix='/api/users')


@users_bp.route('/me', methods=['GET'])
@jwt_required_custom
def get_current_user():
    """
    Get current user profile

    Returns the authenticated user's profile information.

    **Authentication**: JWT required

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "User profile retrieved successfully",
                "data": {
                    "id": "uuid",
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "is_active": true,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z"
                }
            }

        404 Not Found: User not found
        500 Internal Server Error: Server error

    **Example**:
        GET /api/users/me
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Fetching profile for user_id={user_id}")

        # Fetch user from database
        user = User.query.filter_by(id=user_id).first()

        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return not_found('User not found')

        # Serialize user data (excludes password_hash automatically)
        user_data = user_response_schema.dump(user)

        logger.info(f"User profile retrieved successfully: user_id={user_id}")
        return ok(user_data, 'User profile retrieved successfully')

    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}", exc_info=True)
        return internal_error('Failed to fetch user profile')


@users_bp.route('/me', methods=['PUT'])
@jwt_required_custom
def update_current_user():
    """
    Update current user profile

    Updates the authenticated user's profile information.
    Only first_name and last_name can be updated.
    Email is immutable.

    **Authentication**: JWT required

    **Request Body**:
        {
            "first_name": "Jane",      // Optional
            "last_name": "Smith"       // Optional
        }

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "User profile updated successfully",
                "data": {
                    "id": "uuid",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "email": "john@example.com",
                    "is_active": true,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z"
                }
            }

        400 Bad Request: Validation error
        404 Not Found: User not found
        500 Internal Server Error: Server error

    **Example**:
        PUT /api/users/me
        Authorization: Bearer <access_token>
        Content-Type: application/json

        {
            "first_name": "Jane",
            "last_name": "Smith"
        }
    """
    try:
        user_id = g.user_id
        logger.info(f"Updating profile for user_id={user_id}")

        # Get request data
        data = request.get_json()

        if not data:
            logger.warning("Empty request body")
            return bad_request('Request body is required')

        # Validate input data
        try:
            validated_data = user_update_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        # Fetch user from database
        user = User.query.filter_by(id=user_id).first()

        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return not_found('User not found')

        # Update user fields
        if 'first_name' in validated_data:
            user.first_name = validated_data['first_name']

        if 'last_name' in validated_data:
            user.last_name = validated_data['last_name']

        # Commit changes
        db.session.commit()

        # Serialize updated user data
        user_data = user_response_schema.dump(user)

        logger.info(f"User profile updated successfully: user_id={user_id}")
        return ok(user_data, 'User profile updated successfully')

    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to update user profile')


@users_bp.route('/me/tenants', methods=['GET'])
@jwt_required_custom
def get_current_user_tenants():
    """
    Get current user's tenants with roles

    Returns a list of all tenants the authenticated user has access to,
    along with their role in each tenant.

    **Authentication**: JWT required

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "User tenants retrieved successfully",
                "data": [
                    {
                        "id": "uuid",
                        "name": "Acme Corp",
                        "database_name": "tenant_acme_corp_a1b2c3d4",
                        "is_active": true,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                        "role": "admin",                    // User's role in this tenant
                        "joined_at": "2024-01-01T00:00:00Z" // When user joined tenant
                    }
                ]
            }

        404 Not Found: User not found
        500 Internal Server Error: Server error

    **Example**:
        GET /api/users/me/tenants
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Fetching tenants for user_id={user_id}")

        # Fetch user from database
        user = User.query.filter_by(id=user_id).first()

        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return not_found('User not found')

        # Get user's tenant associations with roles
        # Join UserTenantAssociation -> Tenant to get tenant details
        associations = (
            db.session.query(UserTenantAssociation, Tenant)
            .join(Tenant, UserTenantAssociation.tenant_id == Tenant.id)
            .filter(UserTenantAssociation.user_id == user_id)
            .filter(Tenant.is_active == True)  # Only active tenants
            .order_by(UserTenantAssociation.joined_at.desc())
            .all()
        )

        # Build response with tenant details + user's role
        tenants_with_roles = []
        for association, tenant in associations:
            tenant_dict = tenant.to_dict()
            tenant_dict['role'] = association.role
            tenant_dict['joined_at'] = association.joined_at.isoformat() if association.joined_at else None
            tenants_with_roles.append(tenant_dict)

        logger.info(f"Retrieved {len(tenants_with_roles)} tenants for user_id={user_id}")
        return ok(tenants_with_roles, 'User tenants retrieved successfully')

    except Exception as e:
        logger.error(f"Error fetching user tenants: {str(e)}", exc_info=True)
        return internal_error('Failed to fetch user tenants')


@users_bp.route('/me/sso-identities', methods=['GET'])
@jwt_required_custom
def get_user_sso_identities():
    """
    Get all SSO identities for the current user

    Returns all Azure AD identities linked to the authenticated user across all tenants.

    **Authentication**: JWT required

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "SSO identities retrieved successfully",
                "data": [
                    {
                        "tenant_id": "uuid",
                        "tenant_name": "Acme Corp",
                        "azure_tenant_id": "azure-tenant-uuid",
                        "azure_object_id": "azure-object-uuid",
                        "azure_upn": "user@domain.com",
                        "last_sync": "2024-01-01T00:00:00Z",
                        "has_valid_token": true
                    }
                ]
            }

        404 Not Found: User not found
        500 Internal Server Error: Server error

    **Example**:
        GET /api/users/me/sso-identities
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Fetching SSO identities for user_id={user_id}")

        # Fetch user from database
        user = User.query.filter_by(id=user_id).first()

        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return not_found('User not found')

        # Get all Azure identities for the user
        identities = []
        for identity in user.azure_identities:
            tenant = Tenant.query.get(identity.tenant_id)
            identities.append({
                'tenant_id': str(identity.tenant_id),
                'tenant_name': tenant.name if tenant else 'Unknown',
                'azure_tenant_id': identity.azure_tenant_id,
                'azure_object_id': identity.azure_object_id,
                'azure_upn': identity.azure_upn,
                'last_sync': identity.last_sync.isoformat() if identity.last_sync else None,
                'has_valid_token': not identity.is_access_token_expired()
            })

        logger.info(f"Retrieved {len(identities)} SSO identities for user_id={user_id}")
        return ok(identities, 'SSO identities retrieved successfully')

    except Exception as e:
        logger.error(f"Error fetching SSO identities: {str(e)}", exc_info=True)
        return internal_error('Failed to fetch SSO identities')


@users_bp.route('/me/sso-identities/<string:tenant_id>', methods=['DELETE'])
@jwt_required_custom
def delete_user_sso_identity(tenant_id):
    """
    Delete SSO identity for a specific tenant

    Removes the Azure AD identity link for the authenticated user for a specific tenant.
    This does not delete the user account, only the SSO link.

    **Authentication**: JWT required

    **Parameters**:
        tenant_id: UUID of the tenant to remove SSO identity for

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "SSO identity removed successfully",
                "data": {
                    "tenant_id": "uuid",
                    "tenant_name": "Acme Corp",
                    "azure_object_id": "azure-object-uuid"
                }
            }

        400 Bad Request: Invalid tenant ID
        404 Not Found: User not found or SSO identity not found
        500 Internal Server Error: Server error

    **Example**:
        DELETE /api/users/me/sso-identities/123e4567-e89b-12d3-a456-426614174000
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Deleting SSO identity for user_id={user_id}, tenant_id={tenant_id}")

        # Validate tenant_id format (should be UUID)
        import uuid
        try:
            uuid.UUID(tenant_id)
        except ValueError:
            logger.warning(f"Invalid tenant ID format: {tenant_id}")
            return bad_request('Invalid tenant ID format')

        # Fetch user from database
        user = User.query.filter_by(id=user_id).first()

        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            return not_found('User not found')

        # Get the Azure identity for this user and tenant
        azure_identity = UserAzureIdentity.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not azure_identity:
            logger.warning(f"SSO identity not found for user_id={user_id}, tenant_id={tenant_id}")
            return not_found('SSO identity not found for this tenant')

        # Get tenant info before deletion
        tenant = Tenant.query.get(tenant_id)
        response_data = {
            'tenant_id': str(azure_identity.tenant_id),
            'tenant_name': tenant.name if tenant else 'Unknown',
            'azure_object_id': azure_identity.azure_object_id
        }

        # Delete the SSO identity
        db.session.delete(azure_identity)
        db.session.commit()

        logger.info(f"SSO identity removed successfully for user_id={user_id}, tenant_id={tenant_id}")
        return ok(response_data, 'SSO identity removed successfully')

    except Exception as e:
        logger.error(f"Error deleting SSO identity: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to delete SSO identity')


@users_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for users blueprint

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Users API is healthy",
                "data": {
                    "status": "healthy",
                    "blueprint": "users"
                }
            }
    """
    return ok({
        'status': 'healthy',
        'blueprint': 'users'
    }, 'Users API is healthy')
