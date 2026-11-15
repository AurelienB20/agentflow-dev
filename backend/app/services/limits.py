"""Abuse protection for the public demo: per-IP rate limit and per-session quota.

In-memory (single instance MVP). Behind several instances, move this to a
shared store; not needed for a demo deployment.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import Settings


class RateLimiter:
    def __init__(self) -> None:
        self._ip_hits: dict[str, deque[float]] = defaultdict(deque)
        self._session_counts: dict[str, int] = defaultdict(int)
        self._day = ""
        self._day_count = 0

    @staticmethod
    def client_ip(request: Request, trust_proxy: bool) -> str:
        if trust_proxy:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request, settings: Settings) -> None:
        ip = self.client_ip(request, settings.trust_proxy)
        now = time.time()
        hits = self._ip_hits[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= settings.rate_limit_per_ip_per_hour:
            raise HTTPException(429, detail=f"Rate limit: {settings.rate_limit_per_ip_per_hour} live workflows per hour. "
                                            "The Guided Demo remains available.")
        session = (request.headers.get("x-session-id") or "")[:64]
        if session and self._session_counts[session] >= settings.quota_per_session:
            raise HTTPException(429, detail=f"Session quota reached ({settings.quota_per_session} live workflows). "
                                            "The Guided Demo remains available.")
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if day != self._day:
            self._day, self._day_count = day, 0
        if self._day_count >= settings.max_live_workflows_per_day:
            raise HTTPException(429, detail="The daily budget of live AI runs is used up. "
                                            "The Guided Demo remains available.")
        hits.append(now)
        self._day_count += 1
        if session:
            self._session_counts[session] += 1

    def reset(self) -> None:
        self._ip_hits.clear()
        self._session_counts.clear()
        self._day, self._day_count = "", 0


limiter = RateLimiter()
