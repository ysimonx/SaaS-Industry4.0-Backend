# Guide de Configuration Azure AD pour SSO Backend

## Problème : AADSTS9002327

L'erreur "Tokens issued for the 'Single-Page Application' client-type may only be redeemed via cross-origin requests" se produit lorsque l'application Azure AD est configurée comme SPA au lieu d'application Web.

## Solution : Reconfigurer l'Application Azure AD

### Étapes pour corriger la configuration dans Azure Portal

1. **Connectez-vous au portail Azure**
   - Allez sur [https://portal.azure.com](https://portal.azure.com)
   - Naviguez vers **Azure Active Directory** → **App registrations**

2. **Trouvez votre application**
   - Recherchez votre application par son nom ou Client ID : `61da75ae-c4de-4245-8eeb-7b49a5c50339`

3. **Modifiez le type d'authentification**

   **Option A : Modifier l'application existante**

   a. Cliquez sur **Authentication** dans le menu de gauche

   b. Dans la section **Platform configurations**, supprimez la plateforme "Single-page application" si elle existe

   c. Cliquez sur **Add a platform** → **Web**

   d. Configurez les paramètres suivants :
      - **Redirect URIs** :
        - `http://localhost:4999/api/auth/sso/azure/callback`
        - Ajoutez aussi vos URLs de production si nécessaire
      - **Front-channel logout URL** : Laissez vide
      - **Implicit grant and hybrid flows** :
        - ❌ Ne cochez PAS "Access tokens"
        - ❌ Ne cochez PAS "ID tokens"
      - **Allow public client flows** : No

   e. Cliquez sur **Configure**

   **Option B : Créer une nouvelle application (recommandé si vous avez des problèmes)**

   a. Cliquez sur **New registration**

   b. Configurez :
      - **Name** : Votre nom d'application
      - **Supported account types** : Choisissez selon vos besoins
      - **Redirect URI** :
        - Type : **Web** (PAS "SPA")
        - URI : `http://localhost:4999/api/auth/sso/azure/callback`

   c. Cliquez sur **Register**

   d. Notez le nouveau **Application (client) ID**

4. **Vérifiez les API permissions**
   - Cliquez sur **API permissions**
   - Assurez-vous d'avoir au minimum :
     - Microsoft Graph → `User.Read` (Delegated)
     - Microsoft Graph → `openid` (Delegated)
     - Microsoft Graph → `profile` (Delegated)
     - Microsoft Graph → `email` (Delegated)

5. **Important : Type d'application**
   - Dans **Authentication** → **Advanced settings**
   - **Application type** doit être **"Web"**, pas "SPA"
   - **Allow public client flows** : **No**

### Configuration pour Public Client (PKCE) avec Application Web

Notre backend utilise PKCE (Proof Key for Code Exchange) sans client secret, ce qui est supporté par les applications Web Azure AD en mode "public client". C'est la configuration correcte pour votre cas.

#### Vérifications importantes :

1. **Dans Authentication** :
   - Platform : **Web** (pas SPA)
   - Redirect URIs : URLs de callback correctes
   - NO implicit grant flows activés

2. **Dans Certificates & secrets** :
   - Vous n'avez PAS besoin de client secret
   - Le champ peut rester vide

3. **Dans Manifest** (optionnel, pour vérification) :
   - `"allowPublicClient": false` ou `null` (pas `true`)
   - `"replyUrlsWithType"`: devrait avoir `"type": "Web"`

### Exemple de Manifest correct

```json
{
    ...
    "replyUrlsWithType": [
        {
            "url": "http://localhost:4999/api/auth/sso/azure/callback",
            "type": "Web"
        }
    ],
    "allowPublicClient": false,
    ...
}
```

## Test après reconfiguration

1. **Testez le flux complet** :
   ```bash
   # Démarrez par l'URL de login
   http://localhost:4999/api/auth/sso/azure/login/{tenant_id}
   ```

2. **Vérifiez les logs** :
   ```bash
   docker-compose logs -f api | grep -E "(SSO|Azure|PKCE)"
   ```

3. **En cas d'erreur persistante** :
   - Attendez 5-10 minutes après les changements (propagation Azure AD)
   - Videz le cache du navigateur
   - Testez en navigation privée

## Configuration actuelle dans le code

Le code backend est configuré correctement pour fonctionner avec une application Web Azure AD utilisant PKCE :

```python
# backend/app/services/azure_ad_service.py
# Configuration correcte pour application Web avec PKCE (sans client_secret)

token_data = {
    'client_id': self.sso_config.client_id,
    'grant_type': 'authorization_code',
    'code': code,
    'redirect_uri': redirect_uri,
    'code_verifier': code_verifier,  # PKCE
    'scope': ' '.join(self.DEFAULT_SCOPES)
    # Pas de client_secret - c'est correct
}
```

## Différences entre les types d'applications

| Aspect | Single-Page Application (SPA) | Web Application |
|--------|-------------------------------|-----------------|
| Token Exchange | Frontend uniquement (CORS) | Backend ou Frontend |
| Client Secret | Non supporté | Optionnel |
| PKCE | Obligatoire | Recommandé |
| Implicit Flow | Déprécié mais possible | Déconseillé |
| Auth Code Flow | Oui, frontend uniquement | Oui, backend ou frontend |
| Redirect URI Type | SPA | Web |
| Usage typique | React, Vue, Angular (frontend) | Flask, Django, .NET (backend) |

## Votre cas d'usage

- **Architecture** : Backend Flask avec API REST
- **Type requis** : **Web Application**
- **Flux** : Authorization Code Flow avec PKCE
- **Secret** : Pas nécessaire (public client avec PKCE)

## Erreurs courantes et solutions

### Erreur : AADSTS9002327
**Cause** : Application configurée comme SPA
**Solution** : Reconfigurer comme Web (voir ci-dessus)

### Erreur : AADSTS7000218
**Cause** : Client secret manquant pour une app confidentielle
**Solution** : Soit ajouter un secret, soit utiliser PKCE sans secret

### Erreur : AADSTS50011
**Cause** : Redirect URI ne correspond pas
**Solution** : Vérifier que l'URI est exactement identique (protocole, port, path)

## Support et ressources

- [Documentation Microsoft - App types](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-app-types)
- [OAuth 2.0 auth code flow](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)
- [PKCE for OAuth](https://oauth.net/2/pkce/)

## Prochaines étapes

Après avoir reconfiguré votre application Azure AD :

1. Mettez à jour le `client_id` si vous avez créé une nouvelle app
2. Redémarrez votre backend Flask
3. Testez le flux SSO complet
4. Surveillez les logs pour tout problème résiduel