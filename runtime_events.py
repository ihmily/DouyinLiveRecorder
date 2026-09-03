import json
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any


_event_lock = threading.Lock()


def _get_application_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))


def emit_runtime_event(event: str, **fields: Any) -> None:
    try:
        event_data = {
            **fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
        }

        log_directory = os.path.join(
            _get_application_directory(),
            "logs"
        )
        os.makedirs(log_directory, exist_ok=True)

        event_file = os.path.join(
            log_directory,
            "runtime_events.jsonl"
        )

        line = json.dumps(
            event_data,
            ensure_ascii=False,
            separators=(",", ":")
        )

        with _event_lock:
            with open(event_file, "a", encoding="utf-8") as file:
                file.write(line + "\n")

    except Exception:
        pass
