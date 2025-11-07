"""
Unit tests for S3 client public URL replacement functionality.

This module tests the S3Client's ability to replace internal Docker endpoint URLs
with public URLs in pre-signed URLs, enabling client access from outside Docker.

Test scenarios:
- URL replacement from internal (minio:9000) to public (localhost:9000)
- No replacement when URLs are identical
- Production HTTPS domain replacement
- Handling of None/missing public URL configuration
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.utils.s3_client import S3Client


class TestS3ClientPublicUrl:
    """Test S3 client public URL replacement in pre-signed URLs."""

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_replaces_internal_url(self, mock_boto3, mock_app):
        """Test that internal endpoint URL is replaced with public URL."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        # Mock boto3 client
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Mock presigned URL with internal endpoint
        internal_url = 'http://minio:9000/test-bucket/tenants/test/file.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=test&X-Amz-Date=20240101T000000Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=abc123'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/test/file.pdf',
            expires_in=3600
        )

        # Assert
        assert error is None
        assert url is not None
        assert 'localhost:9000' in url
        assert 'minio:9000' not in url
        assert url.startswith('http://localhost:9000/test-bucket/')
        assert 'X-Amz-Signature=abc123' in url  # Signature preserved

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_no_replacement_when_same(self, mock_boto3, mock_app):
        """Test that URL is not modified when endpoint and public URL are the same."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://localhost:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',  # Same as endpoint
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        original_url = 'http://localhost:9000/test-bucket/file.pdf?X-Amz-Signature=abc123'
        mock_client.generate_presigned_url.return_value = original_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/test/file.pdf',
            expires_in=3600
        )

        # Assert
        assert error is None
        assert url == original_url  # No modification

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_production_https(self, mock_boto3, mock_app):
        """Test URL replacement with production HTTPS domain."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'prod-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'https://documents.example.com',
            'S3_REGION': 'eu-west-1',
            'S3_ACCESS_KEY_ID': 'prod-key',
            'S3_SECRET_ACCESS_KEY': 'prod-secret',
            'S3_USE_SSL': True
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        internal_url = 'http://minio:9000/prod-bucket/tenants/acme/file.pdf?X-Amz-Signature=xyz789'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='tenants/acme/file.pdf',
            expires_in=7200
        )

        # Assert
        assert error is None
        assert url == 'https://documents.example.com/prod-bucket/tenants/acme/file.pdf?X-Amz-Signature=xyz789'
        assert 'minio:9000' not in url
        assert url.startswith('https://documents.example.com/')

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_missing_public_url(self, mock_boto3, mock_app):
        """Test behavior when S3_PUBLIC_URL is not configured (fallback to endpoint)."""
        # Setup - S3_PUBLIC_URL not in config
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            # S3_PUBLIC_URL missing - should fallback to S3_ENDPOINT_URL
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        internal_url = 'http://minio:9000/test-bucket/file.pdf?X-Amz-Signature=abc123'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='file.pdf',
            expires_in=3600
        )

        # Assert - should use internal URL (no replacement)
        assert error is None
        assert url == internal_url
        assert 'minio:9000' in url

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_with_content_disposition(self, mock_boto3, mock_app):
        """Test that URL replacement works with Content-Disposition parameter."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # URL with Content-Disposition parameter
        internal_url = 'http://minio:9000/test-bucket/file.pdf?response-content-disposition=attachment%3B%20filename%3D%22report.pdf%22&X-Amz-Signature=abc123'
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='file.pdf',
            expires_in=3600,
            response_content_disposition='attachment; filename="report.pdf"'
        )

        # Assert
        assert error is None
        assert 'localhost:9000' in url
        assert 'minio:9000' not in url
        assert 'response-content-disposition' in url
        assert 'report.pdf' in url

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_initialization_stores_public_url(self, mock_boto3, mock_app):
        """Test that S3Client correctly stores both endpoint and public URLs during initialization."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Execute
        s3_client = S3Client()
        s3_client._ensure_initialized()

        # Assert
        assert s3_client._endpoint_url == 'http://minio:9000'
        assert s3_client._public_url == 'http://localhost:9000'
        assert s3_client._bucket == 'test-bucket'

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_preserves_query_params(self, mock_boto3, mock_app):
        """Test that all query parameters are preserved after URL replacement."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Complex URL with multiple query parameters
        internal_url = (
            'http://minio:9000/test-bucket/file.pdf?'
            'X-Amz-Algorithm=AWS4-HMAC-SHA256&'
            'X-Amz-Credential=test%2F20240101%2Fus-east-1%2Fs3%2Faws4_request&'
            'X-Amz-Date=20240101T000000Z&'
            'X-Amz-Expires=3600&'
            'X-Amz-SignedHeaders=host&'
            'X-Amz-Signature=abc123def456'
        )
        mock_client.generate_presigned_url.return_value = internal_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='file.pdf',
            expires_in=3600
        )

        # Assert
        assert error is None
        assert url.startswith('http://localhost:9000/test-bucket/file.pdf?')
        assert 'X-Amz-Algorithm=AWS4-HMAC-SHA256' in url
        assert 'X-Amz-Credential=test' in url
        assert 'X-Amz-Date=20240101T000000Z' in url
        assert 'X-Amz-Expires=3600' in url
        assert 'X-Amz-SignedHeaders=host' in url
        assert 'X-Amz-Signature=abc123def456' in url

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_generate_presigned_url_error_handling(self, mock_boto3, mock_app):
        """Test error handling when boto3 client fails to generate URL."""
        # Setup
        mock_app.config = {
            'S3_BUCKET': 'test-bucket',
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Simulate boto3 error
        mock_client.generate_presigned_url.side_effect = Exception('S3 connection failed')

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='file.pdf',
            expires_in=3600
        )

        # Assert
        assert url is None
        assert error is not None
        assert 'Pre-signed URL generation failed' in error
        assert 'S3 connection failed' in error


class TestS3ClientBackwardCompatibility:
    """Test backward compatibility with existing S3 configurations."""

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_supports_s3_bucket_name_alias(self, mock_boto3, mock_app):
        """Test support for S3_BUCKET_NAME config key (backward compatibility)."""
        # Setup - using S3_BUCKET_NAME instead of S3_BUCKET
        mock_app.config = {
            'S3_BUCKET_NAME': 'legacy-bucket',  # Old config key
            'S3_ENDPOINT_URL': 'http://minio:9000',
            'S3_PUBLIC_URL': 'http://localhost:9000',
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'test',
            'S3_SECRET_ACCESS_KEY': 'test',
            'S3_USE_SSL': False
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # Execute
        s3_client = S3Client()
        s3_client._ensure_initialized()

        # Assert
        assert s3_client._bucket == 'legacy-bucket'

    @patch('app.utils.s3_client.current_app')
    @patch('app.utils.s3_client.boto3')
    def test_aws_s3_without_endpoint_url(self, mock_boto3, mock_app):
        """Test configuration for AWS S3 (no custom endpoint)."""
        # Setup - AWS S3 without custom endpoint
        mock_app.config = {
            'S3_BUCKET': 'aws-bucket',
            'S3_ENDPOINT_URL': None,  # AWS S3 doesn't use custom endpoint
            'S3_PUBLIC_URL': None,
            'S3_REGION': 'us-east-1',
            'S3_ACCESS_KEY_ID': 'aws-key',
            'S3_SECRET_ACCESS_KEY': 'aws-secret',
            'S3_USE_SSL': True
        }

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        # AWS S3 URL (no custom endpoint in URL)
        aws_url = 'https://aws-bucket.s3.amazonaws.com/file.pdf?X-Amz-Signature=abc123'
        mock_client.generate_presigned_url.return_value = aws_url

        # Execute
        s3_client = S3Client()
        url, error = s3_client.generate_presigned_url(
            s3_path='file.pdf',
            expires_in=3600
        )

        # Assert - URL should not be modified (no endpoint replacement needed)
        assert error is None
        assert url == aws_url
