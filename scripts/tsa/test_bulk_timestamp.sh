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
echo "Bulk Timestamp Test"
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

# Step 2: Upload 3 test files
echo -e "${YELLOW}Step 2: Upload 3 test files${NC}"
FILE_IDS=()

for i in 1 2 3; do
  TEST_FILE="/tmp/bulk_test_${i}_$RANDOM.txt"
  echo "Bulk test file $i - $(date)" > $TEST_FILE
  
  UPLOAD_RESPONSE=$(curl -s -X POST \
    "${API_URL}/api/tenants/${TENANT_ID}/documents" \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "file=@${TEST_FILE}" \
    -F "filename=bulk_test_${i}.txt" \
    -F "description=Bulk timestamp test file $i")
  
  FILE_ID=$(echo $UPLOAD_RESPONSE | jq -r '.data.file_id')
  FILE_IDS+=("$FILE_ID")
  
  rm -f $TEST_FILE
  echo "  File $i uploaded: $FILE_ID"
done

echo -e "${GREEN}✓ 3 files uploaded${NC}"
echo

# Step 3: Wait a bit to ensure files are ready
echo -e "${YELLOW}Step 3: Wait for files to settle (5 seconds)...${NC}"
sleep 5

# Step 4: Check files that need timestamping
echo -e "${YELLOW}Step 4: Check files in database (before bulk timestamp)${NC}"
docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOSQL
SELECT
    f.id,
    LEFT(f.sha256_hash, 12) as sha256,
    COALESCE(f.file_metadata->'tsa_timestamp'->>'status', 'not_set') as tsa_status
FROM files f
WHERE f.id::text IN ('${FILE_IDS[0]}', '${FILE_IDS[1]}', '${FILE_IDS[2]}')
ORDER BY f.created_at DESC;
EOSQL
echo

# Step 5: Trigger bulk timestamp with filter
echo -e "${YELLOW}Step 5: Trigger bulk timestamp (not_timestamped filter)${NC}"
BULK_RESPONSE=$(curl -s -X POST \
  "${API_URL}/api/tenants/${TENANT_ID}/files/timestamp/bulk" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "not_timestamped": true
    }
  }')

echo $BULK_RESPONSE | jq .

TOTAL_FILES=$(echo $BULK_RESPONSE | jq -r '.data.total_files // 0')
TASKS_SCHEDULED=$(echo $BULK_RESPONSE | jq -r '.data.tasks_scheduled // 0')
ESTIMATED_MINUTES=$(echo $BULK_RESPONSE | jq -r '.data.estimated_duration_minutes // 0')

if [ "$TASKS_SCHEDULED" -gt 0 ]; then
  echo -e "${GREEN}✓ Bulk timestamp tasks scheduled${NC}"
  echo "  Total files: $TOTAL_FILES"
  echo "  Tasks scheduled: $TASKS_SCHEDULED"
  echo "  Estimated duration: ${ESTIMATED_MINUTES} minutes"
else
  echo -e "${YELLOW}⚠ No files to timestamp${NC}"
fi
echo

# Step 6: Wait for tasks to complete
if [ "$TASKS_SCHEDULED" -gt 0 ]; then
  WAIT_TIME=30
  echo -e "${YELLOW}Step 6: Wait for bulk timestamp tasks ($WAIT_TIME seconds)...${NC}"
  sleep $WAIT_TIME

  # Step 7: Check final status
  echo -e "${YELLOW}Step 7: Verify timestamps in database${NC}"
  docker-compose exec -T postgres psql -U postgres -d tenant_fidwork_916d299c << EOSQL
SELECT
    f.id,
    LEFT(f.sha256_hash, 12) as sha256,
    f.file_metadata->'tsa_timestamp'->>'status' as tsa_status,
    LEFT(f.file_metadata->'tsa_timestamp'->>'serial_number', 20) as serial
FROM files f
WHERE f.id::text IN ('${FILE_IDS[0]}', '${FILE_IDS[1]}', '${FILE_IDS[2]}')
ORDER BY f.created_at DESC;
EOSQL
  echo
fi

echo -e "${GREEN}✓ Bulk timestamp test completed${NC}"
