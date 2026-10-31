"""Build Graxia delivery bundles from the existing AI Factory assets.

The source repository remains untouched.  This importer copies the real,
operator-owned text assets into one deterministic Markdown bundle per product
so the funnel asset API can deliver them as content.  It fails closed when a
source file is missing or contains an environment file.

Usage:
    python scripts/import_ai_factory_assets.py \
      --source-dir C:\\Users\\menum\\ai-factory \
      --output-dir C:\\Users\\menum\\graxia-os\\backend\\assets\\catalog
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PRODUCT_SOURCES: dict[str, tuple[str, ...]] = {
    "prompt-pack-th": ("downloads/01-prompt-pack-th.md",),
    "obsidian-student-kit": (
        "downloads/02-obsidian-student-kit/00-README.md",
        "downloads/02-obsidian-student-kit/01-course-note-template.md",
    ),
    "freelance-pricing-calculator": (
        "downloads/03-freelance-pricing-calculator.html",
    ),
    "cold-email-template-pack": (
        "downloads/04-cold-email-template-pack.md",
    ),
    "ai-automation-workflow": (
        "downloads/05-ai-automation-workflow-guide.md",
    ),
    "cv-international-template": (
        "downloads/06-cv-international-template.md",
    ),
    "n8n-sme-workflow-pack": (
        "downloads/07-n8n-sme-workflow-pack/README.md",
        "downloads/07-n8n-sme-workflow-pack/01-line-oa-auto-reply.json",
        "downloads/07-n8n-sme-workflow-pack/02-invoice-ocr-to-sheets.json",
        "downloads/07-n8n-sme-workflow-pack/03-daily-report-pos.json",
        "downloads/07-n8n-sme-workflow-pack/04-fb-lead-enrichment.json",
        "downloads/07-n8n-sme-workflow-pack/05-content-repurposing.json",
    ),
    "content-calendar-90d": (
        "downloads/08-content-calendar-90d.md",
        "downloads/08-content-calendar-90d.csv",
    ),
    "finance-tracker-thb": ("downloads/09-finance-tracker-thb.html",),
    "ai-agent-starter-github": (
        "downloads/10-ai-agent-starter-github/README.md",
        "downloads/10-ai-agent-starter-github/ARCHITECTURE.md",
        "downloads/10-ai-agent-starter-github/DEPLOY.md",
        "downloads/10-ai-agent-starter-github/EXAMPLES.md",
        "downloads/10-ai-agent-starter-github/LICENSE",
        "downloads/10-ai-agent-starter-github/prompts/system-prompt.md",
        "downloads/10-ai-agent-starter-github/code/agent_loop.py",
        "downloads/10-ai-agent-starter-github/code/memory.py",
        "downloads/10-ai-agent-starter-github/code/tools.py",
        "downloads/10-ai-agent-starter-github/code/requirements.txt",
        "downloads/10-ai-agent-starter-github/code/tests/test_agent.py",
    ),
}

TEXT_SUFFIXES = {".csv", ".html", ".json", ".md", ".py", ".txt", ".yml", ""}


def _read_source(source_root: Path, relative: str) -> tuple[Path, str]:
    path = (source_root / relative).resolve()
    if source_root.resolve() not in path.parents:
        raise ValueError(f"source escapes source directory: {relative}")
    if path.name.lower().startswith(".env"):
        raise ValueError(f"environment file is not a delivery asset: {relative}")
    if not path.is_file():
        raise FileNotFoundError(relative)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError(f"unsupported text asset: {relative}")
    return path, path.read_text(encoding="utf-8")


def _bundle(slug: str, source_root: Path) -> tuple[str, list[dict[str, object]]]:
    sections: list[str] = [
        f"# {slug} delivery bundle",
        "",
        "This bundle contains the original AI Factory delivery assets.",
        "Source files are preserved below with their relative paths.",
        "",
    ]
    manifest: list[dict[str, object]] = []
    for relative in PRODUCT_SOURCES[slug]:
        path, content = _read_source(source_root, relative)
        if not content.strip():
            raise ValueError(f"empty delivery asset: {relative}")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        language = path.suffix.lower().lstrip(".") or "text"
        sections.extend(
            [
                f"## Source: `{relative}`",
                "",
                f"```{language}",
                content.rstrip(),
                "```",
                "",
            ]
        )
        manifest.append(
            {
                "source": relative,
                "sha256": digest,
                "bytes": len(content.encode("utf-8")),
            }
        )
    return "\n".join(sections), manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    source_root = args.source_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source_root.is_dir():
        raise SystemExit(f"missing source directory: {source_root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    products: dict[str, object] = {}
    for slug in sorted(PRODUCT_SOURCES):
        content, sources = _bundle(slug, source_root)
        target = output_dir / f"{slug}.md"
        target.write_text(content, encoding="utf-8", newline="\n")
        products[slug] = {
            "file": target.name,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "bytes": len(content.encode("utf-8")),
            "sources": sources,
        }

    manifest = {
        "source_repository": str(source_root),
        "generated_by": "backend/scripts/import_ai_factory_assets.py",
        "products": products,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Generated {len(products)} delivery bundles in {output_dir}")
    for slug, info in products.items():
        print(f"OK {slug} {info['bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
