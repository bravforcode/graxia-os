from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx


@dataclass(frozen=True)
class HealthSnapshot:
    ok: bool
    mode: str
    status_code: int
    issues: list[str]
    raw: dict


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def coerce_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def parse_system_health_payload(payload: dict, status_code: int) -> HealthSnapshot:
    readiness = payload.get("readiness") if isinstance(payload, dict) else None
    if not isinstance(readiness, dict):
        readiness = {}

    mode = readiness.get("mode")
    if not isinstance(mode, str) or not mode:
        mode = "unknown"

    issues = coerce_str_list(readiness.get("issues"))

    ok = status_code == 200 and mode in {"full", "degraded"}

    return HealthSnapshot(
        ok=ok,
        mode=mode,
        status_code=status_code,
        issues=issues,
        raw=payload if isinstance(payload, dict) else {"raw": payload},
    )


async def fetch_system_health(client: httpx.AsyncClient, url: str, token: str | None) -> HealthSnapshot:
    headers: dict[str, str] = {"accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"

    resp = await client.get(url, headers=headers)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw_text": resp.text}
    return parse_system_health_payload(payload, resp.status_code)


def format_event(ts: datetime, snapshot: HealthSnapshot, elapsed_s: float) -> str:
    return json.dumps(
        {
            "ts": ts.isoformat(),
            "elapsed_s": round(elapsed_s, 3),
            "ok": snapshot.ok,
            "mode": snapshot.mode,
            "status_code": snapshot.status_code,
            "issues": snapshot.issues,
        },
        ensure_ascii=False,
    )


def join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"


async def run_soak(
    *,
    url: str,
    token: str | None,
    duration: timedelta,
    interval: timedelta,
    max_consecutive_failures: int,
    timeout_s: float,
) -> int:
    start = now_utc()
    deadline = start + duration
    consecutive_failures = 0

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while True:
            now = now_utc()
            elapsed_s = (now - start).total_seconds()
            try:
                snapshot = await fetch_system_health(client, url, token)
                print(format_event(now, snapshot, elapsed_s))
                if snapshot.ok:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except Exception as exc:
                consecutive_failures += 1
                print(
                    json.dumps(
                        {
                            "ts": now.isoformat(),
                            "elapsed_s": round(elapsed_s, 3),
                            "ok": False,
                            "mode": "error",
                            "status_code": 0,
                            "issues": [str(exc)],
                        },
                        ensure_ascii=False,
                    )
                )

            if consecutive_failures >= max_consecutive_failures:
                return 2

            if now >= deadline:
                return 0 if consecutive_failures == 0 else 3

            remaining = deadline - now
            sleep_for = interval
            if sleep_for > remaining:
                sleep_for = remaining
            await asyncio.sleep(max(sleep_for.total_seconds(), 0.0))

