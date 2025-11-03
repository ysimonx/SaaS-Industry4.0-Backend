"""
Files Blueprint - API Routes for File Management

This blueprint provides administrative endpoints for managing files in tenant databases.
Files are immutable and created automatically during document upload with MD5 deduplication.

Key features:
- List all files in tenant database with pagination and statistics
- Get file details with document references
- Delete orphaned files (admin-only safety checks)
- Cross-database user reference validation
- Tenant access control with role-based permissions

Endpoints:
1. GET /api/files/<tenant_id>/files - List all files (paginated)
2. GET /api/files/<tenant_id>/files/<file_id> - Get file details
3. DELETE /api/files/<tenant_id>/files/<file_id> - Delete orphaned file (admin-only)

Architecture notes:
- Files stored in tenant-specific databases (NOT main database)
- One File can be referenced by multiple Documents (MD5 deduplication)
- Deletion requires admin role and orphan status check (safety measure)
- Uses TenantDatabaseManager for tenant database context switching
"""

import logging
from flask import Blueprint, request, jsonify
from marshmallow import ValidationError

from app.models import Tenant, UserTenantAssociation
from app.models.file import File
from app.models.document import Document
from app.schemas import file_response_schema, files_response_schema
from app.utils.responses import ok, created, not_found, bad_request, internal_error, forbidden
from app.utils.decorators import jwt_required_custom
from app.utils.database import tenant_db_manager
from app.extensions import db

logger = logging.getLogger(__name__)

# Create Blueprint
files_bp = Blueprint('files', __name__, url_prefix='/api/files')


def check_tenant_access(user_id: str, tenant_id: str) -> tuple[bool, dict | None]:
    """
    Check if user has access to the specified tenant.

    Args:
        user_id: UUID of user making the request
        tenant_id: UUID of tenant to check access for

    Returns:
        Tuple of (has_access: bool, error_response: dict | None)
        - If has_access is True, error_response is None
        - If has_access is False, error_response contains error details
    """
    # Check if tenant exists and is active
    tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
    if not tenant:
        return False, not_found('Tenant not found')

    # Check if user has access to this tenant
    association = UserTenantAssociation.query.filter_by(
        user_id=user_id,
        tenant_id=tenant_id
    ).first()

    if not association:
        return False, not_found('Tenant not found or access denied')

    return True, None


def check_admin_access(user_id: str, tenant_id: str) -> tuple[bool, dict | None]:
    """
    Check if user has admin access to the specified tenant.

    Args:
        user_id: UUID of user making the request
        tenant_id: UUID of tenant to check access for

    Returns:
        Tuple of (is_admin: bool, error_response: dict | None)
        - If is_admin is True, error_response is None
        - If is_admin is False, error_response contains error details
    """
    # Check tenant access first
    has_access, error = check_tenant_access(user_id, tenant_id)
    if not has_access:
        return False, error

    # Check if user is admin
    association = UserTenantAssociation.query.filter_by(
        user_id=user_id,
        tenant_id=tenant_id
    ).first()

    if association.role != 'admin':
        return False, forbidden('Admin access required for this operation')

    return True, None


@files_bp.route('/<tenant_id>/files', methods=['GET'])
@jwt_required_custom
def list_files(tenant_id: str):
    """
    List all files in tenant database with pagination and statistics.

    GET /api/files/<tenant_id>/files?page=1&per_page=20&include_stats=true

    Query Parameters:
        page (int, optional): Page number (default: 1)
        per_page (int, optional): Items per page (default: 20, max: 100)
        include_stats (bool, optional): Include document count and orphan status (default: false)

    Returns:
        200 OK: List of files with pagination metadata
        {
            "success": true,
            "message": "Files retrieved successfully",
            "data": {
                "files": [
                    {
                        "id": "file-uuid",
                        "md5_hash": "5d41402abc4b2a76b9719d911017c592",
                        "s3_path": "tenants/{tenant_id}/files/5d/41/...",
                        "file_size": 1048576,
                        "created_at": "2024-01-01T00:00:00Z",
                        "document_count": 3,  // if include_stats=true
                        "is_orphaned": false  // if include_stats=true
                    }
                ],
                "pagination": {
                    "page": 1,
                    "per_page": 20,
                    "total": 100,
                    "pages": 5
                },
                "stats": {
                    "total_files": 100,
                    "total_storage_bytes": 52428800,
                    "total_storage_mb": 50.0
                }
            }
        }
        400 Bad Request: Invalid tenant ID or query parameters
        403 Forbidden: User does not have access to tenant
        404 Not Found: Tenant not found
        500 Internal Server Error: Database error

    Authorization:
        Requires JWT token with valid user_id
        User must have access to the specified tenant (any role)
    """
    try:
        # Get current user from JWT token (set by @jwt_required_custom decorator)
        user_id = request.user_id

        # Validate tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
        database_name = tenant.database_name

        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        include_stats = request.args.get('include_stats', 'false').lower() == 'true'

        # Validate pagination parameters
        if page < 1:
            return bad_request('Page number must be >= 1')
        if per_page < 1 or per_page > 100:
            return bad_request('Per page must be between 1 and 100')

        # Switch to tenant database and query files
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Build query
            query = session.query(File).order_by(File.created_at.desc())

            # Get total count
            total = query.count()

            # Calculate pagination metadata
            total_pages = (total + per_page - 1) // per_page  # Ceiling division

            # Apply pagination
            files = query.offset((page - 1) * per_page).limit(per_page).all()

            # Serialize files
            if include_stats:
                # Include document count and orphan status
                files_data = [
                    file.to_dict(include_stats=True) for file in files
                ]
            else:
                # Basic serialization
                files_data = files_response_schema.dump(files)

            # Calculate storage statistics
            total_storage_bytes = session.query(File).with_entities(
                db.func.sum(File.file_size)
            ).scalar() or 0
            total_storage_mb = total_storage_bytes / (1024 * 1024)

            logger.info(
                f"Retrieved {len(files)} files for tenant {tenant_id} "
                f"(page {page}/{total_pages}, total: {total})"
            )

            return ok(
                message='Files retrieved successfully',
                data={
                    'files': files_data,
                    'pagination': {
                        'page': page,
                        'per_page': per_page,
                        'total': total,
                        'pages': total_pages
                    },
                    'stats': {
                        'total_files': total,
                        'total_storage_bytes': total_storage_bytes,
                        'total_storage_mb': round(total_storage_mb, 2)
                    }
                }
            )

    except Exception as e:
        logger.error(f"Error listing files for tenant {tenant_id}: {str(e)}", exc_info=True)
        return internal_error(f'Failed to list files: {str(e)}')


@files_bp.route('/<tenant_id>/files/<file_id>', methods=['GET'])
@jwt_required_custom
def get_file(tenant_id: str, file_id: str):
    """
    Get file details with document references.

    GET /api/files/<tenant_id>/files/<file_id>

    Returns:
        200 OK: File details with document list
        {
            "success": true,
            "message": "File retrieved successfully",
            "data": {
                "id": "file-uuid",
                "md5_hash": "5d41402abc4b2a76b9719d911017c592",
                "s3_path": "tenants/{tenant_id}/files/5d/41/...",
                "file_size": 1048576,
                "created_at": "2024-01-01T00:00:00Z",
                "document_count": 3,
                "is_orphaned": false,
                "documents": [
                    {
                        "id": "doc-uuid-1",
                        "filename": "report.pdf",
                        "mime_type": "application/pdf"
                    },
                    {
                        "id": "doc-uuid-2",
                        "filename": "backup.pdf",
                        "mime_type": "application/pdf"
                    }
                ]
            }
        }
        400 Bad Request: Invalid tenant ID or file ID
        403 Forbidden: User does not have access to tenant
        404 Not Found: Tenant or file not found
        500 Internal Server Error: Database error

    Authorization:
        Requires JWT token with valid user_id
        User must have access to the specified tenant (any role)
    """
    try:
        # Get current user from JWT token
        user_id = request.user_id

        # Validate tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
        database_name = tenant.database_name

        # Switch to tenant database and get file
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Get file
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                return not_found('File not found')

            # Serialize file with stats
            file_data = file.to_dict(include_stats=True)

            # Add document details
            documents_data = []
            for doc in file.documents:
                documents_data.append({
                    'id': str(doc.id),
                    'filename': doc.filename,
                    'mime_type': doc.mime_type,
                    'created_at': doc.created_at.isoformat() if doc.created_at else None
                })

            file_data['documents'] = documents_data

            logger.info(f"Retrieved file {file_id} for tenant {tenant_id}")

            return ok(
                message='File retrieved successfully',
                data=file_data
            )

    except Exception as e:
        logger.error(
            f"Error retrieving file {file_id} for tenant {tenant_id}: {str(e)}",
            exc_info=True
        )
        return internal_error(f'Failed to retrieve file: {str(e)}')


@files_bp.route('/<tenant_id>/files/<file_id>', methods=['DELETE'])
@jwt_required_custom
def delete_file(tenant_id: str, file_id: str):
    """
    Delete orphaned file from tenant database and S3 storage.

    DELETE /api/files/<tenant_id>/files/<file_id>

    Safety checks:
    - User must have admin role in tenant
    - File must be orphaned (no documents reference it)
    - File will be deleted from both database and S3

    Returns:
        200 OK: File deleted successfully
        {
            "success": true,
            "message": "Orphaned file deleted successfully",
            "data": {
                "file_id": "file-uuid",
                "md5_hash": "5d41402abc4b2a76b9719d911017c592",
                "freed_storage_bytes": 1048576,
                "freed_storage_mb": 1.0
            }
        }
        400 Bad Request: Invalid tenant ID or file ID, or file is not orphaned
        403 Forbidden: User is not admin or does not have access to tenant
        404 Not Found: Tenant or file not found
        500 Internal Server Error: Database or S3 deletion error

    Authorization:
        Requires JWT token with valid user_id
        User must have admin role in the specified tenant

    Example error response when file is not orphaned:
        {
            "success": false,
            "message": "Cannot delete file: still referenced by 3 documents",
            "data": null
        }
    """
    try:
        # Get current user from JWT token
        user_id = request.user_id

        # Validate admin access
        is_admin, error_response = check_admin_access(user_id, tenant_id)
        if not is_admin:
            return error_response

        # Get tenant
        tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
        database_name = tenant.database_name

        # Switch to tenant database and delete file
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Get file
            file = session.query(File).filter_by(id=file_id).first()

            if not file:
                return not_found('File not found')

            # Safety check: ensure file is orphaned
            document_count = file.get_document_count()
            if document_count > 0:
                logger.warning(
                    f"Attempted to delete non-orphaned file {file_id} "
                    f"(referenced by {document_count} documents)"
                )
                return bad_request(
                    f'Cannot delete file: still referenced by {document_count} documents'
                )

            # Save file details for response
            file_data = {
                'file_id': str(file.id),
                'md5_hash': file.md5_hash,
                'freed_storage_bytes': file.file_size,
                'freed_storage_mb': round(file.file_size / (1024 * 1024), 2)
            }

            # Delete from S3 (placeholder for Phase 6)
            # TODO: Implement S3 deletion in Phase 6
            logger.warning(f"S3 deletion not yet implemented for: {file.s3_path}")

            # Delete from database
            session.delete(file)
            session.commit()

            logger.info(
                f"Deleted orphaned file {file_id} from tenant {tenant_id} "
                f"(freed {file_data['freed_storage_mb']} MB)"
            )

            return ok(
                message='Orphaned file deleted successfully',
                data=file_data
            )

    except Exception as e:
        logger.error(
            f"Error deleting file {file_id} for tenant {tenant_id}: {str(e)}",
            exc_info=True
        )
        return internal_error(f'Failed to delete file: {str(e)}')


# Export blueprint
__all__ = ['files_bp']
