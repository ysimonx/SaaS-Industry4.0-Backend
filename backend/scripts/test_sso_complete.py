#!/usr/bin/env python
"""
Test complet du flux SSO avec le nouveau Client ID Azure AD.
"""

import sys
import os
import json

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.services.azure_ad_service import AzureADService

def test_sso_complete():
    """Test complet de la configuration SSO."""
    app = create_app()

    CLIENT_ID = "dd5f0275-3e46-4103-bce5-1589a6f13d48"
    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    with app.app_context():
        print("\n" + "="*70)
        print("TEST COMPLET SSO AZURE AD")
        print("="*70)

        # 1. Vérifier la configuration
        print("\n✅ ÉTAPE 1: Vérification de la configuration")
        print("-" * 40)

        tenant = Tenant.query.get(TENANT_ID)
        if not tenant:
            print(f"❌ Tenant non trouvé: {TENANT_ID}")
            return

        print(f"  Tenant: {tenant.name}")
        print(f"  ID: {TENANT_ID}")
        print(f"  Auth Method: {tenant.auth_method}")

        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(TENANT_ID)
        if not sso_config:
            print("❌ Configuration SSO non trouvée ou désactivée")
            return

        print(f"\n  Configuration SSO:")
        print(f"    Client ID: {sso_config.client_id}")
        print(f"    ✅ Correspond au nouveau ID" if sso_config.client_id == CLIENT_ID else f"❌ NE CORRESPOND PAS! Attendu: {CLIENT_ID}")
        print(f"    Azure Tenant: {sso_config.provider_tenant_id}")
        print(f"    Redirect URI: {sso_config.redirect_uri}")
        print(f"    Client Secret: {'❌ CONFIGURÉ (problème!)' if sso_config.client_secret else '✅ Aucun (mode PKCE)'}")
        print(f"    Activé: {'✅ Oui' if sso_config.is_enabled else '❌ Non'}")

        # 2. Test PKCE
        print("\n✅ ÉTAPE 2: Test de génération PKCE")
        print("-" * 40)

        try:
            azure_service = AzureADService(TENANT_ID)
            code_verifier, code_challenge = azure_service.generate_pkce_pair()
            state = azure_service.generate_state_token()

            print(f"  Code Verifier généré: {len(code_verifier)} caractères")
            print(f"  Code Challenge généré: {len(code_challenge)} caractères")
            print(f"  State Token généré: {len(state)} caractères")
            print("  ✅ Génération PKCE réussie")
        except Exception as e:
            print(f"  ❌ Erreur PKCE: {str(e)}")
            return

        # 3. Génération URL d'autorisation
        print("\n✅ ÉTAPE 3: Génération de l'URL d'autorisation")
        print("-" * 40)

        try:
            auth_url = azure_service.get_authorization_url(
                redirect_uri=sso_config.redirect_uri,
                state=state,
                code_challenge=code_challenge
            )

            # Vérifier que l'URL contient les bons paramètres
            if CLIENT_ID in auth_url:
                print(f"  ✅ Client ID présent dans l'URL")
            else:
                print(f"  ❌ Client ID manquant dans l'URL!")

            if "code_challenge" in auth_url:
                print(f"  ✅ Code challenge PKCE présent")
            else:
                print(f"  ❌ Code challenge PKCE manquant!")

            if "code_challenge_method=S256" in auth_url:
                print(f"  ✅ Méthode PKCE S256 configurée")
            else:
                print(f"  ❌ Méthode PKCE non configurée!")

            print(f"\n  URL d'autorisation (tronquée):")
            print(f"  {auth_url[:150]}...")

        except Exception as e:
            print(f"  ❌ Erreur génération URL: {str(e)}")
            return

        # 4. URLs des endpoints
        print("\n✅ ÉTAPE 4: URLs des endpoints SSO")
        print("-" * 40)

        print(f"  Check disponibilité SSO:")
        print(f"    http://localhost:4999/api/auth/sso/check-availability/{TENANT_ID}")
        print(f"\n  Initier login SSO:")
        print(f"    http://localhost:4999/api/auth/sso/azure/login/{TENANT_ID}")
        print(f"\n  Callback SSO:")
        print(f"    {sso_config.redirect_uri}")

        # 5. Checklist Azure Portal
        print("\n⚠️  ÉTAPE 5: Configuration Azure Portal REQUISE")
        print("-" * 40)
        print("  Vérifiez dans Azure Portal (https://portal.azure.com):")
        print(f"\n  1. Inscriptions d'applications → Client ID: {CLIENT_ID}")
        print(f"  2. Authentification → Configurations de plateforme:")
        print(f"     - Type: Web (PAS Application monopage)")
        print(f"     - URI de redirection: {sso_config.redirect_uri}")
        print(f"  3. Authentification → Paramètres avancés:")
        print(f"     - 'Activer les flux mobiles et de bureau suivants': OUI ⚠️  CRITIQUE!")
        print(f"     (En anglais: 'Allow public client flows': YES)")
        print(f"  4. Certificats et secrets:")
        print(f"     - AUCUNE clé secrète client ne doit être configurée")
        print(f"  5. Autorisations des API:")
        print(f"     - Microsoft Graph > User.Read")
        print(f"     - openid, profile, email")

        # 6. Test avec curl
        print("\n✅ ÉTAPE 6: Test avec curl")
        print("-" * 40)
        print("  Exécutez cette commande pour tester:")
        print(f"\n  curl http://localhost:4999/api/auth/sso/check-availability/{TENANT_ID}")

        print("\n" + "="*70)
        print("FIN DU TEST")
        print("="*70)

if __name__ == "__main__":
    test_sso_complete()