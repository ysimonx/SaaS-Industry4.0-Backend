#!/usr/bin/env python
"""
Script pour configurer le client secret Azure AD pour SSO.
Passe du mode Public Client (PKCE) au mode Confidential Client (avec secret).
"""

import sys
import os
import getpass

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.extensions import db

def set_client_secret():
    """Configure le client secret pour SSO."""
    app = create_app()

    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    with app.app_context():
        print("\n" + "="*70)
        print("CONFIGURATION CLIENT SECRET AZURE AD")
        print("="*70)

        # Récupérer la configuration SSO
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(TENANT_ID)
        if not sso_config:
            print("❌ Configuration SSO non trouvée")
            return

        tenant = Tenant.query.get(TENANT_ID)
        print(f"\n📋 Tenant: {tenant.name}")
        print(f"   ID: {TENANT_ID}")
        print(f"   Client ID: {sso_config.client_id}")

        # Afficher l'état actuel
        print("\n📊 État actuel:")
        if sso_config.client_secret:
            print("   Client Secret: ✅ CONFIGURÉ")
            print(f"   Longueur: {len(sso_config.client_secret)} caractères")
            print(f"   Premiers chars: {sso_config.client_secret[:10]}...")
            print("\n⚠️  Un client secret est déjà configuré.")
            response = input("   Voulez-vous le remplacer ? (oui/non): ").strip().lower()
            if response not in ['oui', 'o', 'yes', 'y']:
                print("   Opération annulée.")
                return
        else:
            print("   Client Secret: ❌ NON CONFIGURÉ (mode PKCE)")

        # Demander le client secret
        print("\n" + "-"*70)
        print("COMMENT OBTENIR LE CLIENT SECRET:")
        print("-"*70)
        print("1. Allez sur https://portal.azure.com")
        print("2. Azure Active Directory → Inscriptions d'applications")
        print(f"3. Sélectionnez votre app (Client ID: {sso_config.client_id})")
        print("4. Certificats et secrets → + Nouvelle clé secrète client")
        print("5. Créez une clé secrète et copiez la VALEUR")
        print("   ⚠️  La valeur n'est affichée qu'UNE SEULE FOIS!")
        print("-"*70)

        print("\n💡 Le client secret ressemble à:")
        print("   8Q~abcdefghijklmnopqrstuvwxyz1234567890ABCD")
        print("   (commence souvent par des chiffres et contient ~ ou -)")

        # Saisie sécurisée du client secret
        print("\n🔐 Entrez le client secret (la saisie sera masquée):")
        client_secret = getpass.getpass("   Client Secret: ").strip()

        if not client_secret:
            print("❌ Client secret vide. Opération annulée.")
            return

        # Validation basique
        if len(client_secret) < 20:
            print("⚠️  Attention: Le client secret semble très court.")
            print(f"   Longueur: {len(client_secret)} caractères")
            response = input("   Continuer quand même ? (oui/non): ").strip().lower()
            if response not in ['oui', 'o', 'yes', 'y']:
                print("   Opération annulée.")
                return

        # Confirmation
        print(f"\n✅ Client secret reçu ({len(client_secret)} caractères)")
        print(f"   Premiers chars: {client_secret[:10]}...")
        response = input("\n   Confirmer l'enregistrement ? (oui/non): ").strip().lower()

        if response not in ['oui', 'o', 'yes', 'y']:
            print("   Opération annulée.")
            return

        # Enregistrer le client secret
        try:
            sso_config.client_secret = client_secret

            # Mettre à jour le metadata pour indiquer le mode confidential
            if not sso_config.config_metadata:
                sso_config.config_metadata = {}
            sso_config.config_metadata['app_type'] = 'confidential'

            db.session.commit()

            print("\n" + "="*70)
            print("✅ CLIENT SECRET CONFIGURÉ AVEC SUCCÈS")
            print("="*70)

            print(f"\n📊 Nouvelle configuration:")
            print(f"   Mode: Confidential Application (avec client secret)")
            print(f"   Client Secret: {'*' * (len(client_secret) - 4)}{client_secret[-4:]}")
            print(f"   App Type: {sso_config.config_metadata.get('app_type')}")

            print(f"\n🧪 Test de l'authentification:")
            print(f"   1. Ouvrez un navigateur en mode privé")
            print(f"   2. Allez à: http://localhost:4999/api/auth/sso/azure/login/{TENANT_ID}")
            print(f"   3. Authentifiez-vous avec Azure AD")
            print(f"   4. Vous devriez recevoir vos tokens JWT")

            print("\n💡 Le secret sera utilisé lors de l'échange du code d'autorisation.")
            print("   Plus besoin de PKCE - le secret suffit pour sécuriser le flux.")

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Erreur lors de l'enregistrement: {str(e)}")
            return

        print("\n" + "="*70)

if __name__ == "__main__":
    set_client_secret()