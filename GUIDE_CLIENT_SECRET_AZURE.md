# Guide : Configurer Azure AD avec Client Secret (Mode Confidential)

## 📋 Vue d'ensemble

Si le mode PKCE (Public Client) ne fonctionne pas, vous pouvez utiliser le mode **Confidential Application** avec un client secret. C'est plus traditionnel et plus largement supporté.

### Différences entre les deux modes

| Aspect | Public Client (PKCE) | Confidential Client (Secret) |
|--------|---------------------|----------------------------|
| Sécurité | Code challenge dynamique | Secret statique |
| Configuration | Plus simple | Nécessite gestion secret |
| Compatibilité | Certaines restrictions Azure | Universellement supporté |
| Stockage | Rien à stocker côté backend | Secret à sécuriser |

---

## 🔐 ÉTAPE 1 : Créer un Client Secret dans Azure Portal

### 1. Accéder à Azure Portal

1. Allez sur https://portal.azure.com
2. **Azure Active Directory** (ou Microsoft Entra ID)
3. **Inscriptions d'applications** (App registrations)
4. Sélectionnez votre application : `dd5f0275-3e46-4103-bce5-1589a6f13d48`

### 2. Créer le Client Secret

1. Dans le menu de gauche, cliquez sur **Certificats et secrets**
2. Sous **Clés secrètes client**, cliquez sur **+ Nouvelle clé secrète client**
3. Configurez la clé secrète :
   - **Description** : `Backend API Secret` (ou un nom descriptif)
   - **Expire le** : Choisissez une durée (recommandé : 6 mois ou 1 an)
4. Cliquez sur **Ajouter**

### 3. Copier le Client Secret

⚠️ **IMPORTANT** : La valeur du secret n'est affichée **qu'UNE SEULE FOIS** !

1. Une fois créé, vous verrez deux valeurs :
   - **ID de la clé secrète** : Ne pas utiliser
   - **Valeur** : ⚠️ **COPIEZ CETTE VALEUR IMMÉDIATEMENT**

2. Exemple de valeur :
   ```
   8Q~abcdefghijklmnopqrstuvwxyz1234567890ABCD
   ```

3. ⚠️ Si vous perdez cette valeur, vous devrez créer une nouvelle clé secrète !

---

## 🔧 ÉTAPE 2 : Configurer le Client Secret dans l'application

### Option A : Via l'API (Recommandé)

Utilisez l'endpoint pour mettre à jour la configuration SSO :

```bash
# Remplacez YOUR_ACCESS_TOKEN, TENANT_ID et CLIENT_SECRET
curl -X PUT \
  'http://localhost:4999/api/tenants/{TENANT_ID}/sso/config' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "client_secret": "8Q~abcdefghijklmnopqrstuvwxyz1234567890ABCD"
  }'
```

### Option B : Directement dans la base de données

```bash
# Connectez-vous à la base de données
docker-compose exec postgres psql -U postgres -d saas_platform

# Mettez à jour la configuration SSO
UPDATE tenant_sso_configs
SET client_secret = '8Q~abcdefghijklmnopqrstuvwxyz1234567890ABCD'
WHERE tenant_id = 'cb859f98-291e-41b2-b30f-2287c2699205';

# Vérifiez
SELECT tenant_id, client_id,
       CASE WHEN client_secret IS NOT NULL THEN '[SECRET CONFIGURÉ]' ELSE '[PAS DE SECRET]' END as secret_status
FROM tenant_sso_configs;

# Quittez
\q
```

### Option C : Via un script Python

Créons un script dédié :

```bash
docker-compose exec api python scripts/set_sso_client_secret.py
```

---

## 📝 ÉTAPE 3 : Utiliser le script de configuration

Le script interactif vous guide à travers la configuration :

```bash
docker-compose exec api python scripts/set_sso_client_secret.py
```

Le script va :
1. ✅ Afficher l'état actuel de la configuration
2. ✅ Vous demander le client secret (saisie masquée)
3. ✅ Valider et enregistrer le secret
4. ✅ Mettre à jour le mode en "confidential"

---

## 🧪 ÉTAPE 4 : Tester l'authentification

Après avoir configuré le client secret :

### Test dans le navigateur

1. **Ouvrez un navigateur en mode privé**
2. **Allez à :**
   ```
   http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205
   ```
3. **Authentifiez-vous avec Azure AD**
4. **Résultat attendu** : Vous recevez vos tokens JWT

### Vérifier les logs

```bash
docker-compose logs -f api | grep -i "client_secret\|token exchange"
```

Vous devriez voir :
```
INFO - Using client_secret for token exchange (confidential app)
INFO - Successfully exchanged code for tokens
```

---

## 🔒 Sécurité : Utiliser les variables d'environnement (Production)

Pour la production, **NE STOCKEZ JAMAIS** le client secret directement dans la base de données ou le code source.

### Option 1 : Variables d'environnement

```bash
# Dans .env ou docker-compose.yml
AZURE_CLIENT_SECRET=8Q~abcdefghijklmnopqrstuvwxyz1234567890ABCD
```

### Option 2 : HashiCorp Vault (Recommandé en production)

Le projet supporte déjà Vault. Activez-le avec :

```bash
USE_VAULT=true
```

Les secrets seront chargés depuis Vault au démarrage.

### Option 3 : Azure Key Vault

Stockez le secret dans Azure Key Vault et récupérez-le au démarrage de l'application.

---

## 🔄 Passer de PKCE à Client Secret (résumé complet)

### Étape par étape

1. **Créer le client secret dans Azure Portal**
   - Certificats et secrets → Nouvelle clé secrète client
   - Copiez la valeur (une seule fois !)

2. **Configurer dans l'application**
   ```bash
   docker-compose exec api python scripts/set_sso_client_secret.py
   ```

3. **Optionnel : Désactiver les flux publics dans Azure Portal**
   - Authentification → Paramètres avancés
   - "Activer les flux mobiles et de bureau suivants" → NON

4. **Tester**
   - Ouvrir : `http://localhost:4999/api/auth/sso/azure/login/{tenant_id}`
   - S'authentifier
   - Vérifier les logs

---

## ✅ Vérification de la configuration

Utilisez ce script pour vérifier :

```bash
docker-compose exec api python scripts/verify_azure_config.py
```

Résultat attendu :
```
Client Secret: ✅ Configuré (XX caractères)
App Type: confidential
Mode: Confidential Application (avec client secret)
```

---

## 🆚 PKCE vs Client Secret : Quel mode choisir ?

### Utilisez PKCE (Public Client) si :
- ✅ Vous développez une application frontend (SPA, Mobile)
- ✅ Vous ne pouvez pas stocker de secrets de manière sécurisée
- ✅ Vous voulez la sécurité moderne recommandée par OAuth 2.1

### Utilisez Client Secret (Confidential) si :
- ✅ Votre backend peut stocker des secrets en sécurité
- ✅ PKCE ne fonctionne pas avec votre configuration Azure
- ✅ Vous avez des contraintes de compatibilité
- ✅ C'est plus simple pour votre infrastructure

**Pour votre cas** : Comme PKCE pose problème, le mode Client Secret est la solution pragmatique.

---

## 🚨 Problèmes courants

### "Invalid client secret"

- ✅ Vérifiez que vous avez copié la **Valeur** et pas l'**ID de la clé**
- ✅ Pas d'espaces au début/fin
- ✅ Le secret n'a pas expiré (vérifiez dans Azure Portal)
- ✅ La bonne app registration est utilisée

### "Client credentials flow is not supported"

- ❌ Vous essayez un mauvais flow
- ✅ Utilisez le Authorization Code Flow (ce que fait l'application)

### Le secret a expiré

1. Créez un nouveau secret dans Azure Portal
2. Mettez à jour avec le script
3. L'ancien secret continue de fonctionner jusqu'à expiration

---

## 📚 Documentation connexe

- [GUIDE_TEST_SSO.md](GUIDE_TEST_SSO.md) - Guide de test SSO
- [AZURE_AD_PKCE_FIX.md](AZURE_AD_PKCE_FIX.md) - Tentative de fix PKCE
- [CLAUDE.md](CLAUDE.md) - Documentation générale du projet

---

## 💡 Questions fréquentes

**Q: Puis-je avoir à la fois PKCE et client secret ?**
R: Techniquement oui, mais l'application utilisera le client secret en priorité s'il est configuré.

**Q: Comment supprimer le client secret pour revenir à PKCE ?**
R: Mettez le champ `client_secret` à `NULL` dans la base de données.

**Q: Le client secret est-il chiffré dans la base ?**
R: Non par défaut. Pour le chiffrement, activez Vault Transit Engine (déjà supporté pour les tokens Azure).

**Q: Combien de temps le secret est-il valide ?**
R: Durée choisie lors de la création (6 mois, 1 an, ou 2 ans maximum).
