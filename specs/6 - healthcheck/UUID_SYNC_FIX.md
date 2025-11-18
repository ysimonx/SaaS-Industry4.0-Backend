# Fix: Healthchecks UUID Synchronization

## Problème

Lors de l'exécution de `start-healthchecks-enhanced.sh`, les checks Healthchecks.io étaient recréés avec de nouveaux UUIDs au lieu de réutiliser les UUIDs définis dans `.env.healthchecks`.

### Cause

L'ancien script `ensure_healthchecks.py` utilisait l'**API REST de Healthchecks.io** pour créer les checks. Cette API ne permet **pas de forcer un UUID spécifique** lors de la création d'un check :

```python
# ❌ BUG dans ensure_healthchecks.py ligne 304
created_check = manager.create_check(check_config)  # UUID non passé !
```

Même si l'UUID était passé (ligne 190), le paramètre `unique` de l'API sert uniquement à éviter les doublons, pas à imposer un UUID.

## Solution

### Nouvelle Architecture

Au lieu d'utiliser l'API REST, nous utilisons maintenant **Django ORM directement** pour accéder à la base de données Healthchecks et créer les checks avec les UUIDs exacts.

### Fichiers Créés

1. **`backend/scripts/ensure_healthchecks_with_uuid.py`**
   - Script Python qui utilise Django ORM
   - Lit les UUIDs depuis `.env.healthchecks`
   - Crée ou met à jour les checks directement en base de données
   - Garantit que les UUIDs correspondent exactement

2. **`scripts/healthcheck/sync-healthchecks-uuids.sh`**
   - Wrapper shell qui exécute le script Python dans le conteneur Healthchecks
   - Gère la copie des fichiers dans le conteneur
   - Détecte automatiquement le nom du conteneur

### Fichiers Modifiés

- **`scripts/healthcheck/start-healthchecks-enhanced.sh`**
  - Remplace l'appel à `ensure_healthchecks.py` par `sync-healthchecks-uuids.sh`
  - Plus simple et plus fiable

## Utilisation

### Synchronisation Manuelle

Si vous voulez synchroniser les UUIDs sans redémarrer tout :

```bash
./scripts/healthcheck/sync-healthchecks-uuids.sh
```

### Nettoyage des Checks Dupliqués

Si vous avez des checks dupliqués (avec des UUIDs aléatoires), utilisez :

```bash
./scripts/healthcheck/cleanup-duplicate-checks.sh
```

Ce script :
- ✅ Conserve les checks avec les UUIDs de `.env.healthchecks`
- 🗑️ Supprime tous les autres checks (doublons avec UUIDs aléatoires)
- 📊 Affiche un résumé des opérations

### Avec le Script de Démarrage

Le nouveau script est automatiquement appelé par `start-healthchecks-enhanced.sh` :

```bash
./scripts/healthcheck/start-healthchecks-enhanced.sh
```

## Vérification

1. **Avant** : Les checks avaient des UUIDs aléatoires différents à chaque exécution
2. **Après** : Les checks conservent les UUIDs définis dans `.env.healthchecks`

Vérifier dans l'interface Healthchecks :
```bash
open http://localhost:8000
```

Les UUIDs doivent correspondre à ceux de `.env.healthchecks` :
```bash
grep "^HC_CHECK_" .env.healthchecks
```

## Détails Techniques

### Pourquoi Django ORM au lieu de l'API ?

| Approche | Avantages | Inconvénients |
|----------|-----------|---------------|
| **API REST** | Simple, documentée | ❌ Ne permet pas de forcer les UUIDs |
| **Django ORM** | ✅ Contrôle total sur les UUIDs | Nécessite accès au conteneur Healthchecks |

### Comment Django ORM Force les UUIDs

```python
# Dans ensure_healthchecks_with_uuid.py
check = Check(
    code=uuid,  # ✅ UUID forcé directement !
    project=project,
    name=check_config['name'],
    # ... autres champs
)
check.save()
```

### Flux d'Exécution

1. `start-healthchecks-enhanced.sh` démarre Healthchecks
2. Crée le compte admin et récupère l'API key
3. Appelle `sync-healthchecks-uuids.sh`
4. Copie `.env.healthchecks` dans le conteneur Healthchecks
5. Copie `ensure_healthchecks_with_uuid.py` dans le conteneur
6. Exécute le script Python via Django shell
7. Le script lit les UUIDs et crée/met à jour les checks en base de données

## Compatibilité

- ✅ Compatible avec l'ancien `.env.healthchecks`
- ✅ Pas besoin de recréer les UUIDs
- ✅ Idempotent : peut être exécuté plusieurs fois sans effet de bord
- ✅ Met à jour automatiquement les checks existants si la configuration change

## Rollback

Si besoin de revenir à l'ancien système (déconseillé) :

```bash
# Dans start-healthchecks-enhanced.sh, remplacer :
bash "$SCRIPT_DIR/sync-healthchecks-uuids.sh"

# Par :
docker-compose exec -T api python scripts/ensure_healthchecks.py --env-file .env.healthchecks
```

## Notes

- Le script `ensure_healthchecks.py` est **conservé** pour compatibilité, mais n'est plus utilisé par défaut
- Le nouveau script nécessite que le conteneur Healthchecks soit démarré
- Les UUIDs dans `.env.healthchecks` sont **immuables** une fois créés
- Si un UUID n'existe pas dans `.env.healthchecks`, le script **skip** le check (ne le crée pas)

## Références

- Script principal : [backend/scripts/ensure_healthchecks_with_uuid.py](../../backend/scripts/ensure_healthchecks_with_uuid.py)
- Wrapper shell : [scripts/healthcheck/sync-healthchecks-uuids.sh](../../scripts/healthcheck/sync-healthchecks-uuids.sh)
- Configuration : [.env.healthchecks](../../.env.healthchecks)
