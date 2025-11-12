"""
FileService - Business Logic for File Management

This service handles all file-related business logic including file uploads, downloads,
deduplication, and orphaned file cleanup. It integrates with S3 for file storage and
manages File records in tenant-specific databases.

Key responsibilities:
- Upload files to S3 with MD5-based deduplication
- Retrieve file metadata from tenant databases
- Check for duplicate files by MD5 hash
- Delete files from S3 and database
- Clean up orphaned files (files with no document references)
- Generate pre-signed S3 URLs for secure downloads

Architecture:
- Service layer sits between routes (controllers) and models (data layer)
- Handles business logic, validation, and orchestration
- Integrates with S3 for file storage (Phase 6)
- Integrates with Kafka for file events (Phase 6)
- Uses tenant-specific database context for all operations

File Deduplication:
- Files are identified by MD5 hash (calculated on upload)
- Duplicate files (same MD5) within a tenant share the same File record
- Multiple documents can reference the same File record
- S3 path structure: bucket/tenants/{tenant_id}/files/{year}/{month}/{file_id}_{md5_hash}

Orphaned File Cleanup:
- Files with no document references are considered orphaned
- Orphaned files can be deleted to save storage costs
- Cleanup is coordinated with DocumentService
- Bulk cleanup operation for maintenance
"""

import logging
import hashlib
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from app.models.file import File
from app.models.document import Document
from app.models.tenant import Tenant
from app.utils.database import TenantDatabaseManager

logger = logging.getLogger(__name__)

# Initialize tenant database manager
tenant_db_manager = TenantDatabaseManager()


class FileService:
    """
    Service class for file management operations.

    This class provides methods for uploading files, retrieving file metadata,
    checking for duplicates, deleting files, and managing orphaned files.
    All methods are static since there's no instance state to maintain.
    """

    @staticmethod
    def upload_file(
        tenant_id: str,
        tenant_database_name: str,
        file_obj: BytesIO,
        file_size: int,
        user_id: str,
        original_filename: Optional[str] = None
    ) -> Tuple[Optional[File], Optional[str]]:
        """
        Upload file to S3 and create File record with MD5 deduplication.

        This method handles the complete file upload flow:
        1. Calculate MD5 hash of file content
        2. Check for existing file with same MD5 (deduplication)
        3. If duplicate exists, return existing File record
        4. If new file, upload to S3 and create File record
        5. Schedule TSA timestamping (if enabled for tenant)
        6. Publish file.uploaded event to Kafka (Phase 6)

        Args:
            tenant_id: Tenant's UUID string
            tenant_database_name: Tenant's database name for context switching
            file_obj: File content as BytesIO object
            file_size: Size of file in bytes
            user_id: User's UUID string (uploader)
            original_filename: Optional original filename for logging

        Returns:
            Tuple of (File object, error message)
            - If successful (new file): (file, None)
            - If successful (duplicate): (existing_file, None)
            - If error: (None, error_message)

        Example:
            file_obj = BytesIO(request.files['file'].read())
            file, error = FileService.upload_file(
                tenant_id='123e4567-e89b-12d3-a456-426614174000',
                tenant_database_name='tenant_acme_corp',
                file_obj=file_obj,
                file_size=1024000,
                user_id='user-uuid',
                original_filename='document.pdf'
            )
            if error:
                return server_error(error)
            return created('File uploaded', {'file_id': str(file.id)})

        Business Rules:
            - MD5 hash is calculated from entire file content
            - Files with same MD5 within tenant are deduplicated
            - S3 path includes tenant_id, year, month, file_id, and md5_hash
            - File record stores S3 path, MD5 hash, size, and upload timestamp
            - Duplicate files reuse existing File record (no S3 upload)
            - S3 upload is placeholder for Phase 6 implementation

        S3 Path Structure:
            bucket/tenants/{tenant_id}/files/{year}/{month}/{file_id}_{md5_hash}
            Example: bucket/tenants/123-456/files/2024/01/789-abc_def123.pdf

        Deduplication Logic:
            - Query File table by MD5 hash in tenant database
            - If match found, return existing file (no upload)
            - If no match, upload to S3 and create new File record
        """
        try:
            # Calculate MD5 and SHA-256 hashes of file content
            file_obj.seek(0)  # Reset file pointer to beginning
            file_data = file_obj.read()
            md5_hash = hashlib.md5(file_data).hexdigest()
            sha256_hash = hashlib.sha256(file_data).hexdigest()
            file_obj.seek(0)  # Reset for potential upload

            logger.debug(
                f"Calculated hashes for file: MD5={md5_hash}, SHA-256={sha256_hash[:16]}... "
                f"(size: {file_size} bytes, filename: {original_filename})"
            )

            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Check for existing file with same MD5 (deduplication)
                existing_file = session.query(File).filter_by(md5_hash=md5_hash).first()

                if existing_file:
                    logger.info(
                        f"File deduplication: Reusing existing file {existing_file.id} "
                        f"with MD5 {md5_hash} (tenant: {tenant_id})"
                    )
                    return existing_file, None

                # Generate S3 path for new file
                # Path structure: tenants/{tenant_id}/files/{year}/{month}/{file_id}_{md5_hash}
                # Note: file_id will be added after File record is created
                now = datetime.utcnow()
                year = now.strftime('%Y')
                month = now.strftime('%m')
                s3_path_prefix = f"tenants/{tenant_id}/files/{year}/{month}"

                # Create new File record
                new_file = File(
                    md5_hash=md5_hash,
                    sha256_hash=sha256_hash,
                    s3_path=f"{s3_path_prefix}/placeholder",  # Updated after flush
                    file_size=file_size
                )

                # Add to session and flush to get file_id
                session.add(new_file)
                session.flush()

                # Update S3 path with actual file_id
                file_extension = ''
                if original_filename and '.' in original_filename:
                    file_extension = '.' + original_filename.rsplit('.', 1)[1]
                s3_path = f"{s3_path_prefix}/{new_file.id}_{md5_hash}{file_extension}"
                new_file.s3_path = s3_path

                # TODO Phase 6: Upload file to S3
                # s3_client.upload_fileobj(
                #     Fileobj=file_obj,
                #     Bucket=current_app.config['S3_BUCKET'],
                #     Key=s3_path,
                #     ExtraArgs={'ContentType': mime_type}
                # )
                logger.debug(
                    f"[PLACEHOLDER] Would upload file to S3: {s3_path} "
                    f"(size: {file_size} bytes)"
                )

                # Commit transaction
                session.commit()

                # TODO Phase 6: Publish file.uploaded event to Kafka
                # kafka_producer.send('file.uploaded', {
                #     'tenant_id': tenant_id,
                #     'file_id': str(new_file.id),
                #     'md5_hash': md5_hash,
                #     'file_size': file_size,
                #     's3_path': s3_path,
                #     'uploaded_by': user_id,
                #     'uploaded_at': new_file.created_at.isoformat()
                # })
                logger.debug(
                    f"[PLACEHOLDER] Would publish file.uploaded event to Kafka "
                    f"(file_id: {new_file.id}, tenant: {tenant_id})"
                )

                logger.info(
                    f"File uploaded successfully: {new_file.id} "
                    f"(MD5: {md5_hash}, size: {file_size} bytes, tenant: {tenant_id})"
                )

            # TSA Timestamping (outside session to avoid long transaction)
            # Check if TSA is enabled for this tenant
            tenant = Tenant.query.filter_by(id=tenant_id).first()
            if tenant and tenant.tsa_enabled:
                try:
                    # Import here to avoid circular dependency
                    from app.tasks.tsa_tasks import timestamp_file

                    # Schedule async timestamping task
                    # Wait 5 seconds to ensure DB commit is complete
                    task = timestamp_file.apply_async(
                        args=[str(new_file.id), tenant_database_name, sha256_hash],
                        countdown=5
                    )

                    logger.info(
                        f"TSA timestamping scheduled for file {new_file.id} "
                        f"(task_id: {task.id}, tenant: {tenant_id})"
                    )

                except Exception as tsa_error:
                    # Don't fail the upload if TSA scheduling fails
                    logger.error(
                        f"Failed to schedule TSA timestamp for file {new_file.id}: {tsa_error}",
                        exc_info=True
                    )

            return new_file, None

        except Exception as e:
            logger.error(
                f"Error uploading file (tenant: {tenant_id}, user: {user_id}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to upload file: {str(e)}'

    @staticmethod
    def get_file(
        tenant_database_name: str,
        file_id: str
    ) -> Tuple[Optional[File], Optional[str]]:
        """
        Retrieve file metadata from tenant database.

        This method fetches a File record from the tenant-specific database.
        It returns file metadata including S3 path, MD5 hash, size, and timestamps.

        Args:
            tenant_database_name: Tenant's database name for context switching
            file_id: File's UUID string

        Returns:
            Tuple of (File object, error message)
            - If successful: (file, None)
            - If not found: (None, 'File not found')
            - If error: (None, error_message)

        Example:
            file, error = FileService.get_file(
                tenant_database_name='tenant_acme_corp',
                file_id='789e4567-e89b-12d3-a456-426614174000'
            )
            if error:
                return not_found(error)
            return success('File retrieved', file_response_schema.dump(file))

        Business Rules:
            - File must exist in tenant database
            - Returns all file metadata (id, md5_hash, s3_path, file_size, timestamps)
            - Does not fetch file content from S3 (use generate_download_url for that)
            - Used for file metadata display and validation
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Query file by ID
                file = session.query(File).filter_by(id=file_id).first()

                if not file:
                    logger.warning(
                        f"File not found: {file_id} (tenant database: {tenant_database_name})"
                    )
                    return None, 'File not found'

                logger.debug(
                    f"File retrieved: {file.id} "
                    f"(MD5: {file.md5_hash}, size: {file.file_size} bytes)"
                )

                return file, None

        except Exception as e:
            logger.error(
                f"Error fetching file {file_id} (tenant database: {tenant_database_name}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to fetch file: {str(e)}'

    @staticmethod
    def check_duplicate(
        tenant_database_name: str,
        md5_hash: str
    ) -> Tuple[Optional[File], Optional[str]]:
        """
        Check if file with given MD5 hash already exists (deduplication check).

        This method queries the tenant database for an existing file with the same
        MD5 hash. It's used to prevent duplicate file uploads and enable file reuse.

        Args:
            tenant_database_name: Tenant's database name for context switching
            md5_hash: MD5 hash string (32 hex characters)

        Returns:
            Tuple of (File object, error message)
            - If duplicate found: (file, None)
            - If no duplicate: (None, None) - NOT an error, just no match
            - If error: (None, error_message)

        Example:
            existing_file, error = FileService.check_duplicate(
                tenant_database_name='tenant_acme_corp',
                md5_hash='5d41402abc4b2a76b9719d911017c592'
            )
            if error:
                return server_error(error)
            if existing_file:
                return success('Duplicate found', {'file_id': str(existing_file.id)})
            return success('No duplicate found')

        Business Rules:
            - MD5 hash must be 32 hex characters
            - Searches only within tenant's database (tenant-specific deduplication)
            - Returns None (not error) if no duplicate found
            - Used before file upload to check for duplicates
            - Enables file reuse across multiple documents
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Query file by MD5 hash
                file = session.query(File).filter_by(md5_hash=md5_hash).first()

                if file:
                    logger.debug(
                        f"Duplicate file found: {file.id} with MD5 {md5_hash} "
                        f"(tenant database: {tenant_database_name})"
                    )
                    return file, None
                else:
                    logger.debug(
                        f"No duplicate file found for MD5 {md5_hash} "
                        f"(tenant database: {tenant_database_name})"
                    )
                    return None, None  # No duplicate - not an error

        except Exception as e:
            logger.error(
                f"Error checking duplicate for MD5 {md5_hash} "
                f"(tenant database: {tenant_database_name}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to check duplicate: {str(e)}'

    @staticmethod
    def delete_file(
        tenant_id: str,
        tenant_database_name: str,
        file_id: str,
        force: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete file from S3 and database with orphan check.

        This method handles file deletion:
        1. Verify file exists
        2. Check if file is orphaned (no document references)
        3. If force=False and file is not orphaned, return error
        4. If force=True or file is orphaned, delete from S3 and database
        5. Publish file.deleted event to Kafka (Phase 6)

        Args:
            tenant_id: Tenant's UUID string
            tenant_database_name: Tenant's database name for context switching
            file_id: File's UUID string
            force: If True, delete even if file is not orphaned (default: False)

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If file not found: (False, 'File not found')
            - If file not orphaned and force=False: (False, 'File still has document references')
            - If error: (False, error_message)

        Example:
            success, error = FileService.delete_file(
                tenant_id='123e4567-e89b-12d3-a456-426614174000',
                tenant_database_name='tenant_acme_corp',
                file_id='789e4567-e89b-12d3-a456-426614174000',
                force=False
            )
            if error:
                return bad_request(error)
            return success('File deleted')

        Business Rules:
            - File must be orphaned (no document references) unless force=True
            - force=True allows deletion of files with document references (dangerous!)
            - S3 object is deleted before database record
            - Database transaction rolled back if S3 deletion fails
            - Publishes file.deleted event to Kafka (Phase 6)

        Safety Notes:
            - force=True should be used with caution (can break document references)
            - Orphan check prevents accidental deletion of referenced files
            - S3 deletion is placeholder for Phase 6 implementation
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Fetch file
                file = session.query(File).filter_by(id=file_id).first()

                if not file:
                    logger.warning(
                        f"Delete failed: File not found: {file_id} "
                        f"(tenant database: {tenant_database_name})"
                    )
                    return False, 'File not found'

                # Check if file is orphaned (no document references)
                if not force:
                    is_orphaned = file.is_orphaned()
                    if not is_orphaned:
                        logger.warning(
                            f"Delete failed: File {file_id} still has document references "
                            f"(tenant: {tenant_id}). Use force=True to delete anyway."
                        )
                        return False, 'File still has document references. Cannot delete.'

                # Store S3 path and MD5 for logging
                s3_path = file.s3_path
                md5_hash = file.md5_hash

                # TODO Phase 6: Delete file from S3
                # s3_client.delete_object(
                #     Bucket=current_app.config['S3_BUCKET'],
                #     Key=s3_path
                # )
                logger.debug(
                    f"[PLACEHOLDER] Would delete file from S3: {s3_path}"
                )

                # Delete file record from database
                session.delete(file)
                session.commit()

                # TODO Phase 6: Publish file.deleted event to Kafka
                # kafka_producer.send('file.deleted', {
                #     'tenant_id': tenant_id,
                #     'file_id': file_id,
                #     'md5_hash': md5_hash,
                #     's3_path': s3_path,
                #     'deleted_at': datetime.utcnow().isoformat()
                # })
                logger.debug(
                    f"[PLACEHOLDER] Would publish file.deleted event to Kafka "
                    f"(file_id: {file_id}, tenant: {tenant_id})"
                )

                logger.info(
                    f"File deleted successfully: {file_id} "
                    f"(MD5: {md5_hash}, S3 path: {s3_path}, tenant: {tenant_id}, force: {force})"
                )

                return True, None

        except Exception as e:
            logger.error(
                f"Error deleting file {file_id} (tenant: {tenant_id}): {str(e)}",
                exc_info=True
            )
            return False, f'Failed to delete file: {str(e)}'

    @staticmethod
    def delete_orphaned_files(
        tenant_id: str,
        tenant_database_name: str,
        batch_size: int = 100
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Bulk delete orphaned files (files with no document references).

        This method handles bulk cleanup of orphaned files:
        1. Query all File records in tenant database
        2. Check each file for document references
        3. Collect orphaned files (no references)
        4. Delete orphaned files from S3 and database in batches
        5. Return cleanup statistics

        This is a maintenance operation typically run periodically or on-demand
        to reclaim storage space from unreferenced files.

        Args:
            tenant_id: Tenant's UUID string
            tenant_database_name: Tenant's database name for context switching
            batch_size: Number of files to process in each batch (default: 100)

        Returns:
            Tuple of (cleanup stats dict, error message)
            - If successful: ({'total_checked': N, 'deleted': M, 'failed': K}, None)
            - If error: (None, error_message)

        Example:
            stats, error = FileService.delete_orphaned_files(
                tenant_id='123e4567-e89b-12d3-a456-426614174000',
                tenant_database_name='tenant_acme_corp',
                batch_size=100
            )
            if error:
                return server_error(error)
            return success('Orphaned files deleted', stats)

        Business Rules:
            - Only deletes files with zero document references
            - Processes files in batches to avoid memory issues
            - Continues processing even if individual deletions fail
            - Returns statistics: total_checked, deleted, failed
            - S3 deletion is placeholder for Phase 6 implementation

        Performance Notes:
            - Batch size controls memory usage and transaction size
            - Large tenants may have many files (batch processing recommended)
            - Failed deletions are logged but don't stop the process
            - Consider running during off-peak hours for large cleanups
        """
        try:
            deleted_count = 0
            failed_count = 0
            total_checked = 0

            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Query all files in batches
                offset = 0
                while True:
                    # Fetch batch of files
                    files = session.query(File).offset(offset).limit(batch_size).all()

                    if not files:
                        break  # No more files to process

                    # Process each file in batch
                    for file in files:
                        total_checked += 1

                        # Check if file is orphaned
                        if file.is_orphaned():
                            try:
                                # Store S3 path and ID for logging
                                s3_path = file.s3_path
                                file_id = str(file.id)

                                # TODO Phase 6: Delete file from S3
                                # s3_client.delete_object(
                                #     Bucket=current_app.config['S3_BUCKET'],
                                #     Key=s3_path
                                # )
                                logger.debug(
                                    f"[PLACEHOLDER] Would delete orphaned file from S3: {s3_path}"
                                )

                                # Delete file record from database
                                session.delete(file)
                                deleted_count += 1

                                logger.debug(
                                    f"Deleted orphaned file: {file_id} "
                                    f"(S3 path: {s3_path}, tenant: {tenant_id})"
                                )

                            except Exception as e:
                                failed_count += 1
                                logger.error(
                                    f"Failed to delete orphaned file {file.id} "
                                    f"(tenant: {tenant_id}): {str(e)}"
                                )
                                # Continue with next file

                    # Commit batch deletions
                    session.commit()

                    # Move to next batch
                    offset += batch_size

            # Build statistics
            stats = {
                'total_checked': total_checked,
                'deleted': deleted_count,
                'failed': failed_count
            }

            logger.info(
                f"Orphaned file cleanup completed for tenant {tenant_id}: "
                f"{deleted_count} deleted, {failed_count} failed, {total_checked} total checked"
            )

            return stats, None

        except Exception as e:
            logger.error(
                f"Error during orphaned file cleanup (tenant: {tenant_id}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to delete orphaned files: {str(e)}'

    @staticmethod
    def generate_download_url(
        tenant_id: str,
        tenant_database_name: str,
        file_id: str,
        expiration: int = 3600
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate pre-signed S3 URL for secure file download.

        This method generates a time-limited pre-signed URL that allows users
        to download files directly from S3 without exposing credentials.

        Args:
            tenant_id: Tenant's UUID string
            tenant_database_name: Tenant's database name for context switching
            file_id: File's UUID string
            expiration: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Tuple of (pre-signed URL, error message)
            - If successful: (url_string, None)
            - If file not found: (None, 'File not found')
            - If error: (None, error_message)

        Example:
            url, error = FileService.generate_download_url(
                tenant_id='123e4567-e89b-12d3-a456-426614174000',
                tenant_database_name='tenant_acme_corp',
                file_id='789e4567-e89b-12d3-a456-426614174000',
                expiration=3600
            )
            if error:
                return not_found(error)
            return success('Download URL generated', {'url': url, 'expires_in': 3600})

        Business Rules:
            - File must exist in tenant database
            - URL expires after specified time (default: 1 hour)
            - URL provides temporary access without authentication
            - S3 pre-signed URL generation is placeholder for Phase 6
            - Expiration should be short for security (3600 seconds recommended)

        Security Notes:
            - Pre-signed URLs bypass normal authentication
            - Keep expiration time short to limit exposure
            - URLs can be shared, so consider logging downloads
            - S3 bucket should have proper CORS configuration
        """
        try:
            # Switch to tenant database context
            with tenant_db_manager.tenant_db_session(tenant_database_name) as session:
                # Fetch file to verify it exists and get S3 path
                file = session.query(File).filter_by(id=file_id).first()

                if not file:
                    logger.warning(
                        f"Download URL generation failed: File not found: {file_id} "
                        f"(tenant database: {tenant_database_name})"
                    )
                    return None, 'File not found'

                s3_path = file.s3_path

                # TODO Phase 6: Generate pre-signed S3 URL
                # url = s3_client.generate_presigned_url(
                #     'get_object',
                #     Params={
                #         'Bucket': current_app.config['S3_BUCKET'],
                #         'Key': s3_path
                #     },
                #     ExpiresIn=expiration
                # )
                placeholder_url = f"https://placeholder-s3-url.com/{s3_path}?expires={expiration}"
                logger.debug(
                    f"[PLACEHOLDER] Would generate pre-signed S3 URL for file: {file_id} "
                    f"(S3 path: {s3_path}, expiration: {expiration}s, tenant: {tenant_id})"
                )

                logger.info(
                    f"Download URL generated for file: {file_id} "
                    f"(expiration: {expiration}s, tenant: {tenant_id})"
                )

                return placeholder_url, None

        except Exception as e:
            logger.error(
                f"Error generating download URL for file {file_id} (tenant: {tenant_id}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to generate download URL: {str(e)}'


# Export service class
__all__ = ['FileService']
