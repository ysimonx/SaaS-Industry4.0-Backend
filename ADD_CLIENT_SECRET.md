# 🔐 Ajouter le Client Secret pour SSO

## Étape 1 : Créer le secret dans Azure Portal

1. **Allez sur** [Azure Portal](https://portal.azure.com)
2. **Naviguez vers** : Azure Active Directory → App registrations
3. **Trouvez votre application** :
   - Client ID : `28d84fdd-1d63-4257-8543-86294a55aa80`
4. **Dans le menu de gauche**, cliquez sur **"Certificates & secrets"**
5. **Onglet "Client secrets"** → Cliquez sur **"+ New client secret"**
6. **Configurez** :
   - Description : `Backend SSO Secret`
   - Expires : `24 months` (ou votre préférence)
7. **Cliquez sur "Add"**

## ⚠️ IMPORTANT : Copiez le secret MAINTENANT !

Après avoir créé le secret :
- **COPIEZ LA VALEUR** (pas l'ID !)
- Elle ressemble à : `kOp8Q~xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
- **⚠️ VOUS NE POURREZ PLUS LA VOIR APRÈS !**

## Étape 2 : Ajouter le secret dans votre backend

### Option A : Utiliser le script interactif (recommandé)

```bash
docker-compose exec api python scripts/update_sso_secret.py
```

Le script vous guidera pour :
1. Sélectionner le tenant
2. Coller le secret de manière sécurisée
3. Sauvegarder dans la base de données

### Option B : Manuellement via SQL

```bash
# Se connecter à PostgreSQL
docker-compose exec postgres psql -U postgres -d saas_platform

# Mettre à jour le secret (remplacez YOUR_SECRET_HERE)
UPDATE tenant_sso_configs
SET client_secret = 'YOUR_SECRET_HERE'
WHERE client_id = '28d84fdd-1d63-4257-8543-86294a55aa80';

# Quitter
\q
```

## Étape 3 : Tester

Testez immédiatement le SSO :

```bash
# Dans votre navigateur, allez à :
http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205
```

## ✅ Résultat attendu

Si tout fonctionne :
1. Vous serez redirigé vers Microsoft pour vous connecter
2. Après connexion, vous reviendrez avec un JSON contenant :
   - `access_token`
   - `refresh_token`
   - `user` (informations utilisateur)

## 🔍 Vérification

Pour vérifier que le secret est bien enregistré :

```bash
docker-compose exec api python -c "
from app import create_app
from app.models import TenantSSOConfig

app = create_app()
with app.app_context():
    config = TenantSSOConfig.query.filter_by(client_id='28d84fdd-1d63-4257-8543-86294a55aa80').first()
    if config and config.client_secret:
        print('✅ Secret configuré (', len(config.client_secret), 'caractères)')
    else:
        print('❌ Secret non configuré')
"
```

## Résumé de la configuration

| Paramètre | Valeur |
|-----------|--------|
| Client ID | `28d84fdd-1d63-4257-8543-86294a55aa80` |
| Azure Tenant | `072a8ae9-5c75-4606-98c3-c0754cf130aa` |
| Redirect URI | `http://localhost:4999/api/auth/sso/azure/callback` |
| Platform Type | Web (pas SPA) |
| Client Secret | ✅ Requis (vous venez de l'ajouter) |

## Notes

- Le secret expire (vérifiez la date dans Azure Portal)
- Notez la date d'expiration pour le renouveler à temps
- Gardez le secret en sécurité (ne le commitez jamais dans Git !)
- En production, utilisez un gestionnaire de secrets (Vault, Azure Key Vault, etc.)