"""Append metadata-only records. Failure to record propagates to the caller."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self, *, principal: str, tool: str, status: str, run_id: str, duration_ms: float = 0
    ) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "principal": principal,
            "tool": tool,
            "status": status,
            "run_id": run_id,
            "duration_ms": round(duration_ms, 2),
        }
        data = (json.dumps(event, separators=(",", ":")) + "\n").encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(fd, data) != len(data):
                raise OSError("Incomplete audit write")
            os.fsync(fd)
        finally:
            os.close(fd)
