# Healthchecks vs Celery Beat - Timing Summary

## Quick Reference Table

| Service | Celery Task | Celery Schedule | HC Timeout | HC Grace | Total Alert Time | Status |
|---------|-------------|----------------|------------|----------|------------------|--------|
| PostgreSQL | `monitoring.check_postgres` | `*/2` (2min) | 2m | 4m | 6m | ✅ ALIGNED |
| Redis | `monitoring.check_redis` | `*/2` (2min) | 2m | 4m | 6m | ✅ ALIGNED |
| Flask API | `monitoring.check_api` | `*/3` (3min) | 3m | 6m | 9m | ✅ ALIGNED |
| Celery Worker | `monitoring.check_celery` | `*/5` (5min) | 5m | 10m | 15m | ✅ ALIGNED |
| Celery Beat | `monitoring.check_celery` | `*/5` (5min) | 5m | 10m | 15m | ✅ ALIGNED |

## Timeline Examples

### PostgreSQL (2-minute checks)
```
Time:  0:00  0:02  0:04  0:06  0:08  0:10
Ping:   ✓     ✓     ✓     ✗     ✗     ✗
Alert:  -     -     -     -     -    DOWN (6m after last ping at 0:04)
```

### Flask API (3-minute checks)
```
Time:  0:00  0:03  0:06  0:09  0:12  0:15
Ping:   ✓     ✓     ✓     ✗     ✗     ✗
Alert:  -     -     -     -    DOWN (9m after last ping at 0:06)
```

## How It Works

1. **Celery Beat** schedules tasks at defined intervals
2. **Monitoring tasks** run health checks and send pings
3. **Healthchecks** expects pings within `timeout` period
4. **Grace period** provides buffer before alerting
5. **Alert triggers** if no ping received after `timeout + grace`

## Previous Mismatch (FIXED)

### Before Fix ❌
```
PostgreSQL:
  Celery: Every 2 minutes (crontab(minute='*/2'))
  Healthchecks: timeout=30s, grace=120s
  Problem: Expected ping every 30s, received every 2min → CONSTANT ALERTS
```

### After Fix ✅
```
PostgreSQL:
  Celery: Every 2 minutes (crontab(minute='*/2'))
  Healthchecks: timeout=120s (2m), grace=240s (4m)
  Result: Expected ping every 2min, received every 2min → WORKING CORRECTLY
```

## Verification Commands

```bash
# View Celery Beat schedule
docker-compose exec api python -c "
from app.celery_app import celery_app
import json
print(json.dumps(celery_app.conf.beat_schedule, indent=2, default=str))
"

# Check Healthchecks configuration
docker-compose exec api python scripts/fix_healthchecks_timing.py

# Monitor Celery Beat logs
docker-compose logs -f celery-beat

# Access Healthchecks UI
open http://localhost:8000
```

## Maintenance

When changing monitoring intervals:

1. ✅ Update Celery Beat schedule in `app/celery_app.py`
2. ✅ Update setup config in `scripts/setup_healthchecks.py`
3. ✅ Run fix script: `python scripts/fix_healthchecks_timing.py`
4. ✅ Restart Celery Beat: `docker-compose restart celery-beat`
5. ✅ Verify in Healthchecks UI after 2-3 ping cycles

## Related Documentation

- Full timing details: [HEALTHCHECKS_TIMING.md](HEALTHCHECKS_TIMING.md)
- Docker setup: [DOCKER_HEALTHCHECK.md](../DOCKER_HEALTHCHECK.md)
- Implementation plan: [plan-healthcheck.md](../plan-healthcheck.md)
