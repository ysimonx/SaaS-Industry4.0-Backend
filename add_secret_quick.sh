#!/bin/bash

echo "========================================"
echo "AJOUT RAPIDE DU CLIENT SECRET"
echo "========================================"
echo ""
echo "1. Créez le secret dans Azure Portal :"
echo "   - Certificates & secrets → New client secret"
echo "   - COPIEZ LA VALEUR (pas l'ID !)"
echo ""
echo "2. Collez le secret ci-dessous :"
echo ""
read -p "Client Secret: " CLIENT_SECRET

if [ -z "$CLIENT_SECRET" ]; then
    echo "❌ Aucun secret fourni"
    exit 1
fi

echo ""
echo "Ajout du secret dans la base de données..."

docker-compose exec postgres psql -U postgres -d saas_platform -c \
"UPDATE tenant_sso_configs
 SET client_secret = '$CLIENT_SECRET'
 WHERE client_id = '28d84fdd-1d63-4257-8543-86294a55aa80';"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Secret ajouté avec succès !"
    echo ""
    echo "Testez maintenant :"
    echo "http://localhost:4999/api/auth/sso/azure/login/cb859f98-291e-41b2-b30f-2287c2699205"
else
    echo "❌ Erreur lors de l'ajout du secret"
fi