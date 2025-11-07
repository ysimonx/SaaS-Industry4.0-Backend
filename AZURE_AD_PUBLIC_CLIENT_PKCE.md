# Configuration Azure AD pour Client Public avec PKCE (sans secret)

## Pourquoi cette erreur ?

L'erreur **AADSTS7000218** indique que votre application Azure AD est configurée comme "confidentielle" et attend un client_secret. Pour utiliser PKCE sans secret, vous devez activer le mode "client public".

## ✅ Solution : Activer "Allow public client flows"

### Étape 1 : Accédez à votre application

1. **Allez sur** [Azure Portal](https://portal.azure.com)
2. **Azure Active Directory** → **App registrations**
3. **Trouvez votre application** :
   - Client ID : `28d84fdd-1d63-4257-8543-86294a55aa80`

### Étape 2 : Configurez le client public

#### Option A : Via l'interface Authentication

1. **Dans le menu de gauche**, cliquez sur **"Authentication"**
2. **Faites défiler jusqu'à "Advanced settings"**
3. **Trouvez "Allow public client flows"**
4. **Activez le switch** : `Yes` ✅
5. **Cliquez sur "Save"** en haut de la page

#### Option B : Via le Manifest (plus technique)

1. **Dans le menu de gauche**, cliquez sur **"Manifest"**
2. **Cherchez la ligne** : `"allowPublicClient": false`
3. **Changez-la en** : `"allowPublicClient": true`
4. **Cliquez sur "Save"** en haut

### Étape 3 : Vérifiez la configuration

Votre configuration doit maintenant être :

| Paramètre | Valeur |
|-----------|--------|
| Platform | Web ✅ |
| Redirect URI | `http://localhost:4999/api/auth/sso/azure/callback` ✅ |
| Allow public client flows | **Yes** ✅ |
| Implicit grant | Tout décoché ❌ |
| Client secret | Pas nécessaire |

## 🔍 Pourquoi ça marche ?

Avec **"Allow public client flows" = Yes** :
- Azure AD accepte les requêtes sans client_secret
- PKCE (code_verifier/code_challenge) remplace le secret
- C'est plus sûr pour les applications où le secret ne peut pas être gardé secret

## Architecture de sécurité

```
Sans client secret (Public Client + PKCE) :
┌──────────┐      ┌──────────┐      ┌──────────┐
│ Browser  │─────▶│  Flask   │─────▶│ Azure AD │
└──────────┘      └──────────┘      └──────────┘
                        │
                   code_verifier
                 (généré dynamiquement)
                        │
                   Plus sûr car :
                   - Pas de secret stocké
                   - Code unique par requête
                   - Vérifié avec challenge
```

## ⚠️ Important

**"Allow public client flows"** ne signifie PAS que votre app est moins sécurisée :
- ✅ PKCE assure la sécurité du flux
- ✅ Le code_verifier est unique et temporaire
- ✅ Azure AD vérifie le code_challenge
- ✅ Recommandé pour les backends qui ne peuvent pas garder un secret de manière 100% sûre

## Test immédiat

Après avoir activé "Allow public client flows" :

1. **Attendez 1-2 minutes** (propagation Azure AD)
2. **Testez dans votre navigateur** :
   ```
   http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205
   ```

## Vérification du code

Le backend est déjà configuré pour supporter les deux modes :

```python
# backend/app/services/azure_ad_service.py

# Si client_secret existe → l'utilise (app confidentielle)
if hasattr(self.sso_config, 'client_secret') and self.sso_config.client_secret:
    token_data['client_secret'] = self.sso_config.client_secret
# Sinon → utilise PKCE (app publique)
else:
    token_data['code_verifier'] = code_verifier
```

## Résolution des problèmes

### Si l'erreur persiste après activation :

1. **Vérifiez dans le Manifest** que `"allowPublicClient": true`
2. **Videz le cache du navigateur** ou testez en navigation privée
3. **Attendez 5 minutes** pour la propagation complète
4. **Vérifiez les logs** :
   ```bash
   docker-compose logs -f api | grep -E "(PKCE|client_secret|token exchange)"
   ```

### Messages attendus dans les logs :

✅ Si configuré correctement :
```
Using PKCE code_verifier for token exchange (public app)
```

❌ Si toujours en mode confidentiel :
```
Token exchange failed: AADSTS7000218
```

## Comparaison des approches

| Aspect | Client Secret | PKCE sans secret |
|--------|--------------|------------------|
| Sécurité | ✅ Très sûr si bien géré | ✅ Très sûr avec PKCE |
| Stockage | Nécessite stockage sécurisé | Rien à stocker |
| Rotation | Doit être renouvelé | Pas de renouvellement |
| Complexité | Plus simple à configurer | Nécessite "Allow public client" |
| Recommandé pour | Apps serveur isolées | Apps publiques, SPAs, backends |

## Résumé

Pour votre cas (backend Flask) :
1. ✅ **Activez "Allow public client flows"** dans Azure Portal
2. ✅ **Pas besoin de client_secret**
3. ✅ **PKCE assure la sécurité**
4. ✅ **Plus simple à maintenir** (pas de secret à renouveler)

Cette configuration est parfaitement sûre et recommandée pour les applications modernes.