"""
Document Model (Tenant Database)

This module defines the Document model for storing document metadata in tenant databases.
Documents represent user-facing files with metadata, while the actual file content
is stored in S3 and referenced via the File model.

Key features:
- Stored in tenant-specific databases (NOT main database)
- Many-to-one relationship with File (multiple documents can reference same file)
- Cross-database user reference (user_id references user in main database)
- Supports file deduplication (multiple documents can share the same physical file)
- Metadata includes filename, MIME type, and ownership information

Storage strategy:
- Document metadata: stored in tenant database (e.g., tenant_acme_corp_a1b2c3d4)
- File content: stored in AWS S3, referenced via File model
- User ownership: user_id references user in main database (cross-database reference)

Example use case:
  User A uploads "report.pdf" (MD5: abc123)
  User B uploads "report.pdf" (same file, MD5: abc123)
  Result: 2 Document records, 1 File record, 1 S3 object
"""

import re
import logging
from typing import Optional, List
from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import BaseModel
from ..extensions import db

logger = logging.getLogger(__name__)


class Document(BaseModel, db.Model):
    """
    Document model representing user documents with metadata (tenant database).

    Each document represents a user-uploaded file with its metadata.
    Multiple documents can reference the same physical file (via file_id)
    for deduplication purposes.

    Attributes:
        filename (str): User-provided filename (e.g., "report.pdf")
        mime_type (str): MIME type of the file (e.g., "application/pdf")
        file_id (UUID): Foreign key to File model (the actual file in S3)
        user_id (UUID): User who owns this document (references main database)

    Relationships:
        file: Many-to-one relationship with File model

    Inherited from BaseModel:
        id (UUID): Primary key
        created_at (datetime): Upload timestamp (UTC)
        updated_at (datetime): Last update timestamp (UTC)
        created_by (UUID): User who created this document

    Cross-database reference:
        user_id references users.id in the main database, but SQLAlchemy
        doesn't enforce this foreign key since they're in different databases.
        Application code must ensure referential integrity.
    """

    __tablename__ = 'documents'
    __bind_key__ = None  # Dynamic binding to tenant database

    # Fields
    filename = db.Column(String(255), nullable=False)
    mime_type = db.Column(String(100), nullable=False)
    file_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey('files.id', ondelete='RESTRICT'),
        nullable=False
    )
    user_id = db.Column(UUID(as_uuid=True), nullable=False)  # Cross-DB reference

    # Relationships
    file = relationship('File', back_populates='documents')

    # Indexes for common queries
    __table_args__ = (
        Index('ix_documents_filename', 'filename'),
        Index('ix_documents_file_id', 'file_id'),
        Index('ix_documents_user_id', 'user_id'),
        Index('ix_documents_user_filename', 'user_id', 'filename'),
        Index('ix_documents_created_at', 'created_at'),
    )

    def __init__(self, **kwargs):
        """
        Initialize a new document record.

        Args:
            filename: User-provided filename
            mime_type: MIME type of the file
            file_id: UUID of the associated File record
            user_id: UUID of the user who owns this document
            created_by: UUID of user who created this document (usually same as user_id)

        Raises:
            ValueError: If filename is empty or mime_type is invalid
        """
        # Validate filename
        if 'filename' in kwargs:
            filename = kwargs['filename']
            if not filename or not filename.strip():
                raise ValueError("Filename cannot be empty")

        # Validate MIME type
        if 'mime_type' in kwargs:
            mime_type = kwargs['mime_type']
            if not self._is_valid_mime_type(mime_type):
                raise ValueError(
                    f"Invalid MIME type format: {mime_type}. "
                    "Must be in format 'type/subtype' (e.g., 'application/pdf')"
                )

        super().__init__(**kwargs)
        logger.info(
            f"Document object initialized: filename={self.filename}, "
            f"mime_type={self.mime_type}, file_id={self.file_id}, user_id={self.user_id}"
        )

    @staticmethod
    def _is_valid_mime_type(mime_type: str) -> bool:
        """
        Validate MIME type format.

        Args:
            mime_type: String to validate

        Returns:
            True if valid MIME type format, False otherwise

        Examples:
            "application/pdf" -> True
            "image/png" -> True
            "text/plain" -> True
            "invalid" -> False
        """
        if not isinstance(mime_type, str):
            return False
        # Basic MIME type validation: type/subtype
        return bool(re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*/[a-zA-Z0-9][a-zA-Z0-9\-\+\.]*$', mime_type))

    def get_download_url(self, expiration: int = 3600) -> str:
        """
        Generate a pre-signed URL for downloading this document.

        This delegates to the associated File's get_s3_url() method.

        Args:
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Pre-signed S3 URL for downloading the file

        Example:
            document = Document.query.first()
            url = document.get_download_url(expiration=7200)  # 2 hours
            # User can download file from this URL
        """
        if not self.file:
            logger.error(f"Document {self.id} has no associated file")
            raise ValueError(f"Document {self.id} has no associated file")

        logger.debug(f"Generating download URL for document {self.id} (file {self.file_id})")
        return self.file.get_s3_url(expiration=expiration)

    def get_owner(self):
        """
        Fetch the user who owns this document from the main database.

        This is a cross-database query - the Document is in a tenant database
        while the User is in the main database.

        Returns:
            User object if found, None otherwise

        Note:
            This requires switching database context. In production, this should
            be implemented in the service layer with proper session management.

        Example:
            document = Document.query.first()
            owner = document.get_owner()
            print(f"Owner: {owner.get_full_name()}")
        """
        from .user import User

        # TODO: This requires proper session management across databases
        # For now, we use the default session which may not work correctly
        # This should be implemented in the service layer
        logger.debug(f"Fetching owner for document {self.id}: user_id={self.user_id}")

        try:
            owner = User.query.filter_by(id=self.user_id).first()
            return owner
        except Exception as e:
            logger.error(f"Error fetching owner for document {self.id}: {str(e)}")
            return None

    def update_metadata(self, filename: Optional[str] = None, mime_type: Optional[str] = None) -> None:
        """
        Update document metadata (filename and/or MIME type).

        Note: This does NOT change the underlying file, only the metadata.
        The file_id and actual file content remain unchanged.

        Args:
            filename: New filename (optional)
            mime_type: New MIME type (optional)

        Raises:
            ValueError: If filename is empty or mime_type is invalid

        Example:
            document = Document.query.first()
            document.update_metadata(filename="updated_report.pdf")
            db.session.commit()
        """
        if filename is not None:
            if not filename or not filename.strip():
                raise ValueError("Filename cannot be empty")
            logger.info(f"Updating document {self.id} filename: {self.filename} -> {filename}")
            self.filename = filename.strip()

        if mime_type is not None:
            if not self._is_valid_mime_type(mime_type):
                raise ValueError(
                    f"Invalid MIME type format: {mime_type}. "
                    "Must be in format 'type/subtype' (e.g., 'application/pdf')"
                )
            logger.info(f"Updating document {self.id} MIME type: {self.mime_type} -> {mime_type}")
            self.mime_type = mime_type

        # Note: Caller is responsible for committing the transaction
        logger.debug(f"Document {self.id} metadata updated")

    def get_file_size(self) -> int:
        """
        Get the size of the underlying file in bytes.

        Returns:
            File size in bytes

        Example:
            document = Document.query.first()
            size_mb = document.get_file_size() / (1024 * 1024)
            print(f"File size: {size_mb:.2f} MB")
        """
        if not self.file:
            logger.error(f"Document {self.id} has no associated file")
            return 0
        return self.file.file_size

    def get_file_hash(self) -> str:
        """
        Get the MD5 hash of the underlying file.

        Returns:
            MD5 hash (32 hex characters)

        Example:
            document = Document.query.first()
            print(f"File hash: {document.get_file_hash()}")
        """
        if not self.file:
            logger.error(f"Document {self.id} has no associated file")
            return ""
        return self.file.md5_hash

    @classmethod
    def find_by_filename(cls, filename: str, user_id: Optional[str] = None) -> List['Document']:
        """
        Find documents by filename (exact match).

        Args:
            filename: Filename to search for
            user_id: Optional user ID to filter by owner

        Returns:
            List of Document objects matching the criteria

        Example:
            # Find all documents named "report.pdf"
            docs = Document.find_by_filename("report.pdf")

            # Find user's documents named "report.pdf"
            docs = Document.find_by_filename("report.pdf", user_id=user.id)
        """
        query = cls.query.filter_by(filename=filename)
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.all()

    @classmethod
    def find_by_user(cls, user_id: str) -> List['Document']:
        """
        Find all documents owned by a specific user.

        Args:
            user_id: User's UUID

        Returns:
            List of Document objects owned by the user

        Example:
            user_docs = Document.find_by_user(user_id)
            print(f"User has {len(user_docs)} documents")
        """
        return cls.query.filter_by(user_id=user_id).order_by(cls.created_at.desc()).all()

    @classmethod
    def count_by_user(cls, user_id: str) -> int:
        """
        Count documents owned by a specific user.

        Args:
            user_id: User's UUID

        Returns:
            Number of documents owned by the user

        Example:
            count = Document.count_by_user(user_id)
            print(f"User has {count} documents")
        """
        return cls.query.filter_by(user_id=user_id).count()

    @classmethod
    def find_by_file(cls, file_id: str) -> List['Document']:
        """
        Find all documents referencing a specific file.

        This is useful for understanding file deduplication - showing
        how many documents share the same physical file.

        Args:
            file_id: File's UUID

        Returns:
            List of Document objects referencing this file

        Example:
            documents = Document.find_by_file(file_id)
            print(f"{len(documents)} documents share this file")
        """
        return cls.query.filter_by(file_id=file_id).all()

    @classmethod
    def count_by_file(cls, file_id: str) -> int:
        """
        Count documents referencing a specific file.

        Args:
            file_id: File's UUID

        Returns:
            Number of documents referencing this file

        Example:
            count = Document.count_by_file(file_id)
            if count == 0:
                print("File is orphaned and can be deleted")
        """
        return cls.query.filter_by(file_id=file_id).count()

    @classmethod
    def search_by_filename(cls, pattern: str, user_id: Optional[str] = None) -> List['Document']:
        """
        Search documents by filename pattern (case-insensitive).

        Args:
            pattern: Search pattern (SQL LIKE syntax, use % for wildcard)
            user_id: Optional user ID to filter by owner

        Returns:
            List of Document objects matching the pattern

        Example:
            # Find all PDF documents
            pdfs = Document.search_by_filename("%.pdf")

            # Find user's documents starting with "report"
            reports = Document.search_by_filename("report%", user_id=user.id)
        """
        query = cls.query.filter(cls.filename.ilike(pattern))
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(cls.created_at.desc()).all()

    @classmethod
    def get_recent(cls, limit: int = 10, user_id: Optional[str] = None) -> List['Document']:
        """
        Get most recent documents.

        Args:
            limit: Maximum number of documents to return
            user_id: Optional user ID to filter by owner

        Returns:
            List of Document objects ordered by creation time (newest first)

        Example:
            # Get 10 most recent documents in tenant
            recent = Document.get_recent(limit=10)

            # Get user's 5 most recent documents
            my_recent = Document.get_recent(limit=5, user_id=user.id)
        """
        query = cls.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.order_by(cls.created_at.desc()).limit(limit).all()

    def to_dict(self, exclude: List[str] = None, include_file: bool = False) -> dict:
        """
        Convert document to dictionary for JSON serialization.

        Args:
            exclude: List of fields to exclude from output
            include_file: If True, include file details in output

        Returns:
            Dictionary representation of the document

        Example:
            document = Document.query.first()
            data = document.to_dict(include_file=True)
            # {
            #   "id": "...",
            #   "filename": "report.pdf",
            #   "mime_type": "application/pdf",
            #   "file_id": "...",
            #   "user_id": "...",
            #   "created_at": "2024-01-01T00:00:00Z",
            #   "file": {
            #     "md5_hash": "...",
            #     "file_size": 1234567
            #   }
            # }
        """
        data = super().to_dict(exclude=exclude)

        if include_file and self.file:
            data['file'] = {
                'md5_hash': self.file.md5_hash,
                's3_path': self.file.s3_path,
                'file_size': self.file.file_size,
                'created_at': self.file.created_at.isoformat() if self.file.created_at else None
            }

        return data

    def before_insert(self) -> None:
        """
        Lifecycle hook called before inserting a new document.

        Validates that:
        - Filename is not empty
        - MIME type is valid format
        - file_id references an existing file (should be validated by FK)
        - user_id is provided
        """
        super().before_insert()

        # Validate filename
        if not self.filename or not self.filename.strip():
            raise ValueError("Filename cannot be empty")

        # Normalize filename (strip whitespace)
        self.filename = self.filename.strip()

        # Validate MIME type
        if not self._is_valid_mime_type(self.mime_type):
            raise ValueError(
                f"Invalid MIME type format: {self.mime_type}. "
                "Must be in format 'type/subtype' (e.g., 'application/pdf')"
            )

        # Validate user_id is provided
        if not self.user_id:
            raise ValueError("user_id is required")

        # Validate file_id is provided
        if not self.file_id:
            raise ValueError("file_id is required")

        logger.debug(f"Document pre-insert validation passed: {self.filename}")

    def before_update(self) -> None:
        """
        Lifecycle hook called before updating a document.

        Prevents changing critical fields after creation:
        - file_id (immutable - document always references same file)
        - user_id (immutable - ownership cannot be transferred)
        """
        super().before_update()

        # Prevent file_id changes
        if db.session.is_modified(self, include_collections=False):
            changes = db.session.dirty
            if self in changes:
                # Check if file_id was changed
                file_id_history = db.inspect(self).attrs.file_id.history
                if file_id_history.has_changes():
                    raise ValueError(
                        "Cannot change file_id after document creation. "
                        "Create a new document instead."
                    )

                # Check if user_id was changed
                user_id_history = db.inspect(self).attrs.user_id.history
                if user_id_history.has_changes():
                    raise ValueError(
                        "Cannot change user_id after document creation. "
                        "Document ownership cannot be transferred."
                    )

        # Validate filename if changed
        if self.filename and not self.filename.strip():
            raise ValueError("Filename cannot be empty")

        logger.debug(f"Document pre-update validation passed: {self.filename}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Document(id={self.id}, filename='{self.filename}', "
            f"mime_type='{self.mime_type}', file_id={self.file_id}, user_id={self.user_id})>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"Document '{self.filename}' ({self.mime_type})"
