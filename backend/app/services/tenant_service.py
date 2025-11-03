"""
TenantService - Business Logic for Tenant Management

This service handles all tenant-related business logic including tenant creation,
updates, deletion, and user association management. It separates business logic
from the route handlers in the tenants blueprint.

Key responsibilities:
- Create tenants with automatic database provisioning
- Update tenant information
- Soft/hard delete tenants with cleanup
- Manage user-tenant associations with role assignment
- Query tenant users and their roles
- Integrate with Kafka for tenant lifecycle events

Architecture:
- Service layer sits between routes (controllers) and models (data layer)
- Handles business logic, validation, and orchestration
- Routes call service methods instead of directly manipulating models
- Services can call other services for complex operations

Tenant Management:
- Tenants stored in main database
- Each tenant has isolated database for documents/files
- Database name auto-generated from tenant name
- Creator automatically added as admin
- Soft delete (is_active=False) by default
- Hard delete available (drops database)
"""

import logging
from typing import Dict, List, Optional, Tuple

from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_tenant_association import UserTenantAssociation
from app.utils.database import tenant_db_manager
from app.extensions import db
from app.tenant_db.tenant_migrations import get_migrator

logger = logging.getLogger(__name__)


class TenantService:
    """
    Service class for tenant management operations.

    This class provides methods for tenant CRUD operations, database management,
    and user association handling. All methods are static since there's no
    instance state to maintain.
    """

    @staticmethod
    def create_tenant(tenant_data: Dict, creator_user_id: str) -> Tuple[Optional[Tenant], Optional[str]]:
        """
        Create new tenant with isolated database and add creator as admin.

        This method handles the complete tenant creation flow:
        1. Validates tenant data (name required)
        2. Checks creator user exists and is active
        3. Creates tenant record in main database
        4. Generates unique database_name from tenant name
        5. Creates isolated PostgreSQL database for tenant
        6. Creates Document and File tables in tenant database
        7. Adds creator as admin to tenant
        8. Commits all changes
        9. (TODO) Sends Kafka message for tenant.created event

        Args:
            tenant_data: Dictionary containing tenant data
                Required fields: name (str)
                Optional fields: is_active (bool, defaults to True)
            creator_user_id: UUID of user creating the tenant (becomes admin)

        Returns:
            Tuple of (Tenant object, error message)
            - If successful: (tenant, None)
            - If creator not found: (None, 'Creator user not found')
            - If validation error: (None, error_message)
            - If error: (None, error_message)

        Example:
            tenant, error = TenantService.create_tenant(
                tenant_data={'name': 'Acme Corporation'},
                creator_user_id='123e4567-e89b-12d3-a456-426614174000'
            )
            if error:
                return bad_request(error)
            return created(tenant_response_schema.dump(tenant))

        Business Rules:
            - Tenant name is required and must be non-empty
            - Database name is auto-generated (format: tenant_{slug}_{uuid8})
            - Database name is unique and immutable after creation
            - Creator must exist and be active
            - Creator automatically gets 'admin' role in tenant
            - Tenant is active by default (is_active=True)
            - Database and tables created atomically
            - Kafka message sent for async processing (TODO Phase 6)

        Transaction Safety:
            - Main database transaction rolled back on any error
            - Tenant database creation is idempotent (uses checkfirst=True)
            - If database creation fails, tenant record is rolled back
            - Association creation failure triggers rollback
        """
        try:
            # Validate creator user exists and is active
            creator = User.query.filter_by(id=creator_user_id, is_active=True).first()
            if not creator:
                logger.warning(f"Tenant creation failed: Creator user not found or inactive: {creator_user_id}")
                return None, 'Creator user not found or inactive'

            # Validate tenant name
            tenant_name = tenant_data.get('name', '').strip()
            if not tenant_name:
                logger.warning("Tenant creation failed: Tenant name is required")
                return None, 'Tenant name is required'

            # Create tenant record (database_name will be auto-generated)
            tenant = Tenant(
                name=tenant_name,
                is_active=tenant_data.get('is_active', True),
                created_by=creator_user_id
            )

            # Add to session (triggers before_insert which generates database_name)
            db.session.add(tenant)
            db.session.flush()  # Flush to get tenant.id and tenant.database_name

            # Create isolated tenant database with Document/File tables
            # This calls Tenant.create_database() which uses TenantDatabaseManager
            try:
                tenant.create_database()
                logger.info(
                    f"Created tenant database: {tenant.database_name} "
                    f"for tenant {tenant.id} ({tenant.name})"
                )

                # Apply tenant-specific migrations
                try:
                    # Obtenir une session pour le tenant
                    session_factory = tenant_db_manager.get_tenant_session_factory(tenant.database_name)
                    tenant_db = session_factory()

                    try:
                        migrator = get_migrator(tenant_db)
                        applied_migrations = migrator.migrate_to_latest()

                        if applied_migrations:
                            logger.info(
                                f"Applied {len(applied_migrations)} migration(s) to tenant {tenant.id}: "
                                f"{', '.join(applied_migrations)}"
                            )
                        else:
                            logger.info(f"Tenant {tenant.id} schema is up to date")
                    finally:
                        tenant_db.close()

                except Exception as migration_error:
                    logger.error(
                        f"Failed to apply tenant migrations: {str(migration_error)}",
                        exc_info=True
                    )
                    # Continue without failing - migrations can be applied later
                    # using migrate_all_tenants.py script

            except Exception as e:
                db.session.rollback()
                logger.error(
                    f"Failed to create tenant database: {str(e)}",
                    exc_info=True
                )
                return None, f'Failed to create tenant database: {str(e)}'

            # Add creator as admin to tenant
            try:
                association = UserTenantAssociation.create_association(
                    user_id=creator_user_id,
                    tenant_id=tenant.id,
                    role='admin'
                )
                db.session.add(association)
                logger.info(
                    f"Added creator {creator_user_id} as admin to tenant {tenant.id}"
                )
            except Exception as e:
                db.session.rollback()
                logger.error(
                    f"Failed to add creator as admin: {str(e)}",
                    exc_info=True
                )
                return None, f'Failed to add creator as admin: {str(e)}'

            # Commit all changes to main database
            db.session.commit()

            # TODO Phase 6: Send Kafka message for tenant.created event
            # kafka_service.produce_message(
            #     topic='tenant.created',
            #     event_type='tenant.created',
            #     tenant_id=str(tenant.id),
            #     user_id=creator_user_id,
            #     data={
            #         'tenant_name': tenant.name,
            #         'database_name': tenant.database_name
            #     }
            # )

            logger.info(
                f"Tenant created successfully: {tenant.id} ({tenant.name}) "
                f"by user {creator_user_id}"
            )

            return tenant, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Tenant creation error: {str(e)}", exc_info=True)
            return None, f'Tenant creation failed: {str(e)}'

    @staticmethod
    def get_tenant(tenant_id: str) -> Tuple[Optional[Tenant], Optional[str]]:
        """
        Fetch tenant by UUID.

        This method retrieves a tenant record from the main database by its UUID.
        Returns both active and inactive tenants (caller should check is_active if needed).

        Args:
            tenant_id: Tenant's UUID string

        Returns:
            Tuple of (Tenant object, error message)
            - If successful: (tenant, None)
            - If not found: (None, 'Tenant not found')
            - If error: (None, error_message)

        Example:
            tenant, error = TenantService.get_tenant('123e4567-e89b-12d3-a456-426614174000')
            if error:
                return not_found(error)
            return success('Tenant retrieved', tenant_response_schema.dump(tenant))

        Business Rules:
            - Returns tenant regardless of is_active status
            - Caller should check tenant.is_active if needed
            - Returns None if tenant_id is invalid UUID format
        """
        try:
            # Query tenant by ID
            tenant = Tenant.query.filter_by(id=tenant_id).first()

            if not tenant:
                logger.warning(f"Tenant not found: {tenant_id}")
                return None, 'Tenant not found'

            logger.debug(f"Tenant retrieved: {tenant.id} ({tenant.name})")
            return tenant, None

        except Exception as e:
            logger.error(f"Error fetching tenant by ID {tenant_id}: {str(e)}", exc_info=True)
            return None, f'Failed to fetch tenant: {str(e)}'

    @staticmethod
    def update_tenant(tenant_id: str, tenant_data: Dict) -> Tuple[Optional[Tenant], Optional[str]]:
        """
        Update tenant information.

        This method handles updating tenant fields including:
        - name: Tenant's display name
        - is_active: Account active status (soft delete)

        Database name cannot be changed after creation (immutable).

        Args:
            tenant_id: Tenant's UUID string
            tenant_data: Dictionary containing fields to update
                Allowed fields: name, is_active
                All fields are optional (only provided fields are updated)

        Returns:
            Tuple of (updated Tenant object, error message)
            - If successful: (tenant, None)
            - If tenant not found: (None, 'Tenant not found')
            - If validation error: (None, error_message)
            - If error: (None, error_message)

        Example:
            tenant, error = TenantService.update_tenant(
                tenant_id='123e4567-e89b-12d3-a456-426614174000',
                tenant_data={
                    'name': 'Acme Corp Updated',
                    'is_active': True
                }
            )
            if error:
                return bad_request(error)
            return success('Tenant updated', tenant_response_schema.dump(tenant))

        Business Rules:
            - Only updates fields present in tenant_data (partial updates allowed)
            - Database name is immutable (cannot be changed after creation)
            - Name validation enforced (non-empty, trimmed)
            - Database transaction rolled back on any error
            - Tenant must exist (no creation through update)

        Security Notes:
            - Caller should validate that requester has admin role in tenant
            - is_active field should only be updatable by admins
            - Soft delete sets is_active=False (database not dropped)
        """
        try:
            # Fetch tenant
            tenant = Tenant.query.filter_by(id=tenant_id).first()

            if not tenant:
                logger.warning(f"Update failed: Tenant not found: {tenant_id}")
                return None, 'Tenant not found'

            # Track what fields are being updated (for logging)
            updated_fields = []

            # Update name if provided
            if 'name' in tenant_data:
                new_name = tenant_data['name'].strip()
                if not new_name:
                    logger.warning(f"Update failed: Empty tenant name for {tenant_id}")
                    return None, 'Tenant name cannot be empty'

                tenant.name = new_name
                updated_fields.append('name')

            # Update is_active if provided
            if 'is_active' in tenant_data:
                tenant.is_active = tenant_data['is_active']
                updated_fields.append('is_active')

            # Commit changes to database
            db.session.commit()

            logger.info(
                f"Tenant updated: {tenant.id} ({tenant.name}) - "
                f"Updated fields: {', '.join(updated_fields) if updated_fields else 'none'}"
            )

            return tenant, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating tenant {tenant_id}: {str(e)}", exc_info=True)
            return None, f'Failed to update tenant: {str(e)}'

    @staticmethod
    def delete_tenant(tenant_id: str, hard_delete: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Delete tenant (soft delete by default, hard delete optional).

        This method handles tenant deletion with two modes:
        1. Soft delete (default): Set is_active=False, keep database
        2. Hard delete: Drop tenant database and delete record

        Args:
            tenant_id: Tenant's UUID string
            hard_delete: If True, drops database and deletes record permanently
                        If False (default), sets is_active=False (soft delete)

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If tenant not found: (False, 'Tenant not found')
            - If error: (False, error_message)

        Example:
            # Soft delete (default)
            success, error = TenantService.delete_tenant('tenant-uuid')

            # Hard delete (drops database)
            success, error = TenantService.delete_tenant('tenant-uuid', hard_delete=True)

        Business Rules:
            - Soft delete: Sets is_active=False, keeps database and data
            - Hard delete: Drops PostgreSQL database, deletes tenant record
            - Hard delete terminates all active connections to database
            - Hard delete is irreversible (no recovery possible)
            - Kafka message sent for tenant.deleted event (TODO Phase 6)

        Security Notes:
            - Caller should validate that requester has admin role
            - Hard delete should require additional confirmation
            - Consider backup before hard delete
            - Soft delete is recommended for audit trail

        Warnings:
            - Hard delete drops all tenant data permanently
            - Hard delete cannot be undone
            - Active database connections are terminated
        """
        try:
            # Fetch tenant
            tenant = Tenant.query.filter_by(id=tenant_id).first()

            if not tenant:
                logger.warning(f"Delete failed: Tenant not found: {tenant_id}")
                return False, 'Tenant not found'

            if hard_delete:
                # Hard delete: Drop database and delete record
                logger.warning(
                    f"Hard deleting tenant {tenant_id} ({tenant.name}) - "
                    f"Database {tenant.database_name} will be dropped permanently"
                )

                try:
                    # Drop tenant database
                    tenant.delete_database(confirm=True)
                    logger.info(f"Dropped tenant database: {tenant.database_name}")
                except Exception as e:
                    db.session.rollback()
                    logger.error(
                        f"Failed to drop tenant database: {str(e)}",
                        exc_info=True
                    )
                    return False, f'Failed to drop tenant database: {str(e)}'

                # Delete tenant record from main database
                db.session.delete(tenant)
                db.session.commit()

                logger.info(
                    f"Hard deleted tenant: {tenant_id} ({tenant.name}) - "
                    f"Database dropped permanently"
                )

                # TODO Phase 6: Send Kafka message for tenant.deleted event
                # kafka_service.produce_message(
                #     topic='tenant.deleted',
                #     event_type='tenant.deleted',
                #     tenant_id=tenant_id,
                #     user_id=None,
                #     data={
                #         'tenant_name': tenant.name,
                #         'database_name': tenant.database_name,
                #         'delete_type': 'hard'
                #     }
                # )

            else:
                # Soft delete: Set is_active=False
                tenant.deactivate()
                db.session.commit()

                logger.info(
                    f"Soft deleted tenant: {tenant_id} ({tenant.name}) - "
                    f"Set is_active=False (database preserved)"
                )

                # TODO Phase 6: Send Kafka message for tenant.deactivated event
                # kafka_service.produce_message(
                #     topic='tenant.deactivated',
                #     event_type='tenant.deactivated',
                #     tenant_id=tenant_id,
                #     user_id=None,
                #     data={
                #         'tenant_name': tenant.name,
                #         'database_name': tenant.database_name,
                #         'delete_type': 'soft'
                #     }
                # )

            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting tenant {tenant_id}: {str(e)}", exc_info=True)
            return False, f'Failed to delete tenant: {str(e)}'

    @staticmethod
    def add_user_to_tenant(tenant_id: str, user_id: str, role: str) -> Tuple[Optional[UserTenantAssociation], Optional[str]]:
        """
        Add user to tenant with specified role.

        This method creates a new user-tenant association with role assignment.
        Validates that both user and tenant exist, and that no duplicate association exists.

        Args:
            tenant_id: Tenant's UUID string
            user_id: User's UUID string
            role: User's role in tenant ('admin', 'user', or 'viewer')

        Returns:
            Tuple of (UserTenantAssociation object, error message)
            - If successful: (association, None)
            - If tenant not found: (None, 'Tenant not found')
            - If user not found: (None, 'User not found')
            - If duplicate: (None, 'User already member of tenant')
            - If invalid role: (None, 'Invalid role')
            - If error: (None, error_message)

        Example:
            association, error = TenantService.add_user_to_tenant(
                tenant_id='tenant-uuid',
                user_id='user-uuid',
                role='admin'
            )
            if error:
                return bad_request(error)
            return created(user_tenant_association_response_schema.dump(association))

        Business Rules:
            - Valid roles: 'admin', 'user', 'viewer'
            - Tenant must exist and be active
            - User must exist and be active
            - User cannot be added twice to same tenant (composite PK prevents duplicates)
            - Role hierarchy: admin > user > viewer
            - joined_at timestamp automatically set to current UTC time

        Security Notes:
            - Caller should validate that requester has admin role in tenant
            - Only admins can add users to tenants
            - Role validation enforced by UserTenantAssociation model
        """
        try:
            # Validate tenant exists and is active
            tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
            if not tenant:
                logger.warning(f"Add user failed: Tenant not found or inactive: {tenant_id}")
                return None, 'Tenant not found'

            # Validate user exists and is active
            user = User.query.filter_by(id=user_id, is_active=True).first()
            if not user:
                logger.warning(f"Add user failed: User not found or inactive: {user_id}")
                return None, 'User not found'

            # Check if association already exists
            existing = UserTenantAssociation.find_by_user_and_tenant(user_id, tenant_id)
            if existing:
                logger.warning(
                    f"Add user failed: User {user_id} already member of tenant {tenant_id} "
                    f"with role {existing.role}"
                )
                return None, 'User already member of tenant'

            # Create association with role
            association = UserTenantAssociation.create_association(
                user_id=user_id,
                tenant_id=tenant_id,
                role=role
            )

            db.session.add(association)
            db.session.commit()

            logger.info(
                f"Added user {user_id} ({user.email}) to tenant {tenant_id} ({tenant.name}) "
                f"with role {role}"
            )

            return association, None

        except ValueError as e:
            # Raised by create_association for invalid role
            db.session.rollback()
            logger.warning(f"Add user failed: {str(e)}")
            return None, str(e)

        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error adding user {user_id} to tenant {tenant_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to add user to tenant: {str(e)}'

    @staticmethod
    def remove_user_from_tenant(tenant_id: str, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Remove user from tenant.

        This method deletes the user-tenant association, revoking the user's access
        to the tenant and all its resources.

        Args:
            tenant_id: Tenant's UUID string
            user_id: User's UUID string

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If association not found: (False, 'User not member of tenant')
            - If error: (False, error_message)

        Example:
            success, error = TenantService.remove_user_from_tenant(
                tenant_id='tenant-uuid',
                user_id='user-uuid'
            )
            if error:
                return not_found(error)
            return success('User removed from tenant')

        Business Rules:
            - Association must exist to be removed
            - Caller should prevent removing last admin (business logic in route)
            - User immediately loses access to tenant resources
            - Soft delete: association record is deleted (not marked inactive)

        Security Notes:
            - Caller should validate that requester has admin role in tenant
            - Cannot remove yourself as last admin (prevent lockout)
            - Consider checking for last admin before removal
        """
        try:
            # Find association
            association = UserTenantAssociation.find_by_user_and_tenant(user_id, tenant_id)

            if not association:
                logger.warning(
                    f"Remove user failed: User {user_id} not member of tenant {tenant_id}"
                )
                return False, 'User not member of tenant'

            # Delete association
            role = association.role  # Save for logging before deletion
            UserTenantAssociation.remove_association(user_id, tenant_id)
            db.session.commit()

            logger.info(
                f"Removed user {user_id} from tenant {tenant_id} (role was {role})"
            )

            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error removing user {user_id} from tenant {tenant_id}: {str(e)}",
                exc_info=True
            )
            return False, f'Failed to remove user from tenant: {str(e)}'

    @staticmethod
    def get_tenant_users(tenant_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get list of users in tenant with roles.

        This method retrieves all user associations for a tenant, including:
        - User details (id, email, first_name, last_name, is_active)
        - User's role in tenant (admin, user, viewer)
        - Association metadata (joined_at timestamp)

        Args:
            tenant_id: Tenant's UUID string

        Returns:
            Tuple of (user list, error message)
            - If successful: (user_list, None) where user_list is:
                [
                    {
                        'user_id': 'user-uuid',
                        'email': 'user@example.com',
                        'first_name': 'John',
                        'last_name': 'Doe',
                        'role': 'admin',
                        'joined_at': '2024-01-01T00:00:00Z',
                        'is_active': True
                    },
                    ...
                ]
            - If tenant not found: (None, 'Tenant not found')
            - If error: (None, error_message)
            - If tenant has no users: ([], None) - empty list is success

        Example:
            users, error = TenantService.get_tenant_users('tenant-uuid')
            if error:
                return not_found(error)
            return success('Tenant users retrieved', {'users': users})

        Business Rules:
            - Returns ALL user associations (active and inactive users)
            - Sorted by joined_at ascending (oldest first)
            - Includes role information for authorization checks
            - Returns empty list if tenant has no users (not an error)
            - Tenant must exist (returns error if tenant_id invalid)

        Architecture Notes:
            - Joins Tenant → UserTenantAssociation → User
            - Query executes in main database (not tenant-specific)
            - Used for tenant member management pages and admin dashboards
        """
        try:
            # Verify tenant exists
            tenant = Tenant.query.filter_by(id=tenant_id).first()

            if not tenant:
                logger.warning(f"Get users failed: Tenant not found: {tenant_id}")
                return None, 'Tenant not found'

            # Query tenant-user associations with user details
            associations = UserTenantAssociation.query.filter_by(
                tenant_id=tenant_id
            ).join(
                UserTenantAssociation.user
            ).order_by(
                UserTenantAssociation.joined_at.asc()
            ).all()

            # Build user list with role and status information
            users = []
            for assoc in associations:
                users.append({
                    'user_id': str(assoc.user_id),
                    'email': assoc.user.email,
                    'first_name': assoc.user.first_name,
                    'last_name': assoc.user.last_name,
                    'role': assoc.role,
                    'joined_at': assoc.joined_at.isoformat() if assoc.joined_at else None,
                    'is_active': assoc.user.is_active
                })

            logger.debug(
                f"Retrieved {len(users)} user associations for tenant: {tenant_id} ({tenant.name})"
            )

            return users, None

        except Exception as e:
            logger.error(
                f"Error fetching users for tenant {tenant_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to fetch tenant users: {str(e)}'


# Export service class
__all__ = ['TenantService']
