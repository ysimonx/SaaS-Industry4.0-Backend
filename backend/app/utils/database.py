"""
Database utilities for multi-tenant database management.

Provides session management, connection factory, and tenant database operations.
"""

from typing import Optional, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.pool import NullPool
import logging

logger = logging.getLogger(__name__)


class TenantDatabaseManager:
    """
    Manages tenant-specific database connections and operations.

    Handles dynamic database creation, connection pooling, and session management
    for isolated tenant databases.
    """

    def __init__(self, app=None):
        """
        Initialize the tenant database manager.

        Args:
            app: Flask application instance (optional, can be set later with init_app)
        """
        self.app = app
        self._engines = {}  # Cache of tenant database engines
        self._session_factories = {}  # Cache of session factories per tenant

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialize the manager with Flask app configuration.

        Args:
            app: Flask application instance
        """
        self.app = app
        self.main_db_url = app.config['SQLALCHEMY_DATABASE_URI']
        self.tenant_db_url_template = app.config['TENANT_DATABASE_URL_TEMPLATE']
        self.pool_size = app.config['SQLALCHEMY_ENGINE_OPTIONS'].get('pool_size', 10)
        self.pool_timeout = app.config['SQLALCHEMY_ENGINE_OPTIONS'].get('pool_timeout', 30)
        self.pool_recycle = app.config['SQLALCHEMY_ENGINE_OPTIONS'].get('pool_recycle', 3600)
        self.max_overflow = app.config['SQLALCHEMY_ENGINE_OPTIONS'].get('max_overflow', 20)

    def get_tenant_db_url(self, database_name: str) -> str:
        """
        Generate database URL for a specific tenant.

        Args:
            database_name: Name of the tenant database

        Returns:
            Complete database connection URL

        Example:
            >>> manager.get_tenant_db_url('tenant_123')
            'postgresql://postgres:postgres@localhost:5432/tenant_123'
        """
        return self.tenant_db_url_template.format(database_name=database_name)

    def get_tenant_engine(self, database_name: str):
        """
        Get or create SQLAlchemy engine for tenant database.

        Engines are cached for reuse. Creates new engine with connection pooling
        if not already cached.

        Args:
            database_name: Name of the tenant database

        Returns:
            SQLAlchemy Engine instance
        """
        if database_name not in self._engines:
            db_url = self.get_tenant_db_url(database_name)

            engine = create_engine(
                db_url,
                pool_size=self.pool_size,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                max_overflow=self.max_overflow,
                echo=self.app.config.get('SQLALCHEMY_ECHO', False)
            )

            self._engines[database_name] = engine
            logger.info(f"Created engine for tenant database: {database_name}")

        return self._engines[database_name]

    def get_tenant_session_factory(self, database_name: str):
        """
        Get or create session factory for tenant database.

        Args:
            database_name: Name of the tenant database

        Returns:
            SQLAlchemy session factory
        """
        if database_name not in self._session_factories:
            engine = self.get_tenant_engine(database_name)
            session_factory = scoped_session(
                sessionmaker(bind=engine, expire_on_commit=False)
            )
            self._session_factories[database_name] = session_factory
            logger.info(f"Created session factory for tenant database: {database_name}")

        return self._session_factories[database_name]

    @contextmanager
    def tenant_db_session(self, database_name: str) -> Generator[Session, None, None]:
        """
        Context manager for tenant database sessions.

        Provides automatic session management with commit/rollback and cleanup.

        Args:
            database_name: Name of the tenant database

        Yields:
            SQLAlchemy Session for the tenant database

        Example:
            >>> with manager.tenant_db_session('tenant_123') as session:
            ...     documents = session.query(Document).all()
            ...     # Session automatically committed on success, rolled back on error
        """
        session_factory = self.get_tenant_session_factory(database_name)
        session = session_factory()

        try:
            yield session
            session.commit()
            logger.debug(f"Committed transaction for tenant: {database_name}")
        except Exception as e:
            session.rollback()
            logger.error(f"Rolled back transaction for tenant {database_name}: {str(e)}")
            raise
        finally:
            session.close()

    def create_tenant_database(self, database_name: str) -> bool:
        """
        Create a new PostgreSQL database for a tenant.

        Args:
            database_name: Name of the database to create

        Returns:
            True if database was created, False if it already exists

        Raises:
            Exception: If database creation fails
        """
        # Connect to main database to create new database
        engine = create_engine(
            self.main_db_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool
        )

        try:
            with engine.connect() as conn:
                # Check if database already exists
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": database_name}
                )

                if result.fetchone():
                    logger.info(f"Database {database_name} already exists")
                    return False

                # Create the database
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
                logger.info(f"Created tenant database: {database_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to create database {database_name}: {str(e)}")
            raise
        finally:
            engine.dispose()

    def create_tenant_tables(self, database_name: str):
        """
        Create tables in tenant database (Document, File).

        This should be called after creating a new tenant database to initialize
        the schema.

        Args:
            database_name: Name of the tenant database

        Raises:
            Exception: If table creation fails
        """
        engine = self.get_tenant_engine(database_name)

        try:
            # Import tenant database models directly from modules
            # NOT from app.models to avoid including them in main DB migrations
            from app.models.file import File
            from app.models.document import Document
            from app.extensions import db

            # Create only File and Document tables in tenant database
            # These models have __bind_key__ = None, so they need explicit binding
            File.__table__.create(bind=engine, checkfirst=True)
            logger.info(f"Created 'files' table in tenant database: {database_name}")

            Document.__table__.create(bind=engine, checkfirst=True)
            logger.info(f"Created 'documents' table in tenant database: {database_name}")

            logger.info(f"Successfully created all tables in tenant database: {database_name}")

        except Exception as e:
            logger.error(f"Failed to create tables in tenant database {database_name}: {str(e)}")
            raise

    def drop_tenant_database(self, database_name: str, force: bool = False) -> bool:
        """
        Drop a tenant database.

        WARNING: This is a destructive operation that cannot be undone!

        Args:
            database_name: Name of the database to drop
            force: If True, terminates active connections before dropping

        Returns:
            True if database was dropped successfully

        Raises:
            Exception: If database drop fails
        """
        engine = create_engine(
            self.main_db_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool
        )

        try:
            with engine.connect() as conn:
                if force:
                    # Terminate active connections to the database
                    conn.execute(
                        text("""
                            SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = :dbname
                            AND pid <> pg_backend_pid()
                        """),
                        {"dbname": database_name}
                    )
                    logger.info(f"Terminated active connections to {database_name}")

                # Drop the database
                conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
                logger.info(f"Dropped tenant database: {database_name}")

                # Remove cached engine and session factory
                if database_name in self._engines:
                    self._engines[database_name].dispose()
                    del self._engines[database_name]

                if database_name in self._session_factories:
                    self._session_factories[database_name].remove()
                    del self._session_factories[database_name]

                return True

        except Exception as e:
            logger.error(f"Failed to drop database {database_name}: {str(e)}")
            raise
        finally:
            engine.dispose()

    def database_exists(self, database_name: str) -> bool:
        """
        Check if a tenant database exists.

        Args:
            database_name: Name of the database to check

        Returns:
            True if database exists, False otherwise
        """
        engine = create_engine(self.main_db_url, poolclass=NullPool)

        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": database_name}
                )
                return result.fetchone() is not None
        finally:
            engine.dispose()

    def close_all_connections(self):
        """
        Close all cached database connections and dispose engines.

        Useful for cleanup during application shutdown or testing.
        """
        logger.info("Closing all tenant database connections")

        for session_factory in self._session_factories.values():
            session_factory.remove()

        for engine in self._engines.values():
            engine.dispose()

        self._engines.clear()
        self._session_factories.clear()


# Global instance to be initialized with Flask app
tenant_db_manager = TenantDatabaseManager()


def init_tenant_db_manager(app):
    """
    Initialize the global tenant database manager with Flask app.

    Args:
        app: Flask application instance

    Example:
        >>> from app.utils.database import init_tenant_db_manager
        >>> init_tenant_db_manager(app)
    """
    tenant_db_manager.init_app(app)
