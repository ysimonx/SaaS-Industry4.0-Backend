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
from app.utils.s3_client import s3_client

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


def calculate_hashes(file_obj) -> tuple[str, str]:
    """
    Calculate MD5 and SHA-256 hashes of file contents.

    Args:
        file_obj: File object (FileStorage from werkzeug)

    Returns:
        Tuple of (md5_hash, sha256_hash) as hex strings
    """
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()

    # Read file in chunks to handle large files
    file_obj.seek(0)  # Reset file pointer to beginning
    for chunk in iter(lambda: file_obj.read(8192), b''):
        md5_hash.update(chunk)
        sha256_hash.update(chunk)

    file_obj.seek(0)  # Reset file pointer for later use
    return md5_hash.hexdigest(), sha256_hash.hexdigest()


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
    File is uploaded to S3-compatible storage (MinIO).

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

        # Calculate MD5 and SHA-256 hashes
        md5_hash, sha256_hash = calculate_hashes(file_obj)
        logger.info(f"File hashes calculated: MD5={md5_hash}, SHA-256={sha256_hash[:16]}..., size={file_size} bytes")

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        # Track if this is a new file (for TSA processing)
        is_new_file = False
        file_id_for_tsa = None

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
                is_new_file = True

                # First create File with temporary s3_path to get file_id
                temp_s3_path = File.generate_s3_path(database_name, md5_hash, 'temp')

                new_file = File(
                    md5_hash=md5_hash,
                    sha256_hash=sha256_hash,
                    s3_path=temp_s3_path,
                    file_size=file_size,
                    created_by=user_id
                )
                session.add(new_file)
                session.flush()  # Get file ID

                file_id = new_file.id
                file_id_for_tsa = str(file_id)

                # Now generate the final S3 path with the real file_id
                s3_path = File.generate_s3_path(database_name, md5_hash, str(file_id))
                new_file.s3_path = s3_path
                session.flush()  # Update with final s3_path

                logger.info(f"Created new file: file_id={file_id}, md5={md5_hash}, sha256={sha256_hash[:16]}..., s3_path={s3_path}")

                # Upload to S3/MinIO with the correct path
                success, upload_error = s3_client.upload_file(
                    file_obj=file_obj,
                    s3_path=s3_path,
                    content_type=mime_type
                )

                if not success:
                    logger.error(f"Failed to upload file to S3: {upload_error}")
                    # Rollback the file record creation
                    session.rollback()
                    return internal_error(f'Failed to upload file to storage: {upload_error}')

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

        # Trigger TSA timestamping if enabled and this is a new file
        if is_new_file and tenant.tsa_enabled and file_id_for_tsa and sha256_hash:
            try:
                from app.tasks.tsa_tasks import timestamp_file
                task = timestamp_file.apply_async(
                    args=[file_id_for_tsa, database_name, sha256_hash],
                    countdown=5  # 5 second delay to ensure DB commit completes
                )
                logger.info(
                    f"TSA timestamp task scheduled for file {file_id_for_tsa} "
                    f"(task_id: {task.id}, tenant: {tenant.name})"
                )
            except Exception as tsa_error:
                # Don't fail the upload if TSA scheduling fails
                logger.error(f"Failed to schedule TSA task: {tsa_error}", exc_info=True)

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
    Download document file directly (proxy mode)

    Securely downloads the document file from S3 storage by proxying through
    the API. Verifies tenant access and streams the file with proper headers.

    **Authentication**: JWT required
    **Authorization**: Must be a member of the tenant with read permission

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Response**:
        200 OK: Binary file stream with headers:
            - Content-Type: document's MIME type
            - Content-Disposition: attachment; filename="original_filename.ext"
            - Content-Length: file size in bytes

        403 Forbidden: User does not have permission to download files
        404 Not Found: Tenant, document not found, or access denied
        500 Internal Server Error: Server error or S3 download failure

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001/download
        Authorization: Bearer <access_token>

    **Security**:
        - Validates JWT authentication
        - Verifies user has access to the tenant
        - Verifies user has read permission (viewer, user, or admin)
        - Does not expose direct S3 URLs
        - All downloads are logged with user_id, document_id, and timestamp
        - File is streamed through API (never direct S3 access)
    """
    try:
        user_id = g.user_id
        logger.info(f"Download request: tenant_id={tenant_id}, document_id={document_id}, user_id={user_id}")

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            logger.warning(f"Access denied: user_id={user_id}, tenant_id={tenant_id}")
            return error_response

        # Verify user has read permission
        association = UserTenantAssociation.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not association.has_permission('read'):
            logger.warning(
                f"Permission denied: user_id={user_id}, tenant_id={tenant_id}, "
                f"role={association.role}, action=download"
            )
            from app.utils.responses import forbidden
            return forbidden('You do not have permission to download files from this tenant')

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        logger.info(
            f"Access granted: user_id={user_id}, tenant_id={tenant_id}, "
            f"role={association.role}, database={database_name}"
        )

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document with file relationship
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Verify document belongs to the tenant (additional security check)
            # This should always be true due to tenant database isolation, but we verify anyway
            if document.user_id and document.user_id not in [
                assoc.user_id for assoc in
                UserTenantAssociation.query.filter_by(tenant_id=tenant_id).all()
            ]:
                logger.error(
                    f"Security violation: document.user_id={document.user_id} does not belong "
                    f"to tenant_id={tenant_id}"
                )
                return not_found('Document not found')

            # Get file details
            s3_path = document.file.s3_path
            filename = document.filename
            mime_type = document.mime_type
            file_size = document.file.file_size
            md5_hash = document.file.md5_hash

            # Audit log: record download attempt
            logger.info(
                f"AUDIT: Download initiated - "
                f"user_id={user_id}, "
                f"tenant_id={tenant_id}, "
                f"document_id={document_id}, "
                f"filename={filename}, "
                f"size={file_size}, "
                f"md5={md5_hash}, "
                f"role={association.role}"
            )

            # Download file from S3 and stream to client
            from flask import Response, stream_with_context

            # Get S3 object for streaming
            s3_object, s3_error = s3_client.get_object(s3_path)
            if s3_error:
                logger.error(
                    f"S3 download failed - document_id={document_id}, "
                    f"s3_path={s3_path}, error={s3_error}"
                )
                if 'not found' in s3_error.lower():
                    return not_found('File not found in storage')
                return internal_error(f'Failed to download file from storage: {s3_error}')

            # Create streaming response
            def generate():
                """Stream file in chunks to avoid loading entire file in memory"""
                try:
                    # Read in 64KB chunks
                    for chunk in s3_object['Body'].iter_chunks(chunk_size=65536):
                        yield chunk

                    # Log successful completion
                    logger.info(
                        f"AUDIT: Download completed successfully - "
                        f"user_id={user_id}, document_id={document_id}, "
                        f"filename={filename}, size={file_size}"
                    )
                except Exception as e:
                    logger.error(
                        f"AUDIT: Download interrupted - "
                        f"user_id={user_id}, document_id={document_id}, "
                        f"error={str(e)}"
                    )
                    raise
                finally:
                    # Ensure S3 response body is closed
                    s3_object['Body'].close()

            response = Response(
                stream_with_context(generate()),
                mimetype=mime_type,
                direct_passthrough=True
            )

            # Set headers for file download
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Length'] = str(file_size)

            # Security headers
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'

            logger.info(f"Download stream started: document_id={document_id}, size={file_size} bytes")
            return response

    except Exception as e:
        logger.error(f"Error downloading document: {str(e)}", exc_info=True)
        return internal_error('Failed to download document')


@documents_bp.route('/<tenant_id>/documents/<document_id>/download-url', methods=['GET'])
@jwt_required_custom
def get_download_url(tenant_id: str, document_id: str):
    """
    Generate pre-signed S3 URL for document download.

    Returns a temporary URL that allows downloading the document without authentication.
    The URL expires after the specified time (default: 1 hour, max: 24 hours).

    This is useful for scenarios where including a Bearer Token in the URL is not
    practical or secure (e.g., email links, browser downloads, external integrations).

    **Workflow**:
    1. Client calls this endpoint with JWT Bearer Token (authenticated)
    2. API validates permissions and generates temporary S3 pre-signed URL
    3. Client downloads file directly from S3 using the URL (no authentication needed)
    4. URL expires after the specified time

    **Authentication**: JWT required
    **Authorization**: Must have read permission on tenant

    **URL Parameters**:
        tenant_id: UUID of the tenant
        document_id: UUID of the document

    **Query Parameters**:
        expires_in: URL expiration time in seconds (default: 3600, min: 60, max: 86400)

    **Response**:
        200 OK:
            {
                "success": true,
                "message": "Download URL generated successfully",
                "data": {
                    "download_url": "http://localhost:9000/saas-documents/tenants/.../file.pdf?Signature=...",
                    "expires_in": 3600,
                    "expires_at": "2024-01-01T01:00:00Z",
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 1048576
                }
            }

        400 Bad Request: Invalid expires_in parameter
        403 Forbidden: User does not have read permission
        404 Not Found: Tenant or document not found
        500 Internal Server Error: Failed to generate URL

    **Example**:
        GET /api/tenants/123e4567-e89b-12d3-a456-426614174000/documents/456e7890-e89b-12d3-a456-426614174001/download-url?expires_in=3600
        Authorization: Bearer <access_token>

    **Security**:
        - Requires JWT authentication to generate URL
        - Verifies tenant access and read permission
        - URLs are temporary and expire automatically
        - Downloads are logged for audit purposes
        - S3 bucket must be private (pre-signed URLs required)

    **Use cases**:
        - Email links for document sharing
        - Browser downloads without custom headers
        - Mobile app downloads
        - External system integrations
        - Temporary public access to private documents
    """
    try:
        user_id = g.user_id

        # Validate expires_in parameter
        expires_in = request.args.get('expires_in', 3600, type=int)
        if expires_in < 60 or expires_in > 86400:  # 1 min to 24 hours
            logger.warning(f"Invalid expires_in parameter: {expires_in}")
            return bad_request('expires_in must be between 60 and 86400 seconds (1 min to 24 hours)')

        logger.info(
            f"Download URL request: tenant_id={tenant_id}, document_id={document_id}, "
            f"user_id={user_id}, expires_in={expires_in}s"
        )

        # Check tenant access
        has_access, error_response = check_tenant_access(user_id, tenant_id)
        if not has_access:
            logger.warning(f"Tenant access denied: user_id={user_id}, tenant_id={tenant_id}")
            return error_response

        # Check read permission
        association = UserTenantAssociation.query.filter_by(
            user_id=user_id,
            tenant_id=tenant_id
        ).first()

        if not association.has_permission('read'):
            logger.warning(
                f"Read permission denied: user_id={user_id}, tenant_id={tenant_id}, "
                f"role={association.role}"
            )
            from app.utils.responses import forbidden
            return forbidden('You do not have permission to download files from this tenant')

        # Get tenant database name
        tenant = Tenant.query.get(tenant_id)
        database_name = tenant.database_name

        logger.info(
            f"Access granted: user_id={user_id}, tenant_id={tenant_id}, "
            f"role={association.role}, database={database_name}"
        )

        # Switch to tenant database
        with tenant_db_manager.tenant_db_session(database_name) as session:
            # Fetch document with file relationship
            document = session.query(Document).filter_by(id=document_id).first()

            if not document:
                logger.warning(f"Document not found: document_id={document_id}")
                return not_found('Document not found')

            # Get file details
            s3_path = document.file.s3_path
            filename = document.filename
            mime_type = document.mime_type
            file_size = document.file.file_size

            # Generate pre-signed URL
            from datetime import datetime, timedelta

            presigned_url, error = s3_client.generate_presigned_url(
                s3_path=s3_path,
                expires_in=expires_in,
                response_content_disposition=f'attachment; filename="{filename}"'
            )

            if error:
                logger.error(
                    f"Failed to generate pre-signed URL: document_id={document_id}, "
                    f"s3_path={s3_path}, error={error}"
                )
                return internal_error(f'Failed to generate download URL: {error}')

            # Build response
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            response_data = {
                'download_url': presigned_url,
                'expires_in': expires_in,
                'expires_at': expires_at.isoformat() + 'Z',
                'filename': filename,
                'mime_type': mime_type,
                'file_size': file_size
            }

            # Audit log: record URL generation
            logger.info(
                f"AUDIT: Download URL generated - "
                f"user_id={user_id}, "
                f"tenant_id={tenant_id}, "
                f"document_id={document_id}, "
                f"filename={filename}, "
                f"expires_in={expires_in}s, "
                f"role={association.role}"
            )

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
    Note: File is NOT automatically deleted from S3 in this implementation.

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
