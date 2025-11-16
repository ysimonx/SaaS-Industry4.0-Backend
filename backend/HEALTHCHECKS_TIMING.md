# Healthchecks.io Timing Configuration

This document explains the timing configuration for Healthchecks.io monitoring and how it aligns with Celery Beat schedules.

## Overview

The platform uses Healthchecks.io to monitor service health via periodic pings sent by Celery tasks. **It's critical that the Healthchecks timeout/grace configuration matches the Celery Beat schedule**, otherwise false alerts will occur.

## Timing Architecture

### The Problem

If Celery sends pings every 2 minutes but Healthchecks expects them every 30 seconds, the system will generate false "down" alerts because pings arrive late.

**Example of mismatch (WRONG)**:
```python
# setup_healthchecks.py
'schedule': '30',  # Expects ping every 30 seconds
'grace': 120,      # 2-minute grace period

# celery_app.py
'schedule': crontab(minute='*/2'),  # Actually pings every 2 minutes
```

This causes alerts every 2 minutes because pings are "late" (expected at 0:00:30, 0:01:00, 0:01:30... but arrive at 0:00:00, 0:02:00, 0:04:00...).

### The Solution

**Healthchecks timeout must equal Celery schedule interval**:
- Timeout = Expected ping interval (how often the task runs)
- Grace = 2x timeout (buffer for network delays, task execution time)

## Current Configuration

### Tier 1 Services (Critical Infrastructure)

| Service | Celery Schedule | HC Timeout | HC Grace | Task Name |
|---------|----------------|------------|----------|-----------|
| **PostgreSQL** | Every 2 min (`*/2`) | 120s (2m) | 240s (4m) | `monitoring.check_postgres` |
| **Redis** | Every 2 min (`*/2`) | 120s (2m) | 240s (4m) | `monitoring.check_redis` |
| **Flask API** | Every 3 min (`*/3`) | 180s (3m) | 360s (6m) | `monitoring.check_api` |
| **Celery Worker** | Every 5 min (`*/5`) | 300s (5m) | 600s (10m) | `monitoring.check_celery` |
| **Celery Beat** | Every 5 min (`*/5`) | 300s (5m) | 600s (10m) | `monitoring.check_celery` |

### Tier 2 Services (Essential)

| Service | Celery Schedule | HC Timeout | HC Grace | Task Name |
|---------|----------------|------------|----------|-----------|
| **Kafka Broker** | Every 2 min (`*/2`) | 120s (2m) | 300s (5m) | Via `check_kafka` |
| **Kafka Consumer** | Every 2 min (`*/2`) | 120s (2m) | 300s (5m) | Via `check_kafka` |
| **MinIO S3** | Every 5 min (`*/5`) | 300s (5m) | 600s (10m) | Via maintenance |
| **Vault Secrets** | Every 5 min (`*/5`) | 300s (5m) | 600s (10m) | Via maintenance |

### Scheduled Tasks (Cron)

| Task | Celery Schedule | HC Schedule | HC Grace | Notes |
|------|----------------|-------------|----------|-------|
| **SSO Token Refresh** | Every 15 min (`*/15`) | `*/15 * * * *` | 300s | Cron expression |
| **Health Check Task** | Every 5 min (`*/5`) | `*/5 * * * *` | 120s | Cron expression |
| **Token Cleanup** | Daily 2 AM (`0 2 * * *`) | `0 2 * * *` | 3600s | Cron expression |
| **Key Rotation** | Monthly 1st 3 AM | `0 3 1 * *` | 7200s | Cron expression |
| **Comprehensive Check** | Every 10 min (`*/10`) | `*/10 * * * *` | 600s | Aggregates all checks |

## Configuration Files

### 1. Celery Beat Schedules

**File**: `/backend/app/celery_app.py`

```python
beat_schedule={
    'monitor-postgres': {
        'task': 'monitoring.check_postgres',
        'schedule': crontab(minute='*/2'),  # Every 2 minutes
        'options': {'queue': 'monitoring', 'priority': 3}
    },
    'monitor-redis': {
        'task': 'monitoring.check_redis',
        'schedule': crontab(minute='*/2'),  # Every 2 minutes
        'options': {'queue': 'monitoring', 'priority': 3}
    },
    'monitor-api': {
        'task': 'monitoring.check_api',
        'schedule': crontab(minute='*/3'),  # Every 3 minutes
        'options': {'queue': 'monitoring', 'priority': 3}
    },
    'monitor-celery': {
        'task': 'monitoring.check_celery',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'monitoring', 'priority': 3}
    }
}
```

### 2. Healthchecks Setup Configuration

**File**: `/backend/scripts/setup_healthchecks.py`

```python
CHECKS_CONFIG = [
    {
        'name': 'PostgreSQL Database',
        'schedule': '120',  # 2 minutes (matches crontab(minute='*/2'))
        'grace': 240,       # 4 minutes (2x timeout)
    },
    {
        'name': 'Redis Cache/Broker',
        'schedule': '120',  # 2 minutes (matches crontab(minute='*/2'))
        'grace': 240,       # 4 minutes (2x timeout)
    },
    {
        'name': 'Flask API',
        'schedule': '180',  # 3 minutes (matches crontab(minute='*/3'))
        'grace': 360,       # 6 minutes (2x timeout)
    },
    # ... etc
]
```

### 3. Monitoring Tasks

**File**: `/backend/app/tasks/monitoring_tasks.py`

Each monitoring task follows this pattern:

```python
@celery.task(name='monitoring.check_postgres')
@monitor_task(check_name='postgres-health')
def check_postgres_health() -> Dict[str, Any]:
    try:
        # Perform health check
        result = db.session.execute(text("SELECT 1")).scalar()

        # Ping success if configured
        if CHECK_IDS.get('postgres'):
            healthchecks.ping_success(CHECK_IDS['postgres'])

        return metrics
    except Exception as e:
        # Ping failure if configured
        if CHECK_IDS.get('postgres'):
            healthchecks.ping_fail(CHECK_IDS['postgres'])
        raise
```

## Grace Period Calculation

The grace period provides a buffer for:
- Network delays
- Task execution time
- System load variations
- Scheduler jitter

**Formula**: `grace = timeout * 2`

**Example**: PostgreSQL check
- Timeout: 120s (2 minutes between expected pings)
- Grace: 240s (4 minutes total before alert)
- Expected pings: 0:00, 0:02, 0:04, 0:06...
- Alert triggers if no ping by: 0:06 (0:02 + 4min grace)

## How to Update Timing

### Scenario 1: Change Celery Schedule

If you change a Celery Beat schedule:

1. **Update Celery config** (`backend/app/celery_app.py`):
   ```python
   'monitor-postgres': {
       'schedule': crontab(minute='*/5'),  # Changed from */2 to */5
   }
   ```

2. **Update Healthchecks setup** (`backend/scripts/setup_healthchecks.py`):
   ```python
   {
       'name': 'PostgreSQL Database',
       'schedule': '300',  # 5 minutes (was 120)
       'grace': 600,       # 10 minutes (was 240)
   }
   ```

3. **Fix existing checks**:
   ```bash
   docker-compose exec api python /app/scripts/fix_healthchecks_timing.py
   ```

4. **Restart Celery Beat**:
   ```bash
   docker-compose restart celery-beat
   ```

### Scenario 2: Fix Existing Mismatches

Use the automated fix script:

```bash
# Check current configuration
docker-compose exec api python /app/scripts/fix_healthchecks_timing.py

# Or run from host (if environment configured)
cd backend
python scripts/fix_healthchecks_timing.py
```

The script will:
1. Query current Healthchecks configuration via API
2. Compare with expected values from Celery schedules
3. Update any mismatches automatically
4. Report summary of changes

## Monitoring & Verification

### Check Celery Beat Schedule

```bash
# View Celery Beat logs
docker-compose logs -f celery-beat

# Should show scheduled tasks with timing
[2025-11-16 10:00:00,000: INFO/MainProcess] Scheduler: Sending task monitoring.check_postgres
[2025-11-16 10:02:00,000: INFO/MainProcess] Scheduler: Sending task monitoring.check_postgres
[2025-11-16 10:04:00,000: INFO/MainProcess] Scheduler: Sending task monitoring.check_postgres
```

### Verify Healthchecks Configuration

```bash
# View via API
curl -H "X-Api-Key: $HEALTHCHECKS_API_KEY" \
  http://localhost:8000/api/v1/checks/ | jq

# Or access UI
open http://localhost:8000
```

### Check Ping History

In Healthchecks UI:
1. Go to check detail page
2. View "Ping History" tab
3. Verify pings arrive at expected intervals
4. Check for any "late" or "missed" markers

## Troubleshooting

### False "Down" Alerts

**Symptom**: Service marked as "down" even though it's healthy

**Cause**: Healthchecks timeout too short for Celery schedule

**Fix**:
```bash
python scripts/fix_healthchecks_timing.py
```

### No Pings Received

**Symptom**: Check shows "new" status, never receives pings

**Possible causes**:
1. Check ID not in environment variables
2. Celery task not running
3. Healthchecks client disabled

**Debug**:
```bash
# Check environment
docker-compose exec api env | grep HC_CHECK_POSTGRES

# Check Celery Beat is running
docker-compose ps celery-beat

# Check task logs
docker-compose logs celery-beat | grep monitor-postgres

# Verify Healthchecks enabled
docker-compose exec api env | grep HEALTHCHECKS_ENABLED
```

### Pings Too Frequent

**Symptom**: Receiving pings more often than configured

**Cause**: Multiple workers running the same scheduled task

**Fix**: Ensure only one Celery Beat instance runs:
```bash
docker-compose ps | grep celery-beat  # Should show only one
```

## Best Practices

1. **Always match timing**: Healthchecks timeout = Celery interval
2. **Use 2x grace**: Provides reasonable buffer without delaying alerts too long
3. **Document changes**: Update this file when changing schedules
4. **Test after changes**: Wait for 2-3 ping cycles to verify
5. **Monitor alerts**: Check Slack/email for false positives
6. **Version control**: Commit timing changes together (celery_app.py + setup_healthchecks.py)

## Related Files

- `/backend/app/celery_app.py` - Celery Beat schedule definitions
- `/backend/scripts/setup_healthchecks.py` - Initial check creation
- `/backend/scripts/fix_healthchecks_timing.py` - Automated timing fixes
- `/backend/app/tasks/monitoring_tasks.py` - Health check task implementations
- `/backend/app/monitoring/healthchecks_client.py` - API client
- `/.env.healthchecks` - Check IDs and API configuration

## References

- [Healthchecks.io Documentation](https://healthchecks.io/docs/)
- [Celery Beat Documentation](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
- [Crontab Syntax](https://crontab.guru/)
