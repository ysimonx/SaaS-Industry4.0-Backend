#!/bin/bash
# Test script for TSA timestamp on file upload

set -e

# Configuration
API_URL="http://localhost:4999"
TENANT_ID="964fd8df-6c81-4698-a7b6-4f1825c71c45"  # fidwork tenant

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "==================================="
echo "TSA Upload Test"
echo "==================================="
echo

# Step 1: Login
echo -e "${YELLOW}Step 1: Login${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "${API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "12345678"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo -e "${RED}❌ Login failed${NC}"
  echo $LOGIN_RESPONSE | jq .
  exit 1
fi

echo -e "${GREEN}✓ Logged in successfully${NC}"
echo

# Step 2: Create a test file
echo -e "${YELLOW}Step 2: Create test file${NC}"
TEST_FILE="/tmp/tsa_test_$(date +%s).txt"
echo "This is a test file for TSA timestamping at $(date)" > $TEST_FILE
echo -e "${GREEN}✓ Created test file: $TEST_FILE${NC}"
echo

# Step 3: Upload file
echo -e "${YELLOW}Step 3: Upload file to tenant${NC}"
UPLOAD_RESPONSE=$(curl -s -X POST "${API_URL}/api/tenants/${TENANT_ID}/documents" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_FILE}" \
  -F "filename=tsa_test.txt")

echo $UPLOAD_RESPONSE | jq .

DOCUMENT_ID=$(echo $UPLOAD_RESPONSE | jq -r '.data.id')
FILE_ID=$(echo $UPLOAD_RESPONSE | jq -r '.data.file_id')

if [ "$DOCUMENT_ID" = "null" ] || [ -z "$DOCUMENT_ID" ]; then
  echo -e "${RED}❌ Upload failed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ File uploaded successfully${NC}"
echo "  Document ID: $DOCUMENT_ID"
echo "  File ID: $FILE_ID"
echo

# Step 4: Wait for TSA task
echo -e "${YELLOW}Step 4: Waiting for TSA task (10 seconds)...${NC}"
sleep 10

# Step 5: Check file in database
echo -e "${YELLOW}Step 5: Check file details in database${NC}"
docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOF
SELECT
    f.id,
    LEFT(f.md5_hash, 16) as md5,
    LEFT(COALESCE(f.sha256_hash, 'NULL'), 16) as sha256,
    CASE
        WHEN f.file_metadata::text = '{}' THEN 'Empty'
        WHEN f.file_metadata ? 'tsa_timestamp' THEN 'TSA Present'
        ELSE 'Other metadata'
    END as metadata_status,
    f.file_metadata->'tsa_timestamp'->>'status' as tsa_status
FROM files f
WHERE f.id::text = '$FILE_ID';
EOF

echo
echo -e "${GREEN}✓ Test completed${NC}"
echo

# Cleanup
rm -f $TEST_FILE
echo "Test file removed: $TEST_FILE"
