"""
Integration Tests Package

This package contains integration tests that test complete flows and interactions
between multiple components:
- Auth flows: Complete registration and login flows
- Tenant operations: Tenant creation with database provisioning
- Document operations: File upload, storage, and retrieval
- Multi-tenancy: Data isolation between tenants

Integration tests use real database connections but mock external services (S3, Kafka).
"""
