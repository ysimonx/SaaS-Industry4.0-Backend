# Modèle de menaces — Système d'objets dynamiques

Ce document recense les risques de sécurité spécifiques au nouveau système de métadonnées dynamiques décrit dans [DYNAMIC_OBJECTS.md](DYNAMIC_OBJECTS.md).  
Pour les menaces du système existant, voir [SECURITY.md](SECURITY.md).

---

## Périmètre

Le système introduit :
- Des objets, champs et relations définis par les clients (admins tenant)
- Un moteur d'automatisation (triggers + règles stockées en base)
- Un stockage de données arbitraires en JSONB
- Une hiérarchie de permissions métier configurable
- Des pièces jointes liées à des records dynamiques

---

## Tableau des menaces

| # | Menace | Surface | Sévérité | Mitigation |
|---|---|---|---|---|
| T1 | Boucle infinie dans les règles d'automatisation | `automation_rules` | Haute | Compteur de profondeur + timeout |
| T2 | Injection de code dans les conditions | `automation_rules.conditions` | Haute | Jamais `eval()` — opérateurs Python purs + `simpleeval` avec sandbox |
| T3 | Accès cross-tenant dans les actions | `automation_rules.actions` | Critique | Toujours injecter `database_name` du tenant courant dans `AutomationEngine` |
| T4 | DoS par webhooks en masse | `action.type = call_webhook` | Moyenne | Queue asynchrone (Celery) + rate limit par tenant |
| T5 | Escalade de droits via `update_field` | `automation_rules.actions` | Haute | Liste blanche de champs modifiables ; exclure les champs système |
| T6 | Cycle dans un Self-Lookup | `object_records.data` | Moyenne | Limite de profondeur dans la CTE récursive (`depth < 50`) |
| T7 | Suppression en cascade non maîtrisée | `relationship_definitions` | Haute | Confirmer les suppressions Master-Detail avec compte des enfants |
| T8 | Exfiltration de données via `resolve_lookups` | `GET /records?resolve_lookups=true` | Moyenne | Limiter la profondeur de résolution (max 2 niveaux) ; pagination stricte |
| T9 | Déni de service par schéma JSONB massif | `object_records.data` | Faible | Limite de taille du payload JSON (ex: 1 Mo) |
| T10 | Fuite de `document_id` via jonction | `object_record_attachments` | Moyenne | Vérifier l'appartenance tenant du document avant attachement |
| T11 | Pollution de la hiérarchie de permissions | `permission_roles` | Moyenne | Seuls les `admin` peuvent modifier la hiérarchie |
| T12 | IDOR sur `record_id` d'un autre tenant | `/objects/<api_name>/records/<id>` | Critique | Toujours filtrer `object_definition_id` qui est scopé à la tenant DB |

---

## Détail des menaces critiques

### T1 — Boucle infinie dans les règles

**Scénario** : une règle `after_create` sur l'objet `A` crée un record dans `B`, dont une règle `after_create` crée un record dans `A` → boucle infinie.

**Mitigation** :
```python
# Dans AutomationEngine.on_record_event()
MAX_AUTOMATION_DEPTH = 5

def on_record_event(sender, **kwargs):
    depth = kwargs.get('_automation_depth', 0)
    if depth >= MAX_AUTOMATION_DEPTH:
        logger.error(f"Automation depth limit reached for {kwargs['object_api_name']}")
        return
    # Propager la profondeur aux actions récursives
    kwargs['_automation_depth'] = depth + 1
```

Timeout Celery de 30 secondes par tâche d'automatisation comme filet de sécurité supplémentaire.

---

### T2 — Injection de code dans les conditions

**Scénario** : un admin malveillant écrit `{"expr": "__import__('os').system('rm -rf /')"}`dans une condition d'automatisation.

**Règle absolue** : **jamais `eval()` ni `exec()` sur du contenu venant de la base.**

**Mitigation** :
```python
# Uniquement des opérateurs Python purs pour les conditions simples
OP_MAP = {'gt': lambda a, b: float(a) > float(b), ...}

# Pour les expressions arithmétiques avancées uniquement :
from simpleeval import simple_eval, EvalWithCompoundTypes
evaluator = EvalWithCompoundTypes(
    operators={},          # pas d'opérateurs Python arbitraires
    functions={},          # pas de fonctions
    names=record_data      # uniquement les champs du record
)
result = evaluator.eval(expression)  # sûr
```

`simpleeval` n'autorise pas les imports, l'accès aux attributs d'objets, ni les appels de fonctions non whitelistées.

---

### T3 — Accès cross-tenant dans les actions

**Scénario** : une action `create_record` spécifie un `tenant_id` différent dans ses paramètres, créant un record dans la base d'un autre tenant.

**Mitigation** : `AutomationEngine` reçoit `database_name` comme contexte non-modifiable depuis le signal blinker. Les actions ne peuvent pas surcharger ce paramètre :

```python
class AutomationEngine:
    @classmethod
    def on_record_event(cls, sender, database_name, **kwargs):
        # database_name est transmis par DynamicRecordService, pas par la règle
        # Les actions ne peuvent qu'opérer sur database_name
        cls._execute_action(action, database_name=database_name, ...)
        # Jamais : cls._execute_action(action, database_name=action['params'].get('tenant_db'))
```

---

### T5 — Escalade de droits via `update_field`

**Scénario** : une règle d'automatisation met à jour un champ `role` ou `is_admin` via `update_field`, contournant les contrôles d'autorisation normaux.

**Mitigation** : les actions `update_field` et `update_record` sont exécutées par `AutomationEngine` via `DynamicRecordService.update_record()` avec un flag `bypass_automation=True` (pour éviter les boucles) et `system_context=True`. En contexte système, les champs marqués `is_system=True` dans `field_definitions` sont interdits à la modification par automation. Les champs système réservés incluent : `created_by`, `created_at`, tous les champs de la `permission_role_assignments`.

---

### T7 — Suppression en cascade non maîtrisée

**Scénario** : un admin supprime un record "Site" qui, via Master-Detail en cascade, déclenche la suppression de 10 000 records "Bâtiment" → "Étage" → "Équipement", bloquant la base pendant plusieurs secondes.

**Mitigation** :
1. `DELETE /records/{id}` retourne d'abord un `DRY_RUN` avec le nombre total de records affectés si > 100
2. La suppression en cascade massive est envoyée en tâche Celery asynchrone (pas synchrone dans la requête HTTP)
3. Réponse immédiate : `{"status": "pending", "task_id": "...", "estimated_records": 10420}`

---

### T10 — Fuite de document cross-tenant via la jonction

**Scénario** : un utilisateur du tenant A connaît un `document_id` qui appartient au tenant B et l'attache à un record du tenant A.

**Mitigation** : avant d'insérer dans `object_record_attachments`, le service vérifie que le `document_id` existe bien **dans la tenant DB courante** (pas la base principale) :

```python
doc = session.query(Document).filter_by(id=document_id).first()
if not doc:
    return None, f"Document {document_id} not found in this tenant"
# La tenant DB est scopée → un document d'un autre tenant n'est pas visible ici
```

L'isolation par base PostgreSQL distincte rend cette vérification implicitement correcte — mais elle doit quand même être explicite pour la clarté du code.

---

## Audit des données JSONB

Le JSONB `object_records.data` contient des données arbitraires saisies par les utilisateurs. Points de vigilance :

| Risque | Mitigation |
|---|---|
| XSS stocké (si données affichées dans un front-end) | Responsabilité du front-end (échappement HTML). Le backend retourne le JSONB tel quel. |
| Payload oversized | Limite de 1 Mo sur le corps des requêtes (`MAX_CONTENT_LENGTH` dans la config Flask) |
| Caractères spéciaux dans `api_name` | Regex `^[a-z][a-z0-9_]{0,79}$` validée par Marshmallow ET par le service |
| Injection dans les filtres JSONB | Requêtes paramétrées SQLAlchemy — les noms de champs `field_api_name` sont validés contre `field_definitions` avant d'être interpolés |

---

## Recommandations pour la mise en production

1. **Activer les logs d'audit** pour toutes les opérations de l'`AutomationEngine` (quelles règles ont été évaluées, quelles actions exécutées, pour quel record, par quel déclencheur).
2. **Limiter le nombre de règles actives** par objet (ex: max 20) pour prévenir l'abus.
3. **Monitorer les temps d'exécution** des règles d'automatisation via Flower (tâches Celery) — une règle qui prend > 5s est suspecte.
4. **Tests de pénétration** ciblés sur : IDOR entre tenants, injection dans les conditions d'automatisation, suppression en cascade de grande ampleur.
5. **Revue des `automation_rules`** lors de l'onboarding d'un nouveau tenant important — les admins tenant peuvent créer des règles puissantes.
