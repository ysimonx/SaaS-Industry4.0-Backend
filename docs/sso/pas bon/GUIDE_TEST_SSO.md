# Guide de Test SSO Azure AD

## ✅ Problème résolu : "Invalid state token"

L'erreur "Invalid state token" que vous avez rencontrée est **normale** quand vous testez avec l'URL directe Azure AD. Voici pourquoi :

### Pourquoi l'erreur se produit

1. Le flux OAuth2 utilise un **state token** pour la sécurité CSRF
2. Le state token est stocké dans la **session Flask** (cookie)
3. Quand vous copiez l'URL Azure AD directement :
   - ❌ Aucune session Flask n'est créée
   - ❌ Aucun state token n'est stocké
   - ❌ Le callback ne peut pas valider le state

### Solution : Toujours commencer par votre application

Le flux SSO **DOIT** commencer par votre endpoint `/api/auth/sso/azure/login/{tenant_id}` qui :
1. ✅ Crée une session Flask avec cookies
2. ✅ Génère et stocke le state token
3. ✅ Génère et stocke le PKCE code_verifier
4. ✅ Redirige vers Azure AD avec tous les paramètres

---

## 🧪 Comment tester le SSO correctement

### Option 1 : Test dans le navigateur (RECOMMANDÉ)

C'est la façon la plus simple et la plus réaliste :

1. **Ouvrez un nouvel onglet privé/incognito** (pour éviter les sessions existantes)

2. **Collez cette URL dans le navigateur :**
   ```
   http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205
   ```

3. **Vous serez automatiquement redirigé vers Azure AD**
   - Authentifiez-vous avec vos identifiants Azure
   - Acceptez les permissions si demandé

4. **Après l'authentification Azure :**
   - Vous serez redirigé vers le callback
   - Le state token sera validé automatiquement
   - Vous recevrez vos tokens JWT

5. **Résultat attendu :**
   ```json
   {
       "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
       "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
       "user": {
           "id": "...",
           "email": "votre@email.com",
           "name": "Votre Nom"
       },
       "tenant_id": "cb859f98-291e-41b2-b30f-2287c2699205",
       "auth_method": "sso"
   }
   ```

---

### Option 2 : Test avec curl (avancé)

Pour tester avec curl, il faut gérer les cookies :

```bash
# Étape 1: Initier le login et sauvegarder les cookies
curl -c cookies.txt -L -v \
  'http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205' \
  > auth_url.html

# Cela va créer une session et vous donner l'URL Azure AD

# Étape 2: Extraire l'URL de redirection
# (Vous devrez l'ouvrir dans un navigateur pour vous authentifier)

# Étape 3: Après authentification, Azure vous redirige vers:
# http://localhost:4999/api/auth/sso/azure/callback?code=XXX&state=YYY
# Capturez cette URL complète

# Étape 4: Appeler le callback avec les cookies de l'étape 1
curl -b cookies.txt \
  'http://localhost:4999/api/auth/sso/azure/callback?code=XXX&state=YYY'
```

---

## 🔍 Vérification de la configuration

Avant de tester, vérifiez que tout est bien configuré :

```bash
# Exécuter le script de vérification
docker-compose exec api python scripts/verify_azure_config.py
```

Tous ces points doivent être ✅ :
- Client Secret: None (mode PKCE)
- App Type: public
- Azure AD tenant accessible
- PKCE S256 supporté

---

## 🐛 Debugging

Si vous rencontrez encore des problèmes, vérifiez les logs en temps réel :

```bash
# Logs de l'API
docker-compose logs -f api

# Rechercher les entrées SSO
docker-compose logs api | grep -i "sso\|pkce\|azure"
```

### Logs attendus pour un flux réussi

```
INFO - Initiating Azure AD login for tenant cb859f98-...
DEBUG - Generated PKCE pair: verifier length=43, challenge length=43
INFO - Stored PKCE parameters in Redis with key: sso_session:...
INFO - Retrieved PKCE parameters from Redis and deleted key: sso_session:...
INFO - Using PKCE code_verifier for token exchange (public app)
INFO - Successfully exchanged code for tokens for tenant cb859f98-...
INFO - Successfully processed SSO login for user votre@email.com
```

---

## ✅ Checklist finale Azure Portal

Assurez-vous que dans Azure Portal :

1. **Authentification** → **Configurations de plateforme**
   - ✅ Type: **Web** (pas SPA, pas Mobile)
   - ✅ URI de redirection: `http://localhost:4999/api/auth/sso/azure/callback`

2. **Authentification** → **Paramètres avancés**
   - ✅ "Activer les flux mobiles et de bureau suivants": **OUI**

3. **Certificats et secrets**
   - ✅ **AUCUNE** clé secrète client configurée

4. **Autorisations des API**
   - ✅ Microsoft Graph → User.Read
   - ✅ openid, profile, email

---

## 🎉 Prochaines étapes

Une fois le SSO fonctionnel, vous pouvez :

1. **Intégrer avec votre frontend** : Rediriger vers l'URL SSO depuis votre UI
2. **Configurer le auto-provisioning** : Créer automatiquement les utilisateurs lors du premier login
3. **Mapper les rôles Azure AD** : Attribuer automatiquement des rôles selon les groupes Azure
4. **Tester le refresh token** : Utiliser l'endpoint `/api/auth/sso/azure/refresh`

---

## 📚 Scripts disponibles

- `scripts/test_sso_flow.py` - Test complet du flux SSO
- `scripts/verify_azure_config.py` - Vérification configuration Azure
- `scripts/diagnose_sso_error.py` - Diagnostic approfondi
- `scripts/test_sso_complete.py` - Vue d'ensemble de la config

---

## 💡 Questions fréquentes

**Q: Pourquoi l'URL de test direct ne fonctionne pas ?**
R: Elle ne peut pas fonctionner car elle ne crée pas de session. Utilisez toujours `/api/auth/sso/azure/login/{tenant_id}`.

**Q: Comment tester en production ?**
R: Changez les URLs de redirection dans Azure Portal pour pointer vers votre domaine de production.

**Q: Puis-je avoir plusieurs tenants SSO ?**
R: Oui ! Chaque tenant peut avoir sa propre configuration SSO Azure AD.

**Q: Le SSO fonctionne-t-il avec des comptes personnels Microsoft ?**
R: Non, seulement avec des comptes Azure AD d'entreprise (sauf si configuré différemment).
