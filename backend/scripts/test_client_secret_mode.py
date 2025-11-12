#!/usr/bin/env python
"""
Script pour tester que le mode client_secret fonctionne correctement
sans conflit avec PKCE.
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.services.azure_ad_service import AzureADService
from urllib.parse import urlparse, parse_qs

def test_client_secret_mode():
    """Test que le mode client_secret n'envoie pas de paramètres PKCE."""
    app = create_app()

    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    with app.app_context():
        print("\n" + "="*70)
        print("TEST MODE CLIENT_SECRET (Confidential Application)")
        print("="*70)

        # Récupérer la configuration
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(TENANT_ID)
        if not sso_config:
            print("❌ Configuration SSO non trouvée")
            return

        tenant = Tenant.query.get(TENANT_ID)

        print(f"\n📋 Configuration actuelle:")
        print(f"   Tenant: {tenant.name}")
        print(f"   Client ID: {sso_config.client_id}")

        # Vérifier le client_secret
        has_secret = sso_config.client_secret and sso_config.client_secret.strip()
        print(f"\n🔐 Mode d'authentification:")
        if has_secret:
            print(f"   ✅ CLIENT_SECRET configuré ({len(sso_config.client_secret)} chars)")
            print(f"   Mode: Confidential Application")
        else:
            print(f"   ❌ AUCUN CLIENT_SECRET")
            print(f"   Mode: Public Application (PKCE)")
            print("\n⚠️  ERREUR: Vous devez configurer un client_secret!")
            print("   Exécutez: docker-compose exec api python scripts/set_sso_client_secret.py")
            return

        # Générer l'URL d'autorisation
        print(f"\n🔗 Test de génération d'URL d'autorisation:")
        print("-" * 40)

        azure_service = AzureADService(TENANT_ID)
        state = azure_service.generate_state_token()

        # Générer l'URL sans fournir de code_challenge
        auth_url = azure_service.get_authorization_url(
            redirect_uri=sso_config.redirect_uri,
            state=state,
            code_challenge=None  # Ne doit pas être utilisé si client_secret existe
        )

        # Parser l'URL pour vérifier les paramètres
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        print(f"\n✅ URL d'autorisation générée")
        print(f"\n📊 Paramètres présents dans l'URL:")

        required_params = ['client_id', 'response_type', 'redirect_uri', 'scope', 'state']
        pkce_params = ['code_challenge', 'code_challenge_method']

        for param in required_params:
            if param in params:
                value = params[param][0]
                if param == 'state':
                    print(f"   ✅ {param}: {value[:20]}...")
                elif param == 'redirect_uri':
                    print(f"   ✅ {param}: {value}")
                else:
                    print(f"   ✅ {param}: {value[:30]}..." if len(value) > 30 else f"   ✅ {param}: {value}")
            else:
                print(f"   ❌ {param}: MANQUANT")

        print(f"\n🔍 Paramètres PKCE (NE DOIVENT PAS être présents):")
        for param in pkce_params:
            if param in params:
                print(f"   ❌ {param}: PRÉSENT (ERREUR!)")
            else:
                print(f"   ✅ {param}: ABSENT (correct)")

        # Résumé
        has_pkce = any(param in params for param in pkce_params)

        print(f"\n" + "="*70)
        if not has_pkce:
            print("✅ SUCCESS : Configuration correcte pour mode Confidential")
            print("="*70)
            print("\n✅ Le flux d'authentification utilisera le client_secret")
            print("✅ Aucun paramètre PKCE n'est envoyé")
            print("✅ Azure AD acceptera cette configuration")
            print(f"\n🧪 Pour tester l'authentification complète:")
            print(f"   1. Ouvrez un navigateur en mode privé")
            print(f"   2. Allez à: http://localhost:4999/api/auth/sso/azure/login/{TENANT_ID}")
            print(f"   3. Authentifiez-vous avec Azure AD")
            print(f"   4. Vous devriez recevoir vos tokens JWT sans erreur")
        else:
            print("❌ ERREUR : Des paramètres PKCE sont présents")
            print("="*70)
            print("\n❌ L'URL contient des paramètres PKCE alors qu'un client_secret est configuré")
            print("❌ Cela causera l'erreur AADSTS50148 de Azure AD")
            print("\n🔧 Vérifiez que le code a bien été mis à jour:")
            print("   - azure_ad_service.py:get_authorization_url()")
            print("   - sso_auth.py:initiate_azure_login()")

        print("\n" + "="*70)

if __name__ == "__main__":
    test_client_secret_mode()