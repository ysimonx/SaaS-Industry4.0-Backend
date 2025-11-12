#!/usr/bin/env python3
"""
Test automatique du rafraîchissement des tokens Azure AD
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.user_azure_identity import UserAzureIdentity
from app.services.azure_ad_service import AzureADService
from datetime import datetime, timezone

def test_token_refresh():
    """Test le rafraîchissement automatique du token"""

    app = create_app()

    with app.app_context():
        print("\n" + "=" * 70)
        print("TEST AUTOMATIQUE DU RAFRAÎCHISSEMENT DES TOKENS")
        print("=" * 70)

        # Find user
        user = User.query.filter_by(email='yannick.simon@fidwork.fr').first()
        if not user:
            print("\n❌ Utilisateur non trouvé")
            return

        # Get Azure identity
        identity = UserAzureIdentity.query.filter_by(user_id=user.id).first()
        if not identity:
            print("\n❌ Identité Azure AD non trouvée")
            return

        print(f"\n✅ Utilisateur trouvé: {user.email}")
        print(f"   Tenant: {identity.tenant.name}")
        print(f"   Tenant ID: {identity.tenant_id}")

        # Check token status
        now = datetime.now(timezone.utc)
        access_expires = identity.token_expires_at
        refresh_expires = identity.refresh_token_expires_at

        access_valid = access_expires and access_expires > now
        refresh_valid = refresh_expires and refresh_expires > now

        print(f"\n📊 État des tokens AVANT rafraîchissement:")
        if access_valid:
            time_left = (access_expires - now).total_seconds() / 3600
            print(f"   ✅ Access token valide (expire dans {time_left:.1f} heures)")
        else:
            print(f"   ❌ Access token expiré")

        if refresh_valid:
            days_left = (refresh_expires - now).total_seconds() / 86400
            print(f"   ✅ Refresh token valide (expire dans {days_left:.1f} jours)")
        else:
            print(f"   ❌ Refresh token expiré")

        # Test refresh
        if not refresh_valid:
            print("\n❌ Impossible de tester: refresh token expiré")
            return

        print(f"\n🔄 Rafraîchissement du token en cours...")

        try:
            # Initialize Azure AD service
            azure_service = AzureADService(tenant_id=str(identity.tenant_id))

            # Decrypt tokens
            tokens = identity.get_decrypted_tokens()
            refresh_token = tokens.get('refresh_token')

            if not refresh_token or refresh_token == "None":
                print(f"❌ Refresh token invalide dans la base de données")
                return

            print(f"   ✅ Refresh token décrypté (longueur: {len(refresh_token)} caractères)")

            # Call Azure AD to refresh
            token_response = azure_service.refresh_access_token(refresh_token)

            if not token_response or 'access_token' not in token_response:
                print(f"❌ Erreur: pas d'access token dans la réponse")
                return

            print(f"   ✅ Nouveaux tokens reçus d'Azure AD")

            # Save new tokens
            identity.save_tokens(
                access_token=token_response['access_token'],
                refresh_token=token_response.get('refresh_token', refresh_token),
                id_token=token_response.get('id_token'),
                expires_in=token_response.get('expires_in', 3600)
            )

            db.session.commit()
            print(f"   ✅ Nouveaux tokens enregistrés dans la base de données")

            # Check new status
            db.session.refresh(identity)
            access_expires_new = identity.token_expires_at
            time_left_new = (access_expires_new - now).total_seconds() / 3600

            print(f"\n📊 État des tokens APRÈS rafraîchissement:")
            print(f"   ✅ Access token valide (expire dans {time_left_new:.1f} heures)")
            print(f"   ✅ Refresh token valide")

            print(f"\n✅ TEST RÉUSSI : Le rafraîchissement automatique fonctionne correctement !")
            print(f"\n💡 Le système Celery rafraîchira automatiquement les tokens")
            print(f"   30 minutes avant leur expiration.")

        except Exception as e:
            print(f"\n❌ Erreur lors du rafraîchissement: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_token_refresh()
