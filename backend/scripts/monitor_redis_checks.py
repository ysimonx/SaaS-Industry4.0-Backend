#!/usr/bin/env python3
"""
Monitor Redis health checks creation in real-time
"""

import os
import sys
import time
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def monitor_redis_checks():
    """Monitor Redis checks continuously"""
    from app.monitoring.healthchecks_client import healthchecks

    if not healthchecks.enabled:
        print("❌ Healthchecks not enabled")
        return

    print("🔍 Monitoring Redis checks...")
    print(f"Started at: {datetime.now().isoformat()}")
    print("-" * 60)

    # Keep track of checks we've seen
    seen_checks = set()
    iteration = 0

    while True:
        iteration += 1
        checks = healthchecks.list_checks()
        redis_checks = [c for c in checks if 'redis' in c.get('name', '').lower()]

        current_checks = set()
        new_checks = []

        for check in redis_checks:
            check_id = check.get('ping_url', '').split('/')[-1]
            tags = check.get('tags', [])
            if isinstance(tags, str):
                tags = tags.split()

            check_key = f"{check_id}:{check['name']}"
            current_checks.add(check_key)

            if check_key not in seen_checks:
                new_checks.append({
                    'id': check_id,
                    'name': check['name'],
                    'tags': tags,
                    'is_auto': 'auto-created' in tags
                })

        # Report new checks
        if new_checks:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iteration {iteration}")
            for nc in new_checks:
                if nc['is_auto']:
                    print(f"  ⚠️  NEW AUTO-CREATED: {nc['name']} (ID: {nc['id'][:8]}...) Tags: {nc['tags']}")
                else:
                    print(f"  ✅ NEW LEGITIMATE: {nc['name']} (ID: {nc['id'][:8]}...)")
            seen_checks.update(current_checks)

        # Summary every 10 iterations
        if iteration % 10 == 0:
            auto_count = sum(1 for c in redis_checks if 'auto-created' in str(c.get('tags', [])))
            legit_count = len(redis_checks) - auto_count
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Status after {iteration} checks:")
            print(f"  Total Redis checks: {len(redis_checks)}")
            print(f"  Legitimate: {legit_count}")
            print(f"  Auto-created: {auto_count}")
            if auto_count > 0:
                print("  ❌ Still creating duplicates!")
            else:
                print("  ✅ No duplicates!")

        # Wait 30 seconds before next check
        time.sleep(30)


if __name__ == '__main__':
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            monitor_redis_checks()
    except KeyboardInterrupt:
        print("\n\n✋ Monitoring stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)