#!/usr/bin/env python
"""
Diagnostic approfondi de l'erreur SSO avec Azure AD.
"""

import sys
import os
import json
import requests
from urllib.parse import urlencode, parse_qs, urlparse

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import TenantSSOConfig, Tenant
from app.services.azure_ad_service import AzureADService

def diagnose_sso_error():
    """Diagnostic approfondi du problème SSO."""
    app = create_app()

    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    with app.app_context():
        print("\n" + "="*70)
        print("DIAGNOSTIC APPROFONDI SSO AZURE AD")
        print("="*70)

        # Récupérer la configuration
        sso_config = TenantSSOConfig.find_enabled_by_tenant_id(TENANT_ID)
        if not sso_config:
            print("❌ Configuration SSO non trouvée")
            return

        print("\n🔍 ANALYSE DE LA CONFIGURATION")
        print("-" * 40)

        # Vérifier client_secret en détail
        print("\n1. Client Secret:")
        if sso_config.client_secret is None:
            print("   ✅ NULL (correct pour PKCE)")
        else:
            print(f"   ❌ VALEUR PRÉSENTE!")
            print(f"      Type: {type(sso_config.client_secret)}")
            print(f"      Longueur: {len(sso_config.client_secret)}")
            print(f"      Vide après strip: {not sso_config.client_secret.strip()}")
            print(f"      Repr: {repr(sso_config.client_secret)}")
            if sso_config.client_secret:
                print(f"      Premiers chars: {repr(sso_config.client_secret[:10])}")

        # Simuler ce qui se passe lors du token exchange
        print("\n2. Simulation du Token Exchange:")
        print("   Ce qui sera envoyé à Azure AD:")

        token_data_test = {
            'client_id': sso_config.client_id,
            'grant_type': 'authorization_code',
            'code': '[CODE]',
            'redirect_uri': sso_config.redirect_uri,
            'scope': 'openid profile email User.Read'
        }

        # Appliquer exactement la même logique que dans azure_ad_service.py
        if sso_config.client_secret and sso_config.client_secret.strip():
            token_data_test['client_secret'] = '[SECRET]'
            print("   ❌ client_secret SERA INCLUS (cause l'erreur!)")
        else:
            token_data_test['code_verifier'] = '[VERIFIER]'
            print("   ✅ code_verifier sera utilisé (PKCE)")

        print("\n   Paramètres qui seront envoyés:")
        for key in token_data_test:
            print(f"   - {key}")

        # Tester la connectivité Azure AD
        print("\n3. Test de l'endpoint Azure AD:")
        try:
            openid_url = f"{sso_config.get_authority_url()}/v2.0/.well-known/openid-configuration"
            response = requests.get(openid_url, timeout=5)
            if response.status_code == 200:
                config = response.json()
                print("   ✅ Azure AD accessible")

                # Vérifier si PKCE est supporté
                if 'code_challenge_methods_supported' in config:
                    methods = config['code_challenge_methods_supported']
                    if 'S256' in methods:
                        print("   ✅ PKCE S256 supporté par Azure AD")
                    else:
                        print(f"   ⚠️ Méthodes PKCE supportées: {methods}")
                else:
                    print("   ⚠️ Pas d'info sur PKCE dans la config OpenID")
        except Exception as e:
            print(f"   ❌ Erreur: {e}")

        # Générer une URL de test complète
        print("\n4. URL d'autorisation complète pour test:")
        print("-" * 40)

        azure_service = AzureADService(TENANT_ID)
        code_verifier, code_challenge = azure_service.generate_pkce_pair()
        state = azure_service.generate_state_token()

        auth_params = {
            'client_id': sso_config.client_id,
            'response_type': 'code',
            'redirect_uri': sso_config.redirect_uri,
            'response_mode': 'query',
            'scope': 'openid profile email User.Read',
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'prompt': 'select_account'
        }

        auth_url = f"{sso_config.get_authorization_url()}?{urlencode(auth_params)}"

        print(f"\nCopiez cette URL dans votre navigateur pour tester:")
        print(f"\n{auth_url}\n")

        print("\n5. Vérifications Azure Portal:")
        print("-" * 40)
        print("\n⚠️  POINTS À VÉRIFIER DANS AZURE PORTAL:")
        print("\n   A. Type de plateforme (CRITIQUE!):")
        print("      - Doit être: Web")
        print("      - NE DOIT PAS être: Application monopage (SPA)")
        print("      - NE DOIT PAS être: Mobile et applications de bureau")

        print("\n   B. URI de redirection:")
        print(f"      - Doit être EXACTEMENT: {sso_config.redirect_uri}")
        print("      - Pas de slash final en plus/moins")
        print("      - Bon port (4999)")

        print("\n   C. Clés secrètes client:")
        print("      - Aller dans 'Certificats et secrets'")
        print("      - Vérifier qu'AUCUNE clé secrète n'existe")
        print("      - Si une existe, la SUPPRIMER")

        print("\n   D. Type d'application:")
        print("      - Dans 'Vue d'ensemble', vérifier le type")
        print("      - Doit supporter les clients publics")

        # Solutions possibles
        print("\n6. SOLUTIONS À ESSAYER:")
        print("-" * 40)
        print("\n   1. Supprimer TOUTES les clés secrètes dans Azure Portal")
        print("   2. Recréer la plateforme Web (supprimer et recréer)")
        print("   3. Vider le cache du navigateur / utiliser mode privé")
        print("   4. Attendre 5 minutes (propagation Azure AD)")
        print("   5. Créer une NOUVELLE inscription d'application")

        print("\n" + "="*70)
        print("FIN DU DIAGNOSTIC")
        print("="*70)

if __name__ == "__main__":
    diagnose_sso_error()