from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from app.models import FunnelRecommendation, LeadCapture
from app.models.delivery_email_event import DeliveryEmailEvent
from app.models.funnel import DeliveryAccess, LeadMagnet
from app.schemas.funnel import (
    DeliveryAccessPublic,
    FunnelRecommendationCreate,
    FunnelRecommendationRead,
    LeadMagnetPublic,
)


def test_live_funnel_model_mappings_match_catalog_contract():
    magnet = LeadMagnet.__table__
    captures = LeadCapture.__table__
    recommendations = FunnelRecommendation.__table__

    assert set(magnet.c.keys()) == {
        "id",
        "organization_id",
        "name",
        "slug",
        "target_product_id",
        "delivery_asset_id",
        "promise",
        "file_url",
        "landing_page_url",
        "status",
        "opt_in_count",
        "created_at",
        "updated_at",
    }
    assert isinstance(magnet.c.id.type, PG_UUID)
    assert magnet.c.name.type.length == 255
    assert magnet.c.file_url.type.length == 500
    delivery_asset_fk = next(iter(magnet.c.delivery_asset_id.foreign_keys))
    assert delivery_asset_fk.ondelete == "SET NULL"
    assert magnet.c.status.server_default is None
    assert magnet.c.opt_in_count.server_default is None
    magnet_checks = {constraint.name: str(constraint.sqltext) for constraint in magnet.constraints if hasattr(constraint, "sqltext")}
    assert "ck_lead_magnet_status" in magnet_checks
    assert all(value in magnet_checks["ck_lead_magnet_status"] for value in ("active", "published", "archived"))
    assert "ck_lead_magnet_opt_in_count_non_negative" in magnet_checks
    magnet_indexes = {index.name: index for index in magnet.indexes}
    assert magnet_indexes["ix_funnel_lead_magnets_org_slug"].unique is True
    assert "delivery_asset_id" in [column.name for column in magnet_indexes["ix_funnel_lead_magnets_delivery_asset_id"].columns]

    assert set(captures.c.keys()) == {
        "id",
        "organization_id",
        "lead_magnet_id",
        "email",
        "source",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "metadata_json",
        "created_at",
    }
    assert captures.c.email.type.length == 255
    assert captures.c.source.type.length == 100
    capture_fk = next(iter(captures.c.lead_magnet_id.foreign_keys))
    assert capture_fk.target_fullname == "funnel_lead_magnets.id"
    assert capture_fk.constraint.name == "fk_lead_captures_funnel_lead_magnet_id"
    assert {index.name for index in captures.indexes} >= {
        "ix_lead_capture_org_magnet_email",
        "ix_lead_captures_lead_magnet_id",
        "ix_lead_captures_organization_id",
    }

    assert set(recommendations.c.keys()) == {
        "id",
        "organization_id",
        "product_id",
        "recommendation_type",
        "bottleneck",
        "recommended_action",
        "expected_impact",
        "confidence",
        "effort",
        "risk",
        "reasoning",
        "draft_content",
        "rollback_note",
        "approval_request_id",
        "status",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    assert recommendations.c.recommendation_type.type.length == 50
    assert recommendations.c.status.server_default is None
    recommendation_checks = [
        str(constraint.sqltext)
        for constraint in recommendations.constraints
        if hasattr(constraint, "sqltext")
    ]
    assert any(
        all(value in check for value in ("draft", "pending_approval", "approved", "rejected", "archived"))
        for check in recommendation_checks
    )
    assert {index.name for index in recommendations.indexes} >= {
        "ix_funnel_recommendations_organization_id",
        "ix_funnel_recommendations_product_id",
        "ix_funnel_recommendations_approval_request_id",
    }

    assert DeliveryEmailEvent.__module__ == "app.models.delivery_email_event"


def test_delivery_access_mapping_matches_live_v5_catalog():
    access = DeliveryAccess.__table__
    assert set(access.c.keys()) == {
        "id",
        "organization_id",
        "order_id",
        "product_id",
        "order_item_id",
        "asset_id",
        "delivery_asset_id",
        "contact_id",
        "access_token_hash",
        "status",
        "expires_at",
        "first_accessed_at",
        "last_accessed_at",
        "first_opened_at",
        "last_opened_at",
        "download_count",
        "open_count",
        "max_downloads",
        "metadata_json",
        "created_at",
        "updated_at",
    }

    assert isinstance(access.c.id.type, PG_UUID)
    assert access.c.first_opened_at.type.timezone is True
    assert access.c.last_opened_at.type.timezone is True
    assert access.c.open_count.nullable is False
    assert str(access.c.open_count.server_default.arg) == "0"
    assert access.c.status.server_default is None
    assert access.c.download_count.server_default is None
    assert isinstance(access.c.metadata_json.type, JSONB)
    assert access.c.metadata_json.nullable is True

    order_item_fk = next(iter(access.c.order_item_id.foreign_keys))
    assert order_item_fk.target_fullname == "funnel_order_items.id"
    assert order_item_fk.constraint.name == "fk_delivery_accesses_order_item_id"
    assert access.c.asset_id is not access.c.delivery_asset_id
    assert next(iter(access.c.asset_id.foreign_keys)).target_fullname == "delivery_assets.id"
    delivery_asset_fk = next(iter(access.c.delivery_asset_id.foreign_keys))
    assert delivery_asset_fk.target_fullname == "delivery_assets.id"
    assert delivery_asset_fk.constraint.name == "fk_delivery_accesses_delivery_asset_id"

    token_index = next(
        index for index in access.indexes if index.name == "ix_delivery_access_token_hash"
    )
    assert token_index.unique is True
    assert [column.name for column in token_index.columns] == ["access_token_hash"]
    assert "IS NOT NULL" in str(token_index.dialect_options["postgresql"]["where"]).upper()
    assert "IS NOT NULL" in str(token_index.dialect_options["sqlite"]["where"]).upper()
    index_names = {index.name for index in access.indexes}
    assert {
        "ix_delivery_accesses_order_item_id",
        "ix_delivery_accesses_delivery_asset_id",
        "ix_delivery_accesses_asset_id",
        "ix_delivery_accesses_contact_id",
        "ix_delivery_accesses_order_id",
        "ix_delivery_accesses_organization_id",
        "ix_delivery_accesses_product_id",
    } <= index_names

    status_check = next(
        constraint
        for constraint in access.constraints
        if constraint.name == "ck_delivery_access_status"
    )
    assert all(
        status in str(status_check.sqltext)
        for status in ("active", "expired", "revoked")
    )


def test_recommendation_schemas_match_api_route_fields():
    create = FunnelRecommendationCreate(
        recommendation_type="checkout",
        recommended_action="Review checkout completion",
        bottleneck="checkout drop-off",
        expected_impact="Improve paid conversion",
        confidence="medium",
        effort="low",
        risk="low",
        reasoning="Observed incomplete checkouts",
        draft_content="Draft only",
        metadata_json={"source": "test"},
    )
    assert create.recommendation_type == "checkout"
    assert create.metadata_json == {"source": "test"}

    read = FunnelRecommendationRead(
        id=uuid4(),
        product_id=uuid4(),
        organization_id=uuid4(),
        recommendation_type=create.recommendation_type,
        bottleneck=create.bottleneck,
        recommended_action=create.recommended_action,
        expected_impact=create.expected_impact,
        confidence=create.confidence,
        effort=create.effort,
        risk=create.risk,
        reasoning=create.reasoning,
        draft_content=create.draft_content,
        rollback_note=None,
        approval_request_id=None,
        status="draft",
        created_at="2026-10-05T00:00:00Z",
        updated_at="2026-10-05T00:00:00Z",
    )
    assert read.status == "draft"


def test_delivery_access_public_schema_serializes_exact_route_fields():
    response = DeliveryAccessPublic(
        product_name="Guide",
        asset_title="PDF",
        status="active",
        is_opened=True,
        opened_at="2026-10-05T00:00:00Z",
    )
    assert response.model_dump() == {
        "product_name": "Guide",
        "asset_title": "PDF",
        "status": "active",
        "is_opened": True,
        "opened_at": response.opened_at,
    }


@pytest.mark.asyncio
async def test_public_lead_magnet_maps_persisted_name_and_promise():
    from app.api import funnel as funnel_api

    organization_id = uuid4()
    magnet = SimpleNamespace(
        slug="public-guide",
        name="Public guide",
        promise="A short practical guide",
    )
    with patch(
        "app.api.funnel.lead_magnet_service.get_by_slug",
        new=AsyncMock(return_value=magnet),
    ) as get_by_slug:
        response = await funnel_api.get_lead_magnet_public(
            "public-guide",
            auth=SimpleNamespace(organization_id=organization_id),
        )

    assert response == LeadMagnetPublic(
        slug="public-guide",
        title="Public guide",
        description="A short practical guide",
    )
    get_by_slug.assert_awaited_once_with("public-guide", organization_id, db=None)
