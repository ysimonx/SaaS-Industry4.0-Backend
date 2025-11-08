#!/usr/bin/env python
"""
Script pour tester le flux SSO complet avec gestion de session.
"""

import sys
import os
import json
import requests
from urllib.parse import urlparse, parse_qs

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_sso_flow():
    """Test du flux SSO complet avec session."""

    BASE_URL = "http://localhost:4999"
    TENANT_ID = "cb859f98-291e-41b2-b30f-2287c2699205"

    print("\n" + "="*70)
    print("TEST FLUX SSO COMPLET AVEC SESSION")
    print("="*70)

    # Créer une session pour conserver les cookies
    session = requests.Session()

    # 1. Vérifier la disponibilité SSO
    print("\n1️⃣ Vérification de la disponibilité SSO...")
    print("-" * 40)

    check_url = f"{BASE_URL}/api/auth/sso/check-availability/{TENANT_ID}"
    response = session.get(check_url)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ SSO disponible: {data.get('available')}")
        print(f"   Provider: {data.get('provider')}")
        print(f"   Login URL: {data.get('sso_login_url')}")
    else:
        print(f"❌ Erreur: {response.status_code} - {response.text}")
        return

    # 2. Initier le login SSO (créer la session avec state)
    print("\n2️⃣ Initiation du login SSO...")
    print("-" * 40)

    login_url = f"{BASE_URL}/api/auth/sso/azure/login/{TENANT_ID}"

    # Ne pas suivre les redirections automatiquement
    response = session.get(login_url, allow_redirects=False)

    if response.status_code == 302:
        auth_url = response.headers.get('Location')
        print(f"✅ Redirection vers Azure AD")

        # Parser l'URL pour extraire les paramètres
        parsed = urlparse(auth_url)
        params = parse_qs(parsed.query)

        print(f"\n   Paramètres de l'URL d'autorisation:")
        print(f"   - Client ID: {params.get('client_id', ['?'])[0][:20]}...")
        print(f"   - State: {params.get('state', ['?'])[0][:20]}...")
        print(f"   - Code Challenge: {params.get('code_challenge', ['?'])[0][:20]}...")
        print(f"   - Redirect URI: {params.get('redirect_uri', ['?'])[0]}")

        # Afficher les cookies de session
        print(f"\n   Cookies de session créés:")
        for cookie in session.cookies:
            print(f"   - {cookie.name}: {cookie.value[:20]}..." if len(cookie.value) > 20 else f"   - {cookie.name}: {cookie.value}")

        print(f"\n3️⃣ URL pour l'authentification manuelle:")
        print("-" * 40)
        print(f"\n⚠️  IMPORTANT: Copiez cette URL dans votre navigateur:")
        print(f"\n{auth_url}\n")
        print("Après l'authentification Azure, vous serez redirigé vers:")
        print(f"{params.get('redirect_uri', ['?'])[0]}")
        print("\n⚠️  Le callback échouera car le navigateur n'a pas la même session.")
        print("C'est normal! Le state token est stocké dans la session Python.")

    else:
        print(f"❌ Erreur: {response.status_code}")
        print(f"   Contenu: {response.text[:500]}")

    # 4. Instructions pour test complet
    print("\n" + "="*70)
    print("POUR UN TEST COMPLET")
    print("="*70)

    print("\n🔧 Option 1: Test dans le navigateur (recommandé)")
    print("-" * 40)
    print(f"1. Ouvrez un nouvel onglet privé/incognito")
    print(f"2. Allez à: {BASE_URL}/api/auth/sso/azure/login/{TENANT_ID}")
    print(f"3. Authentifiez-vous avec Azure AD")
    print(f"4. Vous serez redirigé et le token sera validé automatiquement")

    print("\n🔧 Option 2: Test avec curl (avancé)")
    print("-" * 40)
    print("# Étape 1: Initier le login et capturer les cookies")
    print(f"curl -c cookies.txt -v -L \\")
    print(f"  '{BASE_URL}/api/auth/sso/azure/login/{TENANT_ID}'")
    print("\n# Étape 2: Suivre la redirection Azure manuellement")
    print("# Étape 3: Appeler le callback avec les cookies")
    print("curl -b cookies.txt \\")
    print(f"  '{BASE_URL}/api/auth/sso/azure/callback?code=CODE&state=STATE'")

    print("\n" + "="*70)
    print("FIN DU TEST")
    print("="*70)

if __name__ == "__main__":
    test_sso_flow()