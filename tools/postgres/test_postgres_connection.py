#!/usr/bin/env python3
"""
Script de test de connexion PostgreSQL
Teste la connexion au container Docker PostgreSQL depuis la machine hôte
"""

import psycopg2
from psycopg2 import OperationalError

def test_connection():
    """Test de connexion à PostgreSQL"""
    connection_params = {
        'host': 'localhost',
        'port': 5432,
        'database': 'saas_platform',
        'user': 'postgres',
        'password': 'postgres'
    }

    print("Test de connexion à PostgreSQL...")
    print(f"Paramètres: {connection_params['user']}@{connection_params['host']}:{connection_params['port']}/{connection_params['database']}")

    try:
        # Tentative de connexion
        connection = psycopg2.connect(**connection_params)
        cursor = connection.cursor()

        # Test de requête simple
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Connexion réussie!")
        print(f"  Version PostgreSQL: {version[0]}")

        # Lister les rôles
        cursor.execute("SELECT rolname FROM pg_roles;")
        roles = cursor.fetchall()
        print(f"✓ Rôles disponibles:")
        for role in roles:
            print(f"  - {role[0]}")

        # Lister les bases de données
        cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        databases = cursor.fetchall()
        print(f"✓ Bases de données:")
        for db in databases:
            print(f"  - {db[0]}")

        cursor.close()
        connection.close()
        return True

    except OperationalError as e:
        print(f"✗ Erreur de connexion: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()

    if not success:
        print("\n--- Solutions possibles ---")
        print("1. Vérifiez que le container est en cours d'exécution:")
        print("   docker ps | grep saas-postgres")
        print("\n2. Vérifiez que le port 5432 est bien exposé:")
        print("   docker port saas-postgres")
        print("\n3. Si vous utilisez un client PostgreSQL en ligne de commande:")
        print("   PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d saas_platform")
        print("\n4. Pour vous connecter directement dans le container:")
        print("   docker exec -it saas-postgres psql -U postgres -d saas_platform")