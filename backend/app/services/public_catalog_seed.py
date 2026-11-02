"""Plan or apply the static storefront catalog to an existing tenant.

New rows stay in draft until a deliverable and its delivery access are
verified. This service never creates assets, payment records, or tenants.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.models.funnel import DigitalProduct
from app.models.organization import Organization

ASSET_CATALOG_ROOT = Path(__file__).resolve().parents[2] / "assets" / "catalog"


@dataclass(frozen=True)
class CatalogProduct:
    slug: str
    name: str
    price_amount: Decimal
    currency: str
    product_type: str


# Keep this list in parity with frontend/src/data/products.ts. The focused
# contract test compares these fields against that source file.
PUBLIC_CATALOG: tuple[CatalogProduct, ...] = (
    CatalogProduct(
        "ai-prompt-pack-50-17014b",
        "AI Prompt Pack Starter (50 Prompts)",
        Decimal("149.00"),
        "THB",
        "prompt_pack",
    ),
    CatalogProduct(
        "notion-business-template-a9655b",
        "Notion Business Template — All-in-One",
        Decimal("299.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "ai-business-course-0278b6",
        "AI for Business Course: Beginner to Practical",
        Decimal("499.00"),
        "THB",
        "course",
    ),
    CatalogProduct(
        "prompt-pack-th",
        "Thai AI Prompt Pack",
        Decimal("299.00"),
        "THB",
        "prompt_pack",
    ),
    CatalogProduct(
        "obsidian-student-kit",
        "Obsidian Student Starter Kit",
        Decimal("199.00"),
        "THB",
        "kit",
    ),
    CatalogProduct(
        "freelance-pricing-calculator",
        "Thai Freelance Pricing Calculator",
        Decimal("149.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "cold-email-template-pack",
        "Cold Email Template Pack TH EN",
        Decimal("399.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "ai-automation-workflow",
        "AI Automation Workflow Cheatsheet",
        Decimal("499.00"),
        "THB",
        "kit",
    ),
    CatalogProduct(
        "cv-international-template",
        "International CV Resume Template",
        Decimal("199.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "n8n-sme-workflow-pack",
        "N8N Workflow Pack for Thai SME",
        Decimal("799.00"),
        "THB",
        "kit",
    ),
    CatalogProduct(
        "content-calendar-90d",
        "Thai Content Calendar 90 Days",
        Decimal("599.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "finance-tracker-thb",
        "Personal Finance Tracker THB",
        Decimal("149.00"),
        "THB",
        "template",
    ),
    CatalogProduct(
        "ai-agent-starter-github",
        "Open Source AI Agent Starter Python",
        Decimal("999.00"),
        "THB",
        "kit",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_catalog_file(root: Path, filename: Any) -> Path | None:
    if not isinstance(filename, str) or not filename:
        return None
    posix_path = PurePosixPath(filename.replace("\\", "/"))
    windows_path = PureWindowsPath(filename)
    if (
        len(posix_path.parts) != 1
        or posix_path.parts[0] in {".", ".."}
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        return None
    try:
        candidate = (root / posix_path.name).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def build_catalog_asset_audit(
    catalog_root: Path = ASSET_CATALOG_ROOT,
) -> dict[str, Any]:
    """Verify manifest-backed file integrity without claiming delivery access."""

    root = Path(catalog_root)
    errors: list[dict[str, str]] = []
    try:
        root = root.resolve(strict=True)
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_products = manifest.get("products")
        if not isinstance(manifest_products, dict):
            raise ValueError("manifest products must be an object")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append({"code": "catalog_manifest_unavailable", "detail": str(exc)})
        manifest_products = {}

    catalog_by_slug = {product.slug: product for product in PUBLIC_CATALOG}
    records: list[dict[str, Any]] = []
    records_by_slug: dict[str, dict[str, Any]] = {}
    for slug, entry in sorted(manifest_products.items()):
        if not isinstance(entry, dict):
            entry = {}
        product = catalog_by_slug.get(slug)
        filename = entry.get("file")
        asset_path = _safe_catalog_file(root, filename)
        file_exists = asset_path is not None
        try:
            actual_bytes = asset_path.stat().st_size if asset_path else None
            actual_sha256 = _sha256(asset_path) if asset_path else None
        except OSError:
            file_exists = False
            actual_bytes = None
            actual_sha256 = None
        expected_bytes = entry.get("bytes")
        expected_sha256 = entry.get("sha256")
        bytes_match = (
            file_exists
            and type(expected_bytes) is int
            and actual_bytes == expected_bytes
        )
        sha256_match = (
            file_exists
            and isinstance(expected_sha256, str)
            and actual_sha256 == expected_sha256.lower()
        )
        sources = entry.get("sources")
        source_entries = sources if isinstance(sources, list) else []
        source_paths = [
            source["source"]
            for source in source_entries
            if isinstance(source, dict) and isinstance(source.get("source"), str)
        ]
        source_metadata_valid = (
            isinstance(sources, list)
            and bool(source_paths)
            and len(source_paths) == len(source_entries)
        )
        html_source_paths = [
            source
            for source in source_paths
            if PurePosixPath(source.replace("\\", "/")).suffix.lower() == ".html"
        ]
        file_integrity_verified = bool(bytes_match and sha256_match)
        payload_integrity_verified = bool(
            product is not None
            and file_integrity_verified
            and source_metadata_valid
            and not html_source_paths
        )
        record = {
            "slug": slug,
            "catalog_name": product.name if product else None,
            "frontend_slug_match": product is not None,
            "file": filename,
            "file_exists": file_exists,
            "expected_bytes": expected_bytes,
            "actual_bytes": actual_bytes,
            "bytes_match": bool(bytes_match),
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
            "sha256_match": bool(sha256_match),
            "file_integrity_verified": file_integrity_verified,
            "source_paths": source_paths,
            "source_metadata_verified": source_metadata_valid,
            "html_source_paths": html_source_paths,
            "html_source_present": bool(html_source_paths),
            "payload_integrity_verified": payload_integrity_verified,
            "delivery_access_verified": False,
            "sellable": False,
        }
        records.append(record)
        records_by_slug[slug] = record

    gaps: list[dict[str, Any]] = []
    for product in PUBLIC_CATALOG:
        record = records_by_slug.get(product.slug)
        if record is None:
            code = "manifest_slug_missing"
        elif not record["file_integrity_verified"]:
            code = "asset_integrity_unverified"
        elif not record["source_metadata_verified"]:
            code = "source_metadata_unverified"
        elif record["html_source_present"]:
            code = "html_source_not_verified_payload"
        elif not record["payload_integrity_verified"]:
            code = "payload_integrity_unverified"
        else:
            code = "protected_delivery_unverified"
        gaps.append(
            {
                "slug": product.slug,
                "name": product.name,
                "code": code,
                "file_integrity_verified": bool(
                    record and record["file_integrity_verified"]
                ),
                "payload_integrity_verified": bool(
                    record and record["payload_integrity_verified"]
                ),
                "delivery_access_verified": False,
                "sellable": False,
            }
        )

    file_integrity_count = sum(record["file_integrity_verified"] for record in records)
    payload_integrity_count = sum(
        record["payload_integrity_verified"] for record in records
    )
    status = (
        "blocked"
        if errors or not manifest_products
        else "integrity_verified_delivery_unverified"
        if payload_integrity_count
        else "no_verified_payloads"
    )
    return {
        "status": status,
        "manifest_path": "backend/assets/catalog/manifest.json",
        "manifest_present": not errors,
        "manifest_record_count": len(manifest_products),
        "frontend_exact_slug_matches": sum(
            record["frontend_slug_match"] for record in records
        ),
        "file_integrity_verified_count": file_integrity_count,
        "payload_integrity_verified_count": payload_integrity_count,
        "delivery_access_verified_count": 0,
        "delivery_access_verification": "not_performed",
        "html_sources_used_as_payloads": False,
        "sellable": False,
        "records": records,
        "gaps": gaps,
        "errors": errors,
    }


def build_public_catalog_seed_summary(
    organization_id: UUID | None,
    configured_organization_id: UUID | None,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Build the machine-readable result and validate tenant configuration."""

    asset_audit = build_catalog_asset_audit()
    payload_by_slug = {
        record["slug"]: record["payload_integrity_verified"]
        for record in asset_audit["records"]
    }
    blocked_from_seed = sum(
        not payload_by_slug.get(product.slug, False) for product in PUBLIC_CATALOG
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "mode": "apply" if apply else "dry_run",
        "status": "blocked",
        "organization_id": str(organization_id) if organization_id else None,
        "configured_organization_id": (
            str(configured_organization_id) if configured_organization_id else None
        ),
        "applied": False,
        "asset_audit": asset_audit,
        "counts": {
            "catalog_items": len(PUBLIC_CATALOG),
            "existing": 0,
            "missing": 0,
            "planned_create": 0,
            "created": 0,
            "conflicts": 0,
            "gaps": len(asset_audit["gaps"]),
            "integrity_verified_files": asset_audit["file_integrity_verified_count"],
            "integrity_verified_payloads": asset_audit[
                "payload_integrity_verified_count"
            ],
            "delivery_access_verified": asset_audit["delivery_access_verified_count"],
            "blocked_from_seed": blocked_from_seed,
        },
        "errors": [],
        "conflicts": [],
        "gaps": asset_audit["gaps"],
        "items": [],
    }

    summary["errors"].extend(asset_audit["errors"])

    if organization_id is None:
        summary["errors"].append(
            {
                "code": "organization_id_required",
                "message": "Pass an explicit --organization-id.",
            }
        )
    if configured_organization_id is None:
        summary["errors"].append(
            {
                "code": "public_funnel_organization_id_required",
                "message": "PUBLIC_FUNNEL_ORGANIZATION_ID must be a valid UUID.",
            }
        )
    if (
        organization_id is not None
        and configured_organization_id is not None
        and organization_id != configured_organization_id
    ):
        summary["errors"].append(
            {
                "code": "organization_id_mismatch",
                "message": (
                    "The explicit organization ID must match "
                    "PUBLIC_FUNNEL_ORGANIZATION_ID."
                ),
            }
        )

    if not summary["errors"]:
        summary["status"] = "ready"
    return summary


def _conflicting_fields(
    existing: DigitalProduct, expected: CatalogProduct
) -> list[str]:
    fields = {
        "name": expected.name,
        "slug": expected.slug,
        "product_type": expected.product_type,
        "price_amount": expected.price_amount,
        "currency": expected.currency,
        "status": "draft",
        "published_at": None,
        "is_deleted": False,
    }
    mismatches: list[str] = []
    for name, value in fields.items():
        actual = getattr(existing, name)
        if name == "price_amount" and actual is not None:
            actual = Decimal(str(actual))
        if actual != value:
            mismatches.append(name)
    return mismatches


async def seed_public_catalog(
    session: AsyncSession,
    organization_id: UUID | None,
    configured_organization_id: UUID | None,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Return a dry-run plan, or insert missing draft rows when explicitly asked."""

    summary = build_public_catalog_seed_summary(
        organization_id, configured_organization_id, apply=apply
    )
    if summary["errors"]:
        return summary

    organization = await session.scalar(
        select(Organization.id).where(Organization.id == organization_id)
    )
    if organization is None:
        summary["errors"].append(
            {
                "code": "organization_not_found",
                "message": (
                    "The organization does not exist; create or select an "
                    "existing tenant before seeding. No tenant was created."
                ),
            }
        )
        summary["status"] = "blocked"
        return summary

    slugs = [product.slug for product in PUBLIC_CATALOG]
    existing_rows = list(
        (
            await session.scalars(
                select(DigitalProduct)
                .options(noload(DigitalProduct.assets))
                .where(
                    DigitalProduct.organization_id == organization_id,
                    DigitalProduct.slug.in_(slugs),
                )
            )
        ).all()
    )
    by_slug: dict[str, list[DigitalProduct]] = {}
    for row in existing_rows:
        by_slug.setdefault(row.slug, []).append(row)

    asset_by_slug = {
        record["slug"]: record for record in summary["asset_audit"]["records"]
    }
    gap_by_slug = {gap["slug"]: gap for gap in summary["gaps"]}
    missing: list[CatalogProduct] = []
    missing_count = 0
    eligible_existing_count = 0
    for product in PUBLIC_CATALOG:
        matches = by_slug.get(product.slug, [])
        asset = asset_by_slug.get(product.slug)
        payload_integrity_verified = bool(asset and asset["payload_integrity_verified"])
        if not matches:
            missing_count += 1
            if payload_integrity_verified:
                missing.append(product)
                summary["items"].append(
                    {
                        "slug": product.slug,
                        "action": "would_create",
                        "name": product.name,
                        "price_amount": str(product.price_amount),
                        "currency": product.currency,
                        "status": "draft",
                        "payload_integrity_verified": True,
                        "delivery_access_verified": False,
                        "sellable": False,
                    }
                )
            else:
                gap = gap_by_slug[product.slug]
                summary["items"].append(
                    {
                        "slug": product.slug,
                        "action": "blocked_by_asset_gap",
                        "name": product.name,
                        "gap_code": gap["code"],
                        "status": "not_seeded",
                        "payload_integrity_verified": False,
                        "delivery_access_verified": False,
                        "sellable": False,
                    }
                )
            continue

        if len(matches) > 1:
            mismatches = ["duplicate_slug_records"]
        else:
            mismatches = _conflicting_fields(matches[0], product)

        if mismatches:
            summary["counts"]["conflicts"] += 1
            summary["conflicts"].append({"slug": product.slug, "fields": mismatches})
            summary["items"].append(
                {
                    "slug": product.slug,
                    "action": "conflict",
                    "fields": mismatches,
                    "sellable": False,
                }
            )
        else:
            summary["counts"]["existing"] += 1
            if payload_integrity_verified:
                eligible_existing_count += 1
            summary["items"].append(
                {
                    "slug": product.slug,
                    "action": "skip_existing",
                    "status": matches[0].status,
                    "payload_integrity_verified": payload_integrity_verified,
                    "delivery_access_verified": False,
                    "sellable": False,
                }
            )

    summary["counts"]["missing"] = missing_count
    if summary["conflicts"]:
        summary["errors"].append(
            {
                "code": "catalog_conflicts_present",
                "message": "Conflicts prevent all catalog writes; existing rows were not changed.",
            }
        )
        for item in summary["items"]:
            if item["action"] == "would_create":
                item["action"] = "blocked_by_conflict"
        summary["status"] = "blocked"
        return summary

    summary["counts"]["planned_create"] = len(missing)
    if not apply:
        summary["status"] = "dry_run"
        return summary

    if not missing:
        eligible_count = summary["asset_audit"]["payload_integrity_verified_count"]
        summary["status"] = (
            "already_seeded"
            if eligible_count > 0 and eligible_existing_count == eligible_count
            else "no_eligible_products"
        )
        return summary

    new_rows = [
        DigitalProduct(
            organization_id=organization_id,
            name=product.name,
            slug=product.slug,
            product_type=product.product_type,
            price_amount=product.price_amount,
            currency=product.currency,
            status="draft",
            description=None,
            short_description=None,
            cover_image_url=None,
            sales_page_content=None,
            published_at=None,
            stripe_price_id=None,
            stripe_product_id=None,
        )
        for product in missing
    ]
    session.add_all(new_rows)
    await session.commit()

    summary["counts"]["created"] = len(new_rows)
    summary["applied"] = True
    summary["status"] = "applied"
    for item in summary["items"]:
        if item["action"] == "would_create":
            item["action"] = "created"
    return summary
