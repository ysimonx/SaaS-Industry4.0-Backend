# Healthchecks Timing Mismatch - Analysis & Fix

## Executive Summary

**Issue**: Timing mismatch between Healthchecks.io configuration and Celery Beat schedules was causing false alerts.

**Root Cause**: `setup_healthchecks.py` configured PostgreSQL and Redis checks to expect pings every 30 seconds, but `celery_app.py` scheduled monitoring tasks to run every 2 minutes.

**Impact**: Constant false "down" alerts because pings arrived every 2 minutes but were expected every 30 seconds.

**Resolution**: Updated Healthchecks configuration to match Celery Beat schedules, using 2x grace period for buffer.

---

## Problem Analysis

### Before Fix ❌

#### setup_healthchecks.py Configuration
```python
{
    'name': 'PostgreSQL Database',
    'schedule': '30',   # ❌ Expected ping every 30 seconds
    'grace': 120,       # 2 minutes grace
}
{
    'name': 'Redis Cache/Broker',
    'schedule': '30',   # ❌ Expected ping every 30 seconds
    'grace': 120,       # 2 minutes grace
}
{
    'name': 'Flask API',
    'schedule': '60',   # ❌ Expected ping every 1 minute
    'grace': 180,       # 3 minutes grace
}
```

#### celery_app.py Actual Schedules
```python
'monitor-postgres': {
    'schedule': crontab(minute='*/2'),  # ✓ Actually runs every 2 minutes
}
'monitor-redis': {
    'schedule': crontab(minute='*/2'),  # ✓ Actually runs every 2 minutes
}
'monitor-api': {
    'schedule': crontab(minute='*/3'),  # ✓ Actually runs every 3 minutes
}
```

#### The Mismatch
- **PostgreSQL/Redis**: Expected every 30s, received every 2min → **4x slower than expected** → **CONSTANT ALERTS**
- **Flask API**: Expected every 1min, received every 3min → **3x slower than expected** → **CONSTANT ALERTS**

---

## Solution Implemented

### 1. Updated setup_healthchecks.py

**File**: `/backend/scripts/setup_healthchecks.py`

```python
# BEFORE (WRONG)
{
    'name': 'PostgreSQL Database',
    'schedule': '30',   # 30 seconds
    'grace': 120,       # 2 minutes
}

# AFTER (CORRECT)
{
    'name': 'PostgreSQL Database',
    'schedule': '120',  # 2 minutes (matches crontab(minute='*/2'))
    'grace': 240,       # 4 minutes (2x timeout for buffer)
    'desc': 'Main PostgreSQL database health'
}
```

**All Changes**:
- PostgreSQL: `30s → 120s` timeout, `120s → 240s` grace
- Redis: `30s → 120s` timeout, `120s → 240s` grace
- Flask API: `60s → 180s` timeout, `180s → 360s` grace
- Celery Worker: `60s → 300s` timeout, `300s → 600s` grace
- Celery Beat: `60s → 300s` timeout, `300s → 600s` grace

### 2. Created Automated Fix Script

**File**: `/backend/scripts/fix_healthchecks_timing.py`

This script:
- Queries Healthchecks API for current configuration
- Compares with expected values from Celery Beat schedules
- Updates any mismatched checks automatically
- Provides detailed before/after report

**Usage**:
```bash
docker-compose exec api python scripts/fix_healthchecks_timing.py
```

**Output Example**:
```
📊 PostgreSQL Database
   Current:  timeout=30s, grace=2m
   Expected: timeout=2m, grace=4m
   🔄 Updating...
   ✓ Updated successfully!
```

### 3. Created Verification Script

**File**: `/backend/scripts/verify_timing_alignment.py`

Validates that Celery Beat schedules are correctly configured:
```bash
docker-compose exec api python scripts/verify_timing_alignment.py
```

### 4. Created Documentation

**Files Created**:
- `/backend/HEALTHCHECKS_TIMING.md` - Comprehensive timing documentation
- `/backend/TIMING_SUMMARY.md` - Quick reference table
- `/HEALTHCHECKS_TIMING_FIX.md` - This document

**Files Updated**:
- `/CLAUDE.md` - Added Healthchecks commands to "Monitoring and Debugging" section

---

## Configuration After Fix ✅

| Service | Celery Schedule | HC Timeout | HC Grace | Total Alert Window | Status |
|---------|----------------|------------|----------|-------------------|--------|
| PostgreSQL | `*/2` (2min) | 2m (120s) | 4m (240s) | 6m | ✅ FIXED |
| Redis | `*/2` (2min) | 2m (120s) | 4m (240s) | 6m | ✅ FIXED |
| Flask API | `*/3` (3min) | 3m (180s) | 6m (360s) | 9m | ✅ FIXED |
| Celery Worker | `*/5` (5min) | 5m (300s) | 10m (600s) | 15m | ✅ FIXED |
| Celery Beat | `*/5` (5min) | 5m (300s) | 10m (600s) | 15m | ✅ FIXED |

### Timing Logic

**Formula**: `Total Alert Window = Timeout + Grace`

**Example - PostgreSQL**:
- Celery sends ping at: `0:00`, `0:02`, `0:04`, `0:06`...
- Healthchecks expects ping every: `2 minutes (timeout)`
- If no ping received, waits: `4 minutes (grace)` before alerting
- Total window before alert: `6 minutes`

**Timeline**:
```
0:00 - Ping received ✓
0:02 - Ping received ✓
0:04 - Ping received ✓
0:06 - [SERVICE GOES DOWN]
0:10 - Alert triggered (6 minutes after last ping at 0:04)
```

---

## Verification Steps

### 1. Check Healthchecks Configuration
```bash
# Access Healthchecks UI
open http://localhost:8000

# Or query via API
curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
  http://localhost:8000/api/v1/checks/ | jq '.checks[] | {name, timeout, grace}'
```

### 2. Monitor Celery Beat Logs
```bash
docker-compose logs -f celery-beat | grep monitor-

# Should see tasks running at correct intervals:
# [INFO] Scheduler: Sending task monitoring.check_postgres
# [INFO] Scheduler: Sending task monitoring.check_redis
```

### 3. Check Ping History
In Healthchecks UI:
1. Click on a check (e.g., "PostgreSQL Database")
2. View "Ping History" tab
3. Verify pings arrive at expected intervals (every 2 minutes for PostgreSQL/Redis)
4. No "late" or "missed" indicators

### 4. Run Verification Script
```bash
docker-compose exec api python scripts/verify_timing_alignment.py
```

Expected output: "✅ All Celery Beat schedules configured correctly"

---

## Tools & Scripts Reference

### Fix Timing Mismatches
```bash
# Automated fix (recommended)
docker-compose exec api python scripts/fix_healthchecks_timing.py

# View current configuration
curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
  http://localhost:8000/api/v1/checks/
```

### Verify Alignment
```bash
# Check Celery Beat schedules
docker-compose exec api python scripts/verify_timing_alignment.py

# View Celery Beat configuration
docker-compose exec api python -c "
from app.celery_app import celery_app
import json
print(json.dumps(celery_app.conf.beat_schedule, indent=2, default=str))
"
```

### Setup New Checks
```bash
# Initial setup (creates all checks)
docker-compose exec api python scripts/setup_healthchecks.py

# This generates .env.healthchecks with check IDs
# Copy IDs to docker-compose environment variables
```

---

## Best Practices Going Forward

### When Changing Monitoring Intervals

**DO THIS** (correct order):

1. ✅ Update Celery Beat schedule in `app/celery_app.py`
2. ✅ Update setup config in `scripts/setup_healthchecks.py`
3. ✅ Run fix script: `python scripts/fix_healthchecks_timing.py`
4. ✅ Restart Celery Beat: `docker-compose restart celery-beat`
5. ✅ Verify in Healthchecks UI after 2-3 cycles
6. ✅ Commit all changes together

**DON'T DO THIS** (wrong):
- ❌ Change Celery schedule without updating Healthchecks
- ❌ Update only one file (causes mismatch)
- ❌ Forget to restart Celery Beat
- ❌ Skip verification step

### Grace Period Guidelines

**Recommended**: `grace = timeout * 2`

**Rationale**:
- Provides buffer for network delays
- Accounts for task execution time
- Handles scheduler jitter
- Prevents false alerts
- Not so long that real issues go unnoticed

**Examples**:
- 2-minute checks → 4-minute grace (total 6 minutes)
- 5-minute checks → 10-minute grace (total 15 minutes)
- 15-minute checks → 30-minute grace (total 45 minutes)

---

## Troubleshooting

### "Check is down" but service is healthy

**Cause**: Timing mismatch or pings not being sent

**Debug**:
```bash
# 1. Check Celery Beat is running
docker-compose ps celery-beat

# 2. Verify task is scheduled
docker-compose logs celery-beat | grep monitor-postgres

# 3. Check Healthchecks configuration
docker-compose exec api python scripts/fix_healthchecks_timing.py

# 4. Verify check ID in environment
docker-compose exec api env | grep HC_CHECK_POSTGRES

# 5. Check monitoring task logs
docker-compose logs api | grep "PostgreSQL health check"
```

### Pings not arriving

**Possible causes**:
1. Celery Beat not running
2. Check ID not configured
3. Healthchecks client disabled
4. Network issue between containers

**Fix**:
```bash
# Check Healthchecks enabled
docker-compose exec api env | grep HEALTHCHECKS_ENABLED
# Should show: HEALTHCHECKS_ENABLED=true

# Check API key configured
docker-compose exec api env | grep HEALTHCHECKS_API_KEY

# Test ping manually
docker-compose exec api python -c "
from app.monitoring.healthchecks_client import healthchecks
result = healthchecks.ping_success('$HC_CHECK_POSTGRES')
print(f'Ping result: {result}')
"
```

### Multiple workers sending pings

**Symptom**: Pings arriving more frequently than expected

**Cause**: Multiple Celery Beat instances running

**Fix**: Ensure only ONE Celery Beat container:
```bash
docker-compose ps | grep celery-beat
# Should show exactly one container

# If multiple, stop extras
docker-compose stop celery-beat
docker-compose up -d celery-beat
```

---

## Impact & Results

### Before Fix
- ❌ Constant false alerts for PostgreSQL, Redis, API
- ❌ Alert fatigue - real issues might be missed
- ❌ Healthchecks dashboard showing services as "down"
- ❌ Confusion about system health

### After Fix
- ✅ Accurate health monitoring
- ✅ Alerts only for real issues
- ✅ Correct timing alignment
- ✅ Clear system health status
- ✅ Automated tools for maintenance

---

## Related Documentation

- [HEALTHCHECKS_TIMING.md](backend/HEALTHCHECKS_TIMING.md) - Comprehensive timing documentation
- [TIMING_SUMMARY.md](backend/TIMING_SUMMARY.md) - Quick reference table
- [DOCKER_HEALTHCHECK.md](DOCKER_HEALTHCHECK.md) - Docker setup guide
- [plan-healthcheck.md](plan-healthcheck.md) - Implementation plan
- [CLAUDE.md](CLAUDE.md) - Updated with Healthchecks commands

---

## Summary

The timing mismatch between Healthchecks.io and Celery Beat has been identified and fixed:

1. ✅ Updated `setup_healthchecks.py` with correct timing
2. ✅ Created automated fix script (`fix_healthchecks_timing.py`)
3. ✅ Created verification script (`verify_timing_alignment.py`)
4. ✅ Fixed existing Healthchecks via API (PostgreSQL, Redis, API, Celery)
5. ✅ Documented timing configuration extensively
6. ✅ Added commands to CLAUDE.md

**Current Status**: All monitoring checks are aligned with Celery Beat schedules using the formula `grace = timeout * 2` for optimal alerting.
