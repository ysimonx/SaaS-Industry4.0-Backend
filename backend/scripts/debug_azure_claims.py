#!/usr/bin/env python
"""
Script pour afficher les claims reçus d'Azure AD lors du SSO.
Permet de voir exactement quelles informations sont disponibles.
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import UserAzureIdentity
from app.extensions import db

def show_azure_claims():
    """Affiche les claims Azure AD du dernier utilisateur SSO créé."""
    app = create_app()

    with app.app_context():
        print("\n" + "="*70)
        print("CLAIMS AZURE AD - DERNIER UTILISATEUR SSO")
        print("="*70)

        # Trouver le dernier utilisateur SSO créé
        azure_identity = UserAzureIdentity.query.order_by(
            UserAzureIdentity.created_at.desc()
        ).first()

        if not azure_identity:
            print("\n❌ Aucun utilisateur SSO trouvé dans la base de données")
            return

        user = azure_identity.user
        tenant = azure_identity.tenant

        print(f"\n👤 Utilisateur: {user.email}")
        print(f"   Tenant: {tenant.name}")
        print(f"   Créé le: {azure_identity.created_at}")

        print(f"\n📋 Informations utilisateur dans la base:")
        print(f"   Email: {user.email}")
        print(f"   First Name: '{user.first_name}' {'❌ VIDE' if not user.first_name else '✅'}")
        print(f"   Last Name: '{user.last_name}' {'❌ VIDE' if not user.last_name else '✅'}")
        print(f"   Has Azure Identity: ✅ (SSO-enabled user)")

        print(f"\n🔐 Informations Azure AD:")
        print(f"   Azure Object ID: {azure_identity.azure_object_id}")
        print(f"   Azure Tenant ID: {azure_identity.azure_tenant_id}")
        print(f"   Azure UPN: {azure_identity.azure_upn}")
        print(f"   Azure Display Name: {azure_identity.azure_display_name}")

        # Afficher les claims stockés
        if azure_identity.azure_claims:
            print(f"\n📦 Claims Azure AD disponibles:")
            print("-" * 40)
            for key, value in sorted(azure_identity.azure_claims.items()):
                if key in ['iat', 'exp', 'nbf', 'auth_time']:
                    # Timestamps - skip for readability
                    continue
                print(f"   {key}: {value}")

            # Analyser les claims pour le nom
            print(f"\n🔍 Analyse des champs de nom:")
            claims = azure_identity.azure_claims

            if 'name' in claims:
                print(f"   ✅ 'name' présent: '{claims['name']}'")
            else:
                print(f"   ❌ 'name' absent")

            if 'given_name' in claims:
                print(f"   ✅ 'given_name' présent: '{claims['given_name']}'")
            else:
                print(f"   ❌ 'given_name' absent")

            if 'family_name' in claims:
                print(f"   ✅ 'family_name' présent: '{claims['family_name']}'")
            else:
                print(f"   ❌ 'family_name' absent")

            # Suggérer une solution
            print(f"\n💡 Solution recommandée:")
            if 'given_name' in claims and 'family_name' in claims:
                print(f"   ✅ Utiliser 'given_name' et 'family_name' directement")
            elif 'name' in claims:
                print(f"   ⚠️  Parser le champ 'name' pour extraire prénom et nom")
                name_parts = claims['name'].split(' ', 1)
                if len(name_parts) == 2:
                    print(f"      Proposition: first_name='{name_parts[0]}', last_name='{name_parts[1]}'")
                else:
                    print(f"      Nom complet: '{claims['name']}'")
            else:
                print(f"   ❌ Aucun champ de nom disponible")
                print(f"   💡 Solution: Utiliser Microsoft Graph API pour obtenir les infos")

        else:
            print(f"\n❌ Aucun claim Azure AD stocké")

        print("\n" + "="*70)

if __name__ == "__main__":
    show_azure_claims()