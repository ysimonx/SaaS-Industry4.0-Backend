"""
Unit Tests for Service Layer

Tests for business logic services with mocked dependencies:
- AuthService: User registration, login, token management
- UserService: User CRUD operations
- TenantService: Tenant management and user associations
- DocumentService: Document upload and management
- FileService: File storage and deduplication
- KafkaService: Message production and consumption

All tests mock external dependencies (database, S3, Kafka)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timedelta
import uuid

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.tenant_service import TenantService
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.kafka_service import KafkaService
from app.models import User, Tenant, UserTenantAssociation, Document, File


class TestAuthService:
    """Tests for AuthService"""

    @patch('app.services.auth_service.User')
    @patch('app.services.auth_service.db')
    def test_register_success(self, mock_db, mock_user_class):
        """Test successful user registration"""
        # Setup mock
        mock_user = Mock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user.email = 'test@example.com'
        mock_user_class.query.filter_by.return_value.first.return_value = None  # No existing user
        mock_user_class.return_value = mock_user

        user_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123',
            'first_name': 'John',
            'last_name': 'Doe'
        }

        # Execute
        result_user, error = AuthService.register(user_data)

        # Assert
        assert error is None
        assert result_user == mock_user
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch('app.services.auth_service.User')
    def test_register_duplicate_email(self, mock_user_class):
        """Test registration fails with duplicate email"""
        # Setup mock - existing user found
        existing_user = Mock(spec=User)
        mock_user_class.query.filter_by.return_value.first.return_value = existing_user

        user_data = {
            'email': 'existing@example.com',
            'password': 'SecurePass123',
            'first_name': 'John',
            'last_name': 'Doe'
        }

        # Execute
        result_user, error = AuthService.register(user_data)

        # Assert
        assert result_user is None
        assert error is not None
        assert 'already exists' in error.lower() or 'duplicate' in error.lower()

    @patch('app.services.auth_service.User')
    @patch('app.services.auth_service.create_access_token')
    @patch('app.services.auth_service.create_refresh_token')
    def test_login_success(self, mock_refresh_token, mock_access_token, mock_user_class):
        """Test successful login"""
        # Setup mocks
        mock_user = Mock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user.email = 'test@example.com'
        mock_user.is_active = True
        mock_user.check_password.return_value = True

        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        mock_access_token.return_value = 'access_token_123'
        mock_refresh_token.return_value = 'refresh_token_456'

        # Execute
        result = AuthService.login('test@example.com', 'correct_password')

        # Assert
        assert result['user'] == mock_user
        assert result['access_token'] == 'access_token_123'
        assert result['refresh_token'] == 'refresh_token_456'
        assert result['error'] is None

    @patch('app.services.auth_service.User')
    def test_login_invalid_credentials(self, mock_user_class):
        """Test login fails with invalid credentials"""
        # Setup mock - user found but password wrong
        mock_user = Mock(spec=User)
        mock_user.check_password.return_value = False
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user

        # Execute
        result = AuthService.login('test@example.com', 'wrong_password')

        # Assert
        assert result['user'] is None
        assert result['error'] is not None
        assert 'invalid' in result['error'].lower()

    @patch('app.services.auth_service.User')
    def test_login_inactive_account(self, mock_user_class):
        """Test login fails with inactive account"""
        # Setup mock
        mock_user = Mock(spec=User)
        mock_user.is_active = False
        mock_user.check_password.return_value = True
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user

        # Execute
        result = AuthService.login('test@example.com', 'correct_password')

        # Assert
        assert result['user'] is None
        assert result['error'] is not None
        assert 'inactive' in result['error'].lower() or 'deactivated' in result['error'].lower()

    def test_blacklist_token(self):
        """Test token blacklisting"""
        jti = 'test_jti_123'

        # Execute
        AuthService.blacklist_token(jti)

        # Assert
        assert AuthService.is_token_blacklisted(jti) is True

    def test_is_token_blacklisted(self):
        """Test token blacklist checking"""
        jti = 'another_jti_456'

        # Initially not blacklisted
        assert AuthService.is_token_blacklisted(jti) is False

        # After blacklisting
        AuthService.blacklist_token(jti)
        assert AuthService.is_token_blacklisted(jti) is True


class TestUserService:
    """Tests for UserService"""

    @patch('app.services.user_service.User')
    def test_get_user_by_id(self, mock_user_class):
        """Test getting user by ID"""
        mock_user = Mock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user_class.query.get.return_value = mock_user

        # Execute
        result = UserService.get_user_by_id(str(mock_user.id))

        # Assert
        assert result == mock_user
        mock_user_class.query.get.assert_called_once()

    @patch('app.services.user_service.User')
    @patch('app.services.user_service.db')
    def test_update_user(self, mock_db, mock_user_class):
        """Test updating user profile"""
        mock_user = Mock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user_class.query.get.return_value = mock_user

        update_data = {
            'first_name': 'Jane',
            'last_name': 'Updated'
        }

        # Execute
        result, error = UserService.update_user(str(mock_user.id), update_data)

        # Assert
        assert error is None
        assert result == mock_user
        assert mock_user.first_name == 'Jane'
        assert mock_user.last_name == 'Updated'
        mock_db.session.commit.assert_called_once()

    @patch('app.services.user_service.User')
    def test_get_user_not_found(self, mock_user_class):
        """Test getting non-existent user"""
        mock_user_class.query.get.return_value = None

        # Execute
        result = UserService.get_user_by_id('non_existent_id')

        # Assert
        assert result is None


class TestTenantService:
    """Tests for TenantService"""

    @patch('app.services.tenant_service.Tenant')
    @patch('app.services.tenant_service.UserTenantAssociation')
    @patch('app.services.tenant_service.tenant_db_manager')
    @patch('app.services.tenant_service.db')
    def test_create_tenant(self, mock_db, mock_db_manager, mock_assoc_class, mock_tenant_class):
        """Test creating a new tenant"""
        # Setup mocks
        mock_tenant = Mock(spec=Tenant)
        mock_tenant.id = uuid.uuid4()
        mock_tenant.name = 'Test Company'
        mock_tenant.database_name = 'tenant_test_company_abc123'
        mock_tenant_class.return_value = mock_tenant

        user_id = uuid.uuid4()

        # Execute
        result, error = TenantService.create_tenant('Test Company', str(user_id))

        # Assert
        assert error is None
        assert result == mock_tenant
        mock_db.session.add.assert_called()
        mock_db.session.commit.assert_called()
        mock_db_manager.create_tenant_database.assert_called_once()
        mock_db_manager.create_tenant_tables.assert_called_once()

    @patch('app.services.tenant_service.Tenant')
    def test_get_tenant_by_id(self, mock_tenant_class):
        """Test getting tenant by ID"""
        mock_tenant = Mock(spec=Tenant)
        mock_tenant.id = uuid.uuid4()
        mock_tenant_class.query.get.return_value = mock_tenant

        # Execute
        result = TenantService.get_tenant_by_id(str(mock_tenant.id))

        # Assert
        assert result == mock_tenant

    @patch('app.services.tenant_service.UserTenantAssociation')
    def test_get_user_role_in_tenant(self, mock_assoc_class):
        """Test getting user's role in tenant"""
        mock_assoc = Mock(spec=UserTenantAssociation)
        mock_assoc.role = 'admin'
        mock_assoc_class.query.filter_by.return_value.first.return_value = mock_assoc

        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        # Execute
        role = TenantService.get_user_role(user_id, tenant_id)

        # Assert
        assert role == 'admin'

    @patch('app.services.tenant_service.UserTenantAssociation')
    @patch('app.services.tenant_service.db')
    def test_add_user_to_tenant(self, mock_db, mock_assoc_class):
        """Test adding user to tenant"""
        mock_assoc = Mock(spec=UserTenantAssociation)
        mock_assoc_class.return_value = mock_assoc
        mock_assoc_class.query.filter_by.return_value.first.return_value = None  # No existing

        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        # Execute
        result, error = TenantService.add_user_to_tenant(user_id, tenant_id, 'user')

        # Assert
        assert error is None
        assert result == mock_assoc
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()


class TestDocumentService:
    """Tests for DocumentService"""

    @patch('app.services.document_service.Document')
    @patch('app.services.document_service.File')
    @patch('app.services.document_service.FileService')
    @patch('app.services.document_service.tenant_db_manager')
    def test_create_document(self, mock_db_manager, mock_file_service, mock_file_class, mock_doc_class):
        """Test creating a document"""
        # Setup mocks
        mock_file = Mock(spec=File)
        mock_file.id = uuid.uuid4()
        mock_file_service.create_or_get_file.return_value = (mock_file, None)

        mock_doc = Mock(spec=Document)
        mock_doc.id = uuid.uuid4()
        mock_doc_class.return_value = mock_doc

        mock_session = Mock()
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Execute
        file_data = {
            'content': b'test content',
            'md5_hash': 'a' * 32
        }
        result, error = DocumentService.create_document(
            tenant_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            filename='test.pdf',
            mime_type='application/pdf',
            file_data=file_data
        )

        # Assert
        assert error is None
        assert result == mock_doc
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch('app.services.document_service.Document')
    @patch('app.services.document_service.tenant_db_manager')
    def test_get_document_by_id(self, mock_db_manager, mock_doc_class):
        """Test getting document by ID"""
        mock_doc = Mock(spec=Document)
        mock_session = Mock()
        mock_session.query.return_value.get.return_value = mock_doc
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Execute
        result = DocumentService.get_document_by_id('tenant_123', str(uuid.uuid4()))

        # Assert
        assert result == mock_doc

    @patch('app.services.document_service.Document')
    @patch('app.services.document_service.tenant_db_manager')
    def test_list_documents_with_pagination(self, mock_db_manager, mock_doc_class):
        """Test listing documents with pagination"""
        mock_docs = [Mock(spec=Document) for _ in range(3)]
        mock_query = Mock()
        mock_query.count.return_value = 10
        mock_query.offset.return_value.limit.return_value.all.return_value = mock_docs

        mock_session = Mock()
        mock_session.query.return_value = mock_query
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Execute
        result = DocumentService.list_documents('tenant_123', page=1, per_page=3)

        # Assert
        assert result['documents'] == mock_docs
        assert result['total'] == 10
        assert result['page'] == 1
        assert result['per_page'] == 3


class TestFileService:
    """Tests for FileService"""

    @patch('app.services.file_service.boto3')
    def test_upload_to_s3(self, mock_boto3):
        """Test uploading file to S3"""
        # Setup mock
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        file_content = b'test file content'
        s3_path = 'tenant_123/files/ab/cd/abcd...'

        # Execute
        result, error = FileService.upload_to_s3(file_content, s3_path)

        # Assert
        assert error is None
        assert result is True
        mock_s3_client.upload_fileobj.assert_called_once()

    @patch('app.services.file_service.boto3')
    def test_delete_from_s3(self, mock_boto3):
        """Test deleting file from S3"""
        # Setup mock
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        s3_path = 'tenant_123/files/test.pdf'

        # Execute
        result, error = FileService.delete_from_s3(s3_path)

        # Assert
        assert error is None
        assert result is True
        mock_s3_client.delete_object.assert_called_once()

    def test_calculate_md5(self):
        """Test MD5 hash calculation"""
        file_content = b'test content'

        # Execute
        md5_hash = FileService.calculate_md5(file_content)

        # Assert
        assert md5_hash is not None
        assert len(md5_hash) == 32  # MD5 hash is 32 hex characters
        assert md5_hash.isalnum()

    def test_generate_s3_path(self):
        """Test S3 path generation with sharding"""
        tenant_id = str(uuid.uuid4())
        md5_hash = 'abcd1234' + 'x' * 24  # 32 char hash

        # Execute
        s3_path = FileService.generate_s3_path(tenant_id, md5_hash)

        # Assert
        assert f'tenants/{tenant_id}' in s3_path
        assert 'files/' in s3_path
        assert md5_hash in s3_path
        # Check sharding (first 2 and next 2 chars)
        assert 'ab/cd/' in s3_path

    @patch('app.services.file_service.File')
    @patch('app.services.file_service.tenant_db_manager')
    def test_check_file_exists_by_md5(self, mock_db_manager, mock_file_class):
        """Test checking if file exists by MD5"""
        mock_file = Mock(spec=File)
        mock_session = Mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_file
        mock_db_manager.tenant_db_session.return_value.__enter__.return_value = mock_session

        # Execute
        result = FileService.get_file_by_md5('tenant_123', 'a' * 32)

        # Assert
        assert result == mock_file


class TestKafkaService:
    """Tests for KafkaService"""

    @patch('app.services.kafka_service.KafkaProducer')
    def test_send_message(self, mock_producer_class):
        """Test sending Kafka message"""
        # Setup mock
        mock_producer = Mock()
        mock_future = Mock()
        mock_future.get.return_value = None
        mock_producer.send.return_value = mock_future
        mock_producer_class.return_value = mock_producer

        topic = 'test.topic'
        message = {'event': 'test', 'data': 'value'}

        # Execute
        result, error = KafkaService.send_message(topic, message)

        # Assert
        assert error is None
        assert result is True
        mock_producer.send.assert_called_once()

    @patch('app.services.kafka_service.KafkaProducer')
    def test_send_message_with_key(self, mock_producer_class):
        """Test sending Kafka message with partition key"""
        mock_producer = Mock()
        mock_future = Mock()
        mock_future.get.return_value = None
        mock_producer.send.return_value = mock_future
        mock_producer_class.return_value = mock_producer

        topic = 'test.topic'
        message = {'event': 'test'}
        key = 'partition_key_123'

        # Execute
        result, error = KafkaService.send_message(topic, message, key=key)

        # Assert
        assert error is None
        mock_producer.send.assert_called_with(
            topic,
            value=message,
            key=key.encode() if isinstance(key, str) else key
        )

    def test_format_event_message(self):
        """Test event message formatting"""
        event_type = 'document.uploaded'
        payload = {'document_id': '123', 'filename': 'test.pdf'}

        # Execute
        formatted = KafkaService.format_event_message(event_type, payload)

        # Assert
        assert formatted['event_type'] == event_type
        assert formatted['payload'] == payload
        assert 'timestamp' in formatted
        assert 'event_id' in formatted


class TestServiceErrorHandling:
    """Tests for service error handling"""

    @patch('app.services.auth_service.db')
    def test_register_handles_database_error(self, mock_db):
        """Test registration handles database errors gracefully"""
        mock_db.session.commit.side_effect = Exception('Database error')

        user_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123',
            'first_name': 'John',
            'last_name': 'Doe'
        }

        # Execute - should not raise exception
        result_user, error = AuthService.register(user_data)

        # Assert
        assert result_user is None
        assert error is not None

    @patch('app.services.file_service.boto3')
    def test_upload_handles_s3_error(self, mock_boto3):
        """Test S3 upload handles errors gracefully"""
        mock_s3_client = Mock()
        mock_s3_client.upload_fileobj.side_effect = Exception('S3 error')
        mock_boto3.client.return_value = mock_s3_client

        # Execute - should not raise exception
        result, error = FileService.upload_to_s3(b'content', 's3_path')

        # Assert
        assert result is False
        assert error is not None
