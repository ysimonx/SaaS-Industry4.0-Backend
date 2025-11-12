#!/usr/bin/env python
"""
Script pour vérifier l'état des tokens Azure AD stockés.
Affiche les informations de tokens, leur expiration, et vérifie s'ils sont valides.
"""

import sys
import os
from datetime import datetime, timezone

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import UserAzureIdentity, User, Tenant
from app.extensions import db

def check_azure_tokens():
    """Vérifier l'état des tokens Azure AD."""
    app = create_app()

    with app.app_context():
        print("\n" + "="*70)
        print("ÉTAT DES TOKENS AZURE AD")
        print("="*70)

        # Récupérer toutes les identités Azure AD
        azure_identities = UserAzureIdentity.query.all()

        if not azure_identities:
            print("\n❌ Aucune identité Azure AD trouvée dans la base de données")
            print("   Les utilisateurs doivent d'abord s'authentifier via SSO")
            return

        now = datetime.now(timezone.utc)

        for azure_identity in azure_identities:
            user = azure_identity.user
            tenant = azure_identity.tenant

            print(f"\n{'='*70}")
            print(f"👤 Utilisateur: {user.email}")
            print(f"   Tenant: {tenant.name}")
            print(f"   Azure Object ID: {azure_identity.azure_object_id}")
            print(f"   Azure UPN: {azure_identity.azure_upn}")
            print(f"   Display Name: {azure_identity.azure_display_name}")

            # Vérifier les tokens
            print(f"\n🔑 Tokens Azure AD:")
            print("-" * 40)

            # Access Token
            has_access_token = azure_identity.encrypted_access_token is not None
            if has_access_token:
                print(f"   ✅ Access Token: Présent")
                if azure_identity.token_expires_at:
                    expires_at = azure_identity.token_expires_at
                    time_until_expiry = expires_at - now
                    hours = time_until_expiry.total_seconds() / 3600

                    if time_until_expiry.total_seconds() > 0:
                        print(f"      Expire dans: {hours:.1f} heures")
                        print(f"      Expire le: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        if hours < 1:
                            print(f"      ⚠️  Token expire bientôt!")
                    else:
                        print(f"      ❌ Token EXPIRÉ depuis: {abs(hours):.1f} heures")
                        print(f"      Expiré le: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                print(f"   ❌ Access Token: Absent")

            # Refresh Token
            has_refresh_token = azure_identity.encrypted_refresh_token is not None
            if has_refresh_token:
                print(f"   ✅ Refresh Token: Présent")
                if azure_identity.refresh_token_expires_at:
                    expires_at = azure_identity.refresh_token_expires_at
                    time_until_expiry = expires_at - now
                    days = time_until_expiry.total_seconds() / 86400

                    if time_until_expiry.total_seconds() > 0:
                        print(f"      Expire dans: {days:.1f} jours")
                        print(f"      Expire le: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        if days < 1:
                            print(f"      ⚠️  Refresh token expire bientôt!")
                    else:
                        print(f"      ❌ Refresh Token EXPIRÉ depuis: {abs(days):.1f} jours")
                        print(f"      Expiré le: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                print(f"   ❌ Refresh Token: Absent")

            # ID Token
            has_id_token = azure_identity.encrypted_id_token is not None
            if has_id_token:
                print(f"   ✅ ID Token: Présent")
            else:
                print(f"   ⚠️  ID Token: Absent")

            # Statut global
            print(f"\n📊 Statut:")
            if has_access_token and has_refresh_token:
                if azure_identity.token_expires_at and azure_identity.token_expires_at > now:
                    print(f"   ✅ Tokens valides et fonctionnels")
                elif has_refresh_token and azure_identity.refresh_token_expires_at and azure_identity.refresh_token_expires_at > now:
                    print(f"   ⚠️  Access token expiré mais refresh token valide")
                    print(f"   💡 Utilisez le script test_azure_token_refresh.py pour rafraîchir")
                else:
                    print(f"   ❌ Tous les tokens sont expirés")
                    print(f"   💡 L'utilisateur doit se ré-authentifier via SSO")
            else:
                print(f"   ❌ Tokens manquants")

            # Dernière mise à jour
            print(f"\n🕐 Dernière mise à jour:")
            print(f"   Créé le: {azure_identity.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"   Mis à jour le: {azure_identity.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        print("\n" + "="*70)
        print("RÉSUMÉ")
        print("="*70)

        total = len(azure_identities)
        valid_access = sum(1 for ai in azure_identities
                          if ai.token_expires_at and ai.token_expires_at > now)
        valid_refresh = sum(1 for ai in azure_identities
                           if ai.refresh_token_expires_at and ai.refresh_token_expires_at > now)

        print(f"\n   Total identités Azure AD: {total}")
        print(f"   Access tokens valides: {valid_access}/{total}")
        print(f"   Refresh tokens valides: {valid_refresh}/{total}")

        if valid_refresh > 0 and valid_access < total:
            print(f"\n   💡 Certains access tokens sont expirés mais peuvent être rafraîchis")
            print(f"   Exécutez: docker-compose exec api python scripts/test_azure_token_refresh.py")

        print("\n" + "="*70)

if __name__ == "__main__":
    check_azure_tokens()