import pytest

from app.config import Settings
from app.core.model_router import build_router_config, route_task


def openai_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "testing",
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_CHAT_MODEL": "account-model-test",
        "OPENAI_INPUT_PRICE_USD_PER_1M": 2.0,
        "OPENAI_OUTPUT_PRICE_USD_PER_1M": 4.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_openai_router_uses_only_explicit_model_and_documented_rates():
    router = build_router_config(openai_settings())

    assert router.cheap.model == "account-model-test"
    assert router.mid.model == "account-model-test"
    assert router.high.model == "account-model-test"
    assert router.cheap.pricing.input_cost_per_1m == 2.0
    assert router.cheap.pricing.output_cost_per_1m == 4.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"OPENAI_CHAT_MODEL": ""},
        {"OPENAI_INPUT_PRICE_USD_PER_1M": 0.0},
        {"OPENAI_OUTPUT_PRICE_USD_PER_1M": -1.0},
    ],
)
def test_openai_router_fails_closed_when_model_or_rate_is_missing(overrides):
    decision = route_task(
        "classification",
        requested_max_tokens=100,
        router=build_router_config(openai_settings(**overrides)),
        estimated_input_tokens=40,
    )

    assert decision.pricing_configured is False
    assert decision.budget_exceeded is True


def test_openai_router_enforces_point_one_dollar_worst_case_call_budget():
    settings = openai_settings(
        OPENAI_INPUT_PRICE_USD_PER_1M=1.0,
        OPENAI_OUTPUT_PRICE_USD_PER_1M=1.0,
        MAX_SINGLE_LLM_CALL_COST_USD=0.10,
    )
    decision = route_task(
        "classification",
        requested_max_tokens=500,
        router=build_router_config(settings),
        estimated_input_tokens=100_000,
    )

    assert decision.pricing_configured is True
    assert decision.estimated_max_cost_usd > 0.10
    assert decision.budget_exceeded is True


def test_openai_prompt_byte_upper_bound_includes_max_output_tokens():
    decision = route_task(
        "classification",
        requested_max_tokens=300,
        router=build_router_config(openai_settings()),
        estimated_input_tokens=100,
    )

    assert decision.estimated_max_cost_usd == pytest.approx(0.0014)
    assert decision.budget_exceeded is False


def test_openai_router_does_not_round_a_cost_over_the_cap_down_to_the_limit():
    settings = openai_settings(
        OPENAI_INPUT_PRICE_USD_PER_1M=1_000.004,
        OPENAI_OUTPUT_PRICE_USD_PER_1M=0.0001,
        MAX_SINGLE_LLM_CALL_COST_USD=0.10,
    )
    decision = route_task(
        "classification",
        requested_max_tokens=1,
        router=build_router_config(settings),
        estimated_input_tokens=100,
    )

    assert decision.estimated_max_cost_usd == 0.1
    assert decision.budget_exceeded is True
