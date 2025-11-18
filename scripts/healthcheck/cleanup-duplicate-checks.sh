#!/bin/bash
#
# Script pour supprimer les checks dupliqués dans Healthchecks.io
# Conserve uniquement les checks avec les UUIDs définis dans .env.healthchecks
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "🧹 Cleaning up duplicate Healthchecks..."

# Charger les UUIDs valides depuis .env.healthchecks
ENV_FILE="$PROJECT_ROOT/.env.healthchecks"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env.healthchecks not found at $ENV_FILE"
    exit 1
fi

# Extraire les UUIDs valides
VALID_UUIDS=$(grep "^HC_CHECK_" "$ENV_FILE" | cut -d'=' -f2 | tr '\n' ' ')
echo "📋 Valid UUIDs from .env.healthchecks:"
echo "$VALID_UUIDS"

# Récupérer l'API key
API_KEY=$(grep "^HEALTHCHECKS_API_KEY=" "$ENV_FILE" | cut -d'=' -f2)

if [ -z "$API_KEY" ]; then
    echo "❌ HEALTHCHECKS_API_KEY not found in .env.healthchecks"
    exit 1
fi

# Lister tous les checks
echo ""
echo "🔍 Fetching all checks from Healthchecks..."
ALL_CHECKS=$(curl -s -H "X-Api-Key: $API_KEY" http://localhost:8000/api/v1/checks/)

# Parser et supprimer les checks invalides
echo "$ALL_CHECKS" | python3 -c "
import sys
import json
import requests

valid_uuids = '''$VALID_UUIDS'''.strip().split()
api_key = '''$API_KEY'''

data = json.load(sys.stdin)
checks = data.get('checks', [])

deleted_count = 0
kept_count = 0

for check in checks:
    uuid = check['ping_url'].split('/')[-1]
    name = check['name']

    if uuid in valid_uuids:
        print(f'✓ Keeping: {name:30s} | {uuid}')
        kept_count += 1
    else:
        print(f'🗑️  Deleting: {name:30s} | {uuid}')
        response = requests.delete(
            f'http://localhost:8000/api/v1/checks/{uuid}',
            headers={'X-Api-Key': api_key}
        )
        if response.status_code in [200, 204]:
            deleted_count += 1
        else:
            print(f'   ❌ Failed to delete: {response.status_code}')

print()
print('='*60)
print(f'✓ Kept: {kept_count} checks')
print(f'🗑️  Deleted: {deleted_count} checks')
print('='*60)
"

echo ""
echo "✅ Cleanup complete!"
