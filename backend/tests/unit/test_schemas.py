"""
Unit Tests for Marshmallow Schemas

Tests for validation schemas including:
- UserSchema: User data validation
- TenantSchema: Tenant data validation
- DocumentSchema: Document data validation
- Field validation and normalization
- Error handling for invalid data
"""

import pytest
from marshmallow import ValidationError

from app.schemas import (
    user_create_schema,
    user_update_schema,
    user_login_schema,
    tenant_create_schema,
    tenant_update_schema,
    document_upload_schema,
    document_update_schema
)


class TestUserSchemas:
    """Tests for User schemas"""

    def test_user_create_valid_data(self):
        """Test user creation with valid data"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@example.com',
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        assert result['first_name'] == 'John'
        assert result['last_name'] == 'Doe'
        assert result['email'] == 'john.doe@example.com'
        assert result['password'] == 'SecurePass123'

    def test_user_create_missing_fields(self):
        """Test user creation fails with missing required fields"""
        data = {
            'first_name': 'John'
            # Missing last_name, email, password
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'last_name' in errors or 'email' in errors

    def test_user_create_invalid_email(self):
        """Test user creation fails with invalid email"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'not-an-email',  # Invalid email
            'password': 'SecurePass123'
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'email' in errors

    def test_user_create_weak_password(self):
        """Test user creation fails with weak password"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': 'weak'  # Too short, no numbers
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'password' in errors

    def test_user_create_password_no_letter(self):
        """Test password must contain at least one letter"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': '12345678'  # Only numbers
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'password' in errors

    def test_user_create_password_no_number(self):
        """Test password must contain at least one number"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': 'onlyletters'  # No numbers
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'password' in errors

    def test_user_create_email_normalization(self):
        """Test email is normalized to lowercase"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'John.Doe@EXAMPLE.COM',  # Mixed case
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        # Email should be normalized to lowercase
        assert result['email'] == 'john.doe@example.com'

    def test_user_create_name_trimming(self):
        """Test names are trimmed of whitespace"""
        data = {
            'first_name': '  John  ',
            'last_name': '  Doe  ',
            'email': 'john@example.com',
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        assert result['first_name'] == 'John'
        assert result['last_name'] == 'Doe'

    def test_user_update_optional_fields(self):
        """Test user update with optional fields"""
        data = {
            'first_name': 'Jane'
            # last_name is optional
        }

        result = user_update_schema.load(data)

        assert result['first_name'] == 'Jane'
        assert 'last_name' not in result

    def test_user_update_empty_data(self):
        """Test user update with no data is valid"""
        data = {}

        result = user_update_schema.load(data)

        assert result == {}

    def test_user_login_valid_data(self):
        """Test login schema with valid data"""
        data = {
            'email': 'john@example.com',
            'password': 'SecurePass123'
        }

        result = user_login_schema.load(data)

        assert result['email'] == 'john@example.com'
        assert result['password'] == 'SecurePass123'

    def test_user_login_missing_fields(self):
        """Test login fails with missing fields"""
        data = {
            'email': 'john@example.com'
            # Missing password
        }

        with pytest.raises(ValidationError) as exc_info:
            user_login_schema.load(data)

        errors = exc_info.value.messages
        assert 'password' in errors


class TestTenantSchemas:
    """Tests for Tenant schemas"""

    def test_tenant_create_valid_data(self):
        """Test tenant creation with valid data"""
        data = {
            'name': 'Acme Corporation'
        }

        result = tenant_create_schema.load(data)

        assert result['name'] == 'Acme Corporation'

    def test_tenant_create_missing_name(self):
        """Test tenant creation fails without name"""
        data = {}

        with pytest.raises(ValidationError) as exc_info:
            tenant_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'name' in errors

    def test_tenant_create_empty_name(self):
        """Test tenant creation fails with empty name"""
        data = {
            'name': ''
        }

        with pytest.raises(ValidationError) as exc_info:
            tenant_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'name' in errors

    def test_tenant_create_whitespace_name(self):
        """Test tenant creation fails with whitespace-only name"""
        data = {
            'name': '   '
        }

        with pytest.raises(ValidationError) as exc_info:
            tenant_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'name' in errors

    def test_tenant_create_name_too_long(self):
        """Test tenant creation fails with name too long"""
        data = {
            'name': 'A' * 256  # Over 255 character limit
        }

        with pytest.raises(ValidationError) as exc_info:
            tenant_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'name' in errors

    def test_tenant_create_name_trimming(self):
        """Test tenant name is trimmed"""
        data = {
            'name': '  Test Company  '
        }

        result = tenant_create_schema.load(data)

        assert result['name'] == 'Test Company'

    def test_tenant_update_optional_name(self):
        """Test tenant update with optional name"""
        data = {
            'name': 'New Company Name'
        }

        result = tenant_update_schema.load(data)

        assert result['name'] == 'New Company Name'

    def test_tenant_update_empty_data(self):
        """Test tenant update with no data"""
        data = {}

        result = tenant_update_schema.load(data)

        assert result == {}


class TestDocumentSchemas:
    """Tests for Document schemas"""

    def test_document_update_valid_filename(self):
        """Test document update with valid filename"""
        data = {
            'filename': 'updated_document.pdf'
        }

        result = document_update_schema.load(data)

        assert result['filename'] == 'updated_document.pdf'

    def test_document_update_empty_filename(self):
        """Test document update fails with empty filename"""
        data = {
            'filename': ''
        }

        with pytest.raises(ValidationError) as exc_info:
            document_update_schema.load(data)

        errors = exc_info.value.messages
        assert 'filename' in errors

    def test_document_update_filename_too_long(self):
        """Test document update fails with filename too long"""
        data = {
            'filename': 'A' * 256  # Over 255 character limit
        }

        with pytest.raises(ValidationError) as exc_info:
            document_update_schema.load(data)

        errors = exc_info.value.messages
        assert 'filename' in errors

    def test_document_update_optional_fields(self):
        """Test document update with optional data"""
        data = {}

        result = document_update_schema.load(data)

        assert result == {}


class TestSchemaValidationEdgeCases:
    """Tests for schema edge cases"""

    def test_extra_fields_ignored(self):
        """Test that extra unknown fields are ignored"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': 'SecurePass123',
            'unknown_field': 'should be ignored'
        }

        # Schema should ignore unknown fields
        result = user_create_schema.load(data)

        assert 'unknown_field' not in result

    def test_null_values(self):
        """Test handling of null values"""
        data = {
            'first_name': None,
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': 'SecurePass123'
        }

        with pytest.raises(ValidationError) as exc_info:
            user_create_schema.load(data)

        errors = exc_info.value.messages
        assert 'first_name' in errors

    def test_unicode_characters(self):
        """Test handling of unicode characters"""
        data = {
            'first_name': 'François',
            'last_name': 'Müller',
            'email': 'francois@example.com',
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        assert result['first_name'] == 'François'
        assert result['last_name'] == 'Müller'

    def test_special_characters_in_email(self):
        """Test email with special characters"""
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe+test@example.co.uk',
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        assert result['email'] == 'john.doe+test@example.co.uk'

    def test_very_long_valid_email(self):
        """Test validation of long but valid email"""
        long_local = 'a' * 64  # Max local part length
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': f'{long_local}@example.com',
            'password': 'SecurePass123'
        }

        result = user_create_schema.load(data)

        assert '@example.com' in result['email']
