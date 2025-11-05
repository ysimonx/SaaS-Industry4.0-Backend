"""
S3 Client Utility - AWS S3 File Storage Integration

This utility provides a wrapper around the boto3 S3 client for file storage operations.
It handles file uploads, downloads, deletions, and pre-signed URL generation for secure
access to private S3 buckets.

Key responsibilities:
- Upload files to S3 with proper content type and metadata
- Delete files from S3 storage
- Generate pre-signed URLs for temporary file access
- Check file existence in S3
- Handle S3-compatible endpoints (AWS S3, MinIO, DigitalOcean Spaces, etc.)

Architecture:
- Singleton S3 client instance for connection pooling
- Configuration loaded from Flask app config or environment variables
- Error handling with tuple return pattern (result, error_message)
- Comprehensive logging for debugging and monitoring

S3 Configuration:
- S3_ENDPOINT_URL: Optional S3-compatible endpoint (e.g., MinIO)
- S3_REGION: AWS region (default: us-east-1)
- S3_BUCKET: Default bucket name for file storage
- S3_ACCESS_KEY_ID: AWS access key ID
- S3_SECRET_ACCESS_KEY: AWS secret access key
- S3_USE_SSL: Use HTTPS for S3 connections (default: True)

Usage Example:
```python
from app.utils.s3_client import s3_client

# Upload file
success, error = s3_client.upload_file(
    file_obj=BytesIO(file_data),
    s3_path='tenants/123/files/2024/01/file.pdf',
    content_type='application/pdf'
)

# Generate download URL
url, error = s3_client.generate_presigned_url(
    s3_path='tenants/123/files/2024/01/file.pdf',
    expires_in=3600
)

# Delete file
success, error = s3_client.delete_file(
    s3_path='tenants/123/files/2024/01/file.pdf'
)
```

Note: This is a PLACEHOLDER implementation for Phase 6. Real implementation will use
boto3 library with proper AWS credentials and error handling.
"""

import logging
from typing import BinaryIO, Optional, Tuple
from flask import current_app

logger = logging.getLogger(__name__)


class S3Client:
    """
    S3 client wrapper for file storage operations.

    This class provides methods for uploading, downloading, and managing files in S3.
    It uses boto3 for AWS S3 integration and supports S3-compatible endpoints.

    Note: This is a PLACEHOLDER implementation. Phase 6 will add real boto3 integration.
    """

    def __init__(self):
        """
        Initialize S3 client with configuration from Flask app or environment.

        Configuration is lazy-loaded when first method is called to ensure Flask app
        context is available.
        """
        self._client = None
        self._bucket = None
        self._initialized = False

    def _ensure_initialized(self) -> Tuple[bool, Optional[str]]:
        """
        Ensure S3 client is initialized with configuration.

        Loads configuration from Flask app config and creates boto3 S3 client.
        This is called automatically by all public methods.

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If error: (False, error_message)

        Configuration:
            - S3_ENDPOINT_URL: Optional custom endpoint (e.g., MinIO)
            - S3_REGION: AWS region (default: us-east-1)
            - S3_BUCKET: Bucket name
            - S3_ACCESS_KEY_ID: AWS access key
            - S3_SECRET_ACCESS_KEY: AWS secret key
            - S3_USE_SSL: Use HTTPS (default: True)

        Phase 6 Implementation:
            - Use boto3.client('s3', ...) to create S3 client
            - Configure endpoint_url, region_name, aws_access_key_id, aws_secret_access_key
            - Enable connection pooling with max_pool_connections
            - Add retry configuration with exponential backoff
        """
        if self._initialized:
            return True, None

        try:
            # Get configuration from Flask app
            if not current_app:
                logger.warning("S3 client: No Flask app context available")
                return False, "No Flask app context"

            config = current_app.config

            # Extract S3 configuration
            # Support both S3_BUCKET and S3_BUCKET_NAME
            self._bucket = config.get('S3_BUCKET') or config.get('S3_BUCKET_NAME', 'default-bucket')
            endpoint_url = config.get('S3_ENDPOINT_URL')
            region = config.get('S3_REGION', 'us-east-1')
            access_key = config.get('S3_ACCESS_KEY_ID')
            secret_key = config.get('S3_SECRET_ACCESS_KEY')
            use_ssl = config.get('S3_USE_SSL', True)

            # Create boto3 S3 client
            import boto3
            from botocore.config import Config

            boto_config = Config(
                region_name=region,
                signature_version='s3v4',
                retries={
                    'max_attempts': 3,
                    'mode': 'adaptive'
                },
                max_pool_connections=50
            )

            self._client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                use_ssl=use_ssl,
                config=boto_config
            )

            logger.debug(
                f"S3 client initialized: bucket={self._bucket}, "
                f"region={region}, endpoint={endpoint_url}, use_ssl={use_ssl}"
            )

            self._initialized = True
            logger.info(f"S3 client initialized: bucket={self._bucket}")

            return True, None

        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}", exc_info=True)
            return False, f'S3 initialization failed: {str(e)}'

    def upload_file(
        self,
        file_obj: BinaryIO,
        s3_path: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload file to S3 bucket.

        Uploads a file object to S3 with the specified path, content type, and metadata.
        The file is stored with private ACL by default for security.

        Args:
            file_obj: File object (BytesIO, file handle, etc.) to upload
            s3_path: S3 object key/path (e.g., 'tenants/123/files/2024/01/file.pdf')
            content_type: MIME type of file (e.g., 'application/pdf', 'image/png')
            metadata: Optional dict of custom metadata to attach to S3 object

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If error: (False, error_message)

        Example:
            success, error = s3_client.upload_file(
                file_obj=BytesIO(file_data),
                s3_path='tenants/123/files/2024/01/report.pdf',
                content_type='application/pdf',
                metadata={'tenant_id': '123', 'user_id': 'user-456'}
            )
            if error:
                logger.error(f"Upload failed: {error}")

        Business Rules:
            - Files are stored with private ACL (not publicly accessible)
            - Content type is important for proper browser handling
            - Metadata is searchable in S3 (use for tenant_id, user_id, etc.)
            - File object is rewound to beginning before upload
            - Large files use multipart upload automatically (boto3 handles this)

        Phase 6 Implementation:
            - Use client.upload_fileobj() for streaming upload
            - Set ACL='private' for security
            - Add server-side encryption (SSE-S3 or SSE-KMS)
            - Use multipart upload for files >5MB
            - Add progress callback for large uploads
            - Verify upload with ETag validation
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return False, error

        try:
            # Rewind file object to beginning
            file_obj.seek(0)

            # Build ExtraArgs for upload
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            if metadata:
                extra_args['Metadata'] = metadata
            extra_args['ACL'] = 'private'  # Security: private by default

            # Upload file to S3
            self._client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=self._bucket,
                Key=s3_path,
                ExtraArgs=extra_args
            )

            logger.debug(
                f"Uploaded file to S3: "
                f"bucket={self._bucket}, path={s3_path}, content_type={content_type}"
            )

            logger.info(f"File uploaded to S3: {s3_path}")
            return True, None

        except Exception as e:
            logger.error(
                f"Error uploading file to S3 (path: {s3_path}): {str(e)}",
                exc_info=True
            )
            return False, f'S3 upload failed: {str(e)}'

    def delete_file(self, s3_path: str) -> Tuple[bool, Optional[str]]:
        """
        Delete file from S3 bucket.

        Removes an object from S3 storage. This operation is idempotent - deleting
        a non-existent file returns success.

        Args:
            s3_path: S3 object key/path to delete

        Returns:
            Tuple of (success bool, error message)
            - If successful: (True, None)
            - If error: (False, error_message)

        Example:
            success, error = s3_client.delete_file(
                s3_path='tenants/123/files/2024/01/old-file.pdf'
            )
            if error:
                logger.error(f"Delete failed: {error}")

        Business Rules:
            - Deleting non-existent file returns success (idempotent)
            - No versioning support (file is permanently deleted)
            - Caller should verify file is orphaned before deletion
            - Cannot be undone (implement soft delete at application level)

        Phase 6 Implementation:
            - Use client.delete_object() to remove file
            - Check DeleteMarker in response for versioned buckets
            - Implement batch delete for multiple files (client.delete_objects)
            - Add lifecycle policies for automatic deletion
            - Consider moving to "deleted" folder instead of permanent deletion
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return False, error

        try:
            # Delete file from S3
            response = self._client.delete_object(
                Bucket=self._bucket,
                Key=s3_path
            )

            # Check if deletion was successful
            delete_marker = response.get('DeleteMarker', False)
            if delete_marker:
                logger.info(f"S3 delete marker created: {s3_path}")

            logger.debug(
                f"Deleted file from S3: "
                f"bucket={self._bucket}, path={s3_path}"
            )

            logger.info(f"File deleted from S3: {s3_path}")
            return True, None

        except Exception as e:
            logger.error(
                f"Error deleting file from S3 (path: {s3_path}): {str(e)}",
                exc_info=True
            )
            return False, f'S3 delete failed: {str(e)}'

    def generate_presigned_url(
        self,
        s3_path: str,
        expires_in: int = 3600,
        response_content_disposition: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate pre-signed URL for temporary file access.

        Creates a time-limited URL that allows downloading a file from S3 without
        authentication. The URL expires after the specified time.

        Args:
            s3_path: S3 object key/path
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour)
            response_content_disposition: Optional Content-Disposition header
                (e.g., 'attachment; filename="report.pdf"' to force download)

        Returns:
            Tuple of (pre-signed URL, error message)
            - If successful: (url_string, None)
            - If error: (None, error_message)

        Example:
            url, error = s3_client.generate_presigned_url(
                s3_path='tenants/123/files/2024/01/report.pdf',
                expires_in=3600,
                response_content_disposition='attachment; filename="report.pdf"'
            )
            if error:
                return internal_error(error)
            return redirect(url)

        Business Rules:
            - URL expires after specified time (default: 1 hour)
            - URL can be shared (no authentication required)
            - Keep expiration short for security (recommend max 1 hour)
            - Content-Disposition controls browser download behavior
            - URL works even if user is not authenticated

        Security Notes:
            - Pre-signed URLs bypass normal authentication
            - Anyone with URL can access file until expiration
            - Consider logging URL generation for audit trail
            - Use short expiration times for sensitive files
            - URL cannot be revoked after generation (wait for expiry)

        Phase 6 Implementation:
            - Use client.generate_presigned_url('get_object', ...)
            - Add Params for ResponseContentDisposition
            - Consider adding ResponseContentType override
            - Implement URL signing with custom expiration
            - Add CloudFront signed URLs for better performance
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return None, error

        try:
            # Build parameters for pre-signed URL
            params = {
                'Bucket': self._bucket,
                'Key': s3_path
            }

            if response_content_disposition:
                params['ResponseContentDisposition'] = response_content_disposition

            # Generate pre-signed URL
            url = self._client.generate_presigned_url(
                ClientMethod='get_object',
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod='GET'
            )

            logger.debug(
                f"Generated pre-signed URL: "
                f"bucket={self._bucket}, path={s3_path}, expires_in={expires_in}"
            )

            logger.info(
                f"Pre-signed URL generated: {s3_path} "
                f"(expires in {expires_in}s)"
            )

            return url, None

        except Exception as e:
            logger.error(
                f"Error generating pre-signed URL (path: {s3_path}): {str(e)}",
                exc_info=True
            )
            return None, f'Pre-signed URL generation failed: {str(e)}'

    def check_file_exists(self, s3_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if file exists in S3 bucket.

        Verifies that an object exists at the specified S3 path without downloading it.
        This is useful for validation before operations.

        Args:
            s3_path: S3 object key/path to check

        Returns:
            Tuple of (exists bool, error message)
            - If file exists: (True, None)
            - If file does not exist: (False, None)
            - If error checking: (False, error_message)

        Example:
            exists, error = s3_client.check_file_exists(
                s3_path='tenants/123/files/2024/01/file.pdf'
            )
            if error:
                logger.error(f"Error checking file: {error}")
            elif exists:
                logger.info("File exists in S3")
            else:
                logger.warning("File not found in S3")

        Business Rules:
            - Does not download file (only HEAD request)
            - Returns False for non-existent files (not an error)
            - Returns error only for S3 connectivity issues
            - Useful for validation and sync operations

        Phase 6 Implementation:
            - Use client.head_object() to check existence
            - Catch ClientError with 404 status for not found
            - Return metadata (size, last_modified) if needed
            - Add caching for frequently checked files
            - Consider batch exists check for multiple files
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return False, error

        try:
            # Check if file exists in S3
            from botocore.exceptions import ClientError
            try:
                self._client.head_object(
                    Bucket=self._bucket,
                    Key=s3_path
                )
                logger.info(f"File exists in S3: {s3_path}")
                return True, None
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info(f"File not found in S3: {s3_path}")
                    return False, None
                else:
                    raise

            logger.debug(
                f"Checked file existence in S3: "
                f"bucket={self._bucket}, path={s3_path}"
            )

        except Exception as e:
            logger.error(
                f"Error checking file existence (path: {s3_path}): {str(e)}",
                exc_info=True
            )
            return False, f'File existence check failed: {str(e)}'

    def get_object(self, s3_path: str):
        """
        Get S3 object for streaming download.

        Retrieves an S3 object that can be streamed to the client. The caller
        is responsible for closing the response body.

        Args:
            s3_path: S3 object key/path to download

        Returns:
            Tuple of (S3 response object, error message)
            - If successful: (response_object, None)
            - If error: (None, error_message)

        Example:
            s3_object, error = s3_client.get_object(
                s3_path='tenants/123/files/2024/01/file.pdf'
            )
            if error:
                return internal_error(error)

            # Stream file in chunks
            for chunk in s3_object['Body'].iter_chunks(chunk_size=65536):
                yield chunk

            # Don't forget to close
            s3_object['Body'].close()

        Business Rules:
            - Returns streaming body that must be closed by caller
            - File is not loaded into memory (streaming)
            - Use iter_chunks() to read in chunks
            - Suitable for large files
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return None, error

        try:
            # Get S3 object
            from botocore.exceptions import ClientError
            try:
                response = self._client.get_object(
                    Bucket=self._bucket,
                    Key=s3_path
                )
                logger.info(f"Retrieved S3 object for streaming: {s3_path}")
                return response, None
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchKey':
                    logger.error(f"File not found in S3: s3_path={s3_path}")
                    return None, f'File not found in storage: {s3_path}'
                else:
                    raise

        except Exception as e:
            logger.error(
                f"Error getting S3 object (path: {s3_path}): {str(e)}",
                exc_info=True
            )
            return None, f'Failed to get S3 object: {str(e)}'

    def get_bucket_name(self) -> Optional[str]:
        """
        Get configured S3 bucket name.

        Returns:
            Bucket name string or None if not initialized

        Example:
            bucket = s3_client.get_bucket_name()
            logger.info(f"Using S3 bucket: {bucket}")
        """
        return self._bucket

    def check_s3_health(self) -> Tuple[bool, Optional[str]]:
        """
        Check S3 service health and connectivity.

        Verifies that S3 is accessible by listing buckets or making a HEAD request.
        Used for application health checks.

        Returns:
            Tuple of (is_healthy bool, error message)
            - If healthy: (True, None)
            - If unhealthy: (False, error_message)

        Example:
            is_healthy, error = s3_client.check_s3_health()
            if not is_healthy:
                logger.error(f"S3 unhealthy: {error}")

        Phase 6 Implementation:
            - Use client.list_buckets() or head_bucket()
            - Verify configured bucket exists
            - Check write permissions with test object
            - Return detailed health status
        """
        # Ensure S3 client is initialized
        initialized, error = self._ensure_initialized()
        if error:
            return False, error

        try:
            # Check S3 health
            response = self._client.head_bucket(Bucket=self._bucket)

            logger.debug(
                f"S3 health check: bucket={self._bucket}"
            )

            logger.info("S3 health check completed")
            return True, None

        except Exception as e:
            logger.error(f"S3 health check failed: {str(e)}", exc_info=True)
            return False, f'S3 unhealthy: {str(e)}'


# Global S3 client instance (singleton)
s3_client = S3Client()

# Export client instance
__all__ = ['s3_client', 'S3Client']
