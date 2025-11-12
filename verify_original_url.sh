#!/bin/bash
set -e

API_URL="http://localhost:4999"
TENANT_ID="964fd8df-6c81-4698-a7b6-4f1825c71c45"
FILE_ID="a9a8584c-a60e-40af-ab2e-e24451fb009b"  # User's original file ID

echo "Verifying original URL from user's question:"
echo "http://localhost:4999/api/tenants/964fd8df-6c81-4698-a7b6-4f1825c71c45/files/a9a8584c-a60e-40af-ab2e-e24451fb009b/timestamp/download"
echo

# Login
echo "Step 1: Login"
LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "12345678"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✓ Logged in"
echo

# Check if file exists and has timestamp
echo "Step 2: Check file status in database"
docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOSQL
SELECT
    f.id,
    LEFT(f.md5_hash, 16) as md5,
    LEFT(COALESCE(f.sha256_hash, 'NULL'), 16) as sha256,
    f.file_metadata->'tsa_timestamp'->>'status' as tsa_status
FROM files f
WHERE f.id::text = '$FILE_ID';
EOSQL

echo

# Try to download timestamp
echo "Step 3: Try to download timestamp"
HTTP_CODE=$(curl -s -o /tmp/test_original.tsr -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_URL}/api/tenants/${TENANT_ID}/files/${FILE_ID}/timestamp/download")

echo "HTTP Response Code: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
  echo "✓ SUCCESS - Timestamp downloaded"
  echo "  File size: $(stat -f%z /tmp/test_original.tsr 2>/dev/null || stat -c%s /tmp/test_original.tsr) bytes"
  rm -f /tmp/test_original.tsr
elif [ "$HTTP_CODE" = "400" ]; then
  echo "⚠ File has no valid timestamp (expected if previous TSA failed)"
elif [ "$HTTP_CODE" = "404" ]; then
  echo "❌ 404 - File not found or endpoint missing"
else
  echo "❌ Unexpected HTTP code: $HTTP_CODE"
fi
