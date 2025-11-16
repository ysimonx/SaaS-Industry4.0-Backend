#!/usr/bin/env python3
"""
Script to fix timing mismatch between Healthchecks config and Celery Beat schedules.

The issue:
- setup_healthchecks.py sets PostgreSQL/Redis to 30 seconds with 120s grace
- celery_app.py runs monitor-postgres/redis every 2 minutes (crontab(minute='*/2'))
- This causes false alerts because pings arrive every 2 minutes but expected every 30s

The fix:
- Update Healthchecks checks to expect 2-minute intervals with appropriate grace period
- Grace period = interval * 2 (4 minutes = 240 seconds)
"""

import os
import sys
import requests

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv('.env.healthchecks')

# Healthchecks API configuration
HEALTHCHECKS_API_URL = os.getenv('HEALTHCHECKS_API_URL', 'http://healthchecks:8000/api/v1')
HEALTHCHECKS_API_KEY = os.getenv('HEALTHCHECKS_API_KEY')

# Checks that need fixing with their correct timing
CHECKS_TO_FIX = {
    # PostgreSQL and Redis: Celery runs every 2 minutes
    'PostgreSQL Database': {
        'check_id': os.getenv('HC_CHECK_POSTGRES'),
        'timeout': 120,  # 2 minutes (interval)
        'grace': 240,    # 4 minutes (2x timeout for buffer)
        'celery_schedule': 'Every 2 minutes (crontab(minute="*/2"))'
    },
    'Redis Cache/Broker': {
        'check_id': os.getenv('HC_CHECK_REDIS'),
        'timeout': 120,  # 2 minutes
        'grace': 240,    # 4 minutes
        'celery_schedule': 'Every 2 minutes (crontab(minute="*/2"))'
    },

    # API: runs every 3 minutes (should update to match)
    'Flask API': {
        'check_id': os.getenv('HC_CHECK_API'),
        'timeout': 180,  # 3 minutes
        'grace': 360,    # 6 minutes
        'celery_schedule': 'Every 3 minutes (crontab(minute="*/3"))'
    },

    # Celery checks: every 5 minutes
    'Celery Worker SSO': {
        'check_id': os.getenv('HC_CHECK_CELERY_WORKER'),
        'timeout': 300,  # 5 minutes
        'grace': 600,    # 10 minutes
        'celery_schedule': 'Every 5 minutes (via monitor-celery)'
    },
    'Celery Beat Scheduler': {
        'check_id': os.getenv('HC_CHECK_CELERY_BEAT'),
        'timeout': 300,  # 5 minutes
        'grace': 600,    # 10 minutes
        'celery_schedule': 'Every 5 minutes (via monitor-celery)'
    }
}


def get_check_details(check_id: str) -> dict:
    """Get current check configuration from Healthchecks API"""
    if not check_id:
        return None

    url = f"{HEALTHCHECKS_API_URL}/checks/{check_id}"
    headers = {'X-Api-Key': HEALTHCHECKS_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"  ❌ Error getting check: {e}")

    return None


def update_check(check_id: str, timeout: int, grace: int) -> bool:
    """Update check timing via Healthchecks API"""
    if not check_id:
        return False

    url = f"{HEALTHCHECKS_API_URL}/checks/{check_id}"
    headers = {
        'X-Api-Key': HEALTHCHECKS_API_KEY,
        'Content-Type': 'application/json'
    }

    data = {
        'timeout': timeout,
        'grace': grace
    }

    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"  ❌ Error updating check: {e}")
        return False


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def main():
    print("="*80)
    print("🔧 Fixing Healthchecks Timing Mismatches")
    print("="*80)
    print()

    if not HEALTHCHECKS_API_KEY:
        print("❌ HEALTHCHECKS_API_KEY not set in .env.healthchecks")
        return False

    print(f"📡 API: {HEALTHCHECKS_API_URL}")
    print()

    fixed_count = 0
    skipped_count = 0
    failed_count = 0

    for check_name, config in CHECKS_TO_FIX.items():
        check_id = config['check_id']
        new_timeout = config['timeout']
        new_grace = config['grace']
        celery_schedule = config['celery_schedule']

        print(f"📊 {check_name}")
        print(f"   Check ID: {check_id}")
        print(f"   Celery Schedule: {celery_schedule}")

        if not check_id:
            print(f"   ⚠️  Check ID not found in environment")
            skipped_count += 1
            print()
            continue

        # Get current configuration
        current = get_check_details(check_id)
        if not current:
            print(f"   ❌ Failed to get current configuration")
            failed_count += 1
            print()
            continue

        current_timeout = current.get('timeout', 0)
        current_grace = current.get('grace', 0)

        print(f"   Current:  timeout={format_duration(current_timeout)}, grace={format_duration(current_grace)}")
        print(f"   Expected: timeout={format_duration(new_timeout)}, grace={format_duration(new_grace)}")

        # Check if update needed
        if current_timeout == new_timeout and current_grace == new_grace:
            print(f"   ✓ Already correct - no update needed")
            skipped_count += 1
        else:
            # Update the check
            print(f"   🔄 Updating...")
            if update_check(check_id, new_timeout, new_grace):
                print(f"   ✓ Updated successfully!")
                fixed_count += 1
            else:
                print(f"   ❌ Update failed")
                failed_count += 1

        print()

    # Summary
    print("="*80)
    print("📈 SUMMARY")
    print("="*80)
    print(f"✓ Fixed:   {fixed_count} checks")
    print(f"⚠️  Skipped: {skipped_count} checks (already correct or missing)")
    print(f"❌ Failed:  {failed_count} checks")
    print()

    if fixed_count > 0:
        print("🎯 Next steps:")
        print("1. Verify changes in Healthchecks UI: http://localhost:8000")
        print("2. Wait for next Celery Beat cycle to see pings arrive")
        print("3. Check logs: docker-compose logs -f celery-beat")
        print()

    return failed_count == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
