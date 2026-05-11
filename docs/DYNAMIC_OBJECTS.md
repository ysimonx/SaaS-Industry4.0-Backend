# Système de métadonnées dynamique (Custom Objects)

## Contexte

Le backend SaaS multi-tenant doit permettre à chaque client de créer ses propres "Objets" (type Asset, Maintenance_Intervention…), d'y ajouter des "Champs" (Custom Fields : text, number, date, picklist, file, lookup…) et de définir des "Relations" (Lookup / Master-Detail) — sans jamais modifier le schéma SQL physique.

Architecture cible inspirée de Salesforce, stockage des données dans des colonnes **JSONB** avec index GIN (meilleur compromis flexibilité / performance pour ce type de SaaS).

---

## Comparaison des stratégies de stockage

| Stratégie | Avantages | Inconvénients | Verdict |
|---|---|---|---|
| **EAV** (`entity_values`) | Simple à implémenter | Requêtes lentes, jointures explosives, pas de typage | ❌ Éliminé |
| **Tables physiques dynamiques** | Contraintes SQL natives, perf maximale | DDL au runtime (locks), gestion migrations complexe, dangereux | ❌ Éliminé |
| **JSONB** (retenu) | Flexible, index GIN, opérateurs `@>` `?`, pas de DDL sur les données | Pas de FK sur les valeurs JSON, validation applicative | ✅ Retenu |

---

## Schéma des 4 tables (toutes dans la base Tenant)

Les 4 tables rejoignent `files` et `documents` dans la base tenant — isolation totale entre clients.

### `object_definitions`
```sql
id UUID PK, api_name VARCHAR(80) UNIQUE, label VARCHAR(255),
label_plural VARCHAR(255), icon VARCHAR(50), description TEXT,
config JSONB DEFAULT '{}',   -- autonumber_format, autonumber_last, etc.
is_active BOOLEAN DEFAULT TRUE,
created_at, updated_at, created_by
```

### `field_definitions`
```sql
id UUID PK, object_id UUID FK→object_definitions CASCADE DELETE,
api_name VARCHAR(80), label VARCHAR(255),
field_type VARCHAR(30),      -- text|number|date|datetime|boolean|picklist|multipicklist
                             -- |textarea|email|url|phone|currency|percent
                             -- |autonumber|file|lookup
is_required BOOLEAN, is_unique BOOLEAN, is_active BOOLEAN,
sort_order INT,
default_value JSONB,
validation_rules JSONB,      -- {"min_length":1, "max_length":255, "min_value":0, "regex":"..."}
picklist_values JSONB,       -- [{"value":"active","label":"Actif","is_default":true}, ...]
lookup_object_id UUID FK→object_definitions SET NULL,
UNIQUE(object_id, api_name)
```

### `relationship_definitions`
```sql
id UUID PK,
name VARCHAR(80), label VARCHAR(255),
relationship_type VARCHAR(20) CHECK IN ('lookup','master_detail','self_lookup'),
parent_object_id UUID FK→object_definitions CASCADE,
child_object_id  UUID FK→object_definitions CASCADE,   -- == parent_object_id si self_lookup
child_field_id   UUID FK→field_definitions  CASCADE,
on_delete_behavior VARCHAR(20) CHECK IN ('cascade','restrict','set_null') DEFAULT 'restrict',
UNIQUE(child_object_id, child_field_id)
```

### `object_records`
```sql
id UUID PK,
object_definition_id UUID FK→object_definitions RESTRICT,
data    JSONB   DEFAULT '{}',  -- toutes les valeurs de champs ici
version INTEGER NOT NULL DEFAULT 1,  -- Optimistic Locking
created_at, updated_at, created_by

INDEX GIN (data)                               -- accélère @>, ?, @?
INDEX (object_definition_id, created_at DESC)
```

---

## Structure de l'API

### Gestion des méta-données (définitions)
```
GET    /api/tenants/<id>/meta/objects                                    → liste objets
POST   /api/tenants/<id>/meta/objects                                    → créer objet (admin)
GET    /api/tenants/<id>/meta/objects/<api_name>                         → détail objet
PUT    /api/tenants/<id>/meta/objects/<api_name>                         → modifier objet (admin)
DELETE /api/tenants/<id>/meta/objects/<api_name>                         → supprimer objet (admin)

GET    /api/tenants/<id>/meta/objects/<api_name>/fields                  → liste champs
POST   /api/tenants/<id>/meta/objects/<api_name>/fields                  → créer champ (admin)
GET    /api/tenants/<id>/meta/objects/<api_name>/fields/<field_api_name> → détail champ
PUT    /api/tenants/<id>/meta/objects/<api_name>/fields/<field_api_name> → modifier champ (admin)
DELETE /api/tenants/<id>/meta/objects/<api_name>/fields/<field_api_name> → supprimer champ (admin)

GET    /api/tenants/<id>/meta/objects/<api_name>/relationships            → liste relations
POST   /api/tenants/<id>/meta/objects/<api_name>/relationships            → créer relation (admin)
DELETE /api/tenants/<id>/meta/objects/<api_name>/relationships/<rel_id>  → supprimer (admin)
```

### CRUD générique sur les enregistrements
```
GET    /api/tenants/<id>/objects/<api_name>/records                      → liste filtrée, triée, paginée
POST   /api/tenants/<id>/objects/<api_name>/records                      → créer (user+)
GET    /api/tenants/<id>/objects/<api_name>/records/<record_id>          → détail
PUT    /api/tenants/<id>/objects/<api_name>/records/<record_id>          → modifier (user+)
DELETE /api/tenants/<id>/objects/<api_name>/records/<record_id>          → supprimer (admin)
POST   /api/tenants/<id>/objects/<api_name>/records/query                → filtre avancé (corps JSON)
```

**`GET /records` — query params supportés** :

```
?filter=data.status:eq:Urgent          → filtre simple sur un champ JSONB
?filter=data.status:eq:Urgent&filter=data.priorite:gte:3   → multi-filtres (AND implicite)
?sort=data.date_intervention:desc      → tri sur champ JSONB
?sort=created_at:asc                   → tri sur colonne native
?page=2&per_page=50                    → pagination offset/limit (défaut: page=1, per_page=20, max: 200)
?resolve_lookups=true                  → résout les UUID lookup en objets imbriqués (batch)
?include_attachments=true              → résout les champs file/file_list avec URLs pré-signées
?apply_hierarchy=true                  → filtre par visibilité hiérarchique (Manager voit ses subordonnés)
```

Syntaxe `filter` : `data.<field_api_name>:<operator>:<value>` pour les champs JSONB, `<column>:<operator>:<value>` pour les colonnes natives (`created_at`, `created_by`).  
`POST /records/query` accepte le même modèle sous forme de corps JSON (préférable pour les filtres complexes avec logique OR).

---

### `permission_roles` (nouvelle table)
```sql
id UUID PK,
api_name  VARCHAR(80) NOT NULL UNIQUE,
label     VARCHAR(255) NOT NULL,
parent_role_id UUID FK→permission_roles(id) SET NULL,  -- Self-lookup : arbre hiérarchique
level     INT NOT NULL DEFAULT 0,  -- profondeur calculée et mise en cache (0 = racine)
created_at, updated_at, created_by
```
Modèle hiérarchique : Directeur (level 0) → Manager (level 1) → Technicien (level 2).
`parent_role_id` est lui-même un **self-lookup** — la première démonstration du pattern Self-Lookup dans le système.

### `permission_role_assignments` (nouvelle table)
```sql
id UUID PK,
user_id   UUID NOT NULL,            -- référence cross-DB vers main DB users.id (pas de FK)
role_id   UUID FK→permission_roles(id) CASCADE,
is_active BOOLEAN NOT NULL DEFAULT TRUE,
UNIQUE(user_id, role_id)
created_at, updated_at, created_by
```

---

## Les trois types de relations

### 1. Master-Detail

> Relation forte : le record enfant ne peut exister sans son parent.

| Propriété | Valeur |
|---|---|
| `relationship_type` | `'master_detail'` |
| `on_delete_behavior` | `'cascade'` (recommandé) ou `'restrict'` |
| Héritage des droits | **Oui** : accès au parent → accès automatique à tous ses enfants |
| Champ obligatoire | Le champ lookup sur l'enfant est `is_required = true` |

**Héritage d'accès** : quand `DynamicRecordService.get_record()` est appelé sur un enfant, le service vérifie d'abord la visibilité directe (ownership) ; si l'utilisateur n'est pas propriétaire, il remonte sur le parent via `child_field_id` et vérifie si l'utilisateur peut voir le parent. Si oui, l'accès est accordé.

**Suppression en cascade** :
```
delete_record(parent_id):
  pour chaque master_detail où parent = cet objet:
    child_records = records où data[child_field.api_name] == parent_id
    pour chaque child_record → delete_record(child_record.id)  # récursif
  DELETE object_records WHERE id = parent_id
```

---

### 2. Lookup

> Relation faible : lien optionnel entre objets indépendants.

| Propriété | Valeur |
|---|---|
| `relationship_type` | `'lookup'` |
| `on_delete_behavior` | `'restrict'` ou `'set_null'` |
| Héritage des droits | **Non** : chaque record est visible selon ses propres règles |
| Champ obligatoire | `is_required = false` (nullable par design) |

Le champ `field_type = 'lookup'` dans `field_definitions` porte l'UUID de l'objet cible via `lookup_object_id`. À la validation, le service vérifie que la valeur soumise est un UUID référençant un `object_records.id` dont `object_definition_id == field.lookup_object_id`.

---

### 3. Self-Lookup

> Arborescence infinie : un objet référence un parent **du même type**.

| Propriété | Valeur |
|---|---|
| `relationship_type` | `'self_lookup'` |
| `parent_object_id` | == `child_object_id` (même objet) |
| `on_delete_behavior` | `'restrict'` (défaut : impossible de supprimer un nœud avec des enfants) |
| Profondeur | Illimitée — PostgreSQL recursive CTE |

**Détection automatique** : un Self-Lookup est identifié quand `field.lookup_object_id == field.object_id`. Le service peut l'enregistrer explicitement dans `relationship_definitions` avec `relationship_type='self_lookup'`.

**Exemple concret** :
```
Emplacement (objet)
  ├── api_name   : "emplacement"
  └── champ      : "parent_id" (field_type='lookup', lookup_object_id=<emplacement_def_id>)

Records :
  Site Paris    (id: A, parent_id: null)
  ├── Bâtiment A (id: B, parent_id: A)
  │   ├── Étage 1 (id: C, parent_id: B)
  │   └── Étage 2 (id: D, parent_id: B)
  └── Bâtiment B (id: E, parent_id: A)
```

**Traversée des descendants** via CTE PostgreSQL récursive :
```sql
WITH RECURSIVE tree AS (
    SELECT id, data, 0 AS depth
    FROM object_records
    WHERE id = :root_id
    AND object_definition_id = :obj_def_id
  UNION ALL
    SELECT r.id, r.data, t.depth + 1
    FROM object_records r
    JOIN tree t ON r.data->>:parent_field_api_name = t.id::text
    WHERE r.object_definition_id = :obj_def_id
    AND t.depth < 50  -- protection contre les cycles
)
SELECT * FROM tree ORDER BY depth, id;
```

**Endpoints dédiés** :
```
GET /api/tenants/<id>/objects/<api_name>/records/<record_id>/descendants
    ?depth=<max_depth>&resolve_lookups=true
GET /api/tenants/<id>/objects/<api_name>/records/<record_id>/ancestors
    → remonte jusqu'à la racine
GET /api/tenants/<id>/objects/<api_name>/records/<record_id>/path
    → chemin complet racine → nœud courant [A → B → C]
```

---

## Table `permission_roles` et hiérarchie des droits

### Principe

Indépendant des rôles système (`admin`/`user`/`viewer`), ce système définit une **hiérarchie métier** de rôles personnalisés par tenant. Un Manager voit les records créés par ses subordonnés directs et indirects.

```
Directeur (level 0)
  ├── Manager Nord (level 1)
  │   ├── Technicien A (level 2)
  │   └── Technicien B (level 2)
  └── Manager Sud (level 1)
      └── Technicien C (level 2)
```

**Règle** : un utilisateur voit les records `created_by` appartenant à :
- lui-même
- tous les utilisateurs dans son sous-arbre de la hiérarchie (subordonnés directs et indirects)

### Algorithme `get_visible_user_ids(user_id)` dans `PermissionService`

```python
@staticmethod
def get_visible_user_ids(session, user_id: str) -> List[str]:
    """Retourne les user_ids dont les records sont visibles pour user_id."""
    # 1. Trouver le rôle de cet utilisateur
    assignment = session.query(PermissionRoleAssignment).filter_by(
        user_id=user_id, is_active=True
    ).first()
    if not assignment:
        return [user_id]  # Pas de rôle métier : voit seulement les siens

    role = session.query(PermissionRole).get(assignment.role_id)

    # 2. Récupérer tous les rôles subordonnés via CTE récursive
    subordinate_role_ids = session.execute(text("""
        WITH RECURSIVE sub AS (
            SELECT id FROM permission_roles WHERE id = :role_id
          UNION ALL
            SELECT r.id FROM permission_roles r
            JOIN sub s ON r.parent_role_id = s.id
        )
        SELECT id FROM sub WHERE id != :role_id
    """), {"role_id": str(role.id)}).scalars().all()

    if not subordinate_role_ids:
        return [user_id]

    # 3. Récupérer tous les user_ids assignés à ces rôles subordonnés
    subordinate_user_ids = session.query(PermissionRoleAssignment.user_id).filter(
        PermissionRoleAssignment.role_id.in_(subordinate_role_ids),
        PermissionRoleAssignment.is_active == True
    ).scalars().all()

    return [user_id] + list(subordinate_user_ids)
```

### Intégration dans `DynamicRecordService`

`list_records()` et `query_records()` acceptent un paramètre optionnel `apply_hierarchy=True` :

```python
# Si apply_hierarchy=True et que l'utilisateur n'est pas admin :
visible_ids = PermissionService.get_visible_user_ids(session, user_id)
query = query.filter(ObjectRecord.created_by.in_(visible_ids))
```

**Règle de bypass** : si l'utilisateur a le rôle système `admin`, `apply_hierarchy` est ignoré et tous les records sont visibles (comportement admin classique).

### Héritage d'accès Master-Detail + Hiérarchie

Quand les deux mécanismes coexistent :
1. Visibilité directe (ownership + hiérarchie) → accès accordé
2. Si non propriétaire : remonter vers le parent Master-Detail → vérifier la visibilité du parent
3. Accès accordé si **l'un ou l'autre** critère est satisfait

### API pour gérer la hiérarchie de permissions

```
GET    /api/tenants/<id>/meta/permissions/roles               → liste des rôles
POST   /api/tenants/<id>/meta/permissions/roles               → créer un rôle (admin)
PUT    /api/tenants/<id>/meta/permissions/roles/<role_id>     → modifier (admin)
DELETE /api/tenants/<id>/meta/permissions/roles/<role_id>     → supprimer (admin)

GET    /api/tenants/<id>/meta/permissions/roles/<role_id>/subordinates → rôles subordonnés
GET    /api/tenants/<id>/meta/permissions/roles/tree          → arbre complet

GET    /api/tenants/<id>/meta/permissions/assignments         → assignations utilisateurs
POST   /api/tenants/<id>/meta/permissions/assignments         → assigner un rôle à un user (admin)
DELETE /api/tenants/<id>/meta/permissions/assignments/<id>    → révoquer (admin)
```

---

## Moteur d'automatisation (Triggers & Règles)

### Table `automation_rules` (8e table tenant DB)

```sql
id                   UUID PK,
object_definition_id UUID NOT NULL FK→object_definitions(id) ON DELETE CASCADE,
name                 VARCHAR(80) NOT NULL,
label                VARCHAR(255),
trigger_event        VARCHAR(30) NOT NULL
                     CHECK IN ('before_create','after_create',
                               'before_update','after_update',
                               'before_delete','after_delete'),
is_active            BOOLEAN NOT NULL DEFAULT TRUE,
sort_order           INT NOT NULL DEFAULT 0,       -- ordre d'évaluation si N règles
conditions           JSONB NOT NULL DEFAULT '[]',  -- liste de conditions
actions              JSONB NOT NULL DEFAULT '[]',  -- liste d'actions à exécuter
created_at, updated_at, created_by

INDEX (object_definition_id, trigger_event, is_active)
```

### Structure des conditions (JSONB)

Logique AND/OR avec groupes imbriqués :

```json
{
  "logic": "AND",
  "conditions": [
    {"field": "temperature", "op": "gt", "value": 100},
    {
      "logic": "OR",
      "conditions": [
        {"field": "status", "op": "eq", "value": "critique"},
        {"field": "age_jours", "op": "gte", "value": 365}
      ]
    }
  ]
}
```

Opérateurs : `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `contains`, `in`, `is_null`, `changed` (champ modifié lors d'un update).

### Structure des actions (JSONB)

```json
[
  {
    "type": "create_record",
    "params": {
      "object": "maintenance_intervention",
      "data": {
        "priorite": "haute",
        "asset_id": "{{record.id}}",
        "titre": "Intervention auto — température {{record.temperature}}°C"
      }
    }
  },
  {
    "type": "update_field",
    "params": {"field": "status", "value": "en_alerte"}
  },
  {
    "type": "call_webhook",
    "params": {"url": "{{tenant.webhook_url}}", "method": "POST"}
  }
]
```

Types d'actions supportés :

| `type` | Description |
|---|---|
| `create_record` | Crée un record dans un autre objet (ou le même) |
| `update_field` | Met à jour un ou plusieurs champs du record courant |
| `update_record` | Met à jour un record cible (via lookup field) |
| `call_webhook` | Appel HTTP vers une URL externe |
| `send_notification` | (futur) Notification interne |

Les templates `{{record.field}}` sont résolus au moment de l'exécution par un moteur de templating léger (regex + substitution sur le dict du record).

---

### Architecture blinker dans `DynamicRecordService`

```python
from blinker import Namespace

_dynamic_signals = Namespace()
record_before_create = _dynamic_signals.signal('record.before_create')
record_after_create  = _dynamic_signals.signal('record.after_create')
record_before_update = _dynamic_signals.signal('record.before_update')
record_after_update  = _dynamic_signals.signal('record.after_update')
record_before_delete = _dynamic_signals.signal('record.before_delete')
record_after_delete  = _dynamic_signals.signal('record.after_delete')
```

Le service émet le signal **après validation, avant/après persistance** :

```python
@staticmethod
def create_record(database_name, api_name, data, user_id):
    # ... validation ...
    record_before_create.send(
        'DynamicRecordService',
        database_name=database_name,
        object_api_name=api_name,
        data=data
    )
    # ... INSERT ...
    record_after_create.send(
        'DynamicRecordService',
        database_name=database_name,
        object_api_name=api_name,
        record=new_record.to_dict()
    )
```

`AutomationEngine` s'abonne à ces signaux au démarrage de l'app (dans `create_app()`) :

```python
# Dans app/__init__.py → initialize_extensions()
from app.services.automation_engine import AutomationEngine
AutomationEngine.connect_signals()
```

```python
class AutomationEngine:
    @classmethod
    def connect_signals(cls):
        record_after_create.connect(cls.on_record_event, weak=False)
        record_after_update.connect(cls.on_record_event, weak=False)
        record_before_delete.connect(cls.on_record_event, weak=False)
```

---

### Évaluation des conditions dans `AutomationEngine`

**Pas d'`eval()` Python** — évaluation par opérateurs Python purs + `simpleeval` pour les expressions arithmétiques complexes :

```python
from simpleeval import simple_eval

OP_MAP = {
    'eq':       lambda a, b: a == b,
    'neq':      lambda a, b: a != b,
    'gt':       lambda a, b: float(a) > float(b),
    'lt':       lambda a, b: float(a) < float(b),
    'gte':      lambda a, b: float(a) >= float(b),
    'lte':      lambda a, b: float(a) <= float(b),
    'contains': lambda a, b: str(b) in str(a),
    'in':       lambda a, b: a in b,
    'is_null':  lambda a, b: a is None,
    'changed':  lambda a, b: True,  # géré par le caller qui compare old/new
}

def evaluate_node(node, record_data, previous_data=None):
    if 'conditions' in node:
        results = [evaluate_node(c, record_data, previous_data) for c in node['conditions']]
        return all(results) if node.get('logic', 'AND') == 'AND' else any(results)
    value = record_data.get(node['field'])
    return OP_MAP[node['op']](value, node.get('value'))
```

`simpleeval` est utilisé **uniquement** pour les expressions de type `"expr": "temperature * 1.8 + 32 > 212"` (optionnel, pour les cas avancés).

---

### API pour gérer les règles d'automatisation

```
GET    /api/tenants/<id>/meta/objects/<api_name>/automations       → liste des règles
POST   /api/tenants/<id>/meta/objects/<api_name>/automations       → créer une règle (admin)
GET    /api/tenants/<id>/meta/objects/<api_name>/automations/<rule_id>
PUT    /api/tenants/<id>/meta/objects/<api_name>/automations/<rule_id>
DELETE /api/tenants/<id>/meta/objects/<api_name>/automations/<rule_id>

POST   /api/tenants/<id>/meta/objects/<api_name>/automations/<rule_id>/test
       Body: {"record_data": {...}}  → simule l'évaluation sans persister
```

L'endpoint `/test` permet aux admins de valider une règle avant de l'activer — essentiel pour le debug.

---

## Fichiers à créer

| Fichier | Rôle |
|---|---|
| `backend/app/models/dynamic_objects.py` | 8 modèles SQLAlchemy tenant DB (+ AutomationRule) |
| `backend/app/schemas/dynamic_meta_schema.py` | Marshmallow : objet/champ/relation definitions |
| `backend/app/schemas/dynamic_record_schema.py` | Marshmallow : record data + query (Schema.from_dict dynamique) |
| `backend/app/schemas/permission_schema.py` | Marshmallow : rôles et assignations hiérarchiques |
| `backend/app/schemas/automation_schema.py` | Marshmallow : règles, conditions, actions |
| `backend/app/services/dynamic_meta_service.py` | CRUD métadonnées + validation self-lookup |
| `backend/app/services/dynamic_record_service.py` | CRUD records + émission signaux blinker |
| `backend/app/services/automation_engine.py` | Abonnement signaux + évaluation conditions + exécution actions |
| `backend/app/services/permission_service.py` | `get_visible_user_ids()` + CRUD rôles hiérarchiques |
| `backend/app/routes/dynamic_meta.py` | Routes /meta/objects/* + /meta/permissions/* + /meta/automations/* |
| `backend/app/routes/dynamic_records.py` | Routes /objects/*/records + /records/{id}/descendants |

## Fichiers à modifier

| Fichier | Modification |
|---|---|
| `backend/app/tenant_db/tenant_migrations.py` | Ajouter `@register_migration(4)` pour les 8 tables |
| `backend/app/__init__.py` | Enregistrer 2 blueprints + appeler `AutomationEngine.connect_signals()` |
| `requirements.txt` / `pyproject.toml` | Ajouter `blinker` (déjà dans Flask), `simpleeval` |

---

## Détails d'implémentation

### Migration tenant v4

Fonction unique `@register_migration(4)` dans [backend/app/tenant_db/tenant_migrations.py](../backend/app/tenant_db/tenant_migrations.py) créant les **6 tables** en séquence (même pattern que v2/v3 existants). Appliquée via `python scripts/migrate_all_tenants.py`.

Ordre de création important (respecte les FK) :
1. `object_definitions`
2. `field_definitions` (FK → object_definitions)
3. `relationship_definitions` (FK → object_definitions + field_definitions)
4. `object_records` (FK → object_definitions)
5. `permission_roles` (FK self-référentielle → permission_roles)
6. `permission_role_assignments` (FK → permission_roles)

### Validation Self-Lookup dans `DynamicMetaService`

Lors de la création d'un champ de type `lookup` avec `lookup_object_id == object.id`, le service :
1. Crée automatiquement une entrée dans `relationship_definitions` avec `relationship_type='self_lookup'`, `parent_object_id = child_object_id = object.id`
2. Interdit de définir `is_required=True` sur ce champ (un nœud racine doit pouvoir avoir `parent_id = null`)

Lors de la suppression d'un record avec un Self-Lookup actif et `on_delete_behavior='restrict'` : vérifier qu'aucun enfant direct ne pointe vers ce record avant de supprimer.

### Modèles SQLAlchemy (`dynamic_objects.py`)

4 classes héritant de `BaseModel, db.Model`, avec `__bind_key__ = None` et `__table_args__ = ({'extend_existing': True},)` — exactement comme `File` et `Document`. **Ne pas importer via `app/models/__init__.py`** pour ne pas polluer la base principale.

### Moteur de validation — Marshmallow `Schema.from_dict()` dynamique

Au lieu d'un validateur custom, on construit un **schéma Marshmallow à la volée** depuis les `field_definitions`, en cohérence avec le reste du projet.

```python
from marshmallow import Schema, fields as mf, validate, ValidationError
from functools import lru_cache

# Mapping field_type → classe Marshmallow
MA_TYPE_MAP = {
    'text':         mf.String,
    'textarea':     mf.String,
    'email':        lambda **kw: mf.Email(**kw),
    'url':          lambda **kw: mf.Url(**kw),
    'phone':        mf.String,
    'number':       mf.Float,
    'currency':     mf.Float,
    'percent':      mf.Float,
    'date':         mf.Date,
    'datetime':     mf.DateTime,
    'boolean':      mf.Boolean,
    'picklist':     mf.String,
    'multipicklist':lambda **kw: mf.List(mf.String(), **kw),
    'file':         mf.UUID,      # document_id
    'file_list':    lambda **kw: mf.List(mf.UUID(), **kw),
    'lookup':       mf.UUID,      # object_record_id
    'autonumber':   mf.String,    # read-only, dump_only=True
}

def build_record_schema(field_defs: list) -> Schema:
    """Construit un schéma Marshmallow depuis les field_definitions de l'objet."""
    schema_fields = {}
    for f in field_defs:
        if f.field_type == 'autonumber':
            schema_fields[f.api_name] = mf.String(dump_only=True, load_default=None)
            continue

        validators = []
        rules = f.validation_rules or {}
        if 'min_length' in rules or 'max_length' in rules:
            validators.append(validate.Length(
                min=rules.get('min_length'), max=rules.get('max_length')
            ))
        if 'min_value' in rules or 'max_value' in rules:
            validators.append(validate.Range(
                min=rules.get('min_value'), max=rules.get('max_value')
            ))
        if 'regex' in rules:
            validators.append(validate.Regexp(rules['regex']))
        if f.field_type == 'picklist' and f.picklist_values:
            allowed = [v['value'] for v in f.picklist_values]
            validators.append(validate.OneOf(allowed))

        field_cls = MA_TYPE_MAP.get(f.field_type, mf.Raw)
        schema_fields[f.api_name] = field_cls(
            required=f.is_required,
            load_default=f.default_value,
            validate=validators or None,
            metadata={'label': f.label}
        )

    return Schema.from_dict(schema_fields)()
```

**Cache du schéma** : les schémas sont mis en cache par `(object_definition_id, schema_version)` (LRU cache en mémoire) et invalidés quand un `FieldDefinition` est modifié.

**Validations complémentaires** hors Marshmallow (après désérialisation) :
- `is_unique` : query `data->>'field_api_name' = value` via index GIN
- `file`/`file_list` : vérification existence dans `documents`
- `lookup` : vérification existence et type dans `object_records`
- `autonumber` : génération via `SELECT FOR UPDATE` sur `object_definitions.config`

Tableau de correspondance `field_type` → type Python attendu après désérialisation Marshmallow :

| field_type | Type Python final |
|---|---|
| `text`, `textarea`, `phone` | `str` |
| `email` | `str` (format email validé) |
| `number`, `currency`, `percent` | `float` |
| `date` | `datetime.date` |
| `datetime` | `datetime.datetime` |
| `boolean` | `bool` |
| `picklist` | `str` (dans picklist_values) |
| `multipicklist` | `list[str]` |
| `file` | `UUID` → vérifié contre `documents` |
| `file_list` | `list[UUID]` → vérifiés contre `documents` |
| `lookup` | `UUID` → vérifié contre `object_records` |
| `autonumber` | généré, `dump_only` |

### Résolution des Lookups (`resolve_lookups=true`)

1. Charger les enregistrements principaux
2. Pour chaque champ `field_type='lookup'`, collecter tous les UUIDs uniques dans le result set
3. Une seule requête batch `WHERE id IN (...)` par type de champ lookup → pas de N+1
4. Injecter les objets résolus en imbriqué dans la réponse

### Suppression en cascade Master-Detail — transaction unique

Toute la cascade s'exécute dans **une seule transaction SQLAlchemy**. Si un delete échoue à n'importe quel niveau, tout est annulé.

```python
@staticmethod
def delete_record(database_name, api_name, record_id):
    with tenant_db_manager.tenant_db_session(database_name) as session:
        # La transaction est ouverte ici — commit ou rollback à la sortie du `with`
        DynamicRecordService._cascade_delete(session, api_name, record_id, depth=0)
        # Si _cascade_delete lève une exception → rollback automatique

@staticmethod
def _cascade_delete(session, api_name, record_id, depth):
    if depth > 10:
        raise ValueError("Cascade depth limit exceeded — possible circular relationship")

    obj = session.query(ObjectDefinition).filter_by(api_name=api_name).first()
    rels = session.query(RelationshipDefinition).filter_by(parent_object_id=obj.id).all()

    for rel in rels:
        child_field_api_name = session.query(FieldDefinition).get(rel.child_field_id).api_name
        child_records = session.query(ObjectRecord).filter(
            ObjectRecord.object_definition_id == rel.child_object_id,
            ObjectRecord.data[child_field_api_name].astext == str(record_id)
        ).all()

        if rel.on_delete_behavior == 'restrict' and child_records:
            raise ConflictError(f"{len(child_records)} child records prevent deletion")

        for child in child_records:
            if rel.on_delete_behavior == 'cascade':
                child_obj_api_name = session.query(ObjectDefinition).get(rel.child_object_id).api_name
                DynamicRecordService._cascade_delete(session, child_obj_api_name, child.id, depth + 1)
            elif rel.on_delete_behavior == 'set_null':
                child.data = {k: v for k, v in child.data.items() if k != child_field_api_name}

    session.query(ObjectRecord).filter_by(id=record_id).delete()
    # Pas de commit ici — le contexte manager s'en charge une fois tout terminé
```

---

### Optimistic Locking — prévention des conflits de mise à jour concurrente

La colonne `version INTEGER` dans `object_records` est incrémentée à chaque `UPDATE`. Si deux utilisateurs modifient le même record simultanément, le second reçoit un `409 Conflict`.

**Flux `PUT /records/{id}`** :

```
Client envoie : {"data": {...}, "version": 3}
Service exécute :
  UPDATE object_records
  SET data = :new_data, version = version + 1, updated_at = NOW()
  WHERE id = :record_id AND version = :expected_version

  → 0 lignes affectées : version a changé entre temps → 409 Conflict
  → 1 ligne affectée  : succès → retourne le record avec version=4
```

```python
@staticmethod
def update_record(database_name, api_name, record_id, data, user_id, expected_version=None):
    with tenant_db_manager.tenant_db_session(database_name) as session:
        record = session.query(ObjectRecord).filter_by(id=record_id).with_for_update().first()

        if expected_version is not None and record.version != expected_version:
            raise ConflictError(
                f"Version conflict: expected {expected_version}, found {record.version}. "
                "Re-fetch the record and retry."
            )
        # ... validation ...
        record.data = {**record.data, **validated_data}
        record.version += 1
```

`expected_version` est **optionnel** — si absent, la mise à jour est acceptée sans vérification (last-write-wins). Le client choisit le niveau de protection en incluant ou non le champ `version` dans sa requête.

---

### Intégrité des métadonnées lors de la suppression d'un champ

Quand un `FieldDefinition` est désactivé (`is_active=False`) ou supprimé, les JSONB existants dans `object_records` contiennent encore la clé. Trois stratégies, au choix par objet (stocké dans `object_definitions.config['field_deletion_policy']`) :

| Stratégie | Comportement | Quand utiliser |
|---|---|---|
| `ignore` (défaut) | Les valeurs orphelines restent dans le JSONB, ignorées à la validation | Simple, réversible — champ désactivé reste récupérable |
| `nullify_on_update` | La clé est retirée du JSONB lors du prochain `UPDATE` du record | Nettoyage progressif sans impact immédiat |
| `async_cleanup` | Tâche Celery planifiée qui retire la clé de tous les records | Nettoyage proactif sur les gros volumes |

**Politique `ignore`** (recommandée pour V1) :

```python
# Dans build_record_schema() :
# Seuls les field_definitions avec is_active=True sont inclus dans le schéma
# Les clés orphelines dans le JSONB sont ignorées lors du chargement (unknown=EXCLUDE)
schema = Schema.from_dict(schema_fields)(unknown=EXCLUDE)
```

**Politique `async_cleanup`** (optionnelle, sur demande admin) :

```python
# Tâche Celery déclenchée manuellement ou lors d'un soft-delete de champ :
@celery.task
def cleanup_field_from_records(database_name, object_definition_id, field_api_name):
    with tenant_db_manager.tenant_db_session(database_name) as session:
        session.execute(text("""
            UPDATE object_records
            SET data = data - :field_name
            WHERE object_definition_id = :obj_id
              AND data ? :field_name
        """), {"field_name": field_api_name, "obj_id": object_definition_id})
```

L'opérateur `-` sur JSONB retire une clé en place — efficient et sans rewrite du row complet grâce aux TOAST PostgreSQL.

---

### Filtres JSONB dans `/records/query`

Corps pour requêtes complexes (logique OR, filtres imbriqués) :
```json
{
  "filters": [
    {"field": "status", "operator": "eq", "value": "Urgent"},
    {"field": "date_intervention", "operator": "gte", "value": "2025-01-01"}
  ],
  "order_by": "date_intervention",
  "order_dir": "desc",
  "page": 1,
  "per_page": 20,
  "resolve_lookups": true,
  "apply_hierarchy": true
}
```

Opérateurs supportés : `eq`, `neq`, `contains`, `gt`, `lt`, `gte`, `lte`, `in`, `is_null`

**Implémentation du tri sur champ JSONB** :
```python
# ?sort=data.date_intervention:desc
if sort_field.startswith('data.'):
    field_name = sort_field[5:]  # "date_intervention"
    query = query.order_by(
        ObjectRecord.data[field_name].astext.desc()
        if sort_dir == 'desc' else
        ObjectRecord.data[field_name].astext.asc()
    )
else:
    # Colonne native : created_at, updated_at, created_by
    col = getattr(ObjectRecord, sort_field)
    query = query.order_by(col.desc() if sort_dir == 'desc' else col.asc())
```

**Parsing des query params `?filter=`** :
```python
# ?filter=data.status:eq:Urgent → {"field": "data.status", "op": "eq", "value": "Urgent"}
def parse_filter_param(param: str) -> dict:
    parts = param.split(':', 2)   # max 3 segments (value peut contenir des `:`)
    if len(parts) != 3:
        raise BadRequest(f"Invalid filter syntax: {param}. Expected field:op:value")
    field, op, value = parts
    if op not in ALLOWED_OPERATORS:
        raise BadRequest(f"Unknown operator: {op}")
    return {"field": field, "operator": op, "value": value}
```

---

## Ordre de construction

1. `requirements.txt` → ajouter `simpleeval`  (`blinker` est déjà fourni par Flask)
2. `tenant_migrations.py` → `@register_migration(4)` pour les 8 tables
3. Appliquer : `docker-compose exec api python scripts/migrate_all_tenants.py --dry-run` puis sans `--dry-run`
4. `models/dynamic_objects.py` → 8 modèles SQLAlchemy (+ AutomationRule)
5. `schemas/dynamic_meta_schema.py` + `schemas/automation_schema.py` + `schemas/permission_schema.py`
6. `schemas/dynamic_record_schema.py` → inclut `build_record_schema()` avec `Schema.from_dict()`
7. `services/permission_service.py` → `get_visible_user_ids()` + CRUD rôles
8. `services/dynamic_meta_service.py` → CRUD définitions + auto-création self_lookup + CRUD automation_rules
9. `services/dynamic_record_service.py` → CRUD records + émission signaux blinker + pièces jointes
10. `services/automation_engine.py` → `connect_signals()` + évaluation conditions + exécution actions
11. `routes/dynamic_meta.py` → /meta/objects/* + /meta/permissions/* + /meta/automations/*
12. `routes/dynamic_records.py` → /objects/*/records + /records/{id}/descendants + /attachments/*
13. `app/__init__.py` → enregistrer les 2 blueprints + `AutomationEngine.connect_signals()`

---

---

## Attachement de fichiers aux objets dynamiques

### Situation existante

La tenant DB contient déjà deux tables bien établies :

| Table | Rôle |
|---|---|
| `files` | Fichier physique S3 (md5_hash, s3_path, file_size, file_metadata JSONB). Dédupliqué par MD5. |
| `documents` | Vue utilisateur sur un fichier (filename, mime_type, file_id → files, user_id). Plusieurs documents peuvent pointer le même fichier physique. |

L'upload, la déduplication MD5, les URLs pré-signées S3 et le timestamping TSA (RFC 3161) fonctionnent déjà via l'endpoint existant `POST /api/tenants/{id}/documents`.

**Objectif** : lier ces `Document` existants aux `object_records` sans dupliquer la logique d'upload.

---

### Comparaison des stratégies d'attachement

| Stratégie | Fonctionnement | Problème |
|---|---|---|
| **UUID dans JSONB** | `data.photo = "doc-uuid-123"` | Pas de FK réelle : document supprimé → UUID fantôme dans le JSONB |
| **Tableau d'UUIDs** | `data.rapports = ["doc-1", "doc-2"]` | Même problème + impossible de requêter "quels records utilisent ce document ?" |
| **Table de jonction** ✅ | `object_record_attachments(record_id, document_id, field_api_name)` | Aucun : FK réelle, cascade propre, lookup bidirectionnel |

**Décision : table de jonction `object_record_attachments`** + UUIDs dénormalisés dans le JSONB pour la compatibilité API. La table de jonction est la **source de vérité**.

---

### Table `object_record_attachments` (7e table tenant DB)

```sql
id               UUID PK,
object_record_id UUID NOT NULL FK→object_records(id) ON DELETE CASCADE,
document_id      UUID NOT NULL FK→documents(id)       ON DELETE RESTRICT,
field_api_name   VARCHAR(80) NOT NULL,  -- quel champ de l'objet est concerné
sort_order       INT NOT NULL DEFAULT 0,
created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
created_by       UUID,
UNIQUE (object_record_id, document_id, field_api_name)

INDEX (object_record_id, field_api_name)  -- lecture des pièces jointes d'un record
INDEX (document_id)                       -- recherche inverse : quels records utilisent ce doc ?
```

- `ON DELETE CASCADE` sur `object_record_id` : supprimer un record supprime automatiquement ses liaisons
- `ON DELETE RESTRICT` sur `document_id` : interdit la suppression d'un document encore attaché à un record (cohérence)
- `UNIQUE (object_record_id, document_id, field_api_name)` : un document ne peut pas être attaché deux fois au même champ du même record

---

### Types de champs fichiers dans `field_definitions`

| `field_type` | Description | Cardinalité dans JSONB | Cardinalité dans la table de jonction |
|---|---|---|---|
| `file` | Pièce jointe unique (ex: photo de profil) | `"photo": "doc-uuid-123"` | 0 ou 1 ligne |
| `file_list` | Pièces jointes multiples (ex: rapports d'inspection) | `"rapports": ["doc-1", "doc-2"]` | N lignes |

`field_type='file_list'` est ajouté à la liste des types valides dans `field_definitions`. La validation `is_required` s'applique sur la liste (au moins un élément requis).

---

### Flux d'attachement : 2 patterns

#### Pattern A — Upload puis attacher (découplé, recommandé)

```
1. Uploader le fichier via l'API existante :
   POST /api/tenants/{id}/documents
   Content-Type: multipart/form-data
   → Retourne document_id

2. Créer/modifier le record avec le document_id :
   POST /api/tenants/{id}/objects/asset/records
   {"data": {"serial_number": "SN-001", "photo_principale": "<document_id>"}}
```

Le service `DynamicRecordService` détecte que `photo_principale` est de `field_type='file'`, valide que `document_id` existe dans `documents`, crée la ligne dans `object_record_attachments`, et stocke l'UUID dans le JSONB.

#### Pattern B — Upload et attachement en une seule requête

```
POST /api/tenants/{id}/objects/asset/records/<record_id>/attachments/<field_api_name>
Content-Type: multipart/form-data
file: <binary>
filename: photo.jpg

→ Service : upload via FileService → crée Document → attache au record
→ Retourne le record mis à jour avec les pièces jointes résolues
```

Ce pattern est un raccourci UX pour les clients front-end qui ne veulent pas faire deux appels.

---

### Validation dans `DynamicRecordService._validate_record_data()`

Pour `field_type='file'` :
```python
# La valeur dans data est un document_id UUID
doc = session.query(Document).filter_by(id=value).first()
if not doc:
    errors[field.api_name] = f"Document {value} introuvable"
```

Pour `field_type='file_list'` :
```python
# La valeur est une liste d'UUIDs
if not isinstance(value, list):
    errors[field.api_name] = "Doit être une liste de document_ids"
for doc_id in value:
    doc = session.query(Document).filter_by(id=doc_id).first()
    if not doc:
        errors[field.api_name] = f"Document {doc_id} introuvable"
```

---

### Sérialisation enrichie (`?include_attachments=true`)

Quand `include_attachments=true` est passé sur un GET, le service résout chaque champ `file`/`file_list` en objet complet avec URL de téléchargement :

```json
{
  "id": "record-uuid",
  "data": {
    "serial_number": "SN-001",
    "photo_principale": {
      "document_id": "doc-uuid-123",
      "filename": "turbine_vue_avant.jpg",
      "mime_type": "image/jpeg",
      "file_size": 245678,
      "download_url": "https://minio.../presigned-url?expires=3600"
    },
    "rapports_inspection": [
      {
        "document_id": "doc-uuid-456",
        "filename": "rapport_jan_2025.pdf",
        "mime_type": "application/pdf",
        "file_size": 1048576,
        "sort_order": 0,
        "download_url": "https://minio.../presigned-url"
      }
    ]
  }
}
```

La résolution est faite en **batch** (pas de N+1) : une seule query `WHERE id IN (...)` sur `documents` pour tous les IDs trouvés dans le JSONB du result set.

---

### Endpoints dédiés aux pièces jointes

```
GET    /api/tenants/<id>/objects/<api_name>/records/<record_id>/attachments
       → liste toutes les pièces jointes du record (avec métadonnées)

GET    /api/tenants/<id>/objects/<api_name>/records/<record_id>/attachments/<field_api_name>
       → pièces jointes d'un champ spécifique

POST   /api/tenants/<id>/objects/<api_name>/records/<record_id>/attachments/<field_api_name>
       Content-Type: multipart/form-data  → upload + attach en une requête (Pattern B)

PUT    /api/tenants/<id>/objects/<api_name>/records/<record_id>/attachments/<field_api_name>
       {"document_id": "<existing_doc_id>"}  → attacher un document existant (Pattern A step 2)

DELETE /api/tenants/<id>/objects/<api_name>/records/<record_id>/attachments/<field_api_name>/<document_id>
       → détacher un document (supprime la ligne de jonction, NE supprime PAS le Document)

GET    /api/tenants/<id>/documents/<document_id>/linked-records
       → recherche inverse : quels records sont liés à ce document ?
```

---

### Suppression en cascade (mise à jour)

Le comportement de suppression d'un record inclut maintenant les pièces jointes :

```
delete_record(record_id):
  # 1. Gérer les relations Master-Detail (cascade/restrict/set_null)
  # 2. Supprimer les lignes object_record_attachments (via FK CASCADE automatique)
  #    Note : les Document/File eux-mêmes ne sont PAS supprimés (ON DELETE RESTRICT)
  #    → les documents restent disponibles dans /api/tenants/{id}/documents
  # 3. Supprimer le record object_records
```

Si le besoin est de supprimer aussi les documents attachés lors de la suppression d'un record, la `relationship_definition` peut porter une option `cascade_files=true` (à stocker dans le JSONB `config` de la relation). Le service vérifie ce flag et appelle `DocumentService.delete_document()` en plus.

---

## Récapitulatif des 8 tables tenant DB

| Table | Objet métier | Relation clé |
|---|---|---|
| `object_definitions` | Type d'objet (Asset, Intervention…) | — |
| `field_definitions` | Champs d'un objet (incl. `file`, `file_list`) | → `object_definitions` CASCADE |
| `relationship_definitions` | Relations (lookup / master_detail / self_lookup) | → `object_definitions`, `field_definitions` |
| `object_records` | Données réelles (JSONB + `version` pour optimistic locking) | → `object_definitions` RESTRICT |
| `object_record_attachments` | Liaisons record ↔ document (FK réelle) | → `object_records` CASCADE, `documents` RESTRICT |
| `automation_rules` | Règles before/after save avec conditions+actions JSONB | → `object_definitions` CASCADE |
| `permission_roles` | Rôles métier hiérarchiques (Manager, Technicien…) | → `permission_roles` self-FK (arbre) |
| `permission_role_assignments` | Assignation user → rôle | → `permission_roles` CASCADE |

---

## Vérification end-to-end

```bash
# 1. Appliquer la migration
docker-compose exec api python scripts/migrate_all_tenants.py

# 2. Créer un objet custom
curl -X POST /api/tenants/{id}/meta/objects \
  -d '{"api_name": "asset", "label": "Asset", "label_plural": "Assets"}'

# 3. Ajouter des champs
curl -X POST /api/tenants/{id}/meta/objects/asset/fields \
  -d '{"api_name": "serial_number", "label": "N° Série", "field_type": "text", "is_required": true, "is_unique": true}'

curl -X POST /api/tenants/{id}/meta/objects/asset/fields \
  -d '{"api_name": "status", "label": "Statut", "field_type": "picklist",
       "picklist_values": [{"value":"active","label":"Actif","is_default":true}, {"value":"retired","label":"Retiré"}]}'

# 4. Créer un objet lié (Maintenance_Intervention → Asset)
curl -X POST /api/tenants/{id}/meta/objects \
  -d '{"api_name": "maintenance_intervention", "label": "Intervention"}'

curl -X POST /api/tenants/{id}/meta/objects/maintenance_intervention/fields \
  -d '{"api_name": "asset_id", "label": "Asset", "field_type": "lookup", "lookup_object_id": "<asset_object_def_id>"}'

# 5. Définir la relation Master-Detail
curl -X POST /api/tenants/{id}/meta/objects/asset/relationships \
  -d '{"name": "interventions", "relationship_type": "master_detail",
       "child_object_id": "<maintenance_intervention_id>",
       "child_field_id": "<asset_id_field_id>",
       "on_delete_behavior": "cascade"}'

# 6. Créer des enregistrements
curl -X POST /api/tenants/{id}/objects/asset/records \
  -d '{"data": {"serial_number": "SN-001", "status": "active"}}'

# 7. Requête filtrée avec hiérarchie d'accès
curl -X POST /api/tenants/{id}/objects/asset/records/query \
  -d '{"filters": [{"field": "status", "operator": "eq", "value": "active"}],
       "resolve_lookups": true, "apply_hierarchy": true}'

# 8. Self-Lookup : créer une arborescence d'emplacements
curl -X POST /api/tenants/{id}/meta/objects \
  -d '{"api_name": "emplacement", "label": "Emplacement"}'

curl -X POST /api/tenants/{id}/meta/objects/emplacement/fields \
  -d '{"api_name": "parent_id", "label": "Emplacement parent",
       "field_type": "lookup", "lookup_object_id": "<emplacement_def_id>",
       "is_required": false}'
# → relationship_definitions self_lookup créé automatiquement

curl -X POST /api/tenants/{id}/objects/emplacement/records \
  -d '{"data": {"nom": "Site Paris", "parent_id": null}}'  # root

curl -X POST /api/tenants/{id}/objects/emplacement/records \
  -d '{"data": {"nom": "Bâtiment A", "parent_id": "<site_paris_id>"}}'

curl -X GET /api/tenants/{id}/objects/emplacement/records/<site_paris_id>/descendants
# → retourne Bâtiment A + tous ses enfants récursivement via CTE

# 9. Hiérarchie de permissions
curl -X POST /api/tenants/{id}/meta/permissions/roles \
  -d '{"api_name": "directeur", "label": "Directeur"}'

curl -X POST /api/tenants/{id}/meta/permissions/roles \
  -d '{"api_name": "manager", "label": "Manager", "parent_role_id": "<directeur_id>"}'

curl -X POST /api/tenants/{id}/meta/permissions/assignments \
  -d '{"user_id": "<user_manager_id>", "role_id": "<manager_id>"}'

# Le Manager voit ses propres records + ceux de ses Techniciens subordonnés
curl -X GET /api/tenants/{id}/objects/asset/records?apply_hierarchy=true
# → filtre automatique : created_by IN (manager_id + technicien_ids)
```
