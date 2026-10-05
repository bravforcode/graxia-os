"""
Daily pipeline orchestrator.

Run automatically by GitHub Actions (.github/workflows/free-pipeline.yml).
Steps:
  1. Generate content (template — $0; --ai uses OpenAI if key present)
  2. Only --live plus META_PAGE_TOKEN may publish the first FB item
  3. Build a Meta ad campaign in DRY-RUN (PAUSED) — never spends money
  4. Report what happened
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="opt into AI provider calls")
    parser.add_argument("--live", action="store_true", help="opt into Facebook posting; ads remain preview-only")
    args = parser.parse_args()
    # 1. Generate
    r = subprocess.run(
        [sys.executable, str(ROOT / "automation" / "content_generator.py")] + (["--ai"] if args.ai else []),
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(r.stdout)
    if r.returncode != 0:
        print("Content generation failed", file=sys.stderr)
        return r.returncode if r.returncode > 0 else 1

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
    if args.live and fb_items and os.environ.get("META_PAGE_TOKEN"):
        r = subprocess.run(
            [sys.executable, str(ROOT / "automation" / "meta_poster.py"), "--post", fb_items[0]["body"], "--live"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if r.returncode != 0:
            print("AUTO-POST failed", file=sys.stderr)
            return r.returncode if r.returncode > 0 else 1
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
    if r.returncode != 0:
        print("ADS preview failed", file=sys.stderr)
        return r.returncode if r.returncode > 0 else 1
    print("ADS:", r.stdout.strip()[:400])

    # 4. Summary for the commit message
    print(f"SUMMARY: {len(fb_items)} FB items, {len(tiktok_items)} TikTok scripts queued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
