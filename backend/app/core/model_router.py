from dataclasses import dataclass

from app.config import Settings, settings


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0


@dataclass(frozen=True)
class ModelTierConfig:
    model: str
    max_tokens: int
    pricing: ModelPricing


@dataclass(frozen=True)
class RouterConfig:
    local: ModelTierConfig | None
    cheap: ModelTierConfig
    mid: ModelTierConfig
    high: ModelTierConfig
    simple_max_complexity: int
    medium_max_complexity: int
    max_single_call_cost_usd: float
    routing_enabled: bool = True


@dataclass(frozen=True)
class RoutingDecision:
    task_class: str
    model: str
    tier: str
    budget_tag: str
    max_tokens: int
    estimated_max_cost_usd: float
    budget_exceeded: bool


_TASK_DEFAULTS: dict[str, tuple[str, str, int]] = {
    "classification": ("cheap", "low", 300),
    "triage": ("cheap", "low", 400),
    "short_summary": ("cheap", "low", 450),
    "analysis": ("mid", "standard", 800),
    "short_draft": ("mid", "standard", 700),
    "meeting_summary": ("mid", "standard", 800),
    "proposal": ("high", "high", 1600),
    "strategy": ("high", "high", 1200),
}

_TIER_ORDER = {"local": 0, "cheap": 1, "mid": 2, "high": 3}


def build_router_config(app_settings: Settings = settings) -> RouterConfig:
    return RouterConfig(
        local=ModelTierConfig(
            model="hermes-local",
            max_tokens=8000,
            pricing=ModelPricing(0.0, 0.0)
        ) if getattr(app_settings, "HERMES_URL", None) else None,
        cheap=ModelTierConfig(
            model=app_settings.CHEAP_MODEL,
            max_tokens=app_settings.CHEAP_MODEL_MAX_TOKENS,
            pricing=ModelPricing(
                input_cost_per_1m=app_settings.CHEAP_MODEL_INPUT_COST_PER_1M,
                output_cost_per_1m=app_settings.CHEAP_MODEL_OUTPUT_COST_PER_1M,
            ),
        ),
        mid=ModelTierConfig(
            model=app_settings.MID_MODEL,
            max_tokens=app_settings.MID_MODEL_MAX_TOKENS,
            pricing=ModelPricing(
                input_cost_per_1m=app_settings.MID_MODEL_INPUT_COST_PER_1M,
                output_cost_per_1m=app_settings.MID_MODEL_OUTPUT_COST_PER_1M,
            ),
        ),
        high=ModelTierConfig(
            model=app_settings.HIGH_QUALITY_MODEL,
            max_tokens=app_settings.HIGH_QUALITY_MODEL_MAX_TOKENS,
            pricing=ModelPricing(
                input_cost_per_1m=app_settings.HIGH_QUALITY_MODEL_INPUT_COST_PER_1M,
                output_cost_per_1m=app_settings.HIGH_QUALITY_MODEL_OUTPUT_COST_PER_1M,
            ),
        ),
        simple_max_complexity=app_settings.ROUTER_SIMPLE_MAX_COMPLEXITY,
        medium_max_complexity=app_settings.ROUTER_MEDIUM_MAX_COMPLEXITY,
        max_single_call_cost_usd=app_settings.MAX_SINGLE_LLM_CALL_COST_USD,
        routing_enabled=app_settings.MODEL_ROUTING_ENABLED,
    )


def route_task(
    task_class: str,
    requested_max_tokens: int | None = None,
    complexity: int | None = None,
    router: RouterConfig | None = None,
) -> RoutingDecision:
    router = router or build_router_config()
    base_tier, budget_tag, default_tokens = _TASK_DEFAULTS.get(
        task_class,
        ("mid", "standard", 800),
    )

    target_tier = base_tier
    if router.local is not None and getattr(settings, "HERMES_URL", None) and getattr(settings, "OPENCLAW_DEFAULT_MODEL", "") == "local-gateway":
        target_tier = "local"
    elif complexity is not None:
        complexity_tier = _tier_from_complexity(complexity, router)
        if _TIER_ORDER[complexity_tier] > _TIER_ORDER[target_tier]:
            target_tier = complexity_tier

    tier_config = getattr(router, target_tier)
    desired_tokens = requested_max_tokens or default_tokens
    max_tokens = min(desired_tokens, tier_config.max_tokens)

    estimated_max_cost_usd = _estimate_cost_usd(
        tier_config=tier_config,
        input_tokens=max_tokens,
        output_tokens=max_tokens,
    )
    budget_exceeded = estimated_max_cost_usd > router.max_single_call_cost_usd

    return RoutingDecision(
        task_class=task_class,
        model=tier_config.model,
        tier=target_tier,
        budget_tag=budget_tag,
        max_tokens=max_tokens,
        estimated_max_cost_usd=estimated_max_cost_usd,
        budget_exceeded=budget_exceeded,
    )


AGENT_MODEL_TIERS = {
    "orchestrator": "cheap",
    "classifier": "cheap", 
    "drafter": "high",
    "researcher": "cheap",
    "briefer": "mid",
    "scorer": "mid",
}

def route_for_agent(agent_name: str) -> str:
    return AGENT_MODEL_TIERS.get(agent_name, "mid")

def _tier_from_complexity(complexity: int, router: RouterConfig) -> str:
    if complexity <= router.simple_max_complexity:
        return "cheap"
    if complexity <= router.medium_max_complexity:
        return "mid"
    return "high"


def _estimate_cost_usd(
    tier_config: ModelTierConfig,
    input_tokens: int,
    output_tokens: int,
) -> float:
    input_cost = (input_tokens / 1_000_000) * tier_config.pricing.input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * tier_config.pricing.output_cost_per_1m
    return round(input_cost + output_cost, 6)
