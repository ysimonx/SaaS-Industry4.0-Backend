#!/usr/bin/env python3
"""
Script de migration pour tous les tenants

Ce script applique les migrations définies dans tenant_migrations.py
à tous les tenants existants dans la base de données principale.

Usage:
    # Dry-run (affiche ce qui serait fait sans appliquer)
    python backend/scripts/migrate_all_tenants.py --dry-run

    # Appliquer les migrations
    python backend/scripts/migrate_all_tenants.py

    # Migrer un seul tenant
    python backend/scripts/migrate_all_tenants.py --tenant-id <tenant_id>

    # Afficher l'historique des migrations
    python backend/scripts/migrate_all_tenants.py --history
"""

import sys
import os
import argparse
from pathlib import Path

# Ajouter le répertoire backend au path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import create_app
from app.models.tenant import Tenant
from app.tenant_db.tenant_migrations import get_migrator
from app.config import Config
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_tenant_session(database_name: str):
    """
    Crée une session pour la base de données d'un tenant

    Args:
        database_name: Nom de la base de données du tenant

    Returns:
        Session: Session SQLAlchemy pour le tenant
    """
    # Utiliser le template d'URL tenant depuis la config
    db_url = Config.TENANT_DATABASE_URL_TEMPLATE.format(database_name=database_name)

    engine = create_engine(db_url, pool_pre_ping=True)
    TenantSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return TenantSessionLocal()


def migrate_tenant(tenant: Tenant, dry_run: bool = False) -> dict:
    """
    Migre un tenant vers la dernière version du schéma

    Args:
        tenant: Instance du tenant à migrer
        dry_run: Si True, simule les migrations sans les appliquer

    Returns:
        dict: Résultat de la migration avec status et détails
    """
    result = {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "database": tenant.database_name,
        "status": "success",
        "current_version": 0,
        "target_version": 0,
        "applied_migrations": [],
        "error": None
    }

    try:
        # Créer une session pour ce tenant
        tenant_db = get_tenant_session(tenant.database_name)

        try:
            # Créer le migrator
            migrator = get_migrator(tenant_db)

            # Obtenir les versions
            current_version = migrator.get_current_version()
            target_version = max(migrator.migrations.keys()) if migrator.migrations else 0

            result["current_version"] = current_version
            result["target_version"] = target_version

            if current_version >= target_version:
                result["status"] = "up_to_date"
                logger.info(f"  ✓ {tenant.name} already up to date (v{current_version})")
            elif dry_run:
                result["status"] = "would_migrate"
                migrations_to_apply = target_version - current_version
                logger.info(f"  → {tenant.name} would apply {migrations_to_apply} migration(s) (v{current_version} → v{target_version})")
            else:
                # Appliquer les migrations
                applied = migrator.migrate_to_latest()
                result["applied_migrations"] = applied
                logger.info(f"  ✓ {tenant.name} migrated successfully (v{current_version} → v{target_version})")

        finally:
            tenant_db.close()

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"  ✗ {tenant.name} migration failed: {e}")

    return result


def show_migration_history(tenant: Tenant):
    """
    Affiche l'historique des migrations pour un tenant

    Args:
        tenant: Instance du tenant
    """
    print(f"\n{'='*80}")
    print(f"Tenant: {tenant.name} ({tenant.database_name})")
    print(f"{'='*80}")

    try:
        tenant_db = get_tenant_session(tenant.database_name)
        try:
            migrator = get_migrator(tenant_db)
            history = migrator.get_migration_history()

            if not history:
                print("No migration history found")
                return

            print(f"\n{'Version':<10} {'Applied At':<25} {'Description'}")
            print(f"{'-'*10} {'-'*25} {'-'*40}")

            for entry in history:
                version = f"v{entry['version']}"
                applied_at = entry['applied_at'].strftime('%Y-%m-%d %H:%M:%S') if entry['applied_at'] else 'N/A'
                description = entry['description'][:40]
                print(f"{version:<10} {applied_at:<25} {description}")

        finally:
            tenant_db.close()

    except Exception as e:
        print(f"Error retrieving history: {e}")


def main():
    """Point d'entrée principal du script"""
    parser = argparse.ArgumentParser(
        description='Migrate tenant-specific database schemas',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without applying migrations'
    )
    parser.add_argument(
        '--tenant-id',
        type=str,
        help='Migrate only a specific tenant by ID'
    )
    parser.add_argument(
        '--history',
        action='store_true',
        help='Show migration history for all tenants (or specific tenant with --tenant-id)'
    )

    args = parser.parse_args()

    # Créer l'application Flask et le contexte
    app = create_app()

    with app.app_context():
        try:
            # Récupérer les tenants
            if args.tenant_id:
                tenants = Tenant.query.filter(Tenant.id == args.tenant_id).all()
                if not tenants:
                    print(f"Error: Tenant with ID '{args.tenant_id}' not found")
                    sys.exit(1)
            else:
                tenants = Tenant.query.all()

            if not tenants:
                print("No tenants found in the database")
                sys.exit(0)

            # Afficher l'historique
            if args.history:
                for tenant in tenants:
                    show_migration_history(tenant)
                sys.exit(0)

            # Migrer les tenants
            print(f"\n{'='*80}")
            print(f"Tenant Schema Migration")
            print(f"{'='*80}")
            print(f"Found {len(tenants)} tenant(s) to process")
            print(f"Mode: {'DRY RUN (no changes will be made)' if args.dry_run else 'LIVE (migrations will be applied)'}")
            print(f"{'='*80}\n")

            results = []
            for tenant in tenants:
                logger.info(f"Processing tenant: {tenant.name} ({tenant.database_name})")
                result = migrate_tenant(tenant, dry_run=args.dry_run)
                results.append(result)

            # Afficher le résumé
            print(f"\n{'='*80}")
            print("Migration Summary")
            print(f"{'='*80}\n")

            success_count = sum(1 for r in results if r['status'] in ['success', 'up_to_date'])
            error_count = sum(1 for r in results if r['status'] == 'error')
            would_migrate_count = sum(1 for r in results if r['status'] == 'would_migrate')

            print(f"Total tenants: {len(results)}")
            print(f"  ✓ Successful: {success_count}")
            if would_migrate_count > 0:
                print(f"  → Would migrate: {would_migrate_count}")
            if error_count > 0:
                print(f"  ✗ Errors: {error_count}")

            # Afficher les détails des erreurs
            errors = [r for r in results if r['status'] == 'error']
            if errors:
                print(f"\n{'='*80}")
                print("Errors:")
                print(f"{'='*80}")
                for error in errors:
                    print(f"\n{error['tenant_name']} ({error['database']}):")
                    print(f"  {error['error']}")

            # Code de sortie
            sys.exit(1 if error_count > 0 else 0)

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            print(f"\n✗ Fatal error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
