"""
Tenants Blueprint - Tenant Management Routes

This module provides REST API endpoints for tenant operations:
- GET /api/tenants - List all tenants user has access to
- POST /api/tenants - Create new tenant with database
- GET /api/tenants/<tenant_id> - Get tenant details with members
- PUT /api/tenants/<tenant_id> - Update tenant (admin only)
- DELETE /api/tenants/<tenant_id> - Soft delete tenant (admin only)
- POST /api/tenants/<tenant_id>/users - Add user to tenant (admin only)
- DELETE /api/tenants/<tenant_id>/users/<user_id> - Remove user from tenant (admin only)

All endpoints require JWT authentication.
Some endpoints require specific tenant roles (admin).
"""

import logging
from flask import Blueprint, request, g
from marshmallow import ValidationError
from sqlalchemy import text

from app.extensions import db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant_association import UserTenantAssociation
from app.schemas.tenant_schema import (
    tenant_create_schema,
    tenant_update_schema,
    tenant_response_schema,
    user_tenant_association_create_schema
)
from app.schemas.user_schema import user_response_schema
from app.utils.responses import ok, created, bad_request, not_found, forbidden, internal_error
from app.utils.decorators import jwt_required_custom
from app.utils.database import tenant_db_manager

logger = logging.getLogger(__name__)

# Create blueprint
tenants_bp = Blueprint('tenants', __name__, url_prefix='/api/tenants')


def get_user_tenant_role(user_id: str, tenant_id: str) -> str | None:
    """
    Get user's role in a specific tenant.

    Args:
        user_id: UUID of the user
        tenant_id: UUID of the tenant

    Returns:
        Role string ('admin', 'user', 'viewer') or None if no association exists
    """
    association = UserTenantAssociation.query.filter_by(
        user_id=user_id,
        tenant_id=tenant_id
    ).first()

    return association.role if association else None


def require_tenant_admin(user_id: str, tenant_id: str) -> tuple[bool, dict | None]:
    """
    Check if user is an admin of the specified tenant.

    Args:
        user_id: UUID of the user
        tenant_id: UUID of the tenant

    Returns:
        Tuple of (is_admin: bool, error_response: dict | None)
    """
    role = get_user_tenant_role(user_id, tenant_id)

    if not role:
        return False, not_found('Tenant not found or access denied')

    if role != 'admin':
        return False, forbidden('Admin role required for this operation')

    return True, None


@tenants_bp.route('', methods=['GET'])
@jwt_required_custom
def list_tenants():
    """
    List all tenants user has access to

    Returns a list of all tenants the authenticated user is a member of,
    along with their role in each tenant.

    **Authentication**: JWT required

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Tenants retrieved successfully",
                "data": [
                    {
                        "id": "uuid",
                        "name": "Acme Corp",
                        "database_name": "tenant_acme_corp_a1b2c3d4",
                        "is_active": true,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                        "role": "admin",
                        "joined_at": "2024-01-01T00:00:00Z"
                    }
                ]
            }

        500 Internal Server Error: Server error

    **Example**:
        GET /api/tenants
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Listing tenants for user_id={user_id}")

        # Get user's tenant associations with roles
        associations = (
            db.session.query(UserTenantAssociation, Tenant)
            .join(Tenant, UserTenantAssociation.tenant_id == Tenant.id)
            .filter(UserTenantAssociation.user_id == user_id)
            .filter(Tenant.is_active == True)
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
        return ok(tenants_with_roles, 'Tenants retrieved successfully')

    except Exception as e:
        logger.error(f"Error listing tenants: {str(e)}", exc_info=True)
        return internal_error('Failed to list tenants')


@tenants_bp.route('', methods=['POST'])
@jwt_required_custom
def create_tenant():
    """
    Create new tenant with isolated database

    Creates a new tenant and automatically:
    - Generates a unique database name
    - Creates the isolated tenant database
    - Adds the creator as an admin

    **Authentication**: JWT required

    **Request Body**:
        {
            "name": "Acme Corp"  // Required, 1-100 chars
        }

    **Response**:
        201 Created:
            {
                "success": true,
                "message": "Tenant created successfully",
                "data": {
                    "id": "uuid",
                    "name": "Acme Corp",
                    "database_name": "tenant_acme_corp_a1b2c3d4",
                    "is_active": true,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "role": "admin"
                }
            }

        400 Bad Request: Validation error
        500 Internal Server Error: Server error

    **Example**:
        POST /api/tenants
        Authorization: Bearer <access_token>
        Content-Type: application/json

        {
            "name": "Acme Corp"
        }
    """
    try:
        user_id = g.user_id
        logger.info(f"Creating tenant for user_id={user_id}")

        # Get request data
        data = request.get_json()

        if not data:
            logger.warning("Empty request body")
            return bad_request('Request body is required')

        # Validate input data
        try:
            validated_data = tenant_create_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        # Create new tenant
        tenant = Tenant(name=validated_data['name'])
        db.session.add(tenant)
        db.session.flush()  # Get tenant ID before committing

        # Create tenant database
        try:
            tenant_db_manager.create_tenant_database(tenant.database_name)
            tenant_db_manager.create_tenant_tables(tenant.database_name)
            logger.info(f"Created database and tables: {tenant.database_name}")
        except Exception as db_err:
            logger.error(f"Failed to create tenant database: {str(db_err)}", exc_info=True)
            db.session.rollback()
            return internal_error('Failed to create tenant database')

        # Add creator as admin
        association = UserTenantAssociation(
            user_id=user_id,
            tenant_id=tenant.id,
            role='admin'
        )
        db.session.add(association)

        # Commit all changes
        db.session.commit()

        # Build response
        tenant_data = tenant.to_dict()
        tenant_data['role'] = 'admin'

        logger.info(f"Tenant created successfully: tenant_id={tenant.id}, database={tenant.database_name}")
        return created(tenant_data, 'Tenant created successfully')

    except Exception as e:
        logger.error(f"Error creating tenant: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to create tenant')


@tenants_bp.route('/<tenant_id>', methods=['GET'])
@jwt_required_custom
def get_tenant(tenant_id: str):
    """
    Get tenant details with member list

    Returns detailed information about a specific tenant, including
    a list of all members with their roles.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Tenant details retrieved successfully",
                "data": {
                    "id": "uuid",
                    "name": "Acme Corp",
                    "database_name": "tenant_acme_corp_a1b2c3d4",
                    "is_active": true,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "role": "admin",
                    "members": [
                        {
                            "id": "uuid",
                            "first_name": "John",
                            "last_name": "Doe",
                            "email": "john@example.com",
                            "role": "admin",
                            "joined_at": "2024-01-01T00:00:00Z"
                        }
                    ]
                }
            }

        404 Not Found: Tenant not found or access denied
        500 Internal Server Error: Server error

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Fetching tenant details: tenant_id={tenant_id}, user_id={user_id}")

        # Check user has access to this tenant
        role = get_user_tenant_role(user_id, tenant_id)
        if not role:
            logger.warning(f"Tenant not found or access denied: tenant_id={tenant_id}, user_id={user_id}")
            return not_found('Tenant not found or access denied')

        # Fetch tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()

        if not tenant:
            logger.warning(f"Tenant not found or inactive: tenant_id={tenant_id}")
            return not_found('Tenant not found')

        # Get all members with their roles
        members_data = (
            db.session.query(UserTenantAssociation, User)
            .join(User, UserTenantAssociation.user_id == User.id)
            .filter(UserTenantAssociation.tenant_id == tenant_id)
            .filter(User.is_active == True)
            .order_by(UserTenantAssociation.joined_at.asc())
            .all()
        )

        # Build members list
        members = []
        for association, user in members_data:
            user_dict = user_response_schema.dump(user)
            user_dict['role'] = association.role
            user_dict['joined_at'] = association.joined_at.isoformat() if association.joined_at else None
            members.append(user_dict)

        # Build response
        tenant_data = tenant.to_dict()
        tenant_data['role'] = role
        tenant_data['members'] = members

        logger.info(f"Tenant details retrieved: tenant_id={tenant_id}, members_count={len(members)}")
        return ok(tenant_data, 'Tenant details retrieved successfully')

    except Exception as e:
        logger.error(f"Error fetching tenant details: {str(e)}", exc_info=True)
        return internal_error('Failed to fetch tenant details')


@tenants_bp.route('/<tenant_id>', methods=['PUT'])
@jwt_required_custom
def update_tenant(tenant_id: str):
    """
    Update tenant information

    Updates tenant name. Only tenant admins can perform this operation.

    **Authentication**: JWT required
    **Authorization**: Must be a tenant admin

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Request Body**:
        {
            "name": "New Company Name"  // Optional, 1-100 chars
        }

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Tenant updated successfully",
                "data": {
                    "id": "uuid",
                    "name": "New Company Name",
                    "database_name": "tenant_acme_corp_a1b2c3d4",
                    "is_active": true,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z"
                }
            }

        400 Bad Request: Validation error
        403 Forbidden: Not a tenant admin
        404 Not Found: Tenant not found or access denied
        500 Internal Server Error: Server error

    **Example**:
        PUT /api/tenants/123e4567-e89b-12d3-a456-426614174000
        Authorization: Bearer <access_token>
        Content-Type: application/json

        {
            "name": "New Company Name"
        }
    """
    try:
        user_id = g.user_id
        logger.info(f"Updating tenant: tenant_id={tenant_id}, user_id={user_id}")

        # Check user is admin
        is_admin, error_response = require_tenant_admin(user_id, tenant_id)
        if not is_admin:
            return error_response

        # Get request data
        data = request.get_json()

        if not data:
            logger.warning("Empty request body")
            return bad_request('Request body is required')

        # Validate input data
        try:
            validated_data = tenant_update_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        # Fetch tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()

        if not tenant:
            logger.warning(f"Tenant not found: tenant_id={tenant_id}")
            return not_found('Tenant not found')

        # Update tenant fields
        if 'name' in validated_data:
            tenant.name = validated_data['name']

        # Commit changes
        db.session.commit()

        # Serialize updated tenant data
        tenant_data = tenant.to_dict()

        logger.info(f"Tenant updated successfully: tenant_id={tenant_id}")
        return ok(tenant_data, 'Tenant updated successfully')

    except Exception as e:
        logger.error(f"Error updating tenant: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to update tenant')


@tenants_bp.route('/<tenant_id>', methods=['DELETE'])
@jwt_required_custom
def delete_tenant(tenant_id: str):
    """
    Soft delete tenant

    Soft deletes a tenant by marking it as inactive.
    Only tenant admins can perform this operation.
    The tenant database is NOT dropped - manual cleanup required.

    **Authentication**: JWT required
    **Authorization**: Must be a tenant admin

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Tenant deleted successfully",
                "data": null
            }

        403 Forbidden: Not a tenant admin
        404 Not Found: Tenant not found or access denied
        500 Internal Server Error: Server error

    **Example**:
        DELETE /api/tenants/123e4567-e89b-12d3-a456-426614174000
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Deleting tenant: tenant_id={tenant_id}, user_id={user_id}")

        # Check user is admin
        is_admin, error_response = require_tenant_admin(user_id, tenant_id)
        if not is_admin:
            return error_response

        # Fetch tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()

        if not tenant:
            logger.warning(f"Tenant not found: tenant_id={tenant_id}")
            return not_found('Tenant not found')

        # Soft delete tenant
        tenant.is_active = False
        db.session.commit()

        logger.info(f"Tenant soft deleted successfully: tenant_id={tenant_id}")
        logger.warning(f"Tenant database NOT dropped: {tenant.database_name} - manual cleanup required")

        return ok(None, 'Tenant deleted successfully')

    except Exception as e:
        logger.error(f"Error deleting tenant: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to delete tenant')


@tenants_bp.route('/<tenant_id>/users', methods=['POST'])
@jwt_required_custom
def add_user_to_tenant(tenant_id: str):
    """
    Add user to tenant with role

    Adds an existing user to a tenant with a specified role.
    Only tenant admins can perform this operation.

    **Authentication**: JWT required
    **Authorization**: Must be a tenant admin

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Request Body**:
        {
            "user_id": "uuid",           // Required, existing user ID
            "role": "user"               // Required, one of: admin, user, viewer
        }

    **Response**:
        201 Created:
            {
                "success": true,
                "message": "User added to tenant successfully",
                "data": {
                    "user_id": "uuid",
                    "tenant_id": "uuid",
                    "role": "user",
                    "joined_at": "2024-01-01T00:00:00Z"
                }
            }

        400 Bad Request: Validation error or user already in tenant
        403 Forbidden: Not a tenant admin
        404 Not Found: Tenant or user not found
        500 Internal Server Error: Server error

    **Example**:
        POST /api/tenants/123e4567-e89b-12d3-a456-426614174000/users
        Authorization: Bearer <access_token>
        Content-Type: application/json

        {
            "user_id": "456e7890-e12b-34d5-b678-901234567890",
            "role": "user"
        }
    """
    try:
        user_id = g.user_id
        logger.info(f"Adding user to tenant: tenant_id={tenant_id}, admin_user_id={user_id}")

        # Check user is admin
        is_admin, error_response = require_tenant_admin(user_id, tenant_id)
        if not is_admin:
            return error_response

        # Get request data
        data = request.get_json()

        if not data:
            logger.warning("Empty request body")
            return bad_request('Request body is required')

        # Validate input data
        try:
            validated_data = user_tenant_association_create_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        target_user_id = validated_data['user_id']
        role = validated_data['role']

        # Check tenant exists and is active
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
        if not tenant:
            logger.warning(f"Tenant not found: tenant_id={tenant_id}")
            return not_found('Tenant not found')

        # Check target user exists and is active
        target_user = User.query.filter_by(id=target_user_id, is_active=True).first()
        if not target_user:
            logger.warning(f"User not found: user_id={target_user_id}")
            return not_found('User not found')

        # Check if user already in tenant
        existing_association = UserTenantAssociation.query.filter_by(
            user_id=target_user_id,
            tenant_id=tenant_id
        ).first()

        if existing_association:
            logger.warning(f"User already in tenant: user_id={target_user_id}, tenant_id={tenant_id}")
            return bad_request('User is already a member of this tenant')

        # Create association
        association = UserTenantAssociation(
            user_id=target_user_id,
            tenant_id=tenant_id,
            role=role
        )
        db.session.add(association)
        db.session.commit()

        # Build response
        association_data = {
            'user_id': str(association.user_id),
            'tenant_id': str(association.tenant_id),
            'role': association.role,
            'joined_at': association.joined_at.isoformat() if association.joined_at else None
        }

        logger.info(f"User added to tenant: user_id={target_user_id}, tenant_id={tenant_id}, role={role}")
        return created(association_data, 'User added to tenant successfully')

    except Exception as e:
        logger.error(f"Error adding user to tenant: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to add user to tenant')


@tenants_bp.route('/<tenant_id>/users/<target_user_id>', methods=['DELETE'])
@jwt_required_custom
def remove_user_from_tenant(tenant_id: str, target_user_id: str):
    """
    Remove user from tenant

    Removes a user's access to a tenant.
    Only tenant admins can perform this operation.
    Admins cannot remove themselves if they are the last admin.

    **Authentication**: JWT required
    **Authorization**: Must be a tenant admin

    **URL Parameters**:
        tenant_id: UUID of the tenant
        target_user_id: UUID of the user to remove

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "User removed from tenant successfully",
                "data": null
            }

        400 Bad Request: Cannot remove last admin
        403 Forbidden: Not a tenant admin
        404 Not Found: Tenant, user, or association not found
        500 Internal Server Error: Server error

    **Example**:
        DELETE /api/tenants/123e4567-e89b-12d3-a456-426614174000/users/456e7890-e12b-34d5-b678-901234567890
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Removing user from tenant: tenant_id={tenant_id}, target_user_id={target_user_id}, admin_user_id={user_id}")

        # Check user is admin
        is_admin, error_response = require_tenant_admin(user_id, tenant_id)
        if not is_admin:
            return error_response

        # Check tenant exists and is active
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
        if not tenant:
            logger.warning(f"Tenant not found: tenant_id={tenant_id}")
            return not_found('Tenant not found')

        # Check association exists
        association = UserTenantAssociation.query.filter_by(
            user_id=target_user_id,
            tenant_id=tenant_id
        ).first()

        if not association:
            logger.warning(f"User not in tenant: user_id={target_user_id}, tenant_id={tenant_id}")
            return not_found('User is not a member of this tenant')

        # Prevent removing last admin
        if association.role == 'admin':
            admin_count = UserTenantAssociation.query.filter_by(
                tenant_id=tenant_id,
                role='admin'
            ).count()

            if admin_count <= 1:
                logger.warning(f"Cannot remove last admin: user_id={target_user_id}, tenant_id={tenant_id}")
                return bad_request('Cannot remove the last admin from the tenant')

        # Remove association
        db.session.delete(association)
        db.session.commit()

        logger.info(f"User removed from tenant: user_id={target_user_id}, tenant_id={tenant_id}")
        return ok(None, 'User removed from tenant successfully')

    except Exception as e:
        logger.error(f"Error removing user from tenant: {str(e)}", exc_info=True)
        db.session.rollback()
        return internal_error('Failed to remove user from tenant')


@tenants_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for tenants blueprint

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Tenants API is healthy",
                "data": {
                    "status": "healthy",
                    "blueprint": "tenants"
                }
            }
    """
    return ok({
        'status': 'healthy',
        'blueprint': 'tenants'
    }, 'Tenants API is healthy')
