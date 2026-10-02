"""Local JSON bridge for the dashboard; no user-supplied commands or paths."""

import json
import sys

from ai_pm_agent import task_lock, task_model, task_service


def main() -> int:
    """Read one bounded JSON request and return one JSON response."""
    try:
        raw = sys.stdin.read(32769)
        if len(raw) > 32768:
            raise ValueError("Request is too large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        with task_lock.acquire(
            timeout=2 if payload.get("action", "read") == "read" else 10
        ):
            result = task_service.execute(payload)
    except task_model.TaskConflictError as error:
        result = {"ok": False, "error": str(error), "conflict": True}
    except (ValueError, OSError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
