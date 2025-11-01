"""
Documents Blueprint - Document Management Routes

This module provides REST API endpoints for document operations within tenant databases:
- GET /api/tenants/<tenant_id>/documents - List documents with pagination
- POST /api/tenants/<tenant_id>/documents - Upload document with file
- GET /api/tenants/<tenant_id>/documents/<document_id> - Get document details
- GET /api/tenants/<tenant_id>/documents/<document_id>/download - Get download URL
- PUT /api/tenants/<tenant_id>/documents/<document_id> - Update document metadata
- DELETE /api/tenants/<tenant_id>/documents/<document_id> - Delete document

All endpoints require JWT authentication and tenant membership.
Documents are stored in isolated tenant databases with files in S3.
"""

import logging
import hashlib
from flask import Blueprint, request, g
from marshmallow import ValidationError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.document import Document
from app.models.file import File
from app.models.user_tenant_association import UserTenantAssociation
from app.models.tenant import Tenant
from app.schemas.document_schema import (
    document_upload_schema,
    document_update_schema,
    document_response_schema,
    document_with_file_response_schema
)
from app.utils.responses import ok, created, bad_request, not_found, internal_error
from app.utils.decorators import jwt_required_custom
from app.utils.database import tenant_db_manager

logger = logging.getLogger(__name__)

# Create blueprint
documents_bp = Blueprint('documents', __name__, url_prefix='/api/tenants')

# Configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB in bytes
ALLOWED_MIME_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/jpeg',
    'image/png',
    'image/gif',
    'text/plain',
    'text/csv',
]


def check_tenant_access(user_id: str, tenant_id: str) -> tuple[bool, dict | None]:
    """
    Check if user has access to the specified tenant.

    Args:
        user_id: UUID of the user
        tenant_id: UUID of the tenant

    Returns:
        Tuple of (has_access: bool, error_response: dict | None)
    """
    # Check if tenant exists and is active
    tenant = Tenant.query.filter_by(id=tenant_id, is_active=True).first()
    if not tenant:
        return False, not_found('Tenant not found')

    # Check user has access to tenant
    association = UserTenantAssociation.query.filter_by(
        user_id=user_id,
        tenant_id=tenant_id
    ).first()

    if not association:
        return False, not_found('Tenant not found or access denied')

    return True, None


def calculate_md5(file_obj) -> str:
    """
    Calculate MD5 hash of file contents.

    Args:
        file_obj: File object (FileStorage from werkzeug)

    Returns:
        MD5 hash as hex string (32 characters)
    """
    md5_hash = hashlib.md5()

    # Read file in chunks to handle large files
    file_obj.seek(0)  # Reset file pointer to beginning
    for chunk in iter(lambda: file_obj.read(8192), b''):
        md5_hash.update(chunk)

    file_obj.seek(0)  # Reset file pointer for later use
    return md5_hash.hexdigest()


@documents_bp.route('/<tenant_id>/documents', methods=['GET'])
@jwt_required_custom
def list_documents(tenant_id: str):
    """
    List documents in tenant database with pagination

    Returns paginated list of documents that the user has access to.
    Supports filtering by filename.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Query Parameters**:
        page: Page number (default: 1)
        per_page: Items per page (default: 20, max: 100)
        filename: Filter by filename (partial match, case-insensitive)

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Documents retrieved successfully",
                "data": {
                    "documents": [...],
                    "pagination": {
                        "page": 1,
                        "per_page": 20,
                        "total": 100,
                        "pages": 5
                    }
                }
            }

        404 Not Found: Tenant not found or access denied
        500 Internal Server Error: Server error

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents?page=1&per_page=20&filename=report
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Listing documents: tenant_id={tenant_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        filename_filter = request.args.get('filename', None, type=str)

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(Tenant.query.get(tenant_id).database_name) as session:
            # Build query
            query = session.query(Document)

            # Apply filename filter if provided
            if filename_filter:
                query = query.filter(Document.filename.ilike(f'%{filename_filter}%'))

            # Get total count
            total = query.count()

            # Apply pagination
            query = query.order_by(Document.created_at.desc())
            query = query.offset((page - 1) * per_page).limit(per_page)

            # Execute query
            documents = query.all()

            # Serialize documents
            documents_data = []
            for doc in documents:
                doc_dict = doc.to_dict()
                documents_data.append(doc_dict)

            # Build pagination metadata
            pagination = {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }

            response_data = {
                'documents': documents_data,
                'pagination': pagination
            }

            logger.info(f"Retrieved {len(documents_data)} documents for tenant_id={tenant_id}")
            return ok(response_data, 'Documents retrieved successfully')

    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}", exc_info=True)
        return internal_error('Failed to list documents')


@documents_bp.route('/<tenant_id>/documents', methods=['POST'])
@jwt_required_custom
def upload_document(tenant_id: str):
    """
    Upload document with file to tenant database

    Handles multipart/form-data file upload with metadata.
    Performs MD5 deduplication - if file already exists, reuses it.
    File is NOT uploaded to S3 in this implementation (placeholder for Phase 6).

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant

    **Request Body** (multipart/form-data):
        file: File binary (required, max 100MB)
        filename: Original filename (optional, will use uploaded filename if not provided)
        mime_type: MIME type (optional, will detect from file if not provided)

    **Response**:
        201 Created:
            {
                "success": true,
                "message": "Document uploaded successfully",
                "data": {
                    "id": "uuid",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_id": "uuid",
                    "user_id": "uuid",
                    "created_at": "2024-01-01T00:00:00Z"
                }
            }

        400 Bad Request: Validation error or file too large
        404 Not Found: Tenant not found or access denied
        500 Internal Server Error: Server error

    **Example**:
        POST /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents
        Authorization: Bearer <access_token>
        Content-Type: multipart/form-data

        file=@report.pdf
        filename=Monthly Report.pdf
        mime_type=application/pdf
    """
    try:
        user_id = g.user_id
        logger.info(f"Uploading document: tenant_id={tenant_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get uploaded file
        if 'file' not in request.files:
            logger.warning("No file provided in request")
            return bad_request('File is required')

        file_obj = request.files['file']

        if file_obj.filename == '':
            logger.warning("Empty filename")
            return bad_request('File is required')

        # Get metadata from form data
        filename = request.form.get('filename', secure_filename(file_obj.filename))
        mime_type = request.form.get('mime_type', file_obj.content_type or 'application/octet-stream')

        # Validate metadata
        try:
            metadata = {
                'filename': filename,
                'mime_type': mime_type
            }
            validated_data = document_upload_schema.load(metadata)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        # Check file size
        file_obj.seek(0, 2)  # Seek to end
        file_size = file_obj.tell()
        file_obj.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})")
            return bad_request(f'File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB')

        if file_size == 0:
            logger.warning("Empty file")
            return bad_request('File is empty')

        # Calculate MD5 hash
        md5_hash = calculate_md5(file_obj)
        logger.info(f"File MD5: {md5_hash}, size: {file_size} bytes")

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Check for duplicate file (MD5 deduplication)
            existing_file = session.query(File).filter_by(md5_hash=md5_hash).first()

            if existing_file:
                # Reuse existing file
                file_id = existing_file.id
                logger.info(f"Reusing existing file: file_id={file_id}, md5={md5_hash}")
            else:
                # Create new file record
                # Generate S3 path (placeholder - actual S3 upload in Phase 6)
                s3_path = File.generate_s3_path(tenant_id, md5_hash, None)

                new_file = File(
                    md5_hash=md5_hash,
                    s3_path=s3_path,
                    file_size=file_size,
                    created_by=user_id
                )
                session.add(new_file)
                session.flush()  # Get file ID

                file_id = new_file.id
                logger.info(f"Created new file: file_id={file_id}, md5={md5_hash}, s3_path={s3_path}")

                # TODO: Phase 6 - Upload to S3
                # s3_client.upload_file(file_obj, s3_path)

            # Create document record
            document = Document(
                filename=validated_data['filename'],
                mime_type=validated_data['mime_type'],
                file_id=file_id,
                user_id=user_id,
                created_by=user_id
            )
            session.add(document)
            session.flush()

            # Serialize document
            document_data = document.to_dict(include_file=True)

            logger.info(f"Document uploaded successfully: document_id={document.id}, file_id={file_id}")

            # TODO: Phase 6 - Send Kafka message
            # kafka_service.produce_message('document.uploaded', tenant_id, user_id, document_data)

            return created(document_data, 'Document uploaded successfully')

    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}", exc_info=True)
        return internal_error('Failed to upload document')


@documents_bp.route('/<tenant_id>/documents/<document_id>', methods=['GET'])
@jwt_required_custom
def get_document(tenant_id: str, document_id: str):
    """
    Get document details with file information

    Returns detailed information about a specific document including
    associated file metadata.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Document retrieved successfully",
                "data": {
                    "id": "uuid",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_id": "uuid",
                    "user_id": "uuid",
                    "created_at": "2024-01-01T00:00:00Z",
                    "file": {
                        "id": "uuid",
                        "md5_hash": "abc123...",
                        "s3_path": "tenants/.../files/...",
                        "file_size": 1024000
                    }
                }
            }

        404 Not Found: Tenant, document not found, or access denied
        500 Internal Server Error: Server error

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Fetching document: tenant_id={tenant_id}, document_id={document_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document with file relationship
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Serialize document with file details
            document_data = document.to_dict(include_file=True)

            logger.info(f"Document retrieved: document_id={document_id}")
            return ok(document_data, 'Document retrieved successfully')

    except Exception as e:
        logger.error(f"Error fetching document: {str(e)}", exc_info=True)
        return internal_error('Failed to fetch document')


@documents_bp.route('/<tenant_id>/documents/<document_id>/download', methods=['GET'])
@jwt_required_custom
def download_document(tenant_id: str, document_id: str):
    """
    Get pre-signed download URL for document

    Generates a temporary pre-signed S3 URL for downloading the document file.
    URL expires after 1 hour by default.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Query Parameters**:
        expires_in: URL expiration in seconds (default: 3600, max: 86400)

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Download URL generated successfully",
                "data": {
                    "download_url": "https://s3.amazonaws.com/...",
                    "expires_in": 3600,
                    "expires_at": "2024-01-01T01:00:00Z",
                    "filename": "report.pdf",
                    "file_size": 1024000
                }
            }

        404 Not Found: Tenant, document not found, or access denied
        500 Internal Server Error: Server error

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001/download
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Generating download URL: tenant_id={tenant_id}, document_id={document_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get expiration parameter
        expires_in = min(request.args.get('expires_in', 3600, type=int), 86400)

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document with file relationship
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Get download URL from document (delegates to file)
            # TODO: Phase 6 - Implement actual S3 pre-signed URL generation
            download_url = f"https://s3.example.com/placeholder/{document.file.s3_path}"

            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            response_data = {
                'download_url': download_url,
                'expires_in': expires_in,
                'expires_at': expires_at.isoformat() + 'Z',
                'filename': document.filename,
                'file_size': document.file.file_size,
                'mime_type': document.mime_type
            }

            logger.info(f"Download URL generated: document_id={document_id}, expires_in={expires_in}s")
            return ok(response_data, 'Download URL generated successfully')

    except Exception as e:
        logger.error(f"Error generating download URL: {str(e)}", exc_info=True)
        return internal_error('Failed to generate download URL')


@documents_bp.route('/<tenant_id>/documents/<document_id>', methods=['PUT'])
@jwt_required_custom
def update_document(tenant_id: str, document_id: str):
    """
    Update document metadata

    Updates filename and/or MIME type of an existing document.
    The underlying file content cannot be changed.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Request Body**:
        {
            "filename": "Updated Report.pdf",  // Optional
            "mime_type": "application/pdf"     // Optional
        }

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Document updated successfully",
                "data": {
                    "id": "uuid",
                    "filename": "Updated Report.pdf",
                    "mime_type": "application/pdf",
                    "file_id": "uuid",
                    "user_id": "uuid",
                    "updated_at": "2024-01-01T12:00:00Z"
                }
            }

        400 Bad Request: Validation error
        404 Not Found: Tenant, document not found, or access denied
        500 Internal Server Error: Server error

    **Example**:
        PUT /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001
        Authorization: Bearer <access_token>
        Content-Type: application/json

        {
            "filename": "Updated Report.pdf"
        }
    """
    try:
        user_id = g.user_id
        logger.info(f"Updating document: tenant_id={tenant_id}, document_id={document_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get request data
        data = request.get_json()

        if not data:
            logger.warning("Empty request body")
            return bad_request('Request body is required')

        # Validate input data
        try:
            validated_data = document_update_schema.load(data)
        except ValidationError as err:
            logger.warning(f"Validation error: {err.messages}")
            return bad_request('Validation failed', details=err.messages)

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Update document fields
            if 'filename' in validated_data:
                document.filename = validated_data['filename']

            if 'mime_type' in validated_data:
                document.mime_type = validated_data['mime_type']

            session.flush()

            # Serialize updated document
            document_data = document.to_dict()

            logger.info(f"Document updated successfully: document_id={document_id}")
            return ok(document_data, 'Document updated successfully')

    except Exception as e:
        logger.error(f"Error updating document: {str(e)}", exc_info=True)
        return internal_error('Failed to update document')


@documents_bp.route('/<tenant_id>/documents/<document_id>', methods=['DELETE'])
@jwt_required_custom
def delete_document(tenant_id: str, document_id: str):
    """
    Delete document from tenant database

    Deletes the document record. If the underlying file becomes orphaned
    (no other documents reference it), it can be cleaned up separately.
    File is NOT deleted from S3 in this implementation (placeholder for Phase 6).

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Document deleted successfully",
                "data": {
                    "deleted_document_id": "uuid",
                    "file_orphaned": true
                }
            }

        404 Not Found: Tenant, document not found, or access denied
        500 Internal Server Error: Server error

    **Example**:
        DELETE /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001
        Authorization: Bearer <access_token>
    """
    try:
        user_id = g.user_id
        logger.info(f"Deleting document: tenant_id={tenant_id}, document_id={document_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            return error_response

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Get file reference before deleting document
            file_id = document.file_id

            # Delete document
            session.delete(document)
            session.flush()

            # Check if file is now orphaned
            file = session.query(File).filter_by(id=file_id).first()
            file_orphaned = file.is_orphaned() if file else False

            if file_orphaned:
                logger.warning(f"File is now orphaned: file_id={file_id}")
                # TODO: Phase 6 - Schedule file cleanup or send Kafka message

            response_data = {
                'deleted_document_id': str(document_id),
                'file_orphaned': file_orphaned
            }

            logger.info(f"Document deleted successfully: document_id={document_id}, file_orphaned={file_orphaned}")

            # TODO: Phase 6 - Send Kafka message
            # kafka_service.produce_message('document.deleted', tenant_id, user_id, response_data)

            return ok(response_data, 'Document deleted successfully')

    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}", exc_info=True)
        return internal_error('Failed to delete document')


@documents_bp.route('/<tenant_id>/documents/health', methods=['GET'])
def health_check(tenant_id: str):
    """
    Health check endpoint for documents blueprint

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Documents API is healthy",
                "data": {
                    "status": "healthy",
                    "blueprint": "documents",
                    "tenant_id": "uuid"
                }
            }
    """
    return ok({
        'status': 'healthy',
        'blueprint': 'documents',
        'tenant_id': tenant_id
    }, 'Documents API is healthy')
