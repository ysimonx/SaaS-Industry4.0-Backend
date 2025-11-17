#!/usr/bin/env python3
"""
Script pour nettoyer les checks Healthchecks.io dupliqués créés automatiquement
Usage: python scripts/cleanup_duplicate_healthchecks.py
"""

import os
import sys
import time

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def cleanup_duplicate_checks():
    """Nettoie tous les checks créés automatiquement (auto-created)"""

    print("🧹 Cleaning up duplicate Healthchecks.io checks...")

    # Import ici pour avoir le contexte Flask
    from app.monitoring.healthchecks_client import healthchecks

    if not healthchecks.enabled:
        print("❌ Healthchecks is not enabled.")
        return False

    # Récupérer tous les checks
    print("📡 Fetching all checks from Healthchecks...")
    all_checks = healthchecks.list_checks()
    print(f"✓ Found {len(all_checks)} total checks.")

    # Identifier les checks à supprimer (ceux avec tag 'auto-created')
    checks_to_delete = []
    for check in all_checks:
        tags = check.get('tags', [])
        # Convertir tags en liste si c'est une chaîne
        if isinstance(tags, str):
            tags = tags.split()

        # Vérifier si 'auto-created' est dans les tags
        if 'auto-created' in tags:
            checks_to_delete.append(check)

    if not checks_to_delete:
        print("✓ No auto-created checks found. Nothing to clean up.")
        return True

    print(f"\n⚠️  Found {len(checks_to_delete)} auto-created checks to delete:")
    for check in checks_to_delete:
        print(f"   - {check['name']} (tags: {check.get('tags', [])})")

    # Demander confirmation
    response = input("\n🗑️  Do you want to delete these checks? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted. No checks deleted.")
        return False

    # Supprimer les checks
    deleted = 0
    failed = 0

    for check in checks_to_delete:
        check_id = check.get('ping_url', '').split('/')[-1]
        check_name = check['name']

        print(f"\n  Deleting {check_name}...", end='')

        try:
            # Note: L'API Healthchecks.io ne supporte pas directement la suppression
            # via l'API v1. Vous devrez peut-être le faire manuellement ou
            # utiliser l'API v2 si disponible
            import requests

            # Essayer de faire un DELETE request
            headers = {'X-Api-Key': healthchecks.api_key}
            url = f"{healthchecks.api_url}/checks/{check_id}"

            response = requests.delete(url, headers=headers, timeout=10)

            if response.status_code in [200, 204]:
                print(" ✓ Deleted")
                deleted += 1
            else:
                print(f" ❌ Failed (status: {response.status_code})")
                failed += 1

            time.sleep(0.5)  # Pause pour éviter le rate limiting

        except Exception as e:
            print(f" ❌ Error: {e}")
            failed += 1

    # Résumé
    print("\n" + "="*60)
    print("📊 CLEANUP SUMMARY")
    print("="*60)
    print(f"✓ Deleted: {deleted} checks")
    if failed > 0:
        print(f"❌ Failed: {failed} checks")

    # Lister les checks restants
    print("\n📊 Remaining checks:")
    remaining = healthchecks.list_checks()
    for check in remaining:
        if 'redis' in check['name'].lower():
            print(f"   - {check['name']} (tags: {check.get('tags', [])})")

    return failed == 0


if __name__ == '__main__':
    # Vérifier si on est dans le bon répertoire
    if not os.path.exists('scripts/cleanup_duplicate_healthchecks.py'):
        print("❌ Please run this script from the backend directory")
        sys.exit(1)

    # Setup Flask app context
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            success = cleanup_duplicate_checks()
            sys.exit(0 if success else 1)
    except ImportError as e:
        print(f"❌ Could not import Flask app: {e}")
        print("Make sure you're running from the backend directory")
        sys.exit(1)