"""
Daily pipeline orchestrator.

Run automatically by GitHub Actions (.github/workflows/free-pipeline.yml).
Steps:
  1. Generate content (template — $0; --ai uses OpenAI if key present)
  2. If META_PAGE_TOKEN is set: post the first FB item to the page
  3. Build a Meta ad campaign in DRY-RUN (PAUSED) — never spends money
  4. Report what happened
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    # 1. Generate
    r = subprocess.run(
        [sys.executable, str(ROOT / "automation" / "content_generator.py"), "--ai"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
        return r.returncode

    # newest generated file
    gen_dir = ROOT / "docs" / "content" / "generated"
    files = sorted(gen_dir.glob("daily-*.json"))
    if not files:
        print("no content generated")
        return 1
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    fb_items = [i for i in data["items"] if i["channel"] == "facebook" and i.get("status") == "queue"]
    tiktok_items = [i for i in data["items"] if i["channel"] == "tiktok"]

    # 2. Auto-post FB (only if token configured — otherwise queue only)
    if fb_items and os.environ.get("META_PAGE_TOKEN"):
        r = subprocess.run(
            [sys.executable, str(ROOT / "automation" / "meta_poster.py"), "--post", fb_items[0]["body"]],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        print("AUTO-POST:", r.stdout.strip())
    else:
        print("AUTO-POST: skipped (META_PAGE_TOKEN not set — items queued for manual posting)")

    # 3. Build ad campaign (always DRY-RUN/paused — safe)
    r = subprocess.run(
        [sys.executable, str(ROOT / "automation" / "meta_poster.py"), "--ads"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print("ADS:", r.stdout.strip()[:400])

    # 4. Summary for the commit message
    print(f"SUMMARY: {len(fb_items)} FB items, {len(tiktok_items)} TikTok scripts queued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
