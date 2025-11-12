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

# Step 6: Download timestamp token
echo -e "${YELLOW}Step 6: Download timestamp token as .tsr file${NC}"
TSR_FILE="/tmp/tsa_test_${FILE_ID}.tsr"
HTTP_CODE=$(curl -s -o "$TSR_FILE" -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_URL}/api/tenants/${TENANT_ID}/files/${FILE_ID}/timestamp/download")

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "${GREEN}✓ Timestamp downloaded successfully${NC}"
  echo "  File: $TSR_FILE"
  echo "  Size: $(stat -f%z "$TSR_FILE" 2>/dev/null || stat -c%s "$TSR_FILE") bytes"
  echo

  # Step 7: Display timestamp info with OpenSSL
  echo -e "${YELLOW}Step 7: Display timestamp info with OpenSSL${NC}"
  openssl ts -reply -in "$TSR_FILE" -text 2>&1 | grep -E "Status:|Time stamp:|Serial number:" || true
  echo

  # Step 8: Download DigiCert certificates (root + intermediate)
  echo -e "${YELLOW}Step 8: Download DigiCert certificates${NC}"

  # Download root certificate (DigiCert Assured ID Root CA)
  # Note: The intermediate cert is signed by this root, not by Global Root G2
  DIGICERT_ROOT="/tmp/digicert_root.pem"
  curl -s -o "$DIGICERT_ROOT" https://cacerts.digicert.com/DigiCertAssuredIDRootCA.crt.pem

  # Download intermediate certificate (DigiCert SHA2 Assured ID Timestamping CA)
  DIGICERT_INTERMEDIATE="/tmp/digicert_intermediate.pem"
  curl -s -o "$DIGICERT_INTERMEDIATE" https://cacerts.digicert.com/DigiCertSHA2AssuredIDTimestampingCA.crt.pem

  # Create combined certificate chain file (intermediate + root)
  DIGICERT_CHAIN="/tmp/digicert_chain.pem"
  cat "$DIGICERT_INTERMEDIATE" "$DIGICERT_ROOT" > "$DIGICERT_CHAIN"

  if [ -f "$DIGICERT_CHAIN" ]; then
    echo -e "${GREEN}✓ DigiCert certificate chain created${NC}"
    echo "  Root: $DIGICERT_ROOT (DigiCert Assured ID Root CA)"
    echo "  Intermediate: $DIGICERT_INTERMEDIATE (SHA2 Timestamping CA)"
    echo "  Chain: $DIGICERT_CHAIN"
  else
    echo -e "${RED}❌ Failed to create certificate chain${NC}"
  fi
  echo

  # Step 9: Verify timestamp with OpenSSL (complete verification)
  echo -e "${YELLOW}Step 9: Verify timestamp authenticity with OpenSSL${NC}"

  # Download the original file to verify against
  ORIGINAL_FILE="/tmp/original_${FILE_ID}.txt"
  curl -s -o "$ORIGINAL_FILE" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${API_URL}/api/tenants/${TENANT_ID}/documents/${DOCUMENT_ID}/download"

  if [ -f "$ORIGINAL_FILE" ]; then
    echo "Downloaded original file for verification"
    echo

    # Perform full OpenSSL verification
    echo "Running OpenSSL verification..."
    echo

    # Disable exit on error temporarily for verification
    set +e

    # Run verification and capture output
    VERIFY_OUTPUT=$(openssl ts -verify \
      -data "$ORIGINAL_FILE" \
      -in "$TSR_FILE" \
      -CAfile "$DIGICERT_CHAIN" 2>&1)

    VERIFY_STATUS=$?

    # Re-enable exit on error
    set -e

    # Display the full output
    echo "$VERIFY_OUTPUT"
    echo

    # Display final status
    if [ $VERIFY_STATUS -eq 0 ]; then
      echo -e "${GREEN}✓ VERIFICATION SUCCESSFUL - Timestamp is authentic${NC}"
    else
      echo -e "${RED}❌ VERIFICATION FAILED${NC}"
      echo "The timestamp could not be verified. This may indicate:"
      echo "  - The file has been modified"
      echo "  - The timestamp token is invalid"
      echo "  - Certificate chain issues"
    fi
  else
    echo -e "${RED}❌ Failed to download original file for verification${NC}"
  fi
  echo
else
  echo -e "${RED}❌ Timestamp download failed (HTTP $HTTP_CODE)${NC}"
fi

echo -e "${GREEN}✓ Test completed${NC}"
echo

# Cleanup
rm -f $TEST_FILE
rm -f $TSR_FILE
rm -f $ORIGINAL_FILE
rm -f $DIGICERT_ROOT
rm -f $DIGICERT_INTERMEDIATE
rm -f $DIGICERT_CHAIN
echo "Test files removed"
