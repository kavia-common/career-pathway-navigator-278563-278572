import logging
from typing import List

from sqlalchemy.orm import Session

from src.db.models import Skill
from src.db.repositories import ProgressRepository, RecommendationRepository, RoleRepository, SkillRepository

logger = logging.getLogger(__name__)


# PUBLIC_INTERFACE
def seed_minimal_dataset(session: Session) -> None:
    """Seed a minimal dataset for the Chief Architect → CTO journey."""
    role_repo = RoleRepository(session)
    skill_repo = SkillRepository(session)
    rec_repo = RecommendationRepository(session)
    prog_repo = ProgressRepository(session)

    # Roles
    chief_architect = role_repo.get_role_by_name("Chief Architect") or role_repo.create_role(
        "Chief Architect",
        description="Leads architecture strategy and complex systems design across the org.",
    )
    cto = role_repo.get_role_by_name("CTO") or role_repo.create_role(
        "CTO",
        description="Exec-level role responsible for technology strategy, execution, and org leadership.",
    )

    # Skills
    skills_spec = [
        ("Technology Leadership", "Leadership", "Drive technical vision, standards, and engineering excellence."),
        ("Business & Product", "Business", "Align technology with business value and product strategy."),
        ("People Leadership", "Leadership", "Build teams, coaching, org structure, hiring."),
        ("Communication", "Soft Skills", "Exec-level communication to board, C-suite, and org."),
        ("Strategy", "Leadership", "Long-term tech strategy, portfolio management, investment planning."),
    ]
    created_skills: List[Skill] = []
    for name, category, description in skills_spec:
        s = skill_repo.get_skill_by_name(name) or skill_repo.create_skill(
            name, category=category, description=description
        )
        created_skills.append(s)

    # Attach role requirements (levels: 1..5)
    # Chief Architect requires high technical leadership and communication; CTO requires higher business/strategy
    mapping = {
        "Chief Architect": {
            "Technology Leadership": 5,
            "Business & Product": 3,
            "People Leadership": 3,
            "Communication": 4,
            "Strategy": 3,
        },
        "CTO": {
            "Technology Leadership": 5,
            "Business & Product": 4,
            "People Leadership": 4,
            "Communication": 5,
            "Strategy": 5,
        },
    }

    for role in (chief_architect, cto):
        for skill in created_skills:
            level = mapping[role.name][skill.name]
            # Attach if not already linked (idempotent seed)
            exists = [rs for rs in role.skills if rs.skill_id == skill.id]
            if exists:
                continue
            link = role_repo.attach_skill(role, skill, required_level=level)
            # Add a couple of sample recommendations for visibility in UI
            if role.name == "CTO" and skill.name == "Business & Product":
                rec_repo.add_recommendation(
                    link,
                    type_="course",
                    title="Finance for Tech Leaders",
                    url="https://www.coursera.org/specializations/finance",
                    details="Understand corporate finance, KPIs, budgeting for CTOs.",
                    priority=2,
                )
                rec_repo.add_recommendation(
                    link,
                    type_="project",
                    title="Define Product-Tech Operating Model",
                    details="Lead an initiative to align product roadmaps with platform strategy.",
                    priority=1,
                )

    # Initialize progress for Chief Architect moving toward CTO
    for skill in created_skills:
        # Assume current level 3 across; working_on key areas
        status = "working_on" if skill.name in {"Business & Product", "Strategy"} else "not_started"
        prog_repo.set_progress(chief_architect, skill, status=status, current_level=3)

    logger.info("Minimal dataset seeded successfully.")
