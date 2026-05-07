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


_TIER_ORDER = {"local": 0, "cheap": 1, "mid": 2, "high": 3}


def _parse_task_defaults(config_str: str) -> dict[str, tuple[str, str, int]]:
    """
    Parse task defaults from configuration string.
    
    Format: "task1:tier,budget,tokens;task2:tier,budget,tokens;..."
    Example: "classification:cheap,low,300;analysis:mid,standard,800"
    
    Returns:
        Dictionary mapping task_class to (tier, budget_tag, default_tokens)
    """
    defaults = {}
    for entry in config_str.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        try:
            task_class, values = entry.split(":", 1)
            tier, budget_tag, tokens_str = values.split(",")
            defaults[task_class.strip()] = (
                tier.strip(),
                budget_tag.strip(),
                int(tokens_str.strip())
            )
        except (ValueError, IndexError):
            # Skip malformed entries
            continue
    return defaults


def _get_task_defaults() -> dict[str, tuple[str, str, int]]:
    """
    Get task defaults from configuration or use hardcoded fallback.
    
    Returns:
        Dictionary mapping task_class to (tier, budget_tag, default_tokens)
    """
    try:
        from app.config import settings
        if hasattr(settings, "ROUTER_TASK_DEFAULTS") and settings.ROUTER_TASK_DEFAULTS:
            return _parse_task_defaults(settings.ROUTER_TASK_DEFAULTS)
    except ImportError:
        pass
    
    # Fallback to hardcoded defaults
    return {
        "classification": ("cheap", "low", 300),
        "triage": ("cheap", "low", 400),
        "short_summary": ("cheap", "low", 450),
        "analysis": ("mid", "standard", 800),
        "short_draft": ("mid", "standard", 700),
        "meeting_summary": ("mid", "standard", 800),
        "proposal": ("high", "high", 1600),
        "strategy": ("high", "high", 1200),
    }


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
    """
    Route a task to the appropriate model tier based on task class and complexity.
    
    Args:
        task_class: Task classification (e.g., "classification", "analysis", "proposal")
        requested_max_tokens: Requested maximum output tokens (overrides default)
        complexity: Task complexity score (0-10, higher = more complex)
        router: Router configuration (defaults to global config)
    
    Returns:
        RoutingDecision with model, tier, cost estimate, and budget status
    
    Cost Estimation:
        Uses realistic input/output ratio based on task class:
        - Classification/Triage: 60% input, 40% output (short responses)
        - Analysis/Summary: 50% input, 50% output (balanced)
        - Drafts/Proposals: 30% input, 70% output (long responses)
        
        This provides more accurate cost estimates than assuming symmetric usage.
    """
    router = router or build_router_config()
    task_defaults = _get_task_defaults()
    base_tier, budget_tag, default_tokens = task_defaults.get(
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

    # Estimate realistic input/output ratio based on task class
    input_ratio, output_ratio = _get_task_token_ratio(task_class)
    estimated_input_tokens = int(max_tokens * input_ratio)
    estimated_output_tokens = int(max_tokens * output_ratio)

    estimated_max_cost_usd = _estimate_cost_usd(
        tier_config=tier_config,
        input_tokens=estimated_input_tokens,
        output_tokens=estimated_output_tokens,
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
    """Map complexity score to model tier."""
    if complexity <= router.simple_max_complexity:
        return "cheap"
    if complexity <= router.medium_max_complexity:
        return "mid"
    return "high"


def _get_task_token_ratio(task_class: str) -> tuple[float, float]:
    """
    Get realistic input/output token ratio for a task class.
    
    Returns:
        Tuple of (input_ratio, output_ratio) where ratios sum to 1.0
    
    Rationale:
        - Classification/Triage: Short responses, mostly input context
        - Analysis/Summary: Balanced input and output
        - Drafts/Proposals: Long responses, less input context
    
    Examples:
        - classification: (0.7, 0.3) - 70% input, 30% output
        - analysis: (0.5, 0.5) - 50% input, 50% output
        - proposal: (0.3, 0.7) - 30% input, 70% output
    """
    # Short response tasks (classification, triage)
    if task_class in ("classification", "triage"):
        return (0.7, 0.3)  # 70% input, 30% output
    
    # Short generation tasks (short summaries, short drafts)
    if task_class in ("short_summary", "short_draft"):
        return (0.6, 0.4)  # 60% input, 40% output
    
    # Balanced tasks (analysis, meeting summaries)
    if task_class in ("analysis", "meeting_summary"):
        return (0.5, 0.5)  # 50% input, 50% output
    
    # Long generation tasks (proposals, strategies)
    if task_class in ("proposal", "strategy"):
        return (0.3, 0.7)  # 30% input, 70% output
    
    # Default: balanced ratio
    return (0.5, 0.5)


def _estimate_cost_usd(
    tier_config: ModelTierConfig,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Estimate cost in USD for a model call.
    
    Args:
        tier_config: Model tier configuration with pricing
        input_tokens: Estimated input tokens (prompt + context)
        output_tokens: Estimated output tokens (completion)
    
    Returns:
        Estimated cost in USD (rounded to 6 decimal places)
    
    Note:
        This is an estimate. Actual costs depend on:
        - Actual token counts from tokenizer
        - Model-specific pricing (may change)
        - Caching (some providers cache prompts)
    """
    input_cost = (input_tokens / 1_000_000) * tier_config.pricing.input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * tier_config.pricing.output_cost_per_1m
    return round(input_cost + output_cost, 6)
