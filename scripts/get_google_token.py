"""
Run this script to get Google OAuth refresh token.
Usage: python scripts/get_google_token.py
"""
from __future__ import annotations

import argparse

from google_auth_oauthlib.flow import InstalledAppFlow
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-type", choices=["installed", "web"], default="installed")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--max-port-attempts", type=int, default=20)
    return parser.parse_args()


def build_client_config(
    client_type: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    if client_type == "web":
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def run_flow(client_type: str, host: str, port: int, max_port_attempts: int):
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    workspace_email = input("Google Workspace Email: ").strip()

    last_exc: Exception | None = None
    attempts = 1 if client_type == "web" else max_port_attempts
    for candidate in range(port, port + attempts):
        try:
            redirect_uri = f"http://{host}:{candidate}/"
            print(f"Using redirect URI: {redirect_uri}")
            client_config = build_client_config(client_type, client_id, client_secret, redirect_uri)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            flow.redirect_uri = redirect_uri
            creds = flow.run_local_server(host=host, port=candidate)
            return client_id, client_secret, workspace_email, creds, candidate
        except OSError as exc:
            last_exc = exc
            if client_type == "web":
                raise SystemExit(
                    f"Cannot bind local server on {redirect_uri} ({exc}). "
                    f"Free port {candidate} or rerun with --port <NEW_PORT> "
                    f"and add that exact redirect URI in Google Cloud Console."
                ) from exc
            continue
        except InvalidGrantError as exc:
            raise SystemExit(f"OAuth failed (invalid_grant): {exc}") from exc
    raise SystemExit(f"Cannot bind local server port starting at {port}: {last_exc}")


def main() -> int:
    args = parse_args()
    client_id, client_secret, workspace_email, creds, bound_port = run_flow(
        client_type=args.client_type,
        host=args.host,
        port=args.port,
        max_port_attempts=max(args.max_port_attempts, 1),
    )

    print("\n=== Copy these to your .env ===")
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print(f"GOOGLE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GOOGLE_WORKSPACE_EMAIL={workspace_email}")
    print(f"\n(local server used http://{args.host}:{bound_port}/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
