import hashlib
import logging
from datetime import UTC
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

ProfileData = dict[str, Any]
ProjectSummary = dict[str, Any]
ScoreWeights = dict[str, float]


class WeightHistoryEntry(TypedDict):
    id: str
    version: int
    weights: ScoreWeights | None
    previous_weights: ScoreWeights | None
    changed_by: str | None
    change_reason: str | None
    confidence_at_change: float | None
    data_points_analyzed: int | None
    is_current: bool | None
    applied_at: str | None
    rolled_back_at: str | None


class WeightApplyResult(TypedDict):
    version: int
    weights: ScoreWeights | None
    changed_by: str | None
    change_reason: str | None


class WeightRollbackResult(TypedDict):
    restored_version: int
    weights: ScoreWeights | None


class CognitiveDefaults(TypedDict):
    default_energy: int
    default_stress: int
    default_available_hours: int


DEFAULT_COGNITIVE_DEFAULTS: CognitiveDefaults = {
    "default_energy": 7,
    "default_stress": 3,
    "default_available_hours": 25,
}

_profile_cache: ProfileData | None = None


def _profile_section(value: Any) -> ProfileData:
    return cast(ProfileData, value) if isinstance(value, dict) else {}


def _profile_list(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value)


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    return [_string(item) for item in _profile_list(value) if _string(item)]


def _weight_map(value: Any) -> ScoreWeights | None:
    if not isinstance(value, dict):
        return None

    raw_weights = cast(dict[Any, Any], value)
    weights: ScoreWeights = {}
    for key, raw_value in raw_weights.items():
        try:
            weights[str(key)] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return weights


def _resolve_profile_path() -> Path:
    candidates = [
        Path(settings.IDENTITY_PATH),
        Path("identity/profile.yaml"),
        Path(__file__).resolve().parents[3] / "identity/profile.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _load_profile() -> ProfileData:
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache

    path = _resolve_profile_path()
    with open(path, encoding="utf-8") as file_handle:
        loaded = yaml.safe_load(file_handle)

    if not isinstance(loaded, dict):
        raise ValueError(f"Identity profile must be a mapping, got {type(loaded).__name__}")

    _profile_cache = cast(ProfileData, loaded)
    logger.info("Identity loaded from %s", path)
    return _profile_cache


class IdentityCore:
    def reload(self) -> None:
        global _profile_cache
        _profile_cache = None
        _load_profile()

    def get_profile(self) -> ProfileData:
        return _load_profile()

    def get_agent_context(self) -> str:
        profile = self.get_profile()
        personal = _profile_section(profile.get("personal"))
        current_status = _profile_section(profile.get("current_status"))
        goals = _profile_section(profile.get("goals"))
        skills_section = _profile_section(profile.get("skills"))
        target_clients = _profile_section(profile.get("target_clients"))
        target_competitions = _profile_section(profile.get("target_competitions"))
        financial = _profile_section(profile.get("financial"))
        constraints = _profile_section(profile.get("constraints"))

        technical_skills = [
            _string(_profile_section(skill).get("name"))
            for skill in _profile_list(skills_section.get("technical"))[:5]
        ]
        technical_skills = [skill for skill in technical_skills if skill]
        comp_types = _string_list(target_competitions.get("types"))
        comp_focus = _string_list(target_competitions.get("focus_areas"))[:3]
        hard_limits = _string_list(constraints.get("hard_limits"))[:3]

        return (
            f"User: {_string(personal.get('name'))}, {_string(current_status.get('role'))}, Bangkok Thailand.\n"
            f"Current positioning: {_string(current_status.get('current_positioning'))}\n"
            f"Goals: {_string(goals.get('north_star'))}\n"
            f"Skills: {', '.join(technical_skills)}\n"
            f"Target clients: {_string(target_clients.get('ideal_client_description'))}\n"
            f"Competition focus: {', '.join(comp_types[:3])} in {', '.join(comp_focus)}\n"
            f"Financial target: {_integer(financial.get('monthly_revenue_target_thb'), 0)} THB/month\n"
            f"Key constraints: {'; '.join(hard_limits)}"
        )

    def get_context_for_audience(self, audience: str) -> str:
        profile = self.get_profile()
        personal = _profile_section(profile.get("personal"))
        current_status = _profile_section(profile.get("current_status"))
        target_clients = _profile_section(profile.get("target_clients"))
        financial = _profile_section(profile.get("financial"))
        voice_and_tone = _profile_section(profile.get("voice_and_tone"))
        target_competitions = _profile_section(profile.get("target_competitions"))

        name = _string(personal.get("name"))
        if audience == "freelance_client":
            return (
                f"Developer: {name}, Bangkok.\n"
                f"Bio: {_string(personal.get('bio_short_en'))}\n"
                f"Ideal for: {_string(target_clients.get('ideal_client_description'))}\n"
                f"Min project: {_integer(financial.get('minimum_project_size_thb'), 0)} THB\n"
                f"Voice: {_string(voice_and_tone.get('english_style'))}"
            )

        if audience == "competition_judge":
            projects = self.get_project_summaries()
            proj_lines = "\n".join(
                f"- {_string(project.get('name'))}: {_string(project.get('tagline'))}"
                for project in projects
            )
            return (
                f"Competitor: {name}, {_string(current_status.get('year'))} {_string(current_status.get('major'))} @ {_string(current_status.get('university'))}.\n"
                f"Bio: {_string(personal.get('bio_short_en'))}\n"
                f"Projects:\n{proj_lines}\n"
                f"Focus: {', '.join(_string_list(target_competitions.get('focus_areas'))[:4])}"
            )

        return self.get_agent_context()

    def get_voice_instructions(self) -> str:
        voice_and_tone = _profile_section(self.get_profile().get("voice_and_tone"))
        phrases_to_avoid = _string_list(voice_and_tone.get("phrases_to_avoid"))[:5]
        avoid = ", ".join(f'"{phrase}"' for phrase in phrases_to_avoid)
        return (
            f"English style: {_string(voice_and_tone.get('english_style'))}\n"
            f"Thai style: {_string(voice_and_tone.get('thai_style'))}\n"
            f"Never use: {avoid}\n"
            f"Sample English:\n{_string(voice_and_tone.get('sample_english_message'))}\n"
            f"Sample Thai:\n{_string(voice_and_tone.get('sample_thai_message'))}"
        )

    async def get_scoring_weights(self) -> ScoreWeights:
        default_weights = _weight_map(self.get_profile().get("scoring_weights")) or {}
        try:
            from sqlalchemy import desc, select

            from app.database import AsyncSessionLocal
            from app.models.scoring_weight_history import ScoringWeightHistory

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ScoringWeightHistory)
                    .where(ScoringWeightHistory.is_current.is_(True))
                    .order_by(desc(ScoringWeightHistory.version))
                    .limit(1)
                )
                current = result.scalar_one_or_none()
                current_weights = (
                    _weight_map(getattr(current, "weights", None))
                    if current is not None
                    else None
                )
                if current_weights:
                    return current_weights
        except Exception as exc:
            logger.warning("Falling back to profile weights: %s", exc)
        return default_weights

    async def get_weight_history(self, limit: int = 10) -> list[WeightHistoryEntry]:
        try:
            from sqlalchemy import desc, select

            from app.database import AsyncSessionLocal
            from app.models.scoring_weight_history import ScoringWeightHistory

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ScoringWeightHistory)
                    .order_by(desc(ScoringWeightHistory.version))
                    .limit(limit)
                )
                rows = list(result.scalars().all())
                history: list[WeightHistoryEntry] = []
                for row in rows:
                    confidence_at_change = getattr(row, "confidence_at_change", None)
                    applied_at = cast(Any, getattr(row, "applied_at", None))
                    rolled_back_at = cast(Any, getattr(row, "rolled_back_at", None))
                    history.append(
                        {
                            "id": str(row.id),
                            "version": _integer(getattr(row, "version", 0), 0),
                            "weights": _weight_map(getattr(row, "weights", None)),
                            "previous_weights": _weight_map(
                                getattr(row, "previous_weights", None)
                            ),
                            "changed_by": cast(str | None, getattr(row, "changed_by", None)),
                            "change_reason": cast(
                                str | None, getattr(row, "change_reason", None)
                            ),
                            "confidence_at_change": float(confidence_at_change)
                            if confidence_at_change is not None
                            else None,
                            "data_points_analyzed": cast(
                                int | None, getattr(row, "data_points_analyzed", None)
                            ),
                            "is_current": cast(
                                bool | None, getattr(row, "is_current", None)
                            ),
                            "applied_at": applied_at.isoformat()
                            if applied_at is not None
                            else None,
                            "rolled_back_at": rolled_back_at.isoformat()
                            if rolled_back_at is not None
                            else None,
                        }
                    )
                return history
        except Exception as exc:
            logger.warning("Failed to read weight history: %s", exc)
            return []

    async def apply_scoring_weights(
        self,
        new_weights: ScoreWeights,
        changed_by: str,
        change_reason: str,
        confidence_at_change: float | None = None,
        data_points_analyzed: int | None = None,
    ) -> WeightApplyResult:
        from sqlalchemy import desc, select

        from app.database import AsyncSessionLocal
        from app.models.scoring_weight_history import ScoringWeightHistory

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScoringWeightHistory)
                .order_by(desc(ScoringWeightHistory.version))
                .limit(1)
            )
            current = result.scalar_one_or_none()
            current_version = _integer(getattr(current, "version", 0), 0) if current else 0
            next_version = current_version + 1

            if current is not None:
                current.is_current = False

            row = ScoringWeightHistory(
                version=next_version,
                weights=new_weights,
                previous_weights=getattr(current, "weights", None) if current else None,
                changed_by=changed_by,
                change_reason=change_reason,
                confidence_at_change=confidence_at_change,
                data_points_analyzed=data_points_analyzed,
                is_current=True,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return {
                "version": _integer(getattr(row, "version", 0), 0),
                "weights": _weight_map(getattr(row, "weights", None)),
                "changed_by": cast(str | None, getattr(row, "changed_by", None)),
                "change_reason": cast(str | None, getattr(row, "change_reason", None)),
            }

    async def rollback_scoring_weights(self) -> WeightRollbackResult | None:
        from datetime import datetime

        from sqlalchemy import desc, select

        from app.database import AsyncSessionLocal
        from app.models.audit import AuditLog
        from app.models.scoring_weight_history import ScoringWeightHistory

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScoringWeightHistory)
                .order_by(desc(ScoringWeightHistory.version))
                .limit(2)
            )
            rows = list(result.scalars().all())
            if len(rows) < 2:
                return None

            current, previous = rows[0], rows[1]
            restored_weights = _weight_map(getattr(previous, "weights", None))

            current.is_current = False
            previous.is_current = True
            previous.rolled_back_at = None
            current.rolled_back_at = datetime.now(UTC)
            db.add(
                AuditLog(
                    action="scoring_weights.rollback",
                    details={
                        "from_version": _integer(getattr(current, "version", 0), 0),
                        "to_version": _integer(getattr(previous, "version", 0), 0),
                        "restored_weights": restored_weights,
                    },
                    triggered_by="identity_core",
                    success=True,
                )
            )
            await db.commit()

            return {
                "restored_version": _integer(getattr(previous, "version", 0), 0),
                "weights": restored_weights,
            }

    def get_constraint_list(self) -> list[str]:
        constraints = _profile_section(self.get_profile().get("constraints"))
        operational_limits = _profile_section(constraints.get("operational_limits"))
        return _string_list(constraints.get("hard_limits")) + list(operational_limits.keys())

    def get_target_client_description(self) -> str:
        target_clients = _profile_section(self.get_profile().get("target_clients"))
        return _string(target_clients.get("ideal_client_description"))

    def get_project_summaries(self, best_for: str | None = None) -> list[ProjectSummary]:
        projects = [
            cast(ProjectSummary, project)
            for project in _profile_list(self.get_profile().get("projects"))
            if isinstance(project, dict)
        ]
        if best_for:
            return [
                project
                for project in projects
                if best_for in _string_list(project.get("best_for"))
            ]
        return projects

    def get_cognitive_defaults(self) -> CognitiveDefaults:
        defaults = _profile_section(self.get_profile().get("cognitive_defaults"))
        return {
            "default_energy": _integer(
                defaults.get("default_energy"), DEFAULT_COGNITIVE_DEFAULTS["default_energy"]
            ),
            "default_stress": _integer(
                defaults.get("default_stress"), DEFAULT_COGNITIVE_DEFAULTS["default_stress"]
            ),
            "default_available_hours": _integer(
                defaults.get("default_available_hours"),
                DEFAULT_COGNITIVE_DEFAULTS["default_available_hours"],
            ),
        }

    async def maybe_snapshot_identity(self) -> None:
        try:
            from datetime import date

            from sqlalchemy import desc, select

            from app.database import AsyncSessionLocal
            from app.models.identity_snapshot import IdentitySnapshot

            profile_path = _resolve_profile_path()
            current_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()

            async with AsyncSessionLocal() as db:
                last = await db.execute(
                    select(IdentitySnapshot)
                    .order_by(desc(IdentitySnapshot.created_at))
                    .limit(1)
                )
                last_snap = last.scalar_one_or_none()
                last_profile_hash = (
                    cast(str | None, getattr(last_snap, "profile_hash", None))
                    if last_snap is not None
                    else None
                )
                if last_profile_hash == current_hash:
                    return

                profile = self.get_profile()
                current_status = _profile_section(profile.get("current_status"))
                personal = _profile_section(profile.get("personal"))
                skills_section = _profile_section(profile.get("skills"))
                key_skills = [
                    _string(_profile_section(skill).get("name"))
                    for skill in _profile_list(skills_section.get("technical"))[:5]
                ]
                key_skills = [skill for skill in key_skills if skill]
                positioning_label = _string(current_status.get("current_positioning"))
                primary_narrative = _string(personal.get("bio_short_en"))

                snapshot = IdentitySnapshot(
                    snapshot_date=date.today(),
                    positioning_label=positioning_label,
                    profile_hash=current_hash,
                    key_skills=key_skills,
                    primary_narrative=primary_narrative,
                    change_trigger="monthly_snapshot",
                )
                db.add(snapshot)
                await db.commit()

                try:
                    from app.telegram_bot.bot import send_message

                    await send_message(
                        f"📸 Identity snapshot saved. Positioning: {positioning_label}"
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.error("Identity snapshot failed: %s", exc)


identity = IdentityCore()
