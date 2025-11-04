# 🔐 Requirements for HashiCorp Vault Integration

Ce document décrit les exigences pour l'intégration de **HashiCorp Vault** afin de stocker et de gérer les secrets du projet **SaaS Python/Flask** dans un environnement **Docker**.

---

## 1. ⚙️ Exigences Techniques et d'Architecture

* **Conteneurisation de Vault (Docker):**
    * Le projet doit inclure un service **Vault** dédié dans son `docker-compose.yml`.
    * Ce conteneur Vault doit être initialisé en mode **Développement** ou **Démo** pour la preuve de concept/développement local. Le plan doit indiquer la transition vers un mode de **Production** (avec unboxing sécurisé et stockage persistant) pour les environnements supérieurs.
    * Vault doit être accessible par les autres conteneurs de l'application (Python/Flask) via un **nom de service** clair (ex: `vault`).
* **Application Flask:**
    * L'application Python/Flask doit utiliser une bibliothèque Python pour interagir avec l'API Vault (par exemple, `hvac`).
    * Tous les secrets d'application (clés de base de données, clés API tierces, etc.) doivent être **supprimés** des fichiers de configuration ou des variables d'environnement des conteneurs applicatifs et récupérés *uniquement* auprès de Vault au démarrage.
* **Chemins de Secrets:**
    * Le plan doit définir une structure de chemin de secrets claire et hiérarchique utilisant le *KV Secrets Engine* (v2), par exemple :
        * `secret/data/saas-project/dev/database`
        * `secret/data/saas-project/prod/api-keys`

---

## 2. 🔑 Exigences de Sécurité et d'Authentification (AppRole)

L'authentification des applications aux secrets doit se faire via la méthode **AppRole**.

* **Mise en place d'AppRole:**
    * Le plan doit détailler la création et la configuration d'un *backend* d'authentification AppRole dédié (ex: `auth/approle`).
    * Il doit inclure la création d'un rôle spécifique pour l'application Flask (ex: `saas-app-role`).
* **Politiques (Policies):**
    * Définir une politique de Vault (**ACL**) stricte qui **autorise uniquement la lecture** des chemins de secrets spécifiques à l'application. La politique doit être associée à l'AppRole créé.
* **Récupération du Secret au Démarrage:**
    * Le script de démarrage du conteneur Flask doit effectuer les étapes suivantes de manière séquentielle :
        1.  Lire le **`Role ID`** et le **`Secret ID`** à partir de variables d'environnement **temporaires** (ex: injectées par Docker Compose pour le dev ou un orchestrateur pour la prod).
        2.  Appeler l'API de Vault pour **s'authentifier** en utilisant le Role ID et le Secret ID.
        3.  Récupérer un **Vault Token** en cas de succès.
        4.  Utiliser ce Vault Token pour **lire** tous les secrets nécessaires.
        5.  Stocker les secrets dans la configuration de l'application Flask (ex: `app.config`).
        6.  Démarrer le serveur Flask.

---

## 3. 🔄 Exigences de Renouvellement de Token

Pour des raisons de sécurité, le Vault Token obtenu via AppRole doit être de courte durée et renouvelé.

* **Renouvellement Automatique de Token:**
    * L'application Flask (ou un thread/processus annexe) doit être configurée pour surveiller le temps restant avant l'expiration du Vault Token.
    * Un mécanisme doit être mis en place pour **renouveler le token** (*renewal*) auprès de Vault **avant qu'il n'expire**.
    * Le renouvellement doit se produire de manière asynchrone pour ne pas bloquer l'application principale.
* **Gestion des Erreurs:**
    * Le plan doit inclure un processus pour gérer l'échec du renouvellement du token. Si le renouvellement échoue, l'application doit **arrêter de servir les requêtes** ou logguer une erreur critique, car elle ne sera plus capable d'accéder aux secrets dynamiques (si utilisés) ou de se re-authentifier correctement à terme.

---

## 4. 📝 Livrables du Plan

Le `plan-vault.md` dans /specs/vault/plan-vault.md que tu vas me générer doit contenir au minimum les sections suivantes :

1.  **Préparation de l'Environnement Local:** Étapes pour modifier `docker-compose.yml` et initialiser Vault.
2.  **Configuration de Vault:** Commandes CLI/API pour activer AppRole, créer la Policy, et l'AppRole.
3.  **Mise à jour de l'Application Flask:** Pseudo-code ou étapes décrivant la logique de démarrage du conteneur pour l'authentification et la récupération des secrets.
4.  **Implémentation du Renouvellement:** Description du code Python pour gérer le renouvellement du token.
