"""Result cache: identical live requests are served from a previous real run.

Most visitors launch a scenario without editing it. Instead of paying for the
same LLM calls again, the event log of the first successful run is stored and
replayed (with its original timing) for the next identical request. Replays
are labelled ``cached`` in every event stream and in the UI, and cost nothing.

Storage: a single SQLite file (stdlib, no extra service).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


def cache_key(*, provider: str, model: str, task_hint: str, code: str, request: str) -> str:
    payload = json.dumps([provider, model, task_hint, code.strip(), request.strip()], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResultCache:
    def __init__(self, path: str | Path, ttl_days: float = 30.0) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.ttl_s = ttl_days * 86400
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, created REAL NOT NULL, "
            "model TEXT NOT NULL, events TEXT NOT NULL, hits INTEGER NOT NULL DEFAULT 0)"
        )
        self._db.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT created, model, events FROM results WHERE key = ?", (key,)).fetchone()
            if row is None:
                return None
            created, model, events = row
            if time.time() - created > self.ttl_s:
                self._db.execute("DELETE FROM results WHERE key = ?", (key,))
                self._db.commit()
                return None
            self._db.execute("UPDATE results SET hits = hits + 1 WHERE key = ?", (key,))
            self._db.commit()
        return {"created": created, "model": model, "events": json.loads(events)}

    def put(self, key: str, model: str, events: list[dict[str, Any]]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO results (key, created, model, events, hits) VALUES (?, ?, ?, ?, 0)",
                (key, time.time(), model, json.dumps(events, ensure_ascii=False)),
            )
            self._db.commit()

    def stats(self) -> dict[str, int]:
        with self._lock:
            entries, hits = self._db.execute("SELECT COUNT(*), COALESCE(SUM(hits), 0) FROM results").fetchone()
        return {"entries": entries, "hits": hits}

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM results")
            self._db.commit()
