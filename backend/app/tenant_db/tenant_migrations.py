"""
Système de migration pour les tables tenant-spécifiques (File, Document)

Ces tables sont créées dynamiquement dans chaque base de données tenant
et ne sont pas gérées par Alembic. Ce module fournit un système de versioning
manuel pour faire évoluer leur schéma.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TenantSchemaMigration:
    """Gère les migrations pour les tables tenant-spécifiques"""

    def __init__(self, tenant_db: Session):
        self.db = tenant_db
        self.migrations: Dict[int, Callable] = {}

    def migration(self, version: int):
        """
        Décorateur pour enregistrer une migration

        Usage:
            @migrator.migration(1)
            def add_column(db):
                db.execute(text("ALTER TABLE files ADD COLUMN ..."))
        """
        def decorator(func):
            self.migrations[version] = func
            return func
        return decorator

    def get_current_version(self) -> int:
        """
        Récupère la version actuelle du schéma

        Returns:
            int: Version actuelle (0 si aucune migration appliquée)
        """
        try:
            result = self.db.execute(
                text("SELECT version FROM tenant_schema_version ORDER BY version DESC LIMIT 1")
            )
            row = result.fetchone()
            return row[0] if row else 0
        except Exception as e:
            # Table n'existe pas encore - rollback de la transaction en erreur
            logger.debug(f"Schema version table doesn't exist yet: {e}")
            self.db.rollback()
            self._create_version_table()
            return 0

    def _create_version_table(self):
        """Crée la table de versioning pour ce tenant"""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS tenant_schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """))
            self.db.execute(text(
                "INSERT INTO tenant_schema_version (version, description) VALUES (0, 'Initial schema')"
            ))
            self.db.commit()
            logger.info("Created tenant_schema_version table")
        except Exception as e:
            self.db.rollback()
            logger.warning(f"Could not create version table: {e}")

    def migrate_to_latest(self) -> list[str]:
        """
        Applique toutes les migrations manquantes

        Returns:
            list[str]: Liste des migrations appliquées
        """
        current = self.get_current_version()
        target = max(self.migrations.keys()) if self.migrations else 0
        applied = []

        if current >= target:
            logger.info(f"Schema already at latest version ({current})")
            return applied

        for version in range(current + 1, target + 1):
            if version in self.migrations:
                migration_func = self.migrations[version]
                migration_name = migration_func.__name__
                migration_doc = migration_func.__doc__ or "No description"

                logger.info(f"Applying migration v{version}: {migration_name}")

                try:
                    # Appliquer la migration
                    migration_func(self.db)

                    # Mettre à jour la version
                    self.db.execute(
                        text("""
                            INSERT INTO tenant_schema_version (version, description)
                            VALUES (:version, :description)
                        """),
                        {"version": version, "description": migration_doc.strip()}
                    )
                    self.db.commit()

                    applied.append(f"v{version}: {migration_name}")
                    logger.info(f"✓ Migration v{version} applied successfully")

                except Exception as e:
                    self.db.rollback()
                    logger.error(f"✗ Migration v{version} failed: {e}")
                    raise Exception(f"Migration v{version} failed: {e}")

        return applied

    def get_migration_history(self) -> list[dict]:
        """
        Récupère l'historique des migrations appliquées

        Returns:
            list[dict]: Liste des migrations avec version, date et description
        """
        try:
            result = self.db.execute(
                text("SELECT version, applied_at, description FROM tenant_schema_version ORDER BY version")
            )
            return [
                {
                    "version": row[0],
                    "applied_at": row[1],
                    "description": row[2]
                }
                for row in result.fetchall()
            ]
        except Exception:
            return []


# Instance globale pour enregistrer les migrations
_global_migrations: Dict[int, Callable] = {}


def register_migration(version: int):
    """
    Décorateur pour enregistrer une migration globalement

    Usage:
        @register_migration(1)
        def add_metadata_column(db):
            '''Ajoute une colonne metadata à File'''
            db.execute(text("ALTER TABLE files ADD COLUMN metadata JSONB"))
    """
    def decorator(func):
        _global_migrations[version] = func
        return func
    return decorator


def get_migrator(tenant_db: Session) -> TenantSchemaMigration:
    """
    Crée un migrator pour un tenant avec toutes les migrations enregistrées

    Args:
        tenant_db: Session de base de données du tenant

    Returns:
        TenantSchemaMigration: Instance du migrator prête à l'emploi
    """
    migrator = TenantSchemaMigration(tenant_db)
    migrator.migrations = _global_migrations.copy()
    return migrator


# ============================================================================
# DÉFINITION DES MIGRATIONS
# ============================================================================
# Ajoutez vos migrations ici en utilisant le décorateur @register_migration
# Les numéros de version doivent être séquentiels et croissants
# ============================================================================

@register_migration(1)
def initial_schema(db: Session):
    """
    Migration initiale - crée les tables File et Document
    Note: Cette migration est principalement documentaire car les tables
    sont créées au moment de la création du tenant
    """
    # Cette migration existe pour documenter la version initiale
    # Les tables sont déjà créées par create_tenant_database()
    pass


# Exemple de migrations futures (à décommenter et adapter selon vos besoins):

@register_migration(2)
def add_file_metadata_column(db: Session):
    """Ajoute une colonne metadata JSONB à la table files pour stocker des métadonnées personnalisées"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb
    """))

    # Créer un index GIN pour permettre des recherches efficaces dans le JSON
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_files_metadata
        ON files USING GIN (metadata)
    """))

@register_migration(3)
def add_document_version_column(db: Session):
    """Ajoute une colonne version à la table documents pour le versioning"""
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1 CHECK (version > 0)
    """))

    # Créer un index pour les requêtes par version
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_documents_version
        ON documents(version)
    """))

# @register_migration(4)
# def add_file_checksum(db: Session):
#     """Ajoute une colonne checksum pour l'intégrité des fichiers"""
#     db.execute(text("""
#         ALTER TABLE files
#         ADD COLUMN IF NOT EXISTS checksum VARCHAR(64),
#         ADD COLUMN IF NOT EXISTS checksum_algorithm VARCHAR(20) DEFAULT 'sha256'
#     """))

# @register_migration(5)
# def add_document_tags(db: Session):
#     """Ajoute un système de tags pour les documents"""
#     db.execute(text("""
#         ALTER TABLE documents
#         ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT ARRAY[]::TEXT[]
#     """))
