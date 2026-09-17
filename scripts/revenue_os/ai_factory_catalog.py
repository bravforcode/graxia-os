"""Validate and provision the Ai Factory storefront catalog in Revenue OS.

The Ai Factory storefront is intentionally not the source of truth for payment
or fulfillment.  This module turns its reviewed display catalog into a
server-side Revenue OS payload and requires a private object-store key for
every paid product before an apply is allowed.

The CLI is check-only by default.  ``--apply`` performs an idempotent database
upsert and never calls Stripe, an object-store provider, or the storefront.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from graxia.packages.revenue_os import models
from graxia.packages.revenue_os.db import get_db_session
from graxia.packages.revenue_os.enums import ProductStatus, ProductType


AI_FACTORY_SLUGS: tuple[str, ...] = (
    "01-prompt-pack-th",
    "02-obsidian-student-kit",
    "03-freelance-pricing-calculator",
    "04-cold-email-template-pack",
    "05-ai-automation-workflow",
    "06-cv-international-template",
    "07-n8n-sme-workflow-pack",
    "08-content-calendar-90d",
    "09-finance-tracker-thb",
    "10-ai-agent-starter-github",
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_PRIVATE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
_PUBLIC_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_UNSAFE_URL_KEYS = {
    "asset_url",
    "download_url",
    "fulfillment_url",
    "gumroad_url",
    "payment_link_url",
    "public_url",
    "stripe_payment_link_url",
}


class CatalogContractError(ValueError):
    """Raised when a storefront catalog cannot safely become a paid product."""


@dataclass(frozen=True)
class StorefrontProduct:
    slug: str
    name_th: str
    name_en: str
    tagline: str
    price_thb: int

    @property
    def price_cents(self) -> int:
        """Return satang using Revenue OS's historical ``*_cents`` field name."""

        return self.price_thb * 100


def _require_text(value: Any, field: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogContractError(f"product {index}: {field} must be non-empty text")
    return value.strip()


def _reject_public_urls(value: Any, path: str = "catalog") -> None:
    if isinstance(value, str) and _PUBLIC_URL_RE.search(value):
        raise CatalogContractError(f"{path}: public URLs are not allowed in the catalog")
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _UNSAFE_URL_KEYS and child:
                raise CatalogContractError(f"{child_path}: public fulfillment/payment URLs are not allowed")
            _reject_public_urls(child, child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_public_urls(child, f"{path}[{index}]")


def load_storefront_catalog(path: str | Path) -> tuple[StorefrontProduct, ...]:
    """Load the exact ten-product Ai Factory catalog.

    ``utf-8-sig`` accepts the BOM currently present in the storefront file,
    while remaining compatible with ordinary UTF-8 JSON.
    """

    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogContractError(f"cannot read catalog {source}: {exc}") from exc

    if not isinstance(raw, Mapping) or not isinstance(raw.get("products"), list):
        raise CatalogContractError("catalog root must contain a products list")
    _reject_public_urls(raw)

    products = raw["products"]
    if len(products) != len(AI_FACTORY_SLUGS):
        raise CatalogContractError(
            f"expected exactly {len(AI_FACTORY_SLUGS)} products, got {len(products)}"
        )

    seen: set[str] = set()
    normalized: list[StorefrontProduct] = []
    for index, item in enumerate(products):
        if not isinstance(item, Mapping):
            raise CatalogContractError(f"product {index}: entry must be an object")
        slug = _require_text(item.get("slug"), "slug", index)
        if not _SLUG_RE.fullmatch(slug):
            raise CatalogContractError(f"product {index}: invalid slug {slug!r}")
        if slug in seen:
            raise CatalogContractError(f"duplicate product slug {slug!r}")
        seen.add(slug)

        price_thb = item.get("price_thb")
        if isinstance(price_thb, bool) or not isinstance(price_thb, int) or price_thb <= 0:
            raise CatalogContractError(f"product {slug}: price_thb must be a positive integer")
        if price_thb > 10_000_000:
            raise CatalogContractError(f"product {slug}: price_thb is outside the supported range")

        normalized.append(
            StorefrontProduct(
                slug=slug,
                name_th=_require_text(item.get("name_th"), "name_th", index),
                name_en=_require_text(item.get("name_en"), "name_en", index),
                tagline=_require_text(item.get("tagline"), "tagline", index),
                price_thb=price_thb,
            )
        )

    if tuple(product.slug for product in normalized) != AI_FACTORY_SLUGS:
        raise CatalogContractError(
            "catalog slug coverage/order does not match the approved Ai Factory catalog"
        )
    return tuple(normalized)


def validate_private_object_keys(keys: Mapping[str, Any]) -> dict[str, str]:
    """Validate a slug-to-private-object-key mapping without revealing values."""

    if not isinstance(keys, Mapping):
        raise CatalogContractError("private object keys must be a JSON object")
    if set(keys) != set(AI_FACTORY_SLUGS):
        missing = sorted(set(AI_FACTORY_SLUGS) - set(keys))
        extra = sorted(set(keys) - set(AI_FACTORY_SLUGS))
        raise CatalogContractError(
            f"private object key coverage mismatch; missing={missing}, extra={extra}"
        )

    normalized: dict[str, str] = {}
    for slug in AI_FACTORY_SLUGS:
        key = keys[slug]
        if not isinstance(key, str) or not key.strip():
            raise CatalogContractError(f"private object key for {slug} must be non-empty text")
        key = key.strip()
        if (
            not key.startswith("ai-factory/")
            or not _PRIVATE_KEY_RE.fullmatch(key)
            or ".." in key
            or "//" in key
            or key.startswith("/")
            or "\\" in key
            or _PUBLIC_URL_RE.search(key)
        ):
            raise CatalogContractError(f"private object key for {slug} is not a safe relative key")
        normalized[slug] = key
    return normalized


def load_private_object_keys(path: str | Path) -> dict[str, str]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogContractError(f"cannot read private object key map {source}: {exc}") from exc
    return validate_private_object_keys(raw)


def build_product_payloads(
    catalog: Sequence[StorefrontProduct],
    private_object_keys: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Build server-side product rows; browser-controlled price is never used."""

    if tuple(product.slug for product in catalog) != AI_FACTORY_SLUGS:
        raise CatalogContractError("catalog does not contain the approved Ai Factory slug set")
    keys = validate_private_object_keys(private_object_keys)

    return tuple(
        {
            "name": product.name_en,
            "slug": product.slug,
            "type": ProductType.LOW_TICKET,
            "price_cents": product.price_cents,
            "currency": "THB",
            "status": ProductStatus.PUBLISHED,
            "promise": product.tagline,
            "target_audience": "Ai Factory storefront buyer",
            "deliverables": "Private digital fulfillment through Revenue OS",
            "fulfillment_instructions": "Issue a short-lived signed download from private object storage.",
            "metadata_": {
                "source_catalog": "ai-factory",
                "private_object_key": keys[product.slug],
            },
        }
        for product in catalog
    )


async def upsert_product_payloads(db: Any, payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Idempotently reconcile rows while preserving provider identifiers."""

    created = 0
    updated = 0
    for payload in payloads:
        product = await db.scalar(
            select(models.Product).where(models.Product.slug == payload["slug"])
        )
        if product is None:
            db.add(models.Product(**dict(payload)))
            created += 1
            continue

        for field in (
            "name",
            "type",
            "price_cents",
            "currency",
            "status",
            "promise",
            "target_audience",
            "deliverables",
            "fulfillment_instructions",
        ):
            setattr(product, field, payload[field])
        # A prior public fulfillment URL must never survive reconciliation.
        product.fulfillment_url = None
        metadata = dict(product.metadata_ or {})
        metadata.update(payload["metadata_"])
        product.metadata_ = metadata
        updated += 1

    await db.flush()
    return {"created": created, "updated": updated, "total": len(payloads)}


def _summary(catalog: Sequence[StorefrontProduct], keys_checked: bool, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "currency": "THB",
        "product_count": len(catalog),
        "slugs": [product.slug for product in catalog],
        "total_price_thb": sum(product.price_thb for product in catalog),
        "private_object_keys_checked": keys_checked,
        "provider_calls_performed": False,
    }


async def _apply(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    async with get_db_session() as db:
        return await upsert_product_payloads(db, payloads)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--private-keys",
        type=Path,
        help="JSON object mapping each product slug to an ai-factory/* private object key",
    )
    parser.add_argument("--apply", action="store_true", help="upsert rows into DATABASE_URL")
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="required in APP_ENV=production together with --apply",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        catalog = load_storefront_catalog(args.catalog)
        if args.private_keys is None:
            if args.apply:
                raise CatalogContractError("--apply requires --private-keys")
            result = _summary(catalog, keys_checked=False, mode="check-only-catalog")
        else:
            keys = load_private_object_keys(args.private_keys)
            payloads = build_product_payloads(catalog, keys)
            if not args.apply:
                result = _summary(catalog, keys_checked=True, mode="check-only-full")
            else:
                app_env = os.getenv("APP_ENV", "").lower()
                if app_env not in {"development", "staging", "production"}:
                    raise CatalogContractError(
                        "--apply requires APP_ENV=development, staging, or production; no rows were changed"
                    )
                if app_env == "production" and not args.confirm_production:
                    raise CatalogContractError(
                        "production apply requires --confirm-production; no rows were changed"
                    )
                result = _summary(catalog, keys_checked=True, mode=f"apply-{app_env}")
                result["upsert"] = asyncio.run(_apply(payloads))
    except CatalogContractError as exc:
        print(f"catalog contract blocked: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
