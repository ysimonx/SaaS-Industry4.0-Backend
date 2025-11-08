# Solution Rapide - Erreur AADSTS500113

## Problème
L'erreur "AADSTS500113: No reply address is registered for the application" signifie que l'URI de redirection n'est pas configurée dans Azure AD.

## Solution Immédiate

### 1. Accédez à votre application dans Azure Portal
- URL : https://portal.azure.com
- Naviguez vers : **Azure Active Directory** → **App registrations**
- Recherchez l'application avec Client ID : **`28d84fdd-1d63-4257-8543-86294a55aa80`**

### 2. Configurez l'URI de redirection

Dans le menu de gauche, cliquez sur **Authentication** :

1. **Si vous voyez une section "Web"** :
   - Cliquez sur **"Add URI"**
   - Ajoutez : `http://localhost:4999/api/auth/sso/azure/callback`
   - Cliquez sur **"Save"** en haut

2. **Si vous ne voyez PAS de section "Web"** :
   - Cliquez sur **"Add a platform"**
   - Choisissez **"Web"** (PAS "Single-page application")
   - Dans "Redirect URIs", entrez : `http://localhost:4999/api/auth/sso/azure/callback`
   - Laissez TOUT décoché (pas d'implicit grant)
   - Cliquez sur **"Configure"**

### 3. Configuration correcte

✅ **Ce que vous devez avoir** :
```
Platform: Web
Redirect URIs:
  - http://localhost:4999/api/auth/sso/azure/callback

Implicit grant and hybrid flows:
  ☐ Access tokens (DOIT être décoché)
  ☐ ID tokens (DOIT être décoché)
```

❌ **Ce que vous ne devez PAS avoir** :
- Platform type: Single-page application
- Cases cochées pour implicit grant

### 4. Pour la production

Ajoutez aussi vos URIs de production si nécessaire :
- `https://votredomaine.com/api/auth/sso/azure/callback`

## Vérification

Après avoir sauvegardé, testez immédiatement :

```bash
# Test direct dans le navigateur
http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205
```

## Si ça ne marche toujours pas

1. **Vérifiez que vous avez bien cliqué sur "Save"** (bouton en haut de la page)
2. **Attendez 1-2 minutes** pour la propagation
3. **Vérifiez le Client ID** - assurez-vous que c'est bien : `28d84fdd-1d63-4257-8543-86294a55aa80`
4. **Testez en navigation privée** pour éviter les problèmes de cache

## Commande de diagnostic

```bash
# Vérifiez votre configuration
docker-compose exec api python scripts/test_azure_ad_config.py
```

## Note importante

L'URI doit être **EXACTEMENT** identique, y compris :
- Le protocole (`http://` pour localhost)
- Le port (`:4999`)
- Le chemin complet (`/api/auth/sso/azure/callback`)

Une seule lettre de différence et ça ne marchera pas !