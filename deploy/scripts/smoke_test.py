#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--skip-tls", action="store_true")
    args = parser.parse_args()

    verify = not args.skip_tls
    with httpx.Client(base_url=args.target, verify=verify, timeout=20.0, follow_redirects=True) as client:
        health = client.get("/health")
        if health.status_code != 200:
            print(f"health check failed: {health.status_code}")
            return 1
        root = client.get("/")
        if root.status_code not in {200, 404}:
            print(f"root endpoint unexpected status: {root.status_code}")
            return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
