from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path

import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.soak_monitor import join_url, run_soak


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL ของ backend เช่น http://localhost:8000 หรือ https://app.yourdomain.com",
    )
    parser.add_argument(
        "--path",
        default="/api/v1/system/health",
        help="Path ของ endpoint health (default: /api/v1/system/health)",
    )
    parser.add_argument("--token", default=None, help="Bearer token (ถ้าระบบปิด auth ไว้)")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-consecutive-failures", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    return parser


def _join_url(base_url: str, path: str) -> str:
    return join_url(base_url, path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    url = _join_url(args.base_url, args.path)
    duration = timedelta(hours=float(args.hours))
    interval = timedelta(seconds=float(args.interval_seconds))

    if args.once:
        duration = timedelta(seconds=0)
        interval = timedelta(seconds=0)

    exit_code = asyncio.run(
        run_soak(
            url=url,
            token=args.token,
            duration=duration,
            interval=interval,
            max_consecutive_failures=int(args.max_consecutive_failures),
            timeout_s=float(args.timeout_seconds),
        )
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
