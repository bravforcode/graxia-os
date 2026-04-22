import logging
from pathlib import Path

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


def wire_event_handlers() -> None:
    """Register the default event-driven agent pipeline.

    This is intentionally idempotent so startup and tests can call it repeatedly.
    """
    from app.agents.briefer import briefer_agent
    from app.agents.compound_engine import compound_engine
    from app.agents.decision_engine import decision_engine
    from app.agents.drafter import drafter_agent
    from app.agents.failure_analysis import failure_analysis
    from app.agents.learning_engine import learning_engine
    from app.agents.obsidian_sync import obsidian_sync_agent
    from app.agents.playbook_capture import playbook_capture
    from app.agents.scorer import scorer_agent
    from app.api.approvals import create_approval_from_event
    from app.core.event_bus import event_bus

    async def handle_cog_suggestion(payload: dict):
        """Route COG weight suggestions through the approval queue (never auto-apply)."""
        await create_approval_from_event(
            action_type="scoring_weight_update",
            what_action=f"Update scoring weights: {payload.get('suggested_weights')}",
            why_now=payload.get("reasoning", ""),
            confidence=payload.get("confidence", 0.5),
            metadata=payload,
        )

    subscriptions = [
        ("opportunity.found", scorer_agent.handle_new_opportunity),
        ("opportunity.scored", decision_engine.handle_scored_opportunity),
        ("opportunity.decided", drafter_agent.handle_decided_opportunity),
        ("opportunity.decided", briefer_agent.handle_decided_opportunity),
        ("draft.approved", briefer_agent.handle_draft_approved),
        ("scraper.failed", briefer_agent.handle_scraper_alert),
        ("cost.budget_warning", briefer_agent.handle_cost_alert),
        ("ai.cost_limit_reached", briefer_agent.handle_cost_alert),
        ("submission.sent", compound_engine.handle_submission_sent),
        ("submission.won", learning_engine.handle_win),
        ("submission.won", playbook_capture.handle_win),
        ("submission.won", compound_engine.handle_win),
        ("submission.lost", learning_engine.handle_loss),
        ("submission.lost", failure_analysis.handle_loss),
        ("cog.evolution_suggested", handle_cog_suggestion),
    ]

    if getattr(settings, "OBSIDIAN_AUTO_SYNC_ENABLED", True):
        subscriptions.extend(
            [
                ("opportunity.found", obsidian_sync_agent.handle_opportunity_found),
                ("opportunity.scored", obsidian_sync_agent.handle_opportunity_found),
                ("opportunity.decided", obsidian_sync_agent.handle_opportunity_found),
                ("submission.sent", obsidian_sync_agent.handle_submission_sent),
                ("submission.won", obsidian_sync_agent.handle_submission_sent),
                ("submission.lost", obsidian_sync_agent.handle_submission_sent),
                ("contact.created", obsidian_sync_agent.handle_contact_created),
                ("task.created", obsidian_sync_agent.handle_task_created),
                ("task.updated", obsidian_sync_agent.handle_task_created),
                ("task.completed", obsidian_sync_agent.handle_task_created),
                ("knowledge.captured", obsidian_sync_agent.handle_knowledge_captured),
            ]
        )

    for event_name, handler in subscriptions:
        event_bus.subscribe(event_name, handler)


async def seed_admin_user() -> None:
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.auth import get_password_hash
    from app.database import AsyncSessionLocal
    from app.models.user import User

    email = (getattr(settings, "GOOGLE_WORKSPACE_EMAIL", "") or "").strip().lower()
    if not email:
        email = (getattr(settings, "ADMIN_DEFAULT_EMAIL", "") or "").strip().lower()
    if not email:
        email = "admin@local"

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            if existing.role != "admin":
                existing.role = "admin"
                existing.updated_at = datetime.now(timezone.utc)
                await db.commit()
            return

        password = str(getattr(settings, "ADMIN_DEFAULT_PASSWORD", "changeme") or "changeme")
        now = datetime.now(timezone.utc)
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Admin",
            role="admin",
            is_active=True,
            totp_enabled=False,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.commit()
        logger.info("Seeded admin user: %s", email)


async def _send_telegram(msg: str) -> None:
    try:
        from app.telegram_bot.bot import send_message
        await send_message(msg)
    except Exception:
        pass


async def initialize_telegram_notifier() -> bool:
    """Initialize real-time Telegram notification service."""
    try:
        from app.core.telegram_notifier import telegram_notifier
        success = await telegram_notifier.initialize()
        if success:
            logger.info("Telegram notifier: Real-time notifications active")
        return success
    except Exception as e:
        logger.warning(f"Telegram notifier: Initialization failed: {e}")
        return False


async def check_system_ready() -> tuple[bool, str, list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    profile = None

    # ── 1. Profile completeness ──────────────────────────
    profile_candidates = [
        Path(settings.IDENTITY_PATH),
        Path("identity/profile.yaml"),
        Path(__file__).resolve().parents[3] / "identity/profile.yaml",
    ]
    profile_path = next(
        (candidate for candidate in profile_candidates if candidate.exists()),
        profile_candidates[-1],
    )
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = yaml.safe_load(f)
        name = profile.get("personal", {}).get("name", "")
        if "[YOUR" in name:
            issues.append("Profile: personal.name not filled in")
        north_star = profile.get("goals", {}).get("north_star", "")
        if "[" in north_star:
            issues.append("Profile: goals.north_star not filled in")
        projects = profile.get("projects", [])
        if not projects:
            issues.append("Profile: no projects defined")
        sample_msg = profile.get("voice_and_tone", {}).get("sample_english_message", "")
        if "[PASTE" in sample_msg:
            issues.append("Profile: voice sample not filled in")
    except Exception as e:
        issues.append(f"Profile: cannot load profile.yaml — {e}")

    # ── 2. API keys ──────────────────────────────────────
    def add_external_readiness(message: str) -> None:
        if settings.STRICT_BOOTSTRAP:
            issues.append(message)
        else:
            warnings.append(message)

    # At least one LLM key required
    if not settings.HAS_REAL_OPENCLAW_KEY and not settings.HAS_REAL_GEMINI_KEY:
        add_external_readiness("API: Neither OPENCLAW_API_KEY nor GEMINI_API_KEY is set — AI features disabled")
    elif settings.HAS_REAL_OPENCLAW_KEY:
        logger.info("LLM: Using OpenClaw (Claude) as primary")
    else:
        logger.info("LLM: Using Gemini as primary (OpenClaw key not set)")
    if not settings.HAS_REAL_TELEGRAM_TOKEN:
        add_external_readiness("API: TELEGRAM_BOT_TOKEN not set or still placeholder")
    if not settings.HAS_REAL_TELEGRAM_CHAT_ID:
        add_external_readiness("API: TELEGRAM_CHAT_ID not set, placeholder, or non-numeric")
    if not settings.HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS:
        warnings.append(
            "Google Workspace not configured — inbox/calendar assistant features disabled"
        )

    # ── 3. Database ──────────────────────────────────────
    try:
        from sqlalchemy import inspect, text

        from app.database import AsyncSessionLocal, engine
        from app.models.scoring_weight_history import ScoringWeightHistory
        from app.models import Base

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            expected_tables = set(Base.metadata.tables.keys())

            def inspect_schema(sync_conn):
                inspector = inspect(sync_conn)
                table_names = set(inspector.get_table_names())
                missing_tables = sorted(expected_tables.difference(table_names))
                missing_columns: list[str] = []
                if not missing_tables:
                    for table_name, table in Base.metadata.tables.items():
                        db_columns = {
                            column["name"] for column in inspector.get_columns(table_name)
                        }
                        table_missing = [
                            column.name
                            for column in table.columns
                            if column.name not in db_columns
                        ]
                        if table_missing:
                            missing_columns.append(
                                f"{table_name}.{', '.join(table_missing[:5])}"
                            )
                return missing_tables, missing_columns

            missing_tables, missing_columns = await conn.run_sync(inspect_schema)

        if missing_tables:
            issues.append(
                f"Database: missing tables — {', '.join(missing_tables[:5])}"
                + ("..." if len(missing_tables) > 5 else "")
            )
        elif missing_columns:
            issues.append(
                f"Database: missing columns — {'; '.join(missing_columns[:3])}"
                + ("..." if len(missing_columns) > 3 else "")
            )

        if profile and not missing_tables and not missing_columns:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select

                result = await db.execute(select(ScoringWeightHistory).limit(1))
                existing = result.scalar_one_or_none()
                if existing is None:
                    db.add(
                        ScoringWeightHistory(
                            version=1,
                            weights=profile.get("scoring_weights", {}),
                            previous_weights=None,
                            changed_by="user",
                            change_reason="Initial weights from identity profile",
                            is_current=True,
                        )
                    )
                    await db.commit()
            if profile and "skill_profiles" in expected_tables:
                from app.core.career import ensure_skill_profiles_seeded

                await ensure_skill_profiles_seeded()
    except Exception as e:
        issues.append(f"Database: cannot connect — {e}")

    # ── 4. Degraded checks (warnings only) ───────────────
    if not settings.HAS_REAL_SERPAPI_KEY:
        warnings.append("SerpAPI not set — search limited to direct scraping")

    if settings.IS_SUPABASE_TRANSACTION_MODE:
        warnings.append(
            "Supabase transaction pooler detected on port 6543 — long-running backend/celery workloads are more stable on a Direct or Session pooler connection when available"
        )

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
    except Exception:
        warnings.append("Redis unavailable — caching and Celery tasks disabled")

    try:
        from pgvector.sqlalchemy import Vector
    except Exception:
        warnings.append("pgvector unavailable — vector features disabled")

    if issues:
        mode = "blocked"
        msg = "🚫 Personal OS BLOCKED — resolve these issues:\n" + "\n".join(f"• {i}" for i in issues)
        await _send_telegram(msg)
        return False, mode, issues

    if warnings:
        mode = "degraded"
        msg = f"⚠️ Personal OS running in degraded mode:\n" + "\n".join(f"• {w}" for w in warnings) + "\nCore features active."
        await _send_telegram(msg)
    else:
        mode = "full"
        await _send_telegram("✅ Personal OS v3 online. Ready to find your next win.")

    try:
        from app.agents.vault_indexer import vault_indexer_agent
        import asyncio
        asyncio.create_task(vault_indexer_agent.index_vault())
    except Exception as e:
        logger.error(f"Failed to start vault indexer: {e}")

    return True, mode, warnings
