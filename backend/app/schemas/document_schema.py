"""
Marshmallow schemas for Document model validation and serialization.

This module provides comprehensive validation schemas for all document-related operations:
- DocumentSchema: Base schema with all Document model fields
- DocumentUploadSchema: For uploading new documents (POST /api/tenants/{id}/documents)
- DocumentUpdateSchema: For updating document metadata (PUT /api/tenants/{id}/documents/{id})
- DocumentResponseSchema: For API responses (all fields dump_only)
- DocumentWithFileResponseSchema: Extended schema including file details

All schemas include:
- Field validation with Marshmallow validators
- MIME type validation
- Data normalization via @post_load hooks
- Proper handling of auto-generated fields (id, file_id, user_id, timestamps)

Pre-instantiated schema instances are provided at the bottom of this file for
convenient import and use in routes and services.

Usage:
    from app.schemas import document_upload_schema, document_response_schema

    # Validate input (note: file binary data handled separately in multipart/form-data)
    data = document_upload_schema.load(request.form)

    # Serialize output
    result = document_response_schema.dump(document)
"""

from marshmallow import Schema, fields, validates, ValidationError, post_load, validate
import re
import logging

logger = logging.getLogger(__name__)


class DocumentSchema(Schema):
    """
    Base schema for Document model with all fields.

    This schema includes all fields from the Document model and can be used
    as a reference or extended for specific use cases.

    Fields:
        id: UUID primary key (auto-generated, dump_only)
        filename: Document filename (required, 1-255 chars)
        mime_type: MIME type (required, format: type/subtype)
        file_id: UUID of associated File record (auto-assigned, dump_only)
        user_id: UUID of document owner (from JWT, dump_only)
        created_at: Creation timestamp (auto-generated, dump_only)
        updated_at: Last update timestamp (auto-generated, dump_only)
        created_by: UUID of user who created document (dump_only)
    """
    id = fields.UUID(dump_only=True)
    filename = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    mime_type = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    file_id = fields.UUID(dump_only=True)  # Auto-assigned during upload
    user_id = fields.UUID(dump_only=True)  # From JWT token
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    created_by = fields.UUID(dump_only=True)

    @validates('filename')
    def validate_filename(self, value, **kwargs):
        """
        Validate document filename format.

        Rules:
        - Must not be empty or only whitespace
        - Must be between 1 and 255 characters after trimming
        - Should not contain path separators (security check)

        Args:
            value: The filename to validate

        Raises:
            ValidationError: If filename is empty, invalid, or contains path separators
        """
        if not value or not value.strip():
            raise ValidationError("Filename cannot be empty or only whitespace")

        if len(value.strip()) > 255:
            raise ValidationError("Filename cannot exceed 255 characters")

        # Security check: prevent path traversal attacks
        if '/' in value or '\\' in value:
            raise ValidationError("Filename cannot contain path separators (/ or \\)")

        logger.debug(f"Validated filename: {value.strip()}")

    @validates('mime_type')
    def validate_mime_type(self, value, **kwargs):
        """
        Validate MIME type format.

        Rules:
        - Must follow format: type/subtype (e.g., "application/pdf", "image/png")
        - Type and subtype must contain only alphanumeric, dash, plus, or dot characters
        - Must not be empty

        Args:
            value: The MIME type to validate

        Raises:
            ValidationError: If MIME type format is invalid

        Examples:
            Valid: "application/pdf", "image/jpeg", "text/plain"
            Invalid: "pdf", "application", "application/"
        """
        if not value or not value.strip():
            raise ValidationError("MIME type cannot be empty")

        # MIME type regex: type/subtype
        # Type and subtype can contain alphanumeric, dash, plus, dot
        mime_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*\/[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*$'

        if not re.match(mime_pattern, value.strip()):
            raise ValidationError(
                "MIME type must follow format 'type/subtype' "
                "(e.g., 'application/pdf', 'image/png')"
            )

        logger.debug(f"Validated MIME type: {value.strip()}")

    @post_load
    def normalize_data(self, data, **kwargs):
        """
        Normalize input data after validation.

        Transformations:
        - Trim whitespace from filename
        - Trim whitespace from mime_type
        - Normalize mime_type to lowercase

        Args:
            data: The validated data dictionary

        Returns:
            Normalized data dictionary
        """
        if 'filename' in data:
            data['filename'] = data['filename'].strip()
            logger.debug(f"Normalized filename: {data['filename']}")

        if 'mime_type' in data:
            data['mime_type'] = data['mime_type'].strip().lower()
            logger.debug(f"Normalized MIME type: {data['mime_type']}")

        return data


class DocumentUploadSchema(Schema):
    """
    Schema for uploading new documents (POST /api/tenants/{tenant_id}/documents).

    This schema validates the metadata portion of a multipart/form-data upload.
    The actual file binary data is handled separately by Flask's request.files.

    Required fields:
        filename: Document filename (1-255 chars, no path separators)
        mime_type: MIME type (format: type/subtype)

    Auto-assigned fields (not included in input):
        id: UUID (generated by database)
        file_id: UUID (assigned after S3 upload and File record creation)
        user_id: UUID (extracted from JWT token)
        created_at, updated_at: Timestamps

    The upload process:
    1. Validate filename and mime_type with this schema
    2. Calculate MD5 hash of uploaded file
    3. Check for duplicate file in tenant database (by MD5)
    4. If duplicate: reuse existing file_id
    5. If new: upload to S3, create File record, get file_id
    6. Create Document record with file_id and user_id from JWT
    7. Return document object with all fields

    Example request (multipart/form-data):
        Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

        ------WebKitFormBoundary
        Content-Disposition: form-data; name="filename"

        my_document.pdf
        ------WebKitFormBoundary
        Content-Disposition: form-data; name="mime_type"

        application/pdf
        ------WebKitFormBoundary
        Content-Disposition: form-data; name="file"; filename="upload.pdf"
        Content-Type: application/pdf

        [binary file data]
        ------WebKitFormBoundary--
    """
    filename = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    mime_type = fields.Str(required=True, validate=validate.Length(min=1, max=100))

    @validates('filename')
    def validate_filename(self, value, **kwargs):
        """
        Validate document filename format.

        Rules:
        - Must not be empty or only whitespace
        - Must be between 1 and 255 characters after trimming
        - Should not contain path separators (security check)

        Args:
            value: The filename to validate

        Raises:
            ValidationError: If filename is empty, invalid, or contains path separators
        """
        if not value or not value.strip():
            raise ValidationError("Filename cannot be empty or only whitespace")

        if len(value.strip()) > 255:
            raise ValidationError("Filename cannot exceed 255 characters")

        # Security check: prevent path traversal attacks
        if '/' in value or '\\' in value:
            raise ValidationError("Filename cannot contain path separators (/ or \\)")

        logger.debug(f"Validated filename for upload: {value.strip()}")

    @validates('mime_type')
    def validate_mime_type(self, value, **kwargs):
        """
        Validate MIME type format.

        Rules:
        - Must follow format: type/subtype (e.g., "application/pdf", "image/png")
        - Type and subtype must contain only alphanumeric, dash, plus, or dot characters
        - Must not be empty

        Args:
            value: The MIME type to validate

        Raises:
            ValidationError: If MIME type format is invalid
        """
        if not value or not value.strip():
            raise ValidationError("MIME type cannot be empty")

        mime_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*\/[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*$'

        if not re.match(mime_pattern, value.strip()):
            raise ValidationError(
                "MIME type must follow format 'type/subtype' "
                "(e.g., 'application/pdf', 'image/png')"
            )

        logger.debug(f"Validated MIME type for upload: {value.strip()}")

    @post_load
    def normalize_data(self, data, **kwargs):
        """
        Normalize input data after validation.

        Transformations:
        - Trim whitespace from filename
        - Trim whitespace from mime_type
        - Normalize mime_type to lowercase

        Args:
            data: The validated data dictionary

        Returns:
            Normalized data dictionary
        """
        if 'filename' in data:
            data['filename'] = data['filename'].strip()
            logger.debug(f"Normalized filename for upload: {data['filename']}")

        if 'mime_type' in data:
            data['mime_type'] = data['mime_type'].strip().lower()
            logger.debug(f"Normalized MIME type for upload: {data['mime_type']}")

        return data


class DocumentUpdateSchema(Schema):
    """
    Schema for updating document metadata (PUT /api/tenants/{tenant_id}/documents/{id}).

    This schema is used when updating document information. All fields are optional
    since this is a partial update endpoint. Note that this only updates metadata;
    the actual file content cannot be changed (file_id is immutable).

    Immutable fields (cannot be updated):
        id: Cannot change primary key
        file_id: Cannot change file reference (would require re-upload)
        user_id: Cannot change ownership
        created_at, created_by: Audit trail immutable

    Updatable fields:
        filename: Document filename (optional, 1-255 chars)
        mime_type: MIME type (optional, format: type/subtype)

    Use cases:
    - Rename document: Update filename only
    - Correct MIME type: Update mime_type only
    - Both: Update both fields

    Example:
        {
            "filename": "updated_document.pdf",
            "mime_type": "application/pdf"
        }
    """
    filename = fields.Str(validate=validate.Length(min=1, max=255))
    mime_type = fields.Str(validate=validate.Length(min=1, max=100))

    @validates('filename')
    def validate_filename(self, value, **kwargs):
        """
        Validate document filename format (if provided).

        Rules:
        - Must not be empty or only whitespace (if provided)
        - Must be between 1 and 255 characters after trimming
        - Should not contain path separators (security check)

        Args:
            value: The filename to validate

        Raises:
            ValidationError: If filename is empty, invalid, or contains path separators
        """
        if value is not None:
            if not value or not value.strip():
                raise ValidationError("Filename cannot be empty or only whitespace")

            if len(value.strip()) > 255:
                raise ValidationError("Filename cannot exceed 255 characters")

            # Security check: prevent path traversal attacks
            if '/' in value or '\\' in value:
                raise ValidationError("Filename cannot contain path separators (/ or \\)")

            logger.debug(f"Validated filename for update: {value.strip()}")

    @validates('mime_type')
    def validate_mime_type(self, value, **kwargs):
        """
        Validate MIME type format (if provided).

        Rules:
        - Must follow format: type/subtype (e.g., "application/pdf", "image/png")
        - Type and subtype must contain only alphanumeric, dash, plus, or dot characters
        - Must not be empty (if provided)

        Args:
            value: The MIME type to validate

        Raises:
            ValidationError: If MIME type format is invalid
        """
        if value is not None:
            if not value or not value.strip():
                raise ValidationError("MIME type cannot be empty")

            mime_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*\/[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*$'

            if not re.match(mime_pattern, value.strip()):
                raise ValidationError(
                    "MIME type must follow format 'type/subtype' "
                    "(e.g., 'application/pdf', 'image/png')"
                )

            logger.debug(f"Validated MIME type for update: {value.strip()}")

    @post_load
    def normalize_data(self, data, **kwargs):
        """
        Normalize input data after validation.

        Transformations:
        - Trim whitespace from filename (if provided)
        - Trim whitespace from mime_type (if provided)
        - Normalize mime_type to lowercase (if provided)

        Args:
            data: The validated data dictionary

        Returns:
            Normalized data dictionary
        """
        if 'filename' in data and data['filename'] is not None:
            data['filename'] = data['filename'].strip()
            logger.debug(f"Normalized filename for update: {data['filename']}")

        if 'mime_type' in data and data['mime_type'] is not None:
            data['mime_type'] = data['mime_type'].strip().lower()
            logger.debug(f"Normalized MIME type for update: {data['mime_type']}")

        return data


class DocumentResponseSchema(Schema):
    """
    Schema for serializing Document objects in API responses.

    This schema is used for all API responses that return document data.
    All fields are dump_only (read-only) since this is purely for output.

    Fields included:
        id: Document UUID
        filename: Document filename
        mime_type: MIME type
        file_id: UUID of associated File record
        user_id: UUID of document owner
        created_at: When document was created
        updated_at: When document was last updated
        created_by: UUID of user who created document

    Example output:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "filename": "my_document.pdf",
            "mime_type": "application/pdf",
            "file_id": "456e7890-e89b-12d3-a456-426614174001",
            "user_id": "789e0123-e89b-12d3-a456-426614174002",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "created_by": "789e0123-e89b-12d3-a456-426614174002"
        }
    """
    id = fields.UUID(dump_only=True)
    filename = fields.Str(dump_only=True)
    mime_type = fields.Str(dump_only=True)
    file_id = fields.UUID(dump_only=True)
    user_id = fields.UUID(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    created_by = fields.UUID(dump_only=True)


class DocumentWithFileResponseSchema(DocumentResponseSchema):
    """
    Extended schema for document responses that include file details.

    This schema extends DocumentResponseSchema to include detailed information
    about the associated File record. Used for GET /api/tenants/{id}/documents/{id}
    endpoint when full document and file details are needed.

    Additional fields:
        file: Nested file object with MD5 hash, S3 path, and file size

    Example output:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "filename": "my_document.pdf",
            "mime_type": "application/pdf",
            "file_id": "456e7890-e89b-12d3-a456-426614174001",
            "user_id": "789e0123-e89b-12d3-a456-426614174002",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "created_by": "789e0123-e89b-12d3-a456-426614174002",
            "file": {
                "id": "456e7890-e89b-12d3-a456-426614174001",
                "md5_hash": "5d41402abc4b2a76b9719d911017c592",
                "s3_path": "tenants/tenant_id/files/5d/41/5d41402abc4b2a76b9719d911017c592_file_uuid",
                "file_size": 1048576,
                "created_at": "2024-01-01T00:00:00Z"
            }
        }
    """
    file = fields.Dict(dump_only=True)


class DocumentDownloadUrlResponseSchema(Schema):
    """
    Schema for pre-signed download URL response.

    This schema validates the response from the GET /download-url endpoint.
    It returns a temporary pre-signed URL that allows downloading the document
    without authentication.

    Fields:
        download_url (str): Temporary pre-signed S3 URL for download
        expires_in (int): Time until URL expires (seconds)
        expires_at (datetime): Exact timestamp when URL expires (ISO 8601)
        filename (str): Document filename
        mime_type (str): MIME type of the document
        file_size (int): File size in bytes

    Example response:
        {
            "download_url": "http://localhost:9000/saas-documents/tenants/.../file.pdf?Signature=...",
            "expires_in": 3600,
            "expires_at": "2024-01-01T01:00:00Z",
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "file_size": 1048576
        }

    Security notes:
        - The download_url is temporary and expires after expires_in seconds
        - Anyone with the URL can download the file until expiration
        - URLs should not be logged or stored permanently
        - Consider using short expiration times for sensitive documents
    """
    download_url = fields.Str(dump_only=True, required=True)
    expires_in = fields.Int(dump_only=True)
    expires_at = fields.DateTime(dump_only=True)
    filename = fields.Str(dump_only=True)
    mime_type = fields.Str(dump_only=True)
    file_size = fields.Int(dump_only=True)


# Pre-instantiated schema instances for convenient import
# These can be imported and used directly in routes and services

# Base schema (rarely used directly)
document_schema = DocumentSchema()

# Input validation schemas
document_upload_schema = DocumentUploadSchema()
document_update_schema = DocumentUpdateSchema()

# Output serialization schemas
document_response_schema = DocumentResponseSchema()
document_with_file_response_schema = DocumentWithFileResponseSchema()
document_download_url_schema = DocumentDownloadUrlResponseSchema()

# For serializing lists of documents
documents_response_schema = DocumentResponseSchema(many=True)


# Export all schemas and instances
__all__ = [
    # Schema classes
    'DocumentSchema',
    'DocumentUploadSchema',
    'DocumentUpdateSchema',
    'DocumentResponseSchema',
    'DocumentWithFileResponseSchema',
    'DocumentDownloadUrlResponseSchema',

    # Pre-instantiated schema instances
    'document_schema',
    'document_upload_schema',
    'document_update_schema',
    'document_response_schema',
    'document_with_file_response_schema',
    'document_download_url_schema',
    'documents_response_schema',
]
