"""
File Model (Tenant Database)

This module defines the File model for storing physical file metadata in tenant databases.
Files are stored in AWS S3 and deduplicated within each tenant using MD5 hashes.

Key features:
- MD5-based deduplication within tenant (same file uploaded multiple times = single S3 object)
- Stored in tenant-specific databases (NOT main database)
- One File can be referenced by multiple Documents
- S3 path stores the actual location in cloud storage
- Tracks file size for storage management and quotas
- Orphan detection for cleanup of unreferenced files

Storage strategy:
- File metadata: stored in tenant database (e.g., tenant_acme_corp_a1b2c3d4)
- File content: stored in AWS S3
- Deduplication: by MD5 hash within tenant boundary

S3 Path format:
  tenants/{database_name}/files/{md5_hash[:2]}/{md5_hash[2:4]}/{md5_hash}_{uuid}
  Example: tenants/tenant_iter_45fca42c/files/3a/c5/3ac5f2e8a1b4c6d7e8f9a0b1c2d3e4f5_def-456
"""

import re
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import String, BigInteger, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import BaseModel
from ..extensions import db

logger = logging.getLogger(__name__)


class File(BaseModel, db.Model):
    """
    File model representing physical files stored in S3 (tenant database).

    Each file represents a unique piece of content identified by its MD5 hash.
    Multiple documents can reference the same file (many-to-one relationship).
    Files are deduplicated within each tenant to save storage space.

    Attributes:
        md5_hash (str): MD5 hash of file content (32 hex chars, unique within tenant)
        s3_path (str): Full S3 path to the file object
        file_size (int): File size in bytes (for quota management)

    Relationships:
        documents: One-to-many relationship with Document model

    Inherited from BaseModel:
        id (UUID): Primary key
        created_at (datetime): Creation timestamp (UTC)
        updated_at (datetime): Last update timestamp (UTC)
        created_by (UUID): User who uploaded this file

    Deduplication:
        If a user uploads the same file twice, only one File record is created.
        Both Document records will reference the same File via file_id.
    """

    __tablename__ = 'files'
    __bind_key__ = None  # Dynamic binding to tenant database

    # Fields
    md5_hash = db.Column(String(32), nullable=False)
    s3_path = db.Column(String(500), nullable=False, unique=True)
    file_size = db.Column(BigInteger, nullable=False)

    # Metadata column - stores custom JSON data
    file_metadata = db.Column(JSONB, nullable=False, default={})

    # Relationships
    documents = relationship('Document', back_populates='file', cascade='all, delete-orphan')

    # Indexes for common queries
    __table_args__ = (
        Index('ix_files_md5_hash', 'md5_hash'),
        Index('ix_files_s3_path', 's3_path', unique=True),
        Index('ix_files_created_at', 'created_at'),
        Index('ix_files_metadata', 'file_metadata', postgresql_using='gin'),
    )

    def __init__(self, **kwargs):
        """
        Initialize a new file record.

        Args:
            md5_hash: MD5 hash of file content (32 hex characters)
            s3_path: Full S3 path to the file
            file_size: Size of file in bytes
            created_by: UUID of user who uploaded the file

        Raises:
            ValueError: If md5_hash format is invalid or file_size is not positive
        """
        # Validate MD5 hash format before initialization
        if 'md5_hash' in kwargs:
            md5_hash = kwargs['md5_hash']
            if not self._is_valid_md5(md5_hash):
                raise ValueError(
                    f"Invalid MD5 hash format: {md5_hash}. "
                    "Must be 32 hexadecimal characters."
                )

        # Validate file size
        if 'file_size' in kwargs:
            file_size = kwargs['file_size']
            if not isinstance(file_size, int) or file_size <= 0:
                raise ValueError(
                    f"Invalid file size: {file_size}. Must be a positive integer."
                )

        super().__init__(**kwargs)
        logger.info(
            f"File object initialized: md5={self.md5_hash}, "
            f"size={self.file_size}, s3_path={self.s3_path}"
        )

    # Metadata helper methods
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get a metadata value by key.

        Args:
            key: The metadata key to retrieve
            default: Default value if key doesn't exist

        Returns:
            The metadata value or default if not found

        Example:
            mime_type = file.get_metadata('mime_type', 'application/octet-stream')
        """
        if self.file_metadata is None:
            return default
        return self.file_metadata.get(key, default)

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Set a metadata value for a specific key.

        Args:
            key: The metadata key to set
            value: The value to store (must be JSON-serializable)

        Example:
            file.set_metadata('mime_type', 'image/jpeg')
            file.set_metadata('dimensions', {'width': 1920, 'height': 1080})
        """
        if self.file_metadata is None:
            self.file_metadata = {}

        # Create a new dict to trigger SQLAlchemy change detection
        new_metadata = dict(self.file_metadata)
        new_metadata[key] = value
        self.file_metadata = new_metadata

    def update_metadata(self, data: Dict[str, Any]) -> None:
        """
        Update multiple metadata fields at once.

        Args:
            data: Dictionary of metadata to update

        Example:
            file.update_metadata({
                'mime_type': 'image/jpeg',
                'width': 1920,
                'height': 1080
            })
        """
        if self.file_metadata is None:
            self.file_metadata = {}

        # Create a new dict to trigger SQLAlchemy change detection
        new_metadata = dict(self.file_metadata)
        new_metadata.update(data)
        self.file_metadata = new_metadata

    def has_metadata(self, key: str) -> bool:
        """
        Check if a metadata key exists.

        Args:
            key: The metadata key to check

        Returns:
            True if key exists, False otherwise

        Example:
            if file.has_metadata('virus_scan_result'):
                result = file.get_metadata('virus_scan_result')
        """
        if self.file_metadata is None:
            return False
        return key in self.file_metadata

    def remove_metadata(self, key: str) -> bool:
        """
        Remove a metadata key.

        Args:
            key: The metadata key to remove

        Returns:
            True if key was removed, False if it didn't exist

        Example:
            file.remove_metadata('temp_flag')
        """
        if self.file_metadata is None or key not in self.file_metadata:
            return False

        # Create a new dict to trigger SQLAlchemy change detection
        new_metadata = dict(self.file_metadata)
        del new_metadata[key]
        self.file_metadata = new_metadata
        return True

    @staticmethod
    def _is_valid_md5(md5_hash: str) -> bool:
        """
        Validate MD5 hash format.

        Args:
            md5_hash: String to validate

        Returns:
            True if valid MD5 hash (32 hex chars), False otherwise
        """
        if not isinstance(md5_hash, str):
            return False
        return bool(re.match(r'^[a-f0-9]{32}$', md5_hash.lower()))

    @classmethod
    def find_by_md5(cls, md5_hash: str) -> Optional['File']:
        """
        Find a file by its MD5 hash within the current tenant database.

        This is used for deduplication - before creating a new file,
        check if one with the same MD5 already exists.

        Args:
            md5_hash: MD5 hash to search for

        Returns:
            File object if found, None otherwise

        Example:
            existing_file = File.find_by_md5('3ac5f2e8a1b4c6d7e8f9a0b1c2d3e4f5')
            if existing_file:
                # File already exists, reuse it
                document.file_id = existing_file.id
            else:
                # New file, create File record and upload to S3
                new_file = File.create(...)
        """
        return cls.query.filter_by(md5_hash=md5_hash.lower()).first()

    @classmethod
    def find_by_s3_path(cls, s3_path: str) -> Optional['File']:
        """
        Find a file by its S3 path.

        Args:
            s3_path: S3 path to search for

        Returns:
            File object if found, None otherwise
        """
        return cls.query.filter_by(s3_path=s3_path).first()

    @classmethod
    def check_duplicate(cls, md5_hash: str) -> bool:
        """
        Check if a file with the given MD5 hash already exists.

        Args:
            md5_hash: MD5 hash to check

        Returns:
            True if file exists, False otherwise

        Example:
            if File.check_duplicate(file_md5):
                print("File already uploaded, will reuse existing")
            else:
                print("New file, will upload to S3")
        """
        return cls.find_by_md5(md5_hash) is not None

    def get_s3_url(self, expiration: int = 3600) -> str:
        """
        Generate a pre-signed URL for downloading this file from S3.

        Args:
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Pre-signed S3 URL for downloading the file

        Note:
            This will be implemented in Phase 6 when S3 integration is added.
            For now, returns a placeholder.
        """
        # TODO: Implement S3 pre-signed URL generation in Phase 6
        logger.debug(f"Generating S3 URL for file {self.id} (expiration={expiration}s)")
        return f"https://s3.amazonaws.com/{self.s3_path}?expires={expiration}"

    def is_orphaned(self) -> bool:
        """
        Check if this file is orphaned (not referenced by any documents).

        Orphaned files can be safely deleted to free up storage space.

        Returns:
            True if no documents reference this file, False otherwise

        Example:
            for file in File.query.all():
                if file.is_orphaned():
                    file.delete_from_s3()
                    db.session.delete(file)
        """
        logger.debug(f"Checking if file {self.id} is orphaned")
        return len(self.documents) == 0

    def get_document_count(self) -> int:
        """
        Get the number of documents referencing this file.

        Returns:
            Number of documents using this file

        Example:
            if file.get_document_count() > 10:
                print(f"Popular file: {file.md5_hash}")
        """
        return len(self.documents)

    def delete_from_s3(self, confirm: bool = False) -> bool:
        """
        Delete the actual file from S3 storage.

        WARNING: This is destructive and cannot be undone!
        Only call this after ensuring no documents reference this file.

        Args:
            confirm: Must be True to proceed with deletion (safety check)

        Returns:
            True if deletion succeeded, False otherwise

        Raises:
            ValueError: If confirm is not True
            Exception: If S3 deletion fails

        Example:
            if file.is_orphaned():
                file.delete_from_s3(confirm=True)
                db.session.delete(file)
                db.session.commit()
        """
        if not confirm:
            raise ValueError(
                "S3 deletion requires explicit confirmation. "
                "Set confirm=True to proceed with this destructive operation."
            )

        logger.warning(f"DELETING file from S3: {self.s3_path}")

        # TODO: Implement S3 deletion in Phase 6
        # For now, just log the action
        logger.warning(f"S3 deletion not yet implemented for: {self.s3_path}")
        return False  # Placeholder until S3 integration exists

    @staticmethod
    def generate_s3_path(database_name: str, md5_hash: str, file_id: str) -> str:
        """
        Generate the S3 path for storing a file.

        Path format: tenants/{database_name}/files/{md5[:2]}/{md5[2:4]}/{md5}_{file_id}

        This sharding strategy (using first 4 chars of MD5) prevents too many
        files in a single S3 "directory", which can slow down listing operations.

        Args:
            database_name: Tenant's database name (e.g., tenant_iter_45fca42c)
            md5_hash: MD5 hash of file content
            file_id: File's UUID

        Returns:
            S3 path string

        Example:
            generate_s3_path(
                database_name='tenant_iter_45fca42c',
                md5_hash='3ac5f2e8a1b4c6d7e8f9a0b1c2d3e4f5',
                file_id='def-456'
            )
            # Returns: tenants/tenant_iter_45fca42c/files/3a/c5/3ac5f2e8a1b4c6d7e8f9a0b1c2d3e4f5_def-456
        """
        md5_lower = md5_hash.lower()
        shard1 = md5_lower[:2]
        shard2 = md5_lower[2:4]
        s3_path = f"tenants/{database_name}/files/{shard1}/{shard2}/{md5_lower}_{file_id}"
        logger.debug(f"Generated S3 path: {s3_path}")
        return s3_path

    def to_dict(self, exclude: List[str] = None, include_stats: bool = False) -> dict:
        """
        Convert file to dictionary for JSON serialization.

        Args:
            exclude: List of fields to exclude from output
            include_stats: If True, include document count and orphan status

        Returns:
            Dictionary representation of the file
        """
        data = super().to_dict(exclude=exclude)

        if include_stats:
            data['document_count'] = self.get_document_count()
            data['is_orphaned'] = self.is_orphaned()

        return data

    @classmethod
    def get_total_storage_used(cls) -> int:
        """
        Calculate total storage used by all files in this tenant (in bytes).

        Returns:
            Total file size in bytes

        Example:
            total_bytes = File.get_total_storage_used()
            total_gb = total_bytes / (1024 ** 3)
            print(f"Tenant using {total_gb:.2f} GB")
        """
        from sqlalchemy import func
        result = db.session.query(func.sum(cls.file_size)).scalar()
        return result or 0

    @classmethod
    def get_file_count(cls) -> int:
        """
        Get total number of files in this tenant.

        Returns:
            Number of file records
        """
        return cls.query.count()

    @classmethod
    def find_orphaned_files(cls) -> List['File']:
        """
        Find all orphaned files (not referenced by any documents).

        Returns:
            List of orphaned File objects

        Example:
            orphaned = File.find_orphaned_files()
            for file in orphaned:
                logger.info(f"Orphaned file: {file.s3_path} ({file.file_size} bytes)")
        """
        from .document import Document

        # Use a LEFT OUTER JOIN to find files with no associated documents
        orphaned = cls.query.outerjoin(Document).filter(Document.id == None).all()
        logger.info(f"Found {len(orphaned)} orphaned files")
        return orphaned

    def before_insert(self) -> None:
        """
        Lifecycle hook called before inserting a new file.

        Validates that:
        - MD5 hash is valid format
        - S3 path is not empty
        - File size is positive
        """
        super().before_insert()

        # Validate MD5 hash
        if not self._is_valid_md5(self.md5_hash):
            raise ValueError(
                f"Invalid MD5 hash format: {self.md5_hash}. "
                "Must be 32 hexadecimal characters."
            )

        # Validate S3 path
        if not self.s3_path or not self.s3_path.strip():
            raise ValueError("S3 path cannot be empty")

        # Validate file size
        if not isinstance(self.file_size, int) or self.file_size <= 0:
            raise ValueError(
                f"Invalid file size: {self.file_size}. Must be a positive integer."
            )

        logger.debug(f"File pre-insert validation passed: {self.md5_hash}")

    def before_update(self) -> None:
        """
        Lifecycle hook called before updating a file.

        Prevents changing critical fields after creation:
        - md5_hash (immutable - represents file content)
        - s3_path (immutable - except for initial placeholder replacement)
        """
        super().before_update()

        # Prevent MD5 hash changes
        if db.session.is_modified(self, include_collections=False):
            changes = db.session.dirty
            if self in changes:
                # Check if md5_hash was changed
                md5_history = db.inspect(self).attrs.md5_hash.history
                if md5_history.has_changes():
                    raise ValueError(
                        "Cannot change md5_hash after file creation. "
                        "Create a new file record instead."
                    )

                # Check if s3_path was changed
                s3_history = db.inspect(self).attrs.s3_path.history
                if s3_history.has_changes():
                    # Allow updating s3_path if the old value was a temporary placeholder
                    old_s3_path = s3_history.deleted[0] if s3_history.deleted else None
                    if old_s3_path and '_temp' in old_s3_path:
                        logger.debug(f"Allowing s3_path update from temporary placeholder: {old_s3_path} -> {self.s3_path}")
                    else:
                        raise ValueError(
                            "Cannot change s3_path after file creation. "
                            "Create a new file record instead."
                        )

        logger.debug(f"File pre-update validation passed: {self.md5_hash}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<File(id={self.id}, md5='{self.md5_hash}', "
            f"size={self.file_size}, s3='{self.s3_path[:50]}...')>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        size_mb = self.file_size / (1024 * 1024)
        return f"File {self.md5_hash} ({size_mb:.2f} MB)"
