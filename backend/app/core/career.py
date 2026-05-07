from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select

from app.core.control_plane import queue_approval_request
from app.core.identity import identity
from app.database import AsyncSessionLocal
from app.models.job_posting import JobPosting
from app.models.opportunity import Opportunity
from app.models.skill_profile import SkillProfile

logger = logging.getLogger(__name__)

LEVEL_WEIGHTS: dict[str, float] = {
    "beginner": 0.4,
    "intermediate": 0.7,
    "advanced": 0.9,
    "expert": 1.0,
}
GENERIC_SKILL_STOPWORDS = {
    "remote",
    "thailand",
    "bangkok",
    "project",
    "developer",
    "development",
    "job",
    "freelance",
    "contract",
    "full time",
    "part time",
}


@dataclass(frozen=True)
class SkillSeed:
    name: str
    normalized_name: str
    category: str
    level: str
    years_experience: float | None
    aliases: list[str]
    evidence: list[str]
    source: str = "identity_profile"


@dataclass(frozen=True)
class JobMatchResult:
    match_score: float
    matched_skills: list[str]
    skill_gap_list: list[str]
    fit_summary: str


def normalize_skill_name(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    raw = raw.replace("&", " and ")
    raw = raw.replace("+", " plus ")
    raw = raw.replace("/", " ")
    raw = raw.replace("-", " ")
    raw = re.sub(r"[()_,:;|]", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def _skill_level(raw_level: str | None) -> str:
    lowered = normalize_skill_name(raw_level)
    if lowered in LEVEL_WEIGHTS:
        return lowered
    return "intermediate"


def _split_skill_fragments(name: str) -> list[str]:
    without_parentheses = re.sub(r"\([^)]*\)", "", name).strip()
    fragments: list[str] = []
    if without_parentheses:
        fragments.append(without_parentheses)
        fragments.extend(part.strip() for part in without_parentheses.split("/") if part.strip())

    for block in re.findall(r"\(([^)]*)\)", name):
        fragments.extend(part.strip() for part in block.split("/") if part.strip())

    fragments.extend(part.strip() for part in name.split("/") if part.strip())
    fragments.append(name)
    return fragments


def build_skill_aliases(name: str) -> list[str]:
    aliases: list[str] = []
    for fragment in _split_skill_fragments(name):
        normalized = normalize_skill_name(fragment)
        if normalized and normalized not in aliases:
            aliases.append(normalized)
        condensed = normalized.replace(" ", "")
        if normalized and condensed and condensed != normalized and condensed not in aliases:
            aliases.append(condensed)
    return aliases


def _project_tech_aliases(profile: dict[str, Any]) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for project in profile.get("projects") or []:
        if not isinstance(project, dict):
            continue
        project_name = str(project.get("name") or "").strip()
        tech_stack = project.get("tech_stack") or []
        if not project_name or not isinstance(tech_stack, list):
            continue
        for tech in tech_stack:
            for alias in build_skill_aliases(str(tech)):
                evidence.setdefault(alias, []).append(project_name)
    return evidence


def extract_skill_seeds_from_profile(profile: dict[str, Any]) -> list[SkillSeed]:
    skills = profile.get("skills") or {}
    technical = skills.get("technical") or []
    soft = skills.get("soft") or []
    project_evidence = _project_tech_aliases(profile)

    seeds: list[SkillSeed] = []
    for raw_skill in technical:
        if not isinstance(raw_skill, dict):
            continue
        name = str(raw_skill.get("name") or "").strip()
        if not name:
            continue
        aliases = build_skill_aliases(name)
        normalized_name = aliases[0] if aliases else normalize_skill_name(name)
        evidence = sorted(
            {
                project
                for alias in aliases
                for project in project_evidence.get(alias, [])
            }
        )
        years = raw_skill.get("years")
        try:
            years_experience = float(years) if years is not None else None
        except (TypeError, ValueError):
            years_experience = None
        seeds.append(
            SkillSeed(
                name=name,
                normalized_name=normalized_name,
                category="technical",
                level=_skill_level(str(raw_skill.get("level") or "")),
                years_experience=years_experience,
                aliases=aliases,
                evidence=evidence,
            )
        )

    for raw_skill in soft:
        name = str(raw_skill or "").strip()
        if not name:
            continue
        normalized_name = normalize_skill_name(name)
        seeds.append(
            SkillSeed(
                name=name,
                normalized_name=normalized_name,
                category="soft",
                level="advanced",
                years_experience=None,
                aliases=[normalized_name] if normalized_name else [],
                evidence=[],
            )
        )

    return seeds


def _level_weight(level: str | None) -> float:
    return LEVEL_WEIGHTS.get(_skill_level(level), LEVEL_WEIGHTS["intermediate"])


def _coerce_skill_aliases(value: Any, fallback_name: str) -> list[str]:
    if isinstance(value, list):
        aliases = [normalize_skill_name(str(item)) for item in value if normalize_skill_name(str(item))]
        if aliases:
            return list(dict.fromkeys(aliases))
    return build_skill_aliases(fallback_name)


def _skill_signature(skill: Any) -> tuple[str, str, float, list[str]]:
    if isinstance(skill, SkillSeed):
        return (
            skill.name,
            skill.normalized_name,
            _level_weight(skill.level),
            list(skill.aliases),
        )

    name = str(getattr(skill, "name", "") or "").strip()
    normalized_name = str(getattr(skill, "normalized_name", "") or "").strip() or normalize_skill_name(name)
    level = str(getattr(skill, "level", "") or "")
    aliases = _coerce_skill_aliases(getattr(skill, "aliases", []), name)
    return (name, normalized_name, _level_weight(level), aliases)


def _find_skill_match(
    normalized_required_skill: str,
    alias_lookup: dict[str, tuple[str, float]],
) -> tuple[str, float] | None:
    direct_match = alias_lookup.get(normalized_required_skill)
    if direct_match:
        return direct_match

    if len(normalized_required_skill) < 3:
        return None

    candidates = [
        (alias, payload)
        for alias, payload in alias_lookup.items()
        if len(alias) >= 3
        and (alias in normalized_required_skill or normalized_required_skill in alias)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-len(item[0]), -item[1][1]))
    return candidates[0][1]


def _summarize_fit(match_score: float, matched: int, required: int, gaps: Sequence[str]) -> str:
    if required == 0:
        return "No structured required skills provided yet. Capture requirements or tags to score this role."
    if match_score >= 60:
        return (
            f"Strong fit across {matched}/{required} required skills. "
            + ("Main gap: " + ", ".join(gaps[:3]) if gaps else "No obvious skill gaps.")
        )
    if match_score >= 35:
        return (
            f"Partial fit across {matched}/{required} required skills. "
            + ("Close the gap on " + ", ".join(gaps[:3]) if gaps else "Needs clearer requirements.")
        )
    return (
        f"Weak fit right now: only {matched}/{required} required skills matched. "
        + ("Largest gaps: " + ", ".join(gaps[:3]) if gaps else "Need more signal before applying.")
    )


def calculate_job_match(
    required_skills: Iterable[str],
    skill_profiles: Iterable[Any],
    title: str = "",
    description: str = "",
    tags: Iterable[str] | None = None,
) -> JobMatchResult:
    del title, description, tags

    normalized_required: list[tuple[str, str]] = []
    for required_skill in required_skills:
        raw_value = str(required_skill or "").strip()
        normalized_value = normalize_skill_name(raw_value)
        if not raw_value or not normalized_value or normalized_value in GENERIC_SKILL_STOPWORDS:
            continue
        normalized_required.append((raw_value, normalized_value))

    if not normalized_required:
        return JobMatchResult(
            match_score=0.0,
            matched_skills=[],
            skill_gap_list=[],
            fit_summary=_summarize_fit(0.0, 0, 0, []),
        )

    alias_lookup: dict[str, tuple[str, float]] = {}
    for skill_profile in skill_profiles:
        canonical_name, normalized_name, weight, aliases = _skill_signature(skill_profile)
        for alias in [normalized_name, *aliases]:
            if not alias:
                continue
            existing = alias_lookup.get(alias)
            if existing is None or weight > existing[1]:
                alias_lookup[alias] = (canonical_name, weight)

    weighted_total = 0.0
    matched_skills: list[str] = []
    skill_gaps: list[str] = []
    matched_requirement_count = 0

    for raw_required_skill, normalized_required_skill in normalized_required:
        match = _find_skill_match(normalized_required_skill, alias_lookup)
        if match is None:
            skill_gaps.append(raw_required_skill)
            continue
        canonical_name, weight = match
        weighted_total += weight
        matched_requirement_count += 1
        if canonical_name not in matched_skills:
            matched_skills.append(canonical_name)

    score = round((weighted_total / len(normalized_required)) * 100, 2)
    fit_summary = _summarize_fit(
        score,
        matched_requirement_count,
        len(normalized_required),
        skill_gaps,
    )
    return JobMatchResult(
        match_score=score,
        matched_skills=matched_skills,
        skill_gap_list=skill_gaps,
        fit_summary=fit_summary,
    )


async def bootstrap_skill_profiles(force: bool = False) -> dict[str, int]:
    profile = identity.get_profile()
    seeds = extract_skill_seeds_from_profile(profile)

    async with AsyncSessionLocal() as db:
        existing_rows = list((await db.execute(select(SkillProfile))).scalars().all())
        existing_lookup = {
            (row.category, row.normalized_name): row
            for row in existing_rows
        }

        inserted = 0
        updated = 0
        for seed in seeds:
            row = existing_lookup.get((seed.category, seed.normalized_name))
            if row is None:
                db.add(
                    SkillProfile(
                        name=seed.name,
                        normalized_name=seed.normalized_name,
                        category=seed.category,
                        level=seed.level,
                        years_experience=seed.years_experience,
                        aliases=seed.aliases,
                        evidence=seed.evidence,
                        source=seed.source,
                        is_active=True,
                    )
                )
                inserted += 1
                continue

            if row.source != "identity_profile" and not force:
                continue

            row.name = seed.name
            row.level = seed.level
            row.years_experience = seed.years_experience
            row.aliases = seed.aliases
            row.evidence = seed.evidence
            row.source = seed.source
            row.is_active = True
            updated += 1

        await db.commit()
        total = await db.scalar(select(func.count()).select_from(SkillProfile))
        return {"inserted": inserted, "updated": updated, "total": int(total or 0)}


async def ensure_skill_profiles_seeded() -> int:
    async with AsyncSessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(SkillProfile))
    if int(total or 0) > 0:
        return int(total or 0)
    result = await bootstrap_skill_profiles()
    return result["total"]


async def _load_active_skill_profiles() -> list[SkillProfile]:
    await ensure_skill_profiles_seeded()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SkillProfile)
            .where(SkillProfile.is_active.is_(True))
            .order_by(SkillProfile.category, desc(SkillProfile.level), SkillProfile.name)
        )
        return list(result.scalars().all())


def _derive_required_skills(
    required_skills: Iterable[str] | None,
    tags: Iterable[str] | None,
) -> list[str]:
    values = list(required_skills or [])
    if not values:
        values = list(tags or [])
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        raw = str(value or "").strip()
        normalized = normalize_skill_name(raw)
        if not raw or not normalized or normalized in GENERIC_SKILL_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(raw)
    return deduped


async def upsert_job_posting(payload: dict[str, Any]) -> JobPosting:
    required_skills = _derive_required_skills(
        payload.get("required_skills"),
        payload.get("tags"),
    )
    skills = await _load_active_skill_profiles()
    match = calculate_job_match(
        required_skills=required_skills,
        skill_profiles=skills,
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        tags=payload.get("tags") or [],
    )

    source_hash = str(payload.get("source_hash") or "").strip() or None
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        row = None
        if source_hash:
            result = await db.execute(
                select(JobPosting).where(JobPosting.source_hash == source_hash)
            )
            row = result.scalar_one_or_none()

        if row is None:
            row = JobPosting(
                title=str(payload.get("title") or "Untitled"),
                company=str(payload.get("company") or "").strip() or None,
                source_platform=str(payload.get("source_platform") or "").strip() or None,
                source_url=str(payload.get("source_url") or "").strip() or None,
                location=str(payload.get("location") or "").strip() or None,
                job_type=str(payload.get("job_type") or "freelance"),
                employment_type=str(payload.get("employment_type") or "").strip() or None,
                description=str(payload.get("description") or "").strip() or None,
                required_skills=required_skills,
                tags=list(payload.get("tags") or []),
                raw_data=dict(payload.get("raw_data") or {}),
                source_hash=source_hash,
            )
            db.add(row)

        row.title = str(payload.get("title") or row.title or "Untitled")
        row.company = str(payload.get("company") or row.company or "").strip() or row.company
        row.source_platform = str(
            payload.get("source_platform") or row.source_platform or ""
        ).strip() or row.source_platform
        row.source_url = str(payload.get("source_url") or row.source_url or "").strip() or row.source_url
        row.location = str(payload.get("location") or row.location or "").strip() or row.location
        row.job_type = str(payload.get("job_type") or row.job_type or "freelance")
        row.employment_type = str(
            payload.get("employment_type") or row.employment_type or ""
        ).strip() or row.employment_type
        row.description = str(payload.get("description") or row.description or "").strip() or row.description
        row.required_skills = required_skills
        row.matched_skills = match.matched_skills
        row.skill_gap_list = match.skill_gap_list
        row.tags = list(payload.get("tags") or row.tags or [])
        row.match_score = Decimal(str(match.match_score))
        row.fit_summary = match.fit_summary
        row.raw_data = dict(payload.get("raw_data") or row.raw_data or {})
        row.last_scored_at = now
        if payload.get("opportunity_id"):
            row.opportunity_id = payload.get("opportunity_id")
        if not row.status:
            row.status = "discovered"

        await db.commit()
        await db.refresh(row)
        return row


async def rescore_job_posting(job_id: UUID) -> JobPosting | None:
    skills = await _load_active_skill_profiles()
    async with AsyncSessionLocal() as db:
        row = await db.get(JobPosting, job_id)
        if row is None:
            return None

        match = calculate_job_match(
            required_skills=row.required_skills or [],
            skill_profiles=skills,
            title=row.title,
            description=row.description or "",
            tags=row.tags or [],
        )
        row.matched_skills = match.matched_skills
        row.skill_gap_list = match.skill_gap_list
        row.match_score = Decimal(str(match.match_score))
        row.fit_summary = match.fit_summary
        row.last_scored_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(row)
        return row


async def update_job_status(
    job_id: UUID,
    status: str,
    follow_up_due: date | None = None,
) -> JobPosting | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(JobPosting, job_id)
        if row is None:
            return None
        row.status = status
        row.follow_up_due = follow_up_due
        if status == "applied":
            row.applied_at = datetime.now(UTC)
            row.follow_up_due = follow_up_due or (datetime.now(UTC) + timedelta(days=5)).date()
        await db.commit()
        await db.refresh(row)
        return row


async def request_job_apply_approval(job_id: UUID):
    async with AsyncSessionLocal() as db:
        job = await db.get(JobPosting, job_id)
        if job is None:
            return None

        preview = {
            "company": job.company,
            "source_platform": job.source_platform,
            "match_score": float(job.match_score or 0),
            "matched_skills": job.matched_skills or [],
            "skill_gaps": job.skill_gap_list or [],
            "source_url": job.source_url,
        }
        details = {
            "job_type": job.job_type,
            "employment_type": job.employment_type,
            "required_skills": job.required_skills or [],
            "status": job.status,
        }

    return await queue_approval_request(
        title=f"Approve application: {job.title}",
        action_type="job_apply_submit",
        subject_type="job_posting",
        subject_id=job_id,
        details=details,
        preview=preview,
        requested_by="jobs_api",
    )


async def upsert_job_posting_from_opportunity(opportunity_id: UUID) -> JobPosting | None:
    async with AsyncSessionLocal() as db:
        opportunity = await db.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.type not in {"job", "freelance"}:
            return None
        payload = {
            "title": opportunity.title,
            "company": None,
            "source_platform": opportunity.source_platform,
            "source_url": opportunity.source_url,
            "location": opportunity.location_type,
            "job_type": "job" if opportunity.type == "job" else "freelance",
            "employment_type": opportunity.type,
            "description": opportunity.description,
            "required_skills": list((opportunity.raw_data or {}).get("required_skills") or []),
            "tags": list(opportunity.tags or []),
            "raw_data": dict(opportunity.raw_data or {}),
            "source_hash": opportunity.source_hash or f"opportunity:{opportunity.id}",
            "opportunity_id": opportunity.id,
        }
    return await upsert_job_posting(payload)


async def sync_job_postings_from_opportunities(limit: int = 50) -> int:
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(Opportunity)
                    .where(Opportunity.type.in_(["job", "freelance"]))
                    .order_by(desc(Opportunity.found_at))
                    .limit(limit)
                )
            ).scalars()
        )

    synced = 0
    for row in rows:
        synced_row = await upsert_job_posting_from_opportunity(row.id)
        if synced_row is not None:
            synced += 1
    return synced
