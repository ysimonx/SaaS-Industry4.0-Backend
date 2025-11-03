"""
Exemples de migrations pour les tables tenant-spécifiques

Ce fichier contient des exemples de migrations que vous pouvez activer
en les décommentant dans tenant_migrations.py

Pour ajouter une nouvelle migration :
1. Copiez l'exemple ci-dessous
2. Ajoutez-le dans tenant_migrations.py
3. Utilisez le décorateur @register_migration(version_number)
4. Exécutez le script migrate_all_tenants.py
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


# ============================================================================
# EXEMPLE 1 : Ajouter une colonne simple
# ============================================================================
def migration_add_file_metadata(db: Session):
    """Ajoute une colonne metadata JSONB à la table files"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb
    """))


# ============================================================================
# EXEMPLE 2 : Ajouter plusieurs colonnes
# ============================================================================
def migration_add_file_checksum(db: Session):
    """Ajoute des colonnes pour l'intégrité des fichiers"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS checksum VARCHAR(64),
        ADD COLUMN IF NOT EXISTS checksum_algorithm VARCHAR(20) DEFAULT 'sha256'
    """))


# ============================================================================
# EXEMPLE 3 : Ajouter une colonne avec contrainte
# ============================================================================
def migration_add_document_version(db: Session):
    """Ajoute une colonne version à la table documents"""
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1 CHECK (version > 0)
    """))


# ============================================================================
# EXEMPLE 4 : Ajouter un index
# ============================================================================
def migration_add_file_created_index(db: Session):
    """Ajoute un index sur created_at pour les requêtes chronologiques"""
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_files_created_at
        ON files(created_at DESC)
    """))


# ============================================================================
# EXEMPLE 5 : Ajouter une colonne array (PostgreSQL)
# ============================================================================
def migration_add_document_tags(db: Session):
    """Ajoute un système de tags pour les documents"""
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT ARRAY[]::TEXT[]
    """))

    # Ajouter un index GIN pour les recherches dans les tags
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_documents_tags
        ON documents USING GIN(tags)
    """))


# ============================================================================
# EXEMPLE 6 : Modifier le type d'une colonne
# ============================================================================
def migration_change_file_size_to_bigint(db: Session):
    """Change le type de file_size de INTEGER à BIGINT pour supporter les gros fichiers"""
    # Note : cette migration peut être lente sur de grandes tables
    db.execute(text("""
        ALTER TABLE files
        ALTER COLUMN file_size TYPE BIGINT
    """))


# ============================================================================
# EXEMPLE 7 : Ajouter une contrainte
# ============================================================================
def migration_add_file_size_constraint(db: Session):
    """Ajoute une contrainte pour s'assurer que file_size est positif"""
    db.execute(text("""
        ALTER TABLE files
        ADD CONSTRAINT check_file_size_positive
        CHECK (file_size >= 0)
    """))


# ============================================================================
# EXEMPLE 8 : Renommer une colonne
# ============================================================================
def migration_rename_document_content(db: Session):
    """Renomme la colonne content en content_text pour plus de clarté"""
    db.execute(text("""
        ALTER TABLE documents
        RENAME COLUMN content TO content_text
    """))


# ============================================================================
# EXEMPLE 9 : Ajouter une colonne avec valeur par défaut calculée
# ============================================================================
def migration_add_file_uploaded_by(db: Session):
    """Ajoute une colonne pour tracer qui a uploadé le fichier"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS uploaded_by_email VARCHAR(255)
    """))


# ============================================================================
# EXEMPLE 10 : Migration de données
# ============================================================================
def migration_populate_mime_types(db: Session):
    """
    Déduit et remplit les mime_type manquants basés sur l'extension

    Note : Cette migration modifie des données existantes
    """
    db.execute(text("""
        UPDATE files
        SET mime_type = CASE
            WHEN filename LIKE '%.pdf' THEN 'application/pdf'
            WHEN filename LIKE '%.jpg' OR filename LIKE '%.jpeg' THEN 'image/jpeg'
            WHEN filename LIKE '%.png' THEN 'image/png'
            WHEN filename LIKE '%.txt' THEN 'text/plain'
            WHEN filename LIKE '%.doc' THEN 'application/msword'
            WHEN filename LIKE '%.docx' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ELSE 'application/octet-stream'
        END
        WHERE mime_type IS NULL OR mime_type = ''
    """))


# ============================================================================
# EXEMPLE 11 : Créer une nouvelle table liée
# ============================================================================
def migration_create_file_versions_table(db: Session):
    """Crée une table pour gérer les versions de fichiers"""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS file_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_size BIGINT NOT NULL,
            checksum VARCHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by_email VARCHAR(255),
            comment TEXT,
            UNIQUE(file_id, version_number)
        )
    """))

    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_file_versions_file_id
        ON file_versions(file_id)
    """))


# ============================================================================
# EXEMPLE 12 : Ajouter une colonne de soft delete
# ============================================================================
def migration_add_soft_delete(db: Session):
    """Ajoute des colonnes pour le soft delete des fichiers et documents"""
    db.execute(text("""
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS deleted_by_email VARCHAR(255)
    """))

    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS deleted_by_email VARCHAR(255)
    """))

    # Créer des index pour filtrer les éléments non-supprimés
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_files_deleted_at
        ON files(deleted_at) WHERE deleted_at IS NULL
    """))

    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_documents_deleted_at
        ON documents(deleted_at) WHERE deleted_at IS NULL
    """))


# ============================================================================
# EXEMPLE 13 : Migration complexe avec transactions
# ============================================================================
def migration_restructure_document_metadata(db: Session):
    """
    Réorganise les métadonnées des documents dans une structure JSON

    Cette migration est plus complexe et touche potentiellement beaucoup de données
    """
    # Créer une nouvelle colonne pour les métadonnées structurées
    db.execute(text("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS metadata_v2 JSONB DEFAULT '{}'::jsonb
    """))

    # Migrer les données existantes (exemple)
    db.execute(text("""
        UPDATE documents
        SET metadata_v2 = jsonb_build_object(
            'legacy_data', metadata,
            'migrated_at', CURRENT_TIMESTAMP
        )
        WHERE metadata IS NOT NULL
    """))


# ============================================================================
# COMMENT UTILISER CES EXEMPLES
# ============================================================================
"""
Pour utiliser ces migrations, copiez-les dans tenant_migrations.py avec le décorateur approprié :

from app.db.tenant_migrations import register_migration

@register_migration(2)
def add_file_metadata(db: Session):
    '''Ajoute une colonne metadata JSONB à la table files'''
    db.execute(text('''
        ALTER TABLE files
        ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb
    '''))

@register_migration(3)
def add_document_version(db: Session):
    '''Ajoute une colonne version à la table documents'''
    db.execute(text('''
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1 CHECK (version > 0)
    '''))

Puis exécutez :
    python backend/scripts/migrate_all_tenants.py --dry-run  # Tester d'abord
    python backend/scripts/migrate_all_tenants.py            # Appliquer

NOTES IMPORTANTES :
- Les numéros de version doivent être séquentiels et croissants
- Utilisez toujours IF NOT EXISTS pour les colonnes/index/contraintes
- Testez d'abord en mode dry-run
- Les migrations sont appliquées dans l'ordre (v1, v2, v3, ...)
- Une migration échouée bloque les suivantes
- Utilisez des transactions (db.execute avec commit automatique)
"""
