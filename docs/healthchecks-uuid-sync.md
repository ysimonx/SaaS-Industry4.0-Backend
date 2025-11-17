# Synchronisation des UUIDs Healthchecks.io

## Problème résolu

Lorsque vous utilisez `.env.healthchecks` sur différentes machines, les checks Healthchecks.io peuvent avoir des UUIDs différents, causant des erreurs 404 lors des pings. Cette documentation explique comment synchroniser les UUIDs entre machines.

## Solution

Nous avons mis en place plusieurs mécanismes pour garantir que les checks existent avec les UUIDs spécifiés dans `.env.healthchecks` :

### 1. Script de synchronisation automatique

Le script `backend/scripts/ensure_healthchecks.py` vérifie et crée les checks avec les UUIDs spécifiés :

```bash
cd backend
python scripts/ensure_healthchecks.py
```

Ce script :
- Lit les UUIDs depuis `.env.healthchecks`
- Vérifie si chaque check existe dans Healthchecks.io
- Crée les checks manquants
- Met à jour les checks existants si nécessaire
- Met à jour `.env.healthchecks` si l'API génère un UUID différent

Options :
- `--force-recreate` : Force la mise à jour de tous les checks
- `--env-file <path>` : Spécifie un fichier d'environnement alternatif

### 2. Client Healthchecks amélioré

Le client `enhanced_healthchecks_client.py` inclut l'auto-provisioning :

```python
from app.monitoring.enhanced_healthchecks_client import enhanced_healthchecks

# Le client créera automatiquement le check s'il n'existe pas
enhanced_healthchecks.ping('uuid-du-check')
```

Fonctionnalités :
- **Auto-provisioning** : Crée automatiquement les checks manquants lors du premier ping
- **Cache** : Évite les requêtes répétées pour vérifier l'existence des checks
- **Mise à jour automatique** : Met à jour `.env.healthchecks` si nécessaire

Configuration (dans `.env.healthchecks`) :
```bash
HEALTHCHECKS_AUTO_PROVISION=true  # Active l'auto-provisioning (par défaut)
```

### 3. Script de démarrage amélioré

Le script `scripts/start-healthchecks-enhanced.sh` automatise tout le processus :

```bash
./scripts/start-healthchecks-enhanced.sh
```

Ce script :
1. Démarre les conteneurs Healthchecks si nécessaire
2. Attend que Healthchecks soit prêt
3. Crée un compte admin si nécessaire
4. Synchronise tous les checks avec les UUIDs fournis
5. Affiche un résumé de la configuration

## Utilisation sur une nouvelle machine

### Méthode 1 : Synchronisation automatique (recommandée)

1. Copiez votre `.env.healthchecks` avec les UUIDs existants
2. Lancez le script de démarrage :
   ```bash
   ./scripts/start-healthchecks-enhanced.sh
   ```
3. Les checks seront automatiquement créés avec les bons UUIDs

### Méthode 2 : Synchronisation manuelle

1. Copiez `.env.healthchecks` sur la nouvelle machine
2. Synchronisez les checks :
   ```bash
   cd backend
   python scripts/ensure_healthchecks.py
   ```
3. Redémarrez les services pour utiliser les nouveaux UUIDs

### Méthode 3 : Auto-provisioning lors de l'exécution

1. Utilisez le client amélioré dans votre code :
   ```python
   # Dans app/__init__.py ou un fichier de configuration
   from app.monitoring.enhanced_healthchecks_client import enhanced_healthchecks

   # Remplacez l'ancien client
   healthchecks = enhanced_healthchecks
   ```

2. Les checks seront créés automatiquement lors du premier ping

## Structure des UUIDs dans .env.healthchecks

```bash
# Check IDs (à conserver entre machines)
HC_CHECK_API=0cab08fe-03f4-48c2-a927-90493fa0b2f2
HC_CHECK_CELERY_BEAT=229acece-8847-4ed7-97f4-94c720651ed3
HC_CHECK_CELERY_WORKER=ed5560b3-ac29-4d5b-adf9-ef59d636dd4f
HC_CHECK_COMPREHENSIVE=e98007a5-6bad-4bc4-a6be-4376f7b9560f
HC_CHECK_HEALTH_TASK=9e0f75b6-0d5f-4675-9a11-4a53cbbdc6bd
HC_CHECK_KAFKA=360a07e6-ec57-4bf2-98e8-eb66d59e49d8
HC_CHECK_KAFKA_CONSUMER=1e465c77-0d23-4e23-b4e3-75e35577bc2a
HC_CHECK_KEY_ROTATION=46cc758c-9e77-4dfe-9ecc-f89c71e16b50
HC_CHECK_MINIO=1430fb9e-a21d-4e3b-a818-46d45eea212b
HC_CHECK_POSTGRES=8d634561-7bb5-461c-84f3-596982e1f80e
HC_CHECK_REDIS=5f671802-21f2-4c94-91b6-0d4b1648f9c3
HC_CHECK_SSO_TOKEN_REFRESH=d2877c0a-88e2-4155-afa2-403119c80af0
HC_CHECK_TOKEN_CLEANUP=ee707316-50b2-4535-bb97-eea6f23966a0
HC_CHECK_VAULT=18c7f459-82c7-43f1-9270-4c9546f82041
```

## Vérification

Pour vérifier que tous les checks sont correctement configurés :

1. **Via l'interface web** :
   ```
   http://localhost:8000
   ```
   Connectez-vous et vérifiez que tous les checks sont présents

2. **Via l'API** :
   ```bash
   curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
        http://localhost:8000/api/v1/checks/
   ```

3. **Test de ping** :
   ```bash
   # Test d'un check spécifique
   curl http://localhost:8000/ping/$HC_CHECK_API
   ```

## Dépannage

### Erreur 404 lors des pings

Si vous obtenez des erreurs 404 :

1. Vérifiez que le check existe :
   ```bash
   curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
        http://localhost:8000/api/v1/checks/$UUID
   ```

2. Si le check n'existe pas, créez-le :
   ```bash
   cd backend
   python scripts/ensure_healthchecks.py
   ```

### UUIDs différents après création

L'API Healthchecks.io génère parfois ses propres UUIDs. Dans ce cas :

1. Le script met automatiquement à jour `.env.healthchecks`
2. Commitez le fichier mis à jour dans votre repo
3. Utilisez les nouveaux UUIDs sur toutes les machines

### Checks en double

Si vous avez des checks en double :

1. Listez tous les checks :
   ```bash
   curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
        http://localhost:8000/api/v1/checks/ | jq
   ```

2. Supprimez les doublons via l'interface web ou l'API

3. Relancez la synchronisation :
   ```bash
   python scripts/ensure_healthchecks.py --force-recreate
   ```

## Best Practices

1. **Versionnez `.env.healthchecks`** : Commitez le fichier (sans les clés API sensibles) pour partager les UUIDs

2. **Utilisez le client amélioré** : Il gère automatiquement la création des checks manquants

3. **Synchronisez régulièrement** : Lancez `ensure_healthchecks.py` dans votre CI/CD

4. **Documentez les checks** : Maintenez à jour la configuration dans `DEFAULT_CHECKS`

5. **Monitoring proactif** : Activez l'auto-provisioning pour éviter les interruptions de monitoring

## Configuration avancée

### Désactiver l'auto-provisioning

Si vous préférez gérer manuellement les checks :

```bash
# Dans .env.healthchecks
HEALTHCHECKS_AUTO_PROVISION=false
```

### Utiliser des UUIDs personnalisés

Pour forcer des UUIDs spécifiques :

1. Éditez `.env.healthchecks` avec vos UUIDs
2. Lancez `ensure_healthchecks.py`
3. Si l'API ne permet pas vos UUIDs, elle en générera de nouveaux

### Migration depuis l'ancien système

Si vous migrez depuis l'ancien client :

1. Remplacez dans votre code :
   ```python
   # Ancien
   from app.monitoring.healthchecks_client import healthchecks

   # Nouveau
   from app.monitoring.enhanced_healthchecks_client import enhanced_healthchecks as healthchecks
   ```

2. L'API reste identique, aucun changement de code nécessaire

## Support

Pour toute question ou problème :
- Consultez les logs : `docker-compose logs healthchecks`
- Vérifiez la configuration : `cat .env.healthchecks`
- Testez la connectivité : `curl http://localhost:8000/api/v1/status/`