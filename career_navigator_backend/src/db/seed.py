import logging
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from src.db.models import Skill
from src.db.repositories import (
    ProgressRepository,
    RecommendationRepository,
    RoleRepository,
    SkillRepository,
)

logger = logging.getLogger(__name__)


def _ensure_skills(skill_repo: SkillRepository, specs: List[Tuple[str, str, str]]) -> List[Skill]:
    """Create or fetch skills by name based on the provided spec list."""
    created: List[Skill] = []
    for name, category, description in specs:
        s = skill_repo.get_skill_by_name(name) or skill_repo.create_skill(
            name, category=category, description=description
        )
        created.append(s)
    return created


def _attach_role_skills(
    role_repo: RoleRepository,
    rec_repo: RecommendationRepository,
    role_name: str,
    role_skill_levels: Dict[str, int],
) -> None:
    """Attach skills to the role according to required levels (idempotent)."""
    role = role_repo.get_role_by_name(role_name)
    if not role:
        return
    for skill_name, level in role_skill_levels.items():
        # Skip if attached
        exists = [rs for rs in role.skills if rs.skill and rs.skill.name == skill_name]
        if exists:
            continue
        # The RoleSkill attach requires a Skill instance; fetch via the session
        skill = next((rs.skill for rs in role.skills if rs.skill and rs.skill.name == skill_name), None)
        if skill is None:
            # When skill isn't already linked, resolve from DB
            skill = role_repo.session.query(Skill).filter(Skill.name == skill_name).first()
        if not skill:
            logger.warning("Skill '%s' not found while attaching to role '%s'", skill_name, role_name)
            continue
        link = role_repo.attach_skill(role, skill, required_level=int(level))
        # Add a small example recommendation per role to showcase UI (optional)
        if role.name in {"CTO", "Head of Engineering"} and skill.name in {"Business & Product", "Organizational Design"}:
            rec_repo.add_recommendation(
                link,
                type_="guidance",
                title="Define quarterly OKRs",
                details="Set measurable outcomes aligned to strategy for this competency.",
                priority=2,
            )


# PUBLIC_INTERFACE
def seed_minimal_dataset(session: Session) -> None:
    """Seed dataset with baseline and extended roles/skills for navigation."""
    role_repo = RoleRepository(session)
    skill_repo = SkillRepository(session)
    rec_repo = RecommendationRepository(session)
    prog_repo = ProgressRepository(session)

    # Core roles (existing)
    chief_architect = role_repo.get_role_by_name("Chief Architect") or role_repo.create_role(
        "Chief Architect",
        description="Leads architecture strategy and complex systems design across the org.",
    )
    cto = role_repo.get_role_by_name("CTO") or role_repo.create_role(
        "CTO",
        description="Exec-level role responsible for technology strategy, execution, and org leadership.",
    )

    # Extended roles to append
    head_eng = role_repo.get_role_by_name("Head of Engineering") or role_repo.create_role(
        "Head of Engineering",
        description="Owns engineering delivery, org health, and operational excellence.",
    )
    staff_eng = role_repo.get_role_by_name("Staff Engineer") or role_repo.create_role(
        "Staff Engineer",
        description="Drives cross-team technical direction and delivers high-impact systems.",
    )
    eng_manager = role_repo.get_role_by_name("Engineering Manager") or role_repo.create_role(
        "Engineering Manager",
        description="Manages engineers, delivery, and career development for a team.",
    )
    product_manager = role_repo.get_role_by_name("Product Manager") or role_repo.create_role(
        "Product Manager",
        description="Owns product discovery, prioritization, and outcomes with cross-functional teams.",
    )
    platform_eng = role_repo.get_role_by_name("Platform Engineer") or role_repo.create_role(
        "Platform Engineer",
        description="Builds and maintains internal platforms that accelerate product teams.",
    )

    # Skills (existing + new) – keep names stable for ID consistency across runs
    skills_spec = [
        # Existing
        ("Technology Leadership", "Leadership", "Drive technical vision, standards, and engineering excellence."),
        ("Business & Product", "Business", "Align technology with business value and product strategy."),
        ("People Leadership", "Leadership", "Build teams, coaching, org structure, hiring."),
        ("Communication", "Soft Skills", "Exec-level communication to board, C-suite, and org."),
        ("Strategy", "Leadership", "Long-term tech strategy, portfolio management, investment planning."),
        # New shared/role-specific competencies
        ("System Design", "Technical", "Design scalable, reliable, and secure systems."),
        ("Cloud Infrastructure", "Technical", "Operate cloud services, networking, and IaC."),
        ("Security & Compliance", "Technical", "Embed security best practices and compliance."),
        ("Data & Analytics", "Technical", "Leverage data platforms, analytics, and insights."),
        ("Organizational Design", "Leadership", "Define structures, processes, and operating models."),
        ("Hiring & Coaching", "Leadership", "Attract, develop, and retain top talent."),
        ("Operational Excellence", "Operations", "SLOs, incident mgmt, change mgmt, and reliability."),
        ("Stakeholder Management", "Business", "Align expectations and maintain trust with key stakeholders."),
        ("Roadmapping & Prioritization", "Product", "Prioritize initiatives and plan roadmaps for outcomes."),
        ("DevEx & Tooling", "Technical", "Developer experience, CI/CD, and internal platforms."),
        ("Observability", "Technical", "Metrics, tracing, logging to understand systems."),
        ("Cost Management", "Business", "Optimize cloud and platform spend vs. value."),
    ]
    created_skills: List[Skill] = _ensure_skills(skill_repo, skills_spec)

    # Role-to-skill mappings (levels 1..5). Roughly 8 skills per new role.
    mapping = {
        # Existing mapping
        "Chief Architect": {
            "Technology Leadership": 5,
            "Business & Product": 3,
            "People Leadership": 3,
            "Communication": 4,
            "Strategy": 3,
            "System Design": 5,
            "Security & Compliance": 4,
            "Stakeholder Management": 3,
        },
        "CTO": {
            "Technology Leadership": 5,
            "Business & Product": 4,
            "People Leadership": 4,
            "Communication": 5,
            "Strategy": 5,
            "Organizational Design": 5,
            "Operational Excellence": 4,
            "Cost Management": 4,
        },
        # New roles
        "Head of Engineering": {
            "Technology Leadership": 4,
            "People Leadership": 5,
            "Operational Excellence": 5,
            "Organizational Design": 4,
            "Communication": 4,
            "Stakeholder Management": 4,
            "Hiring & Coaching": 5,
            "Strategy": 4,
        },
        "Staff Engineer": {
            "System Design": 5,
            "Technology Leadership": 4,
            "Security & Compliance": 4,
            "Communication": 4,
            "Observability": 4,
            "Cloud Infrastructure": 4,
            "DevEx & Tooling": 4,
            "Data & Analytics": 3,
        },
        "Engineering Manager": {
            "People Leadership": 5,
            "Hiring & Coaching": 5,
            "Stakeholder Management": 4,
            "Roadmapping & Prioritization": 4,
            "Operational Excellence": 4,
            "Communication": 4,
            "Technology Leadership": 3,
            "Strategy": 3,
        },
        "Product Manager": {
            "Business & Product": 5,
            "Roadmapping & Prioritization": 5,
            "Stakeholder Management": 5,
            "Communication": 5,
            "Data & Analytics": 4,
            "Strategy": 4,
            "Organizational Design": 3,
            "Operational Excellence": 3,
        },
        "Platform Engineer": {
            "Cloud Infrastructure": 5,
            "DevEx & Tooling": 5,
            "Operational Excellence": 4,
            "Observability": 4,
            "Security & Compliance": 4,
            "System Design": 4,
            "Cost Management": 3,
            "Communication": 3,
        },
    }

    # Ensure all role-skill links exist according to mapping
    for role_name, skills_levels in mapping.items():
        _attach_role_skills(role_repo, rec_repo, role_name, skills_levels)

    # Touch role instances to avoid linter unused-variable warnings and assert existence
    _ = (chief_architect, cto, head_eng, staff_eng, eng_manager, product_manager, platform_eng)

    # Initialize example progress for Chief Architect as a baseline (stable behavior)
    baseline_skills = [
        "Business & Product",
        "Strategy",
        "Technology Leadership",
        "Communication",
        "System Design",
    ]
    for sname in baseline_skills:
        skill = next((s for s in created_skills if s.name == sname), None)
        if not skill:
            continue
        status = "working_on" if sname in {"Business & Product", "Strategy"} else "not_started"
        prog_repo.set_progress(chief_architect, skill, status=status, current_level=3)

    logger.info("Dataset seeded successfully with baseline and extended roles.")


# PUBLIC_INTERFACE
def seed_minimal_dataset_idempotent(session: Session) -> None:
    """
    Idempotent seeding: ensure all baseline and extended roles/skills/mappings exist.
    Safe to run multiple times; inserts missing data only.
    """
    # Reuse the same seeding code; it is already written to upsert by name and
    # attach only missing role-skill links.
    seed_minimal_dataset(session)
