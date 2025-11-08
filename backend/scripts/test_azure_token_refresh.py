#!/usr/bin/env python
"""
Script pour tester le refresh des tokens Azure AD.
Permet de vérifier que le refresh token fonctionne correctement.
"""

import sys
import os
from datetime import datetime, timezone

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import UserAzureIdentity, User, Tenant
from app.services.azure_ad_service import AzureADService
from app.extensions import db

def test_azure_token_refresh():
    """Tester le refresh des tokens Azure AD."""
    app = create_app()

    with app.app_context():
        print("\n" + "="*70)
        print("TEST REFRESH TOKEN AZURE AD")
        print("="*70)

        # Récupérer les identités Azure AD
        azure_identities = UserAzureIdentity.query.all()

        if not azure_identities:
            print("\n❌ Aucune identité Azure AD trouvée")
            print("   Les utilisateurs doivent d'abord s'authentifier via SSO")
            return

        now = datetime.now(timezone.utc)

        for azure_identity in azure_identities:
            user = azure_identity.user
            tenant = azure_identity.tenant

            print(f"\n{'='*70}")
            print(f"👤 Utilisateur: {user.email}")
            print(f"   Tenant: {tenant.name}")
            print(f"   Tenant ID: {tenant.id}")

            # Vérifier l'état actuel
            print(f"\n📊 État actuel des tokens:")

            has_refresh = azure_identity.encrypted_refresh_token is not None
            if not has_refresh:
                print(f"   ❌ Pas de refresh token disponible")
                print(f"   💡 L'utilisateur doit se ré-authentifier via SSO")
                continue

            # Vérifier si le refresh token est expiré
            if azure_identity.refresh_token_expires_at:
                if azure_identity.refresh_token_expires_at < now:
                    print(f"   ❌ Refresh token expiré")
                    print(f"   💡 L'utilisateur doit se ré-authentifier via SSO")
                    continue
                else:
                    days_left = (azure_identity.refresh_token_expires_at - now).total_seconds() / 86400
                    print(f"   ✅ Refresh token valide (expire dans {days_left:.1f} jours)")

            # Afficher l'état de l'access token
            if azure_identity.token_expires_at:
                if azure_identity.token_expires_at < now:
                    hours_expired = (now - azure_identity.token_expires_at).total_seconds() / 3600
                    print(f"   ⚠️  Access token expiré depuis {hours_expired:.1f} heures")
                else:
                    hours_left = (azure_identity.token_expires_at - now).total_seconds() / 3600
                    print(f"   ✅ Access token valide (expire dans {hours_left:.1f} heures)")

            # Demander confirmation
            print(f"\n🔄 Test du refresh token pour {user.email}")
            response = input("   Continuer ? (oui/non): ").strip().lower()

            if response not in ['oui', 'o', 'yes', 'y']:
                print("   ⏭️  Passé")
                continue

            # Initialiser le service Azure AD
            try:
                azure_service = AzureADService(str(tenant.id))

                print(f"\n⏳ Récupération du refresh token...")
                refresh_token = azure_identity.get_refresh_token()

                if not refresh_token:
                    print(f"   ❌ Impossible de récupérer le refresh token")
                    continue

                print(f"   ✅ Refresh token récupéré")
                print(f"\n⏳ Demande de nouveaux tokens à Azure AD...")

                # Appeler Azure AD pour rafraîchir les tokens
                new_tokens = azure_service.refresh_access_token(refresh_token)

                print(f"   ✅ Nouveaux tokens reçus d'Azure AD!")

                # Afficher les informations des nouveaux tokens
                print(f"\n📦 Nouveaux tokens:")
                print(f"   Access Token: {'✅ Reçu' if 'access_token' in new_tokens else '❌ Manquant'}")
                refresh_msg = '✅ Reçu' if 'refresh_token' in new_tokens else '⚠️ Non fourni (réutilise ancien)'
                print(f"   Refresh Token: {refresh_msg}")
                print(f"   ID Token: {'✅ Reçu' if 'id_token' in new_tokens else '❌ Manquant'}")
                print(f"   Expires in: {new_tokens.get('expires_in', 'N/A')} secondes")

                # Sauvegarder les nouveaux tokens
                print(f"\n💾 Sauvegarde des nouveaux tokens...")

                azure_identity.save_tokens(
                    access_token=new_tokens.get('access_token'),
                    refresh_token=new_tokens.get('refresh_token', refresh_token),  # Garde l'ancien si pas nouveau
                    id_token=new_tokens.get('id_token'),
                    expires_in=new_tokens.get('expires_in', 3600),
                    refresh_expires_in=azure_identity.refresh_token_expires_at  # Garde l'ancienne expiration
                )

                db.session.commit()

                print(f"   ✅ Tokens sauvegardés en base de données")

                # Afficher le nouvel état
                print(f"\n📊 Nouvel état:")
                new_expiry = azure_identity.token_expires_at
                if new_expiry:
                    hours_until = (new_expiry - now).total_seconds() / 3600
                    print(f"   Access token expire dans: {hours_until:.1f} heures")
                    print(f"   Expire le: {new_expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                print(f"\n✅ SUCCESS: Refresh token fonctionne correctement!")

            except ValueError as e:
                print(f"\n❌ ERREUR lors du refresh: {str(e)}")
                print(f"\n💡 Causes possibles:")
                print(f"   - Refresh token invalide ou expiré")
                print(f"   - Problème de connexion avec Azure AD")
                print(f"   - Configuration SSO incorrecte")
                print(f"\n💡 Solution: L'utilisateur doit se ré-authentifier via SSO")

            except Exception as e:
                print(f"\n❌ ERREUR inattendue: {str(e)}")
                import traceback
                traceback.print_exc()

        print("\n" + "="*70)
        print("FIN DU TEST")
        print("="*70)

if __name__ == "__main__":
    test_azure_token_refresh()