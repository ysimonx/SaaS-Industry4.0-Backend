#!/usr/bin/env python3
"""
Déclenche manuellement la tâche Celery de rafraîchissement des tokens.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.celery_app import celery_app
from app.tasks.sso_tasks import refresh_expiring_tokens

if __name__ == '__main__':
    print("Déclenchement manuel de la tâche de rafraîchissement des tokens...")
    print("=" * 70)

    # Déclenche la tâche de façon synchrone pour voir le résultat immédiatement
    result = refresh_expiring_tokens.apply()

    print("\n✅ Tâche exécutée !")
    print(f"\nRésultat : {result.result}")
    print("=" * 70)
