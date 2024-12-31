"""
Telemetry Module
--------------------------
Collects and batches usage statistics to be sent to a central server (or
stored for local analysis). This module is intended to keep overhead low
and focuses only on essential telemetry needs.
"""

from pathlib import Path
import atexit
import os
import time
import json
import logging
from typing import Any, Dict, TypeVar, ParamSpec, Callable, Awaitable
import functools

logger = logging.getLogger(__name__)

#: Time in minutes between forced flushes
FLUSH_INTERVAL_MINUTES = 5

#: Number of events to batch prior to sending.
BATCH_SIZE = 10

#: Path for the backup file
BACKUP_FILE = Path.home() / ".omproxy" / "telemetry_backup.jsonl"

#: Buffer to store events.
_events_buffer = []

#: Track the last flush time
_last_flush_time = time.time()


def _load_backup() -> None:
    """
    Load events from backup file if it exists.
    """
    global _events_buffer
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                for line in f:
                    _events_buffer.append(json.loads(line.strip()))
            os.remove(BACKUP_FILE)  # Remove backup after successful load
            logger.info(f"Loaded {len(_events_buffer)} events from backup")
        except Exception as e:
            logger.error(f"Failed to load backup file: {e}")


def _save_backup() -> None:
    """
    Save current buffer to backup file.
    """
    if not _events_buffer:
        return

    try:
        os.makedirs(BACKUP_FILE.parent, exist_ok=True)
        with open(BACKUP_FILE, "w") as f:
            for event in _events_buffer:
                f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Failed to save backup file: {e}")


# Register backup on program exit
atexit.register(_save_backup)

# Load any existing backup when module is imported
_load_backup()


def record_usage_event(event_name: str, details: Dict[str, Any]) -> None:
    """
    Record an individual usage event. This could be used to track:
    - Website analytics: page views, user-agent, session info
    - MCP usage: endpoints called, request times, success/failure
    """
    event = {
        "type": "usage",
        "timestamp": time.time(),
        "event_name": event_name,
        "details": details,
    }
    _add_to_buffer(event)


def record_error_event(error_message: str, stack_trace: str) -> None:
    """
    Record an error event (for example from the MCP server).
    """
    event = {
        "type": "error",
        "timestamp": time.time(),
        "error_message": error_message,
        "stack_trace": stack_trace,
    }
    _add_to_buffer(event)


def _add_to_buffer(event: Dict[str, Any]) -> None:
    """
    Helper method to add an event to the buffer and possibly
    trigger the batch-send if we've reached the threshold.
    """
    global _last_flush_time
    current_time = time.time()

    _events_buffer.append(event)
    if (
        len(_events_buffer) >= BATCH_SIZE
        or current_time - _last_flush_time >= FLUSH_INTERVAL_MINUTES * 60
    ):
        send_batch_events()
        _last_flush_time = current_time


def send_batch_events() -> None:
    """
    Sends the batched events to a hypothetical central server or writes to local storage.
    Here we simply print them or optionally store in a file as an example.
    """
    if not _events_buffer:
        return

    # Placeholder for a server POST, e.g.:
    # requests.post("https://central-telemetry.example.com", json=self._events_buffer)
    logger.info("Sending batch events to central aggregator (stub).")
    try:
        with open("events.jsonl", "w") as f:
            for event in _events_buffer:
                f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Failed to send batch events: {e}")

    # Clear buffer after sending
    _events_buffer.clear()


def flush() -> None:
    """
    Manually flush events if needed.
    """
    send_batch_events()


T = TypeVar("T")
P = ParamSpec("P")


def record_error(
    func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    """Wrap a function to record errors via telemetry.

    Args:
        handler: An async function to wrap with error recording

    Returns:
        Wrapped async function that records errors before re-raising them

    Example:
        @record_error
        async def my_func(x: int, y: str = "") -> Result:
            ...
    """

    @functools.wraps(func)
    async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            import traceback

            record_error_event(str(e), traceback.format_exc())
            raise

    return _wrapper
