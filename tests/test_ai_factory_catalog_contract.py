from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from scripts.revenue_os.ai_factory_catalog import (
    AI_FACTORY_SLUGS,
    CatalogContractError,
    build_product_payloads,
    load_private_object_keys,
    load_storefront_catalog,
    upsert_product_payloads,
    validate_private_object_keys,
)


def _catalog() -> dict:
    return {
        "products": [
            {
                "slug": slug,
                "name_th": f"สินค้า {index}",
                "name_en": f"Product {index}",
                "tagline": f"Promise {index}",
                "price_thb": 100 + index,
            }
            for index, slug in enumerate(AI_FACTORY_SLUGS, start=1)
        ]
    }


def _private_keys() -> dict[str, str]:
    return {slug: f"ai-factory/{slug}.zip" for slug in AI_FACTORY_SLUGS}


def test_loads_bom_catalog_and_requires_approved_slug_order(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8-sig")

    catalog = load_storefront_catalog(path)

    assert tuple(product.slug for product in catalog) == AI_FACTORY_SLUGS
    assert catalog[0].price_cents == 10100


def test_build_payloads_use_server_side_amount_and_private_key():
    catalog = load_storefront_catalog_from_mapping(_catalog())
    payloads = build_product_payloads(catalog, _private_keys())

    assert payloads[0]["price_cents"] == 10100
    assert payloads[0]["currency"] == "THB"
    assert payloads[0]["metadata_"]["private_object_key"].startswith("ai-factory/")
    assert payloads[0]["status"].value == "published"


def test_catalog_rejects_public_asset_url(tmp_path):
    payload = _catalog()
    payload["products"][0]["download_url"] = "https://example.invalid/file.zip"
    path = tmp_path / "products.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogContractError, match="public .* URLs"):
        load_storefront_catalog(path)


def test_catalog_rejects_slug_drift(tmp_path):
    payload = _catalog()
    payload["products"][0]["slug"] = "unexpected-product"
    path = tmp_path / "products.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogContractError, match="slug coverage/order"):
        load_storefront_catalog(path)


@pytest.mark.parametrize(
    "bad_key",
    [
        "https://bucket.example/file.zip",
        "../outside.zip",
        "ai-factory\\unsafe.zip",
        "ai-factory//ambiguous.zip",
        "public/downloads/file.zip",
    ],
)
def test_private_object_keys_fail_closed(bad_key):
    keys = _private_keys()
    keys[AI_FACTORY_SLUGS[0]] = bad_key

    with pytest.raises(CatalogContractError):
        validate_private_object_keys(keys)


def test_private_key_file_accepts_utf8_bom(tmp_path):
    path = tmp_path / "private-object-keys.json"
    path.write_text(json.dumps(_private_keys()), encoding="utf-8-sig")

    assert load_private_object_keys(path)[AI_FACTORY_SLUGS[-1]].startswith("ai-factory/")


async def test_upsert_clears_legacy_public_fulfillment_and_preserves_stripe_id():
    catalog = load_storefront_catalog_from_mapping(_catalog())
    payloads = build_product_payloads(catalog, _private_keys())
    existing = SimpleNamespace(
        slug=AI_FACTORY_SLUGS[0],
        metadata_={"operator_note": "preserve"},
        fulfillment_url="https://public.invalid/file.zip",
        stripe_price_id="price_existing",
    )

    class FakeSession:
        async def scalar(self, _statement):
            return existing

        async def flush(self):
            return None

    result = await upsert_product_payloads(FakeSession(), payloads[:1])

    assert result == {"created": 0, "updated": 1, "total": 1}
    assert existing.fulfillment_url is None
    assert existing.stripe_price_id == "price_existing"
    assert existing.metadata_["operator_note"] == "preserve"
    assert existing.metadata_["private_object_key"].startswith("ai-factory/")


def load_storefront_catalog_from_mapping(payload: dict):
    """Keep the unit fixture in-memory without changing the production loader."""

    # The loader is deliberately file-based; a BOM-backed temp file mirrors the
    # actual storefront contract and keeps tests independent of the other repo.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "products.json"
        path.write_text(json.dumps(copy.deepcopy(payload)), encoding="utf-8-sig")
        return load_storefront_catalog(path)
