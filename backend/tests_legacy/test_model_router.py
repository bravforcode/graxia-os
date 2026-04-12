from app.core.model_router import (
    ModelPricing,
    ModelTierConfig,
    RouterConfig,
    route_task,
)


def _router() -> RouterConfig:
    return RouterConfig(
        cheap=ModelTierConfig(
            model="cheap-model",
            max_tokens=300,
            pricing=ModelPricing(input_cost_per_1m=0.10, output_cost_per_1m=0.20),
        ),
        mid=ModelTierConfig(
            model="mid-model",
            max_tokens=800,
            pricing=ModelPricing(input_cost_per_1m=1.00, output_cost_per_1m=2.00),
        ),
        high=ModelTierConfig(
            model="high-model",
            max_tokens=1600,
            pricing=ModelPricing(input_cost_per_1m=5.00, output_cost_per_1m=10.00),
        ),
        simple_max_complexity=2,
        medium_max_complexity=6,
        max_single_call_cost_usd=0.02,
        routing_enabled=True,
    )


def test_classification_routes_to_cheap_tier_by_default():
    decision = route_task("classification", router=_router())

    assert decision.model == "cheap-model"
    assert decision.tier == "cheap"
    assert decision.budget_tag == "low"
    assert decision.max_tokens == 300


def test_complex_proposal_stays_on_high_tier():
    decision = route_task(
        "proposal",
        requested_max_tokens=2000,
        complexity=9,
        router=_router(),
    )

    assert decision.model == "high-model"
    assert decision.tier == "high"
    assert decision.max_tokens == 1600


def test_budget_guardrail_flags_expensive_routes():
    decision = route_task(
        "proposal",
        requested_max_tokens=1600,
        complexity=9,
        router=_router(),
    )

    assert decision.estimated_max_cost_usd > 0.02
    assert decision.budget_exceeded is True


def test_complexity_can_upgrade_mid_tier_work():
    decision = route_task(
        "short_draft",
        requested_max_tokens=600,
        complexity=7,
        router=_router(),
    )

    assert decision.model == "high-model"
    assert decision.tier == "high"
