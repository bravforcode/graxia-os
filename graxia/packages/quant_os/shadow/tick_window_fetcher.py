"""Tick window fetcher — queries copy_ticks_range with UTC-aware datetimes only.

Rejects naive datetimes. Validates returned ticks within requested window.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import hashlib
import json


class TickWindowFetcher:
    """Fetches ticks from MT5 using copy_ticks_range with UTC-aware input.

    Policy:
    - Only accepts timezone-aware datetime objects
    - Validates every returned tick is within requested window
    - Rejects naive datetimes at config validation time
    """

    def __init__(self, mt5_connection):
        self._mt5 = mt5_connection
        self._mt5_module = mt5_connection._mt5 if hasattr(mt5_connection, '_mt5') else None

    def validate_datetime_aware(self, dt: datetime, name: str) -> None:
        """Reject naive datetime at config validation time."""
        if dt.tzinfo is None:
            raise ValueError(
                f"NAIVE_DATETIME_REJECTED: {name} must be timezone-aware UTC. "
                f"Got naive datetime: {dt.isoformat()}. "
                f"Use: datetime(..., tz=timezone.utc)"
            )

    def fetch_ticks(
        self,
        symbol: str,
        request_from: datetime,
        request_to: datetime,
    ) -> dict:
        """Fetch ticks within [request_from, request_to].

        Returns dict with:
        - ticks: list of tick dicts
        - request_window_hash: hash of the request window
        - first_tick_utc, last_tick_utc: tick boundaries
        - outside_count: ticks outside requested window
        - error: error message if any
        """
        # Reject naive datetimes
        self.validate_datetime_aware(request_from, "request_from")
        self.validate_datetime_aware(request_to, "request_to")

        # Compute request window hash
        window_d = {
            "from": request_from.isoformat(),
            "to": request_to.isoformat(),
        }
        window_hash = hashlib.sha256(
            json.dumps(window_d, sort_keys=True).encode()
        ).hexdigest()[:16]

        result = {
            "ticks": [],
            "request_window_hash": window_hash,
            "request_from_utc": request_from.isoformat(),
            "request_to_utc": request_to.isoformat(),
            "first_tick_utc": "",
            "last_tick_utc": "",
            "first_tick_epoch": 0,
            "last_tick_epoch": 0,
            "outside_count": 0,
            "tick_count": 0,
            "error": "",
        }

        if not self._mt5_module:
            result["error"] = "MT5 module not available"
            return result

        try:
            ticks = self._mt5_module.copy_ticks_range(
                symbol, request_from, request_to,
                self._mt5_module.COPY_TICKS_ALL
            )
        except Exception as e:
            result["error"] = f"copy_ticks_range failed: {e}"
            return result

        if ticks is None or len(ticks) == 0:
            result["error"] = "no ticks returned"
            return result

        # Process ticks
        from_epoch = int(request_from.timestamp())
        to_epoch = int(request_to.timestamp())
        outside = 0

        for t in ticks:
            raw_time = int(t[0])
            tick_dict = {
                "time": raw_time,
                "time_msc": int(t[5]) if len(t) > 5 else raw_time * 1000,
                "bid": float(t[1]),
                "ask": float(t[2]),
                "last": float(t[3]),
                "volume": int(t[4]),
                "flags": int(t[6]) if len(t) > 6 else 0,
            }
            result["ticks"].append(tick_dict)

            # Validate within window
            if raw_time < from_epoch or raw_time > to_epoch:
                outside += 1

        result["tick_count"] = len(result["ticks"])
        result["outside_count"] = outside

        if result["ticks"]:
            first = result["ticks"][0]
            last = result["ticks"][-1]
            result["first_tick_epoch"] = first["time"]
            result["last_tick_epoch"] = last["time"]
            result["first_tick_utc"] = datetime.fromtimestamp(
                first["time"], tz=timezone.utc
            ).isoformat()
            result["last_tick_utc"] = datetime.fromtimestamp(
                last["time"], tz=timezone.utc
            ).isoformat()

        return result
