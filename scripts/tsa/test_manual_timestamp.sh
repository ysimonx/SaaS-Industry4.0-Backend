#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

API_URL="http://localhost:4999"
TENANT_ID="964fd8df-6c81-4698-a7b6-4f1825c71c45"

echo "==================================="
echo "Manual Timestamp Test"
echo "==================================="
echo

# Step 1: Login
echo -e "${YELLOW}Step 1: Login as admin${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "12345678"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo -e "${RED}❌ Login failed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Logged in successfully${NC}"
echo

# Step 2: Upload a file WITHOUT waiting for auto-timestamp
echo -e "${YELLOW}Step 2: Upload test file${NC}"
TEST_FILE="/tmp/manual_test_$RANDOM.txt"
echo "Test file for manual timestamping - $(date)" > $TEST_FILE

UPLOAD_RESPONSE=$(curl -s -X POST \
  "${API_URL}/api/tenants/${TENANT_ID}/documents" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_FILE}" \
  -F "filename=manual_test.txt" \
  -F "description=Testing manual timestamp")

FILE_ID=$(echo $UPLOAD_RESPONSE | jq -r '.data.file_id')
DOCUMENT_ID=$(echo $UPLOAD_RESPONSE | jq -r '.data.id')

if [ "$FILE_ID" = "null" ] || [ -z "$FILE_ID" ]; then
  echo -e "${RED}❌ Upload failed${NC}"
  echo $UPLOAD_RESPONSE | jq .
  exit 1
fi

echo -e "${GREEN}✓ File uploaded${NC}"
echo "  File ID: $FILE_ID"
echo "  Document ID: $DOCUMENT_ID"
echo

# Step 3: Check initial timestamp status (should be pending or not exist yet)
echo -e "${YELLOW}Step 3: Check initial timestamp status${NC}"
sleep 3  # Wait for auto-timestamp to potentially start
docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOSQL
SELECT
    f.id,
    COALESCE(f.file_metadata->'tsa_timestamp'->>'status', 'not_started') as tsa_status
FROM files f
WHERE f.id::text = '$FILE_ID';
EOSQL
echo

# Step 4: Manually trigger timestamp
echo -e "${YELLOW}Step 4: Manually trigger timestamp via API${NC}"
TIMESTAMP_RESPONSE=$(curl -s -X POST \
  "${API_URL}/api/tenants/${TENANT_ID}/files/${FILE_ID}/timestamp/create" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"force": false}')

echo $TIMESTAMP_RESPONSE | jq .

TASK_ID=$(echo $TIMESTAMP_RESPONSE | jq -r '.data.task_id // empty')
STATUS=$(echo $TIMESTAMP_RESPONSE | jq -r '.data.status // .message')

if [ ! -z "$TASK_ID" ]; then
  echo -e "${GREEN}✓ Timestamp task scheduled${NC}"
  echo "  Task ID: $TASK_ID"
elif [[ "$STATUS" == *"already timestamped"* ]]; then
  echo -e "${GREEN}✓ File already timestamped${NC}"
else
  echo -e "${YELLOW}⚠ Unexpected status: $STATUS${NC}"
fi
echo

# Step 5: Wait for task to complete
echo -e "${YELLOW}Step 5: Wait for timestamp task (15 seconds)...${NC}"
sleep 15

# Step 6: Check final timestamp status
echo -e "${YELLOW}Step 6: Verify timestamp in database${NC}"
docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOSQL
SELECT
    f.id,
    LEFT(COALESCE(f.sha256_hash, 'NULL'), 16) as sha256,
    f.file_metadata->'tsa_timestamp'->>'status' as tsa_status,
    f.file_metadata->'tsa_timestamp'->>'gen_time' as timestamp_time,
    f.file_metadata->'tsa_timestamp'->>'serial_number' as serial
FROM files f
WHERE f.id::text = '$FILE_ID';
EOSQL
echo

# Step 7: Try to download timestamp
echo -e "${YELLOW}Step 7: Download timestamp token${NC}"
HTTP_CODE=$(curl -s -o /tmp/manual_test.tsr -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_URL}/api/tenants/${TENANT_ID}/files/${FILE_ID}/timestamp/download")

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "${GREEN}✓ Timestamp downloaded successfully${NC}"
  echo "  File size: $(stat -f%z /tmp/manual_test.tsr 2>/dev/null || stat -c%s /tmp/manual_test.tsr) bytes"
  
  # Verify with OpenSSL
  echo
  echo -e "${YELLOW}Step 8: Verify with OpenSSL${NC}"
  openssl ts -reply -in /tmp/manual_test.tsr -text 2>&1 | grep -E "Status:|Time stamp:|Serial number:" || true
  
  rm -f /tmp/manual_test.tsr
else
  echo -e "${RED}❌ Download failed (HTTP $HTTP_CODE)${NC}"
fi

echo
echo -e "${GREEN}✓ Test completed${NC}"

# Cleanup
rm -f $TEST_FILE
