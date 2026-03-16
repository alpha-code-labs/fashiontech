from __future__ import annotations

import fcntl
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

class SessionLogger:
    def __init__(self):
        self.base_dir = Path("app/data/sessions")

    def write(self, wa_id: str, session: Dict[str, Any]) -> Path:
        ts = time.strftime("%Y%m%d")
        out_dir = self.base_dir / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        # Use uuid to prevent filename collision within same second
        stamp = f"{time.strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}"
        path = out_dir / f"session_{wa_id}_{stamp}.json"

        payload = dict(session)
        payload["logged_at_ts"] = int(time.time())

        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def log_step(self, wa_id: str, step: str) -> None:
        """Append a step to the daily steps CSV for drop-off curve analysis."""
        ts = time.strftime("%Y%m%d")
        out_dir = self.base_dir / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        path = out_dir / "steps.csv"
        line = f"{int(time.time())},{wa_id},{step}\n"

        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
