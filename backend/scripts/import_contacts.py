import json
import sys
from pathlib import Path

import httpx


def _load_dotenv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_contacts.py <contacts.json> [base_url] [email] [password]", file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser().resolve()
    base_url = sys.argv[2] if len(sys.argv) >= 3 else "http://localhost:8000"
    dotenv = _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    email = sys.argv[3] if len(sys.argv) >= 4 else dotenv.get("GOOGLE_WORKSPACE_EMAIL", "")
    password = sys.argv[4] if len(sys.argv) >= 5 else dotenv.get("ADMIN_DEFAULT_PASSWORD", "")
    if not email or not password:
        print("Missing email/password (provide args 3/4 or set GOOGLE_WORKSPACE_EMAIL and ADMIN_DEFAULT_PASSWORD in .env)", file=sys.stderr)
        return 2

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "items" in raw:
        items = raw["items"]
    else:
        items = raw
    if not isinstance(items, list):
        print("JSON must be a list of contacts or {\"items\": [...]} ", file=sys.stderr)
        return 2

    with httpx.Client(timeout=30.0) as client:
        login = client.post(
            f"{base_url.rstrip('/')}/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        login.raise_for_status()
        token = (login.json() or {}).get("access_token")
        if not token:
            print("Login succeeded but no access_token returned", file=sys.stderr)
            return 1

        url = f"{base_url.rstrip('/')}/api/v1/contacts/bulk"
        resp = client.post(url, json=items, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        print(resp.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
