from app.core.career import calculate_job_match, extract_skill_seeds_from_profile


def test_extract_skill_seeds_from_identity_profile_builds_aliases_and_evidence():
    profile = {
        "skills": {
            "technical": [
                {"name": "Python (FastAPI / Django)", "level": "advanced", "years": 2},
                {"name": "React / Next.js", "level": "advanced", "years": 2},
            ],
            "soft": [
                "ships real products while still in year 1",
            ],
        },
        "projects": [
            {
                "name": "Testlyn",
                "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
            },
            {
                "name": "Plexta",
                "tech_stack": ["React", "Next.js", "TailwindCSS"],
            },
        ],
    }

    seeds = extract_skill_seeds_from_profile(profile)

    python_skill = next(seed for seed in seeds if seed.normalized_name == "python")
    soft_skill = next(seed for seed in seeds if seed.category == "soft")

    assert python_skill.level == "advanced"
    assert python_skill.years_experience == 2.0
    assert "fastapi" in python_skill.aliases
    assert "django" in python_skill.aliases
    assert python_skill.evidence == ["Testlyn"]
    assert soft_skill.level == "advanced"


def test_calculate_job_match_returns_score_and_skill_gaps():
    profile = {
        "skills": {
            "technical": [
                {"name": "Python (FastAPI / Django)", "level": "advanced", "years": 2},
                {"name": "PostgreSQL", "level": "intermediate", "years": 2},
                {"name": "Docker / CI-CD", "level": "intermediate", "years": 1},
            ],
        },
        "projects": [],
    }
    skills = extract_skill_seeds_from_profile(profile)

    result = calculate_job_match(
        required_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
        skill_profiles=skills,
        title="Backend Developer",
        description="Build APIs and infrastructure for a production backend.",
        tags=["python", "backend"],
    )

    assert result.match_score == 64.0
    assert "AWS" in result.skill_gap_list
    assert "Python (FastAPI / Django)" in result.matched_skills
    assert "strong fit" in result.fit_summary.lower()


def test_calculate_job_match_handles_missing_structured_requirements():
    skills = extract_skill_seeds_from_profile(
        {
            "skills": {
                "technical": [
                    {"name": "Node.js", "level": "advanced", "years": 2},
                ]
            }
        }
    )

    result = calculate_job_match(
        required_skills=[],
        skill_profiles=skills,
        title="Generalist engineer",
        description="Need someone who can move quickly.",
        tags=[],
    )

    assert result.match_score == 0.0
    assert result.skill_gap_list == []
    assert "no structured required skills" in result.fit_summary.lower()
