import hashlib
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

_profile_cache: Optional[dict] = None


def _load_profile() -> dict:
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache
    path = Path(settings.IDENTITY_PATH)
    if not path.exists():
        # fallback to local path for dev
        path = Path("identity/profile.yaml")
    with open(path, "r", encoding="utf-8") as f:
        _profile_cache = yaml.safe_load(f)
    logger.info(f"Identity loaded from {path}")
    return _profile_cache


class IdentityCore:
    def reload(self) -> None:
        global _profile_cache
        _profile_cache = None
        _load_profile()

    def get_profile(self) -> dict:
        return _load_profile()

    def get_agent_context(self) -> str:
        p = self.get_profile()
        name = p["personal"]["name"]
        role = p["current_status"]["role"]
        positioning = p["current_status"]["current_positioning"]
        north_star = p["goals"]["north_star"].strip()
        skills = [s["name"] for s in p["skills"]["technical"][:5]]
        target_desc = p["target_clients"]["ideal_client_description"].strip()
        comp_types = p["target_competitions"]["types"]
        comp_focus = p["target_competitions"]["focus_areas"][:3]
        monthly_target = p["financial"]["monthly_revenue_target_thb"]
        constraints = p["constraints"]["hard_limits"][:3]
        return (
            f"User: {name}, {role}, Bangkok Thailand.\n"
            f"Current positioning: {positioning}\n"
            f"Goals: {north_star}\n"
            f"Skills: {', '.join(skills)}\n"
            f"Target clients: {target_desc}\n"
            f"Competition focus: {', '.join(comp_types[:3])} in {', '.join(comp_focus)}\n"
            f"Financial target: {monthly_target} THB/month\n"
            f"Key constraints: {'; '.join(constraints)}"
        )

    def get_context_for_audience(self, audience: str) -> str:
        p = self.get_profile()
        name = p["personal"]["name"]
        if audience == "freelance_client":
            return (
                f"Developer: {name}, Bangkok.\n"
                f"Bio: {p['personal']['bio_short_en'].strip()}\n"
                f"Ideal for: {p['target_clients']['ideal_client_description'].strip()}\n"
                f"Min project: {p['financial']['minimum_project_size_thb']} THB\n"
                f"Voice: {p['voice_and_tone']['english_style'].strip()}"
            )
        elif audience == "competition_judge":
            projects = self.get_project_summaries()
            proj_lines = "\n".join(f"- {pj['name']}: {pj['tagline']}" for pj in projects)
            return (
                f"Competitor: {name}, {p['current_status']['year']} {p['current_status']['major']} @ {p['current_status']['university']}.\n"
                f"Bio: {p['personal']['bio_short_en'].strip()}\n"
                f"Projects:\n{proj_lines}\n"
                f"Focus: {', '.join(p['target_competitions']['focus_areas'][:4])}"
            )
        return self.get_agent_context()

    def get_voice_instructions(self) -> str:
        p = self.get_profile()
        vt = p["voice_and_tone"]
        avoid = ", ".join(f'"{ph}"' for ph in vt["phrases_to_avoid"][:5])
        return (
            f"English style: {vt['english_style'].strip()}\n"
            f"Thai style: {vt['thai_style'].strip()}\n"
            f"Never use: {avoid}\n"
            f"Sample English:\n{vt['sample_english_message']}\n"
            f"Sample Thai:\n{vt['sample_thai_message']}"
        )

    def get_scoring_weights(self) -> dict:
        # Always read from profile (DB version managed by learning_engine)
        p = self.get_profile()
        return p["scoring_weights"]

    def get_constraint_list(self) -> list:
        p = self.get_profile()
        return p["constraints"]["hard_limits"] + list(p["constraints"]["operational_limits"].keys())

    def get_target_client_description(self) -> str:
        return self.get_profile()["target_clients"]["ideal_client_description"].strip()

    def get_project_summaries(self, best_for: Optional[str] = None) -> list:
        projects = self.get_profile().get("projects", [])
        if best_for:
            return [p for p in projects if best_for in p.get("best_for", [])]
        return projects

    def get_cognitive_defaults(self) -> dict:
        return self.get_profile().get("cognitive_defaults", {"default_energy": 7, "default_stress": 3, "default_available_hours": 25})

    async def maybe_snapshot_identity(self) -> None:
        try:
            import hashlib
            from datetime import date
            from app.database import AsyncSessionLocal
            from app.models.identity_snapshot import IdentitySnapshot
            from sqlalchemy import select, desc

            profile_str = str(self.get_profile())
            current_hash = hashlib.sha256(profile_str.encode()).hexdigest()

            async with AsyncSessionLocal() as db:
                last = await db.execute(select(IdentitySnapshot).order_by(desc(IdentitySnapshot.created_at)).limit(1))
                last_snap = last.scalar_one_or_none()
                if last_snap and last_snap.profile_hash == current_hash:
                    return

                p = self.get_profile()
                snap = IdentitySnapshot(
                    snapshot_date=date.today(),
                    positioning_label=p["current_status"]["current_positioning"],
                    profile_hash=current_hash,
                    key_skills=[s["name"] for s in p["skills"]["technical"][:5]],
                    primary_narrative=p["personal"]["bio_short_en"].strip(),
                    change_trigger="monthly_snapshot",
                )
                db.add(snap)
                await db.commit()

                try:
                    from app.telegram_bot.bot import send_message
                    await send_message(f"📸 Identity snapshot saved. Positioning: {snap.positioning_label}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Identity snapshot failed: {e}")


identity = IdentityCore()
