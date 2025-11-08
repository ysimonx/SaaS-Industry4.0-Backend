# Guide de Débogage SSO - Problème d'encodage HTML dans les URLs

## Problème Identifié

L'erreur Microsoft "AADSTS900144: The request body must contain the following parameter: 'scope'" se produit lorsque l'URL de redirection contient des entités HTML (`&amp;` au lieu de `&`).

## Diagnostic Effectué

### Tests Réalisés

1. **Test unitaire de génération d'URL** ([test_sso_detect_api.py:67](backend/tests/integration/test_sso_detect_api.py#L67))
   - Résultat : ✅ L'URL générée par `AzureADService.get_authorization_url()` est correcte
   - Les paramètres sont séparés par `&` et non `&amp;`

2. **Test direct de l'endpoint HTTP**
   ```bash
   curl -I "http://localhost:4999/api/auth/sso/azure/login/{tenant_id}"
   ```
   - Résultat : ✅ Le header Location contient une URL correcte avec `&`

3. **Test avec Python requests**
   - Résultat : ✅ L'URL retournée est correcte

## Cause Probable

L'URL est correctement générée par le backend, mais elle est encodée en HTML (`&` → `&amp;`) dans l'un des scénarios suivants :

1. **Copie depuis les DevTools du navigateur** : Certains navigateurs encodent l'URL lors de l'affichage dans l'onglet Network
2. **Proxy ou Middleware** : Un proxy inverse ou middleware peut encoder l'URL
3. **Frontend/Client** : Le client qui consomme l'API encode l'URL avant de l'utiliser
4. **Logs ou monitoring** : L'URL est copiée depuis un système de logs qui l'affiche encodée

## Solutions Recommandées

### Pour les Développeurs

1. **Vérifier l'URL directement avec curl**
   ```bash
   curl -v "http://localhost:4999/api/auth/sso/azure/login/{tenant_id}" 2>&1 | grep Location
   ```

2. **Dans le navigateur**
   - Ne pas copier l'URL depuis l'onglet Network des DevTools
   - Utiliser la console JavaScript pour obtenir l'URL brute :
   ```javascript
   fetch('/api/auth/sso/azure/login/{tenant_id}', {redirect: 'manual'})
     .then(r => console.log(r.headers.get('Location')))
   ```

3. **Si vous utilisez un frontend React/Vue/Angular**
   - Vérifiez que vous n'encodez pas l'URL avant la redirection
   - Utilisez `window.location.href = url` directement sans transformation

### Code Frontend Recommandé

```javascript
// ❌ MAUVAIS - Peut causer l'encodage HTML
const loginSSO = async (tenantId) => {
  const response = await fetch(`/api/auth/sso/azure/login/${tenantId}`);
  const html = await response.text(); // L'URL pourrait être encodée
  window.location.href = html;
}

// ✅ CORRECT - Suit la redirection naturellement
const loginSSO = (tenantId) => {
  window.location.href = `/api/auth/sso/azure/login/${tenantId}`;
}

// ✅ CORRECT - Si vous devez intercepter la réponse
const loginSSO = async (tenantId) => {
  const response = await fetch(`/api/auth/sso/azure/login/${tenantId}`, {
    redirect: 'manual'
  });

  if (response.status === 302 || response.status === 303) {
    const redirectUrl = response.headers.get('Location');
    window.location.href = redirectUrl;
  }
}
```

### Pour Déboguer

1. **Activer les logs détaillés dans le backend**
   ```python
   # Dans backend/app/routes/sso_auth.py ligne 80
   logger.info(f"Initiating Azure AD login for tenant {tenant_id}")
   logger.info(f"Generated auth URL: {auth_url}")  # Ajouter cette ligne
   ```

2. **Vérifier dans les logs Docker**
   ```bash
   docker-compose logs -f api | grep "Generated auth URL"
   ```

3. **Tester avec un script Python simple**
   ```python
   import requests

   tenant_id = "YOUR_TENANT_ID"
   response = requests.get(
       f"http://localhost:4999/api/auth/sso/azure/login/{tenant_id}",
       allow_redirects=False
   )

   location = response.headers.get('Location')
   print(f"URL: {location}")

   if '&amp;' in location:
       print("⚠️  PROBLÈME: L'URL contient des entités HTML")
   else:
       print("✅ L'URL est correcte")
   ```

## Configuration Nginx (si applicable)

Si vous utilisez Nginx comme proxy, assurez-vous qu'il ne modifie pas les headers :

```nginx
location /api/ {
    proxy_pass http://backend:4999;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Important: Ne pas encoder les headers de réponse
    proxy_pass_header Location;
}
```

## Vérification Finale

Pour confirmer que le problème est résolu :

1. Lancez le test automatisé :
   ```bash
   docker-compose exec api pytest tests/integration/test_sso_detect_api.py::TestSSODetectAPI::test_azure_authorization_url_generation -v
   ```

2. Testez manuellement avec votre navigateur :
   - Ouvrez les DevTools (F12)
   - Onglet Network
   - Naviguez vers `/api/auth/sso/azure/login/{tenant_id}`
   - Vérifiez que vous êtes redirigé vers Microsoft sans erreur

## Contact

Si le problème persiste après avoir suivi ce guide, vérifiez :
1. La version du navigateur et les extensions installées
2. Les proxies ou VPN actifs
3. Les middlewares ou intercepteurs dans votre application frontend