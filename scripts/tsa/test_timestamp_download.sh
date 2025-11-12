#!/bin/bash
set -e

API_URL="http://localhost:4999"
TENANT_ID="964fd8df-6c81-4698-a7b6-4f1825c71c45"
FILE_ID="ba45d1f1-0dbe-4de4-aab5-c59c80d75e00"

echo "==================================="
echo "TSA Timestamp Download Test"
echo "==================================="
echo

# Step 1: Login
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
  echo $LOGIN_RESPONSE | jq .
  exit 1
fi

echo "✓ Logged in successfully"
echo

# Step 2: Download timestamp
echo "Step 2: Download timestamp as .tsr file"
curl -v -o /tmp/timestamp.tsr \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_URL}/api/tenants/${TENANT_ID}/files/${FILE_ID}/timestamp/download"

echo
echo

# Step 3: Check file
if [ -f /tmp/timestamp.tsr ]; then
  echo "✓ Timestamp file downloaded: /tmp/timestamp.tsr"
  echo "  Size: $(stat -f%z /tmp/timestamp.tsr 2>/dev/null || stat -c%s /tmp/timestamp.tsr) bytes"
  echo "  Type: $(file /tmp/timestamp.tsr)"
  echo
  
  # Step 4: Show first bytes in hex
  echo "First 32 bytes (hex):"
  hexdump -C /tmp/timestamp.tsr | head -3
else
  echo "❌ File not downloaded"
  exit 1
fi

echo
echo "✓ Test completed successfully"
