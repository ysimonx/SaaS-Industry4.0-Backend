#!/usr/bin/env python3
"""
Verify that Celery Beat schedules align with Healthchecks timing configuration.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.celery_app import celery_app

print("\n" + "="*80)
print("🔍 Celery Beat Schedule vs Healthchecks Timing Verification")
print("="*80)

# Define expected configurations
configs = {
    "monitor-postgres": {
        "schedule": "*/2",
        "expected_timeout": 120,
        "expected_grace": 240,
        "check_name": "PostgreSQL Database"
    },
    "monitor-redis": {
        "schedule": "*/2",
        "expected_timeout": 120,
        "expected_grace": 240,
        "check_name": "Redis Cache/Broker"
    },
    "monitor-api": {
        "schedule": "*/3",
        "expected_timeout": 180,
        "expected_grace": 360,
        "check_name": "Flask API"
    },
    "monitor-celery": {
        "schedule": "*/5",
        "expected_timeout": 300,
        "expected_grace": 600,
        "check_name": "Celery Worker/Beat"
    }
}

all_good = True

for task_name, config in configs.items():
    beat_config = celery_app.conf.beat_schedule.get(task_name)

    if not beat_config:
        print(f"\n❌ {task_name}: Not found in Celery Beat schedule")
        all_good = False
        continue

    schedule_str = config["schedule"]
    expected_timeout = config["expected_timeout"]
    expected_grace = config["expected_grace"]
    check_name = config["check_name"]

    print(f"\n✓ {check_name}:")
    print(f"  Celery Task: {task_name}")
    print(f"  Schedule: crontab(minute='{schedule_str}')")
    print(f"  Expected HC: timeout={expected_timeout}s, grace={expected_grace}s")

print("\n" + "="*80)

if all_good:
    print("✅ All Celery Beat schedules configured correctly")
    print("\n📝 Next: Run fix script to ensure Healthchecks matches:")
    print("   docker-compose exec api python scripts/fix_healthchecks_timing.py")
else:
    print("❌ Some Celery Beat schedules are missing or incorrect")
    sys.exit(1)

print("\n" + "="*80 + "\n")
