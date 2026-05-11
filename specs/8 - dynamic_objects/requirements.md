# Spécification — Système de métadonnées dynamiques (Custom Objects)

**Feature** : #8 — Dynamic Objects  
**Plan d'implémentation** : [docs/DYNAMIC_OBJECTS.md](../../docs/DYNAMIC_OBJECTS.md)  
**Modèle de menaces** : [docs/DYNAMIC_OBJECTS_THREAT_MODEL.md](../../docs/DYNAMIC_OBJECTS_THREAT_MODEL.md)  
**Statut** : Planifié

---

## Contexte métier

Les clients (tenants) du backend SaaS doivent pouvoir modéliser leurs propres données métier sans intervention de l'équipe technique. Aujourd'hui, toute nouvelle entité métier nécessite une migration SQL et un déploiement.

Le système de métadonnées dynamiques élimine cette contrainte : chaque tenant peut créer ses propres types d'objets, définir leurs champs, configurer des relations entre eux, attacher des fichiers et automatiser des comportements — entièrement via l'API, sans toucher au schéma SQL.

---

## Exigences fonctionnelles

### EF-01 — Objets personnalisés
- Un admin tenant peut créer, modifier et supprimer des types d'objets (`ObjectDefinition`)
- Chaque objet a un `api_name` unique par tenant (ex: `asset`, `maintenance_intervention`)
- La suppression d'un objet est bloquée tant qu'il contient des enregistrements

### EF-02 — Champs personnalisés
- Un admin tenant peut ajouter des champs à un objet existant
- Types de champs supportés : `text`, `textarea`, `number`, `currency`, `percent`, `date`, `datetime`, `boolean`, `email`, `url`, `phone`, `picklist`, `multipicklist`, `autonumber`, `file`, `file_list`, `lookup`
- Chaque champ peut être : requis / unique / avec valeur par défaut / avec règles de validation (min, max, regex)
- La modification du `field_type` est interdite si des enregistrements existent déjà

### EF-03 — Relations entre objets
- Trois types de relations : `lookup` (lien faible), `master_detail` (cascade + héritage d'accès), `self_lookup` (arborescence du même type)
- Un objet Master-Detail enfant ne peut pas exister sans son parent
- Le Self-Lookup permet une hiérarchie infinie (ex: Emplacement → sous-Emplacement)

### EF-04 — CRUD générique sur les enregistrements
- Un seul jeu d'endpoints `/api/tenants/{id}/objects/{api_name}/records` sert tous les types d'objets
- La validation des données respecte les `field_definitions` de l'objet (types, contraintes, picklists)
- Filtrage avancé via `POST /records/query` avec opérateurs sur les champs JSONB
- Résolution des lookups en objets imbriqués via `?resolve_lookups=true`

### EF-05 — Pièces jointes
- Les champs `file` et `file_list` permettent d'attacher des `Document` existants à un enregistrement
- L'upload d'un fichier peut se faire en une requête (upload + attachement simultanés)
- La suppression d'un enregistrement supprime les liaisons mais conserve les documents

### EF-06 — Automatisation (Triggers & Règles)
- Un admin peut définir des règles déclenchées sur `before/after create/update/delete`
- Les règles comportent des conditions (AND/OR imbriqués) et des actions (`create_record`, `update_field`, `call_webhook`, etc.)
- Un endpoint `/test` permet de simuler une règle sans persister
- Les règles sont évaluées de façon sécurisée (pas d'`eval()` Python)

### EF-07 — Hiérarchie de permissions métier
- Un admin peut définir des rôles métier (ex: Directeur, Manager, Technicien) avec hiérarchie parent/enfant
- Un utilisateur voit les enregistrements créés par lui-même et ses subordonnés dans la hiérarchie
- Cette hiérarchie est indépendante des rôles système (`admin`/`user`/`viewer`)

---

## Exigences non-fonctionnelles

### ENF-01 — Isolation multi-tenant
Les 8 nouvelles tables sont créées dans la base tenant (pas la base principale). Les définitions d'objets du tenant A ne sont pas accessibles depuis le tenant B.

### ENF-02 — Performance
- Index GIN sur `object_records.data` pour les requêtes JSONB
- Les schémas de validation Marshmallow sont mis en cache par `object_definition_id`
- La résolution des lookups se fait en batch (une query par type, pas N+1)
- La traversée Self-Lookup utilise une CTE récursive PostgreSQL avec limite de profondeur
- Pagination obligatoire sur `GET /records` (max 200 par page)
- Tri sur champ JSONB via `.astext.asc()/desc()` SQLAlchemy

### ENF-05 — Cohérence concurrente
- Colonne `version INTEGER` sur `object_records` pour l'Optimistic Locking
- Les suppressions Master-Detail en cascade s'exécutent dans une transaction unique (rollback total si échec)
- `SELECT FOR UPDATE` sur `object_definitions` lors de la génération de valeurs `autonumber`

### ENF-06 — Intégrité des métadonnées
- La désactivation d'un `field_definition` ne supprime pas les données JSONB existantes (stratégie `ignore` par défaut)
- Une tâche Celery `cleanup_field_from_records` est disponible pour le nettoyage asynchrone sur demande admin
- Les clés orphelines dans le JSONB sont ignorées silencieusement à la validation (`unknown=EXCLUDE` Marshmallow)

### ENF-03 — Compatibilité
Le système ne modifie pas les tables existantes (`files`, `documents`, `users`, `tenants`). Les endpoints existants restent inchangés. La migration est additive.

### ENF-04 — Sécurité
Voir [DYNAMIC_OBJECTS_THREAT_MODEL.md](../../docs/DYNAMIC_OBJECTS_THREAT_MODEL.md) pour le détail des menaces et mitigations.

---

## Contraintes techniques

| Contrainte | Détail |
|---|---|
| Stockage des données | JSONB PostgreSQL (pas EAV, pas de tables dynamiques) |
| Validation | Marshmallow `Schema.from_dict()` construit à la volée depuis `field_definitions` |
| Automatisation | Signaux blinker + `simpleeval` pour les expressions — jamais `eval()` Python |
| Migration | `@register_migration(4)` dans `tenant_migrations.py` — appliquée via `migrate_all_tenants.py` |
| Dépendances nouvelles | `simpleeval` (blinker déjà fourni par Flask) |

---

## Traceabilité

| Exigence | Couverture dans le plan |
|---|---|
| EF-01 Objets | Table `object_definitions` + `DynamicMetaService` + `GET/POST /meta/objects` |
| EF-02 Champs | Table `field_definitions` + `build_record_schema()` + `GET/POST /meta/objects/{api_name}/fields` |
| EF-03 Relations | Table `relationship_definitions` (lookup/master_detail/self_lookup) + CTE récursive |
| EF-04 CRUD générique | `DynamicRecordService` + routes `/objects/{api_name}/records` + query params `?filter=&sort=&page=` |
| ENF-05 Optimistic Locking | Colonne `version` sur `object_records` + vérification dans `update_record()` |
| ENF-06 Intégrité champs | `unknown=EXCLUDE` Marshmallow + tâche `cleanup_field_from_records` |
| EF-05 Pièces jointes | Table `object_record_attachments` + `field_type=file/file_list` + Pattern A/B |
| EF-06 Automatisation | Table `automation_rules` + `AutomationEngine` + signaux blinker |
| EF-07 Permissions | Tables `permission_roles` + `permission_role_assignments` + `PermissionService.get_visible_user_ids()` |

---

## Périmètre exclu (hors scope V1)

- Interface graphique de configuration des objets (front-end)
- Import/export des définitions d'objets entre tenants
- Versionning des définitions de champs (historique des changements de schéma)
- Requêtes analytiques agrégées (SUM, AVG, GROUP BY sur les champs JSONB)
- Webhooks sortants avec retry automatique (prévu dans les actions, implémentation async Celery à confirmer)
