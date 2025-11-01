"""
DocumentService - Business Logic for Document Management

This service handles all document-related business logic including document upload,
retrieval, updates, deletion, and file deduplication. It separates business logic
from the route handlers in the documents blueprint.

Key responsibilities:
- Document CRUD operations with tenant context switching
- File upload with MD5-based deduplication
- S3 integration for file storage (placeholder for Phase 6)
- Kafka integration for document lifecycle events (placeholder for Phase 6)
- Orphaned file detection and cleanup coordination
- Document metadata management

Architecture:
- Service layer sits between routes (controllers) and models (data layer)
- Handles business logic, validation, and orchestration
- Routes call service methods instead of directly manipulating models
- Services can call other services for complex operations

Document Management:
- Documents stored in tenant-specific databases
- Each document references a file via file_id (many-to-one)
- Files are deduplicated by MD5 hash within tenant
- Deleting a document may leave file orphaned (requires cleanup)
- Cross-database user reference (user_id points to main DB)
"""

import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from io import BytesIO

from app.models.document import Document
from app.models.file import File
from app.utils.database import tenant_db_manager
from app.extensions import db

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Service class for document management operations.

    This class provides methods for document CRUD operations with tenant context,
    file deduplication, and S3/Kafka integration. All methods are static since
    there's no instance state to maintain.
    """

    @staticmethod
    def create_document(
        tenant_id: str,
        tenant_database_name: str,
        file_obj: BytesIO,
        filename: str,
        mime_type: str,
        user_id: str
    ) -> Tuple[Optional[Document], Optional[str]]:
        """
        Create new document with file upload and MD5 deduplication.

        This method handles the complete document creation flow:
        1. Calculates MD5 hash of uploaded file
        2. Checks for duplicate file in tenant database (by MD5)
        3. If duplicate: reuses existing File record
        4. If new: uploads to S3 and creates new File record
        5. Creates Document record linking to File
        6. (TODO) Sends Kafka message for document.uploaded event

        Args:
            tenant_id: Tenant's UUID string
            tenant_database_name: Tenant's database name for context switching
            file_obj: File binary data as BytesIO object
            filename: Original filename (user-provided)
            mime_type: File MIME type (e.g., "application/pdf")
            user_id: UUID of user uploading the document

        Returns:
            Tuple of (Document object, error message)
            - If successful: (document, None)
            - If error: (None, error_message)

        Example:
            document, error = DocumentService.create_document(
                tenant_id='tenant-uuid',
                tenant_database_name='tenant_acme_corp_abc123',
                file_obj=BytesIO(file_data),
                filename='report.pdf',
                mime_type='application/pdf',
                user_id='user-uuid'
            )
            if error:
                return server_error(error)
            return created(document_response_schema.dump(document))

        Business Rules:
            - MD5 deduplication within tenant boundary only
            - Duplicate files share same File record (save storage)
            - Each document has unique filename for user
            - File upload to S3 (placeholder for Phase 6)
            - Kafka message sent for async processing (placeholder for Phase 6)

        Transaction Safety:
            - Tenant database transaction rolled back on error
            - S3 upload should be idempotent or cleaned up on failure
        """
        try:
            # Calculate MD5 hash of file content
            file_obj.seek(0)  # Reset to beginning
            file_data = file_obj.read()
            file_size = len(file_data)
            md5_hash = hashlib.md5(file_data).hexdigest()
            file_obj.seek(0)  # Reset for potential re-read

            logger.info(
                f"Creating document in tenant {tenant_id}: "
                f"filename={filename}, size={file_size}, md5={md5_hash}"
            )

            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Check for duplicate file by MD5 hash
                existing_file = session.query(File).filter_by(md5_hash=md5_hash).first()

                if existing_file:
                    # Reuse existing file (deduplication)
                    file_id = existing_file.id
                    logger.info(
                        f"Reusing existing file {file_id} for document "
                        f"(MD5 deduplication: {md5_hash})"
                    )
                else:
                    # Create new File record
                    # Generate S3 path using File model's static method
                    s3_path = File.generate_s3_path(tenant_id, md5_hash, None)  # file_id added after creation

                    # TODO Phase 6: Upload file to S3
                    # s3_client.upload_file(file_obj, s3_path)
                    logger.warning(
                        f"S3 upload not yet implemented (Phase 6): {s3_path}"
                    )

                    # Create File record in tenant database
                    new_file = File(
                        md5_hash=md5_hash,
                        s3_path=s3_path,
                        file_size=file_size,
                        created_by=user_id
                    )
                    session.add(new_file)
                    session.flush()  # Get file.id for S3 path update

                    # Update S3 path with actual file_id
                    new_file.s3_path = File.generate_s3_path(tenant_id, md5_hash, str(new_file.id))

                    file_id = new_file.id
                    logger.info(
                        f"Created new file {file_id} in tenant database "
                        f"(md5={md5_hash}, size={file_size})"
                    )

                # Create Document record
                document = Document(
                    filename=filename,
                    mime_type=mime_type,
                    file_id=file_id,
                    user_id=user_id,
                    created_by=user_id
                )

                session.add(document)
                session.commit()

                # Refresh to get relationships loaded
                session.refresh(document)

                logger.info(
                    f"Document created: {document.id} (filename={filename}, "
                    f"file_id={file_id}, user_id={user_id})"
                )

                # TODO Phase 6: Send Kafka message for document.uploaded event
                # kafka_service.produce_message(
                #     topic='document.uploaded',
                #     event_type='document.uploaded',
                #     tenant_id=tenant_id,
                #     user_id=user_id,
                #     data={
                #         'document_id': str(document.id),
                #         'filename': filename,
                #         'mime_type': mime_type,
                #         'file_id': str(file_id),
                #         'file_size': file_size,
                #         'md5_hash': md5_hash,
                #         'was_deduplicated': existing_file is not None
                #     }
                # )

                return document, None

        except Exception as e:
            logger.error(
                f"Error creating document in tenant {tenant_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to create document: {str(e)}'

    @staticmethod
    def get_document(
        tenant_database_name: str,
        document_id: str
    ) -> Tuple[Optional[Document], Optional[str]]:
        """
        Fetch document by ID with file relationship.

        This method retrieves a document from the tenant database with its
        associated file information loaded.

        Args:
            tenant_database_name: Tenant's database name for context switching
            document_id: Document's UUID string

        Returns:
            Tuple of (Document object, error message)
            - If successful: (document, None)
            - If not found: (None, 'Document not found')
            - If error: (None, error_message)

        Example:
            document, error = DocumentService.get_document(
                tenant_database_name='tenant_acme_corp_abc123',
                document_id='doc-uuid'
            )
            if error:
                return not_found(error)
            return success('Document retrieved', document_response_schema.dump(document))

        Business Rules:
            - Document must exist in tenant database
            - File relationship eagerly loaded for performance
            - Returns document regardless of user ownership (caller should check)
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Query document with file relationship
                document = session.query(Document).filter_by(id=document_id).first()

                if not document:
                    logger.warning(f"Document not found: {document_id}")
                    return None, 'Document not found'

                logger.debug(
                    f"Document retrieved: {document.id} (filename={document.filename})"
                )

                return document, None

        except Exception as e:
            logger.error(
                f"Error fetching document {document_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to fetch document: {str(e)}'

    @staticmethod
    def list_documents(
        tenant_database_name: str,
        filters: Optional[Dict] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        List documents with filtering and pagination.

        This method retrieves documents from the tenant database with optional
        filtering by filename and user_id, and supports pagination.

        Args:
            tenant_database_name: Tenant's database name for context switching
            filters: Optional dictionary with filter criteria:
                - filename: Partial filename match (case-insensitive)
                - user_id: Filter by document owner
            page: Page number (1-indexed, default: 1)
            per_page: Items per page (default: 20, max: 100)

        Returns:
            Tuple of (result dict, error message)
            - If successful: (result, None) where result is:
                {
                    'documents': [...],  # List of Document objects
                    'pagination': {
                        'page': 1,
                        'per_page': 20,
                        'total': 100,
                        'pages': 5
                    }
                }
            - If error: (None, error_message)

        Example:
            result, error = DocumentService.list_documents(
                tenant_database_name='tenant_acme_corp_abc123',
                filters={'filename': 'report', 'user_id': 'user-uuid'},
                page=1,
                per_page=20
            )
            if error:
                return server_error(error)
            return success('Documents retrieved', result)

        Business Rules:
            - Filename filter uses ILIKE for partial case-insensitive match
            - Results sorted by created_at descending (newest first)
            - Empty result set is valid (returns empty list)
            - Pagination metadata included for UI pagination controls
        """
        try:
            if filters is None:
                filters = {}

            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Build query
                query = session.query(Document)

                # Apply filename filter (partial match, case-insensitive)
                if 'filename' in filters and filters['filename']:
                    query = query.filter(
                        Document.filename.ilike(f"%{filters['filename']}%")
                    )

                # Apply user_id filter
                if 'user_id' in filters and filters['user_id']:
                    query = query.filter_by(user_id=filters['user_id'])

                # Sort by created_at descending (newest first)
                query = query.order_by(Document.created_at.desc())

                # Get total count before pagination
                total = query.count()

                # Calculate pagination metadata
                total_pages = (total + per_page - 1) // per_page  # Ceiling division

                # Apply pagination
                documents = query.offset((page - 1) * per_page).limit(per_page).all()

                logger.info(
                    f"Retrieved {len(documents)} documents "
                    f"(page {page}/{total_pages}, total: {total})"
                )

                result = {
                    'documents': documents,
                    'pagination': {
                        'page': page,
                        'per_page': per_page,
                        'total': total,
                        'pages': total_pages
                    }
                }

                return result, None

        except Exception as e:
            logger.error(
                f"Error listing documents: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to list documents: {str(e)}'

    @staticmethod
    def update_document(
        tenant_database_name: str,
        document_id: str,
        metadata: Dict
    ) -> Tuple[Optional[Document], Optional[str]]:
        """
        Update document metadata (filename and mime_type only).

        This method updates document metadata without changing the underlying file.
        Only filename and mime_type can be updated; file_id and user_id are immutable.

        Args:
            tenant_database_name: Tenant's database name for context switching
            document_id: Document's UUID string
            metadata: Dictionary containing fields to update
                Allowed fields: filename, mime_type
                All fields are optional (only provided fields are updated)

        Returns:
            Tuple of (updated Document object, error message)
            - If successful: (document, None)
            - If document not found: (None, 'Document not found')
            - If error: (None, error_message)

        Example:
            document, error = DocumentService.update_document(
                tenant_database_name='tenant_acme_corp_abc123',
                document_id='doc-uuid',
                metadata={
                    'filename': 'updated_report.pdf',
                    'mime_type': 'application/pdf'
                }
            )
            if error:
                return bad_request(error)
            return success('Document updated', document_response_schema.dump(document))

        Business Rules:
            - Only updates fields present in metadata (partial updates allowed)
            - Filename and mime_type are mutable
            - file_id and user_id are immutable (cannot be changed)
            - File content is NOT changed (metadata only)
            - Database transaction rolled back on any error
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Fetch document
                document = session.query(Document).filter_by(id=document_id).first()

                if not document:
                    logger.warning(f"Update failed: Document not found: {document_id}")
                    return None, 'Document not found'

                # Track what fields are being updated (for logging)
                updated_fields = []

                # Update filename if provided
                if 'filename' in metadata:
                    document.filename = metadata['filename']
                    updated_fields.append('filename')

                # Update mime_type if provided
                if 'mime_type' in metadata:
                    document.mime_type = metadata['mime_type']
                    updated_fields.append('mime_type')

                # Commit changes to database
                session.commit()

                logger.info(
                    f"Document updated: {document.id} - "
                    f"Updated fields: {', '.join(updated_fields) if updated_fields else 'none'}"
                )

                return document, None

        except Exception as e:
            logger.error(
                f"Error updating document {document_id}: {str(e)}",
                exc_info=True
            )
            return None, f'Failed to update document: {str(e)}'

    @staticmethod
    def delete_document(
        tenant_id: str,
        tenant_database_name: str,
        document_id: str,
        user_id: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Delete document and detect orphaned files.

        This method deletes a document record and checks if the associated file
        becomes orphaned (no other documents reference it). If orphaned, it can
        be scheduled for cleanup.

        Args:
            tenant_id: Tenant's UUID string (for Kafka message)
            tenant_database_name: Tenant's database name for context switching
            document_id: Document's UUID string
            user_id: UUID of user deleting the document (for Kafka message)

        Returns:
            Tuple of (success bool, file_id if orphaned, error message)
            - If successful: (True, orphaned_file_id or None, None)
            - If document not found: (False, None, 'Document not found')
            - If error: (False, None, error_message)

        Example:
            success, orphaned_file_id, error = DocumentService.delete_document(
                tenant_id='tenant-uuid',
                tenant_database_name='tenant_acme_corp_abc123',
                document_id='doc-uuid',
                user_id='user-uuid'
            )
            if error:
                return not_found(error)
            if orphaned_file_id:
                # File can be cleaned up
                logger.info(f"File {orphaned_file_id} is now orphaned")
            return success('Document deleted')

        Business Rules:
            - Document must exist to be deleted
            - File is NOT automatically deleted (may be referenced by other documents)
            - Orphaned file detection runs after document deletion
            - Kafka message sent for async cleanup (placeholder for Phase 6)
            - Transaction rolled back on any error

        Orphaned File Handling:
            - Method returns orphaned file_id for caller to handle
            - Caller can schedule async cleanup or immediate deletion
            - S3 object should be deleted when file record is deleted
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Fetch document
                document = session.query(Document).filter_by(id=document_id).first()

                if not document:
                    logger.warning(f"Delete failed: Document not found: {document_id}")
                    return False, None, 'Document not found'

                # Save file_id for orphan check
                file_id = document.file_id
                filename = document.filename

                # Delete document record
                session.delete(document)
                session.commit()

                logger.info(
                    f"Document deleted: {document_id} (filename={filename}, file_id={file_id})"
                )

                # Check if file is now orphaned
                file_obj = session.query(File).filter_by(id=file_id).first()
                orphaned_file_id = None

                if file_obj and file_obj.is_orphaned():
                    orphaned_file_id = str(file_id)
                    logger.warning(
                        f"File {file_id} is now orphaned after deleting document {document_id}"
                    )

                # TODO Phase 6: Send Kafka message for document.deleted event
                # kafka_service.produce_message(
                #     topic='document.deleted',
                #     event_type='document.deleted',
                #     tenant_id=tenant_id,
                #     user_id=user_id,
                #     data={
                #         'document_id': document_id,
                #         'filename': filename,
                #         'file_id': str(file_id),
                #         'file_orphaned': orphaned_file_id is not None
                #     }
                # )

                return True, orphaned_file_id, None

        except Exception as e:
            logger.error(
                f"Error deleting document {document_id}: {str(e)}",
                exc_info=True
            )
            return False, None, f'Failed to delete document: {str(e)}'


# Export service class
__all__ = ['DocumentService']
