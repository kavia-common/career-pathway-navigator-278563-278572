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
    """Create or fetch skills by name based on the provided spec list.
    If an existing skill is missing category/description, fill them in (idempotent enrichment).
    """
    created: List[Skill] = []
    for name, category, description in specs:
        existing = skill_repo.get_skill_by_name(name)
        if existing:
            changed = False
            if (existing.category is None or str(existing.category).strip() == "") and category:
                existing.category = category
                changed = True
            if (existing.description is None or str(existing.description).strip() == "") and description:
                existing.description = description
                changed = True
            if changed:
                # Flush only if we've changed fields
                skill_repo.session.flush()
            created.append(existing)
            continue

        s = skill_repo.create_skill(name, category=category, description=description)
        created.append(s)
    return created


def _attach_role_skills(
    role_repo: RoleRepository,
    rec_repo: RecommendationRepository,
    role_name: str,
    role_skill_levels: Dict[str, int],
    target_role_levels: Dict[str, int] | None = None,
) -> None:
    """Attach or update skills to the role according to required levels (idempotent).
    Also computes gap annotations where applicable:
    - If target_role_levels provided (used for current role vs target), mark skills where target requires more as gaps.
    - Ensure at least 3 gap skills per role by marking the highest level skills as gaps when needed.
    """
    role = role_repo.get_role_by_name(role_name)
    if not role:
        return

    # First, ensure links exist; update required_level if changed; do not duplicate
    for skill_name, level in role_skill_levels.items():
        # Resolve Skill
        skill = next((rs.skill for rs in role.skills if rs.skill and rs.skill.name == skill_name), None)
        if skill is None:
            skill = role_repo.session.query(Skill).filter(Skill.name == skill_name).first()
        if not skill:
            logger.warning("Skill '%s' not found while attaching to role '%s'", skill_name, role_name)
            continue

        # Find existing mapping
        existing = next((rs for rs in role.skills if rs.skill and rs.skill.name == skill_name), None)
        if existing:
            # update required_level if changed; leave gap fields to compute below
            if int(existing.required_level) != int(level):
                existing.required_level = int(level)
                role_repo.session.flush()
            link = existing
        else:
            link = role_repo.attach_skill(role, skill, required_level=int(level))

        # Add a small example recommendation per role to showcase UI (optional)
        if role.name in {"CTO", "Head of Engineering"} and skill.name in {"Business & Product", "Organizational Design"}:
            try:
                rec_repo.add_recommendation(
                    link,
                    type_="guidance",
                    title="Define quarterly OKRs",
                    details="Set measurable outcomes aligned to strategy for this competency.",
                    priority=2,
                )
            except Exception:
                # recommendations may already exist - ignore duplication errors silently
                pass

    # Re-load role skills after potential attaches
    role = role_repo.get_role_by_name(role_name)
    if not role:
        return

    # Compute gap annotations. If target_role_levels provided, a gap is when target requires more than role's required.
    GAP_COLOR = "#ef4444"
    if target_role_levels is not None:
        for rs in role.skills:
            t_level = target_role_levels.get(rs.skill.name)
            if t_level is None:
                # if target doesn't require it, consider no gap by default
                rs.is_gap = 0
                rs.color = None
            else:
                is_gap = int(t_level) > int(rs.required_level)
                rs.is_gap = 1 if is_gap else 0
                rs.color = GAP_COLOR if is_gap else None

    # Ensure at least 3 gap skills per role: if fewer than 3 marked, pick top required_level skills to flag as gaps
    try:
        count_gaps = sum(1 for rs in role.skills if (rs.is_gap or 0) == 1)
        if count_gaps < 3 and len(role.skills) > 0:
            # sort by required_level desc and pick additional to reach 3
            sorted_rs = sorted(role.skills, key=lambda r: int(r.required_level), reverse=True)
            for rs in sorted_rs:
                if (rs.is_gap or 0) == 1:
                    continue
                rs.is_gap = 1
                rs.color = GAP_COLOR
                count_gaps += 1
                if count_gaps >= 3:
                    break
        role_repo.session.flush()
    except Exception:
        logger.exception("Failed to compute/enforce gap annotations for role '%s'", role_name)


# PUBLIC_INTERFACE
def seed_minimal_dataset(session: Session) -> None:
    """Seed dataset with baseline and extended roles/skills for navigation."""
    role_repo = RoleRepository(session)
    skill_repo = SkillRepository(session)
    rec_repo = RecommendationRepository(session)
    prog_repo = ProgressRepository(session)

    # Core roles (existing). If an existing role is missing description, enrich it.
    def _ensure_role(name: str, desc: str):
        r = role_repo.get_role_by_name(name)
        if not r:
            r = role_repo.create_role(name, description=desc)
        else:
            if (r.description is None or str(r.description).strip() == "") and desc:
                r.description = desc
                session.flush()
        return r

    chief_architect = _ensure_role(
        "Chief Architect",
        "Leads architecture strategy and complex systems design across the org.",
    )
    cto = _ensure_role(
        "CTO",
        "Exec-level role responsible for technology strategy, execution, and org leadership.",
    )

    # Extended roles to append
    head_eng = _ensure_role(
        "Head of Engineering",
        "Owns engineering delivery, org health, and operational excellence.",
    )
    staff_eng = _ensure_role(
        "Staff Engineer",
        "Drives cross-team technical direction and delivers high-impact systems.",
    )
    eng_manager = _ensure_role(
        "Engineering Manager",
        "Manages engineers, delivery, and career development for a team.",
    )
    product_manager = _ensure_role(
        "Product Manager",
        "Owns product discovery, prioritization, and outcomes with cross-functional teams.",
    )
    platform_eng = _ensure_role(
        "Platform Engineer",
        "Builds and maintains internal platforms that accelerate product teams.",
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

    # Ensure all role-skill links exist according to mapping and compute gap annotations.
    # For simplicity, we mark gaps relative to the role's own highest requirements to ensure at least 3 red items.
    # Additionally, when a natural current/target pair is available in the app, /graph will compute link-level gaps.
    for role_name, skills_levels in mapping.items():
        # Provide target levels same as mapping[role_name] to allow internal comparison; the _attach helper
        # will still enforce a minimum of three gaps per role even if differences are not found.
        _attach_role_skills(role_repo, rec_repo, role_name, skills_levels, target_role_levels=skills_levels)

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
    Safe to run multiple times; inserts missing data only. This function:
    - Upserts roles and skills by stable names.
    - Adds missing role-skill links per mapping.
    - Adds example recommendations if not present.
    - Enriches missing descriptions/categories when blank.
    """
    seed_minimal_dataset(session)
