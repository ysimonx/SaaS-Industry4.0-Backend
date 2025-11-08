#!/usr/bin/env python
"""
Script pour mettre à jour les domaines email autorisés pour l'auto-provisioning SSO.
"""

import sys
import os
import json

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.extensions import db

def update_allowed_domains():
    """Met à jour les domaines email autorisés."""
    app = create_app()

    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    with app.app_context():
        print("\n" + "="*70)
        print("MISE À JOUR DES DOMAINES EMAIL AUTORISÉS")
        print("="*70)

        # Récupérer la configuration
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(TENANT_ID)
        if not sso_config:
            print("❌ Configuration SSO non trouvée")
            return

        tenant = Tenant.query.get(TENANT_ID)
        print(f"\n📋 Tenant: {tenant.name}")
        print(f"   ID: {TENANT_ID}")

        # Afficher la configuration actuelle
        print(f"\n📊 Configuration actuelle:")
        if sso_config.config_metadata and 'auto_provisioning' in sso_config.config_metadata:
            auto_prov = sso_config.config_metadata['auto_provisioning']
            print(f"   Auto-provisioning activé: {auto_prov.get('enabled', False)}")
            print(f"   Domaines autorisés: {auto_prov.get('allowed_email_domains', [])}")
            print(f"   Rôle par défaut: {auto_prov.get('default_role', 'viewer')}")
        else:
            print("   ❌ Aucune configuration d'auto-provisioning")

        # Proposer la nouvelle configuration
        print(f"\n✏️  Nouvelle configuration proposée:")
        new_domains = ["@fidwork.fr", "@example.com"]
        print(f"   Domaines autorisés: {new_domains}")

        response = input("\n   Appliquer cette configuration ? (oui/non): ").strip().lower()
        if response not in ['oui', 'o', 'yes', 'y']:
            print("   Opération annulée.")
            return

        # Mettre à jour la configuration
        if not sso_config.config_metadata:
            sso_config.config_metadata = {}

        if 'auto_provisioning' not in sso_config.config_metadata:
            sso_config.config_metadata['auto_provisioning'] = {}

        # Mise à jour des domaines
        sso_config.config_metadata['auto_provisioning']['allowed_email_domains'] = new_domains

        # Activer l'auto-provisioning si ce n'est pas déjà fait
        if not sso_config.config_metadata['auto_provisioning'].get('enabled'):
            print("\n⚠️  L'auto-provisioning n'est pas activé.")
            response = input("   Voulez-vous l'activer ? (oui/non): ").strip().lower()
            if response in ['oui', 'o', 'yes', 'y']:
                sso_config.config_metadata['auto_provisioning']['enabled'] = True
                print("   ✅ Auto-provisioning activé")

        # S'assurer qu'il y a un rôle par défaut
        if 'default_role' not in sso_config.config_metadata['auto_provisioning']:
            sso_config.config_metadata['auto_provisioning']['default_role'] = 'viewer'

        # Sauvegarder
        try:
            db.session.commit()

            print("\n" + "="*70)
            print("✅ CONFIGURATION MISE À JOUR")
            print("="*70)

            print(f"\n📊 Nouvelle configuration:")
            auto_prov = sso_config.config_metadata['auto_provisioning']
            print(f"   Auto-provisioning: {'✅ Activé' if auto_prov.get('enabled') else '❌ Désactivé'}")
            print(f"   Domaines autorisés: {auto_prov.get('allowed_email_domains', [])}")
            print(f"   Rôle par défaut: {auto_prov.get('default_role', 'viewer')}")

            print(f"\n🧪 Test d'authentification:")
            print(f"   1. Ouvrez un navigateur en mode privé")
            print(f"   2. Allez à: http://localhost:4999/api/auth/sso/azure/login/{TENANT_ID}")
            print(f"   3. Authentifiez-vous avec: yannick.simon@fidwork.fr")
            print(f"   4. Vous devriez maintenant recevoir vos tokens JWT!")

            print("\n💡 L'utilisateur sera automatiquement créé avec le rôle: " +
                  auto_prov.get('default_role', 'viewer'))

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Erreur lors de la sauvegarde: {str(e)}")
            return

        print("\n" + "="*70)

if __name__ == "__main__":
    update_allowed_domains()