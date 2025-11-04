"""
Flask Application Entry Point

This script serves as the main entry point for running the Flask application.
It creates an app instance using the application factory pattern and runs
the development server.

Usage:
    Development: python run.py
    Production: gunicorn -w 4 -b 0.0.0.0:4999 "run:app"
    Flask CLI: flask --app run db migrate
"""

import os
import sys
import logging
from app import create_app

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def initialize_vault():
    """
    Initialise la connexion à Vault et charge les secrets.

    Returns:
        VaultClient authentifié ou None si Vault n'est pas activé
    """
    use_vault = os.environ.get("USE_VAULT", "false").lower() == "true"

    if not use_vault:
        logger.info("Vault désactivé (USE_VAULT=false). Utilisation des variables d'environnement.")
        return None

    try:
        from app.utils.vault_client import VaultClient, VaultError

        logger.info("Initialisation de Vault...")

        # Créer le client Vault
        vault_client = VaultClient()

        # Authentification AppRole
        vault_client.authenticate()

        logger.info("Authentification Vault réussie")

        return vault_client

    except VaultError as e:
        logger.error(f"Erreur d'initialisation de Vault: {e}")
        logger.error("L'application ne peut pas démarrer sans accès à Vault")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'initialisation de Vault: {e}")
        sys.exit(1)


# Initialiser Vault et créer l'application Flask
# Cette instance est utilisée par Gunicorn (run:app)
vault_client = initialize_vault()
config_name = os.environ.get("FLASK_ENV", "development")
app = create_app(config_name, vault_client=vault_client)

if __name__ == '__main__':
    # Run development server
    # Port is configured in app.config (default 4999)
    port = app.config.get('FLASK_PORT', 4999)
    debug = app.config.get('DEBUG', True)

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
