# Fix for Redis Health Check Auto-Creation Issue

## Problem
- New "redis-health" checks were being created every 4 minutes
- These checks had tags "auto-created" and "check_redis_health"
- Multiple duplicate checks were accumulating in Healthchecks.io

## Root Causes Identified

1. **Old Decorator Code**: The monitoring decorators had auto-creation logic that would create new checks when it couldn't find existing ones
2. **Healthchecks.io Auto-Provisioning**: The API key appears to have auto-provisioning enabled, which creates checks when receiving pings to non-existent UUIDs with slugs
3. **Python Bytecode Cache**: Old compiled bytecode (.pyc files) may have retained the old auto-creation logic

## Fixes Applied

### 1. Removed Auto-Creation Logic from Decorators
- File: `app/monitoring/decorators.py`
- Removed all `healthchecks.create_check()` calls
- Made decorators require explicit `check_id` parameters
- Added deprecation warnings for `check_name` parameter

### 2. Added UUID Validation to Ping Method
- File: `app/monitoring/healthchecks_client.py`
- Added validation to ensure check_id is a valid UUID format (36 chars, 4 dashes)
- Prevents pinging with slugs that could trigger auto-creation
- Logs warnings when invalid check IDs are attempted

### 3. Cleaned Python Cache
- Removed all `.pyc` files from containers
- Removed all `__pycache__` directories
- Rebuilt Docker containers without cache

### 4. Created Cleanup and Monitoring Scripts
- `scripts/cleanup_duplicate_healthchecks.py` - Deletes auto-created checks
- `scripts/monitor_redis_checks.py` - Real-time monitoring for new checks

## Verification Steps

1. Clean up existing duplicate checks:
   ```bash
   docker-compose exec api python scripts/cleanup_duplicate_healthchecks.py
   ```

2. Rebuild containers:
   ```bash
   docker-compose build --no-cache celery-worker-monitoring
   docker-compose up -d celery-worker-monitoring
   ```

3. Monitor for new duplicates:
   ```bash
   docker-compose exec api python scripts/monitor_redis_checks.py
   ```

## Configuration
All health check IDs should be defined in environment variables:
- `HC_CHECK_REDIS=c3244506-c2af-4b25-8562-1254d7be601e`
- Other checks follow pattern: `HC_CHECK_{SERVICE}`

These are loaded by monitoring tasks from environment and used for pinging.

## Prevention
- Never use check names/slugs for pinging, only UUIDs
- All checks must be pre-created via `scripts/setup_healthchecks.py`
- Monitoring tasks use environment variables for check IDs
- UUID validation prevents accidental auto-creation