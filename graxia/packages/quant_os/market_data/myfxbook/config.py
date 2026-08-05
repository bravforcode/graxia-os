"""Myfxbook collector configuration.

Pilot scope: all 8 public systems of member Tanon58, taken from the live
"Other Systems by Tanon58" list on the SniperFPG page (fetched 2026-08-04).
"""

from urllib.parse import quote

BASE_URL = "https://www.myfxbook.com/members"

# (member, system, account_id) — URL becomes {BASE_URL}/{member}/{system}/{id}
PILOT_ACCOUNTS: list[tuple[str, str, int]] = [
    ("Tanon58", "sniperfpg", 12096204),
    ("Tanon58", "pamm-rt", 8072229),
    ("Tanon58", "tradewisdom-rich", 9774481),
    ("Tanon58", "master-follow", 11600093),
    ("Tanon58", "master-wasabi", 11627384),
    ("Tanon58", "wasabi-10000", 11627437),
    ("Tanon58", "master-sushi", 11756392),
    ("Tanon58", "punlotprofit", 12096241),
]

REQUEST_DELAY_SECONDS = 5.0  # minimum sleep between requests — be a polite scraper
TIMEOUT_SECONDS = 30.0
DB_PATH = "data/myfxbook.db"
REPORT_DIR = "reports/myfxbook"


def account_url(member: str, system: str, account_id: int) -> str:
    """Build the public account page URL for a (member, system, id) tuple."""
    return f"{BASE_URL}/{quote(member)}/{quote(system)}/{account_id}"
