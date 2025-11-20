import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import Progress, Recommendation, Role, RoleSkill, Skill

logger = logging.getLogger(__name__)


class RoleRepository:
    """Repository for Role entities and related structures."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    def list_roles(self) -> List[Role]:
        """Return all roles sorted by name."""
        stmt = select(Role).order_by(Role.name.asc())
        return list(self.session.scalars(stmt).all())

    # PUBLIC_INTERFACE
    def get_role_by_name(self, name: str) -> Optional[Role]:
        """Fetch a role by its unique name."""
        if not name or not name.strip():
            return None
        stmt = select(Role).where(Role.name == name.strip())
        return self.session.scalars(stmt).first()

    # PUBLIC_INTERFACE
    def create_role(self, name: str, description: Optional[str] = None) -> Role:
        """Create a new role with the given name."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Role name is required")
        role = Role(name=name, description=description)
        self.session.add(role)
        try:
            self.session.flush()
        except IntegrityError as exc:
            logger.warning("Role with name '%s' already exists: %s", name, exc)
            self.session.rollback()
            existing = self.get_role_by_name(name)
            if existing:
                return existing
            raise
        return role

    # PUBLIC_INTERFACE
    def attach_skill(
        self, role: Role, skill: Skill, required_level: int = 3
    ) -> RoleSkill:
        """Attach a skill to a role with a required level."""
        if required_level < 1 or required_level > 5:
            raise ValueError("required_level must be between 1 and 5")
        link = RoleSkill(role=role, skill=skill, required_level=required_level)
        self.session.add(link)
        self.session.flush()
        return link


class SkillRepository:
    """Repository for Skill entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    def list_skills(self) -> List[Skill]:
        """Return all skills sorted by name."""
        stmt = select(Skill).order_by(Skill.name.asc())
        return list(self.session.scalars(stmt).all())

    # PUBLIC_INTERFACE
    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        """Fetch a skill by its unique name."""
        if not name or not name.strip():
            return None
        stmt = select(Skill).where(Skill.name == name.strip())
        return self.session.scalars(stmt).first()

    # PUBLIC_INTERFACE
    def create_skill(
        self, name: str, category: Optional[str] = None, description: Optional[str] = None
    ) -> Skill:
        """Create a new skill with the given name and optional category/description."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Skill name is required")
        skill = Skill(name=name, category=(category or None), description=description)
        self.session.add(skill)
        try:
            self.session.flush()
        except IntegrityError as exc:
            logger.warning("Skill with name '%s' may already exist: %s", name, exc)
            self.session.rollback()
            existing = self.get_skill_by_name(name)
            if existing:
                return existing
            raise
        return skill


class RecommendationRepository:
    """Repository for recommendations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    def add_recommendation(
        self,
        role_skill: RoleSkill,
        type_: str,
        title: str,
        url: Optional[str] = None,
        details: Optional[str] = None,
        priority: int = 3,
    ) -> Recommendation:
        """Create a recommendation for a role-skill mapping."""
        type_clean = (type_ or "").strip().lower()
        title_clean = (title or "").strip()
        if not type_clean or not title_clean:
            raise ValueError("type and title are required for recommendations")
        if priority < 1 or priority > 5:
            raise ValueError("priority must be between 1 and 5")
        rec = Recommendation(
            role_skill=role_skill,
            type=type_clean,
            title=title_clean,
            url=(url or None),
            details=details,
            priority=priority,
        )
        self.session.add(rec)
        self.session.flush()
        return rec


class ProgressRepository:
    """Repository for progress tracking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    def set_progress(
        self,
        role: Role,
        skill: Skill,
        status: str = "not_started",
        current_level: int = 0,
    ) -> Progress:
        """Create or update progress for role/skill."""
        st = (status or "").strip().lower()
        if st not in {"not_started", "working_on", "complete"}:
            raise ValueError("Invalid progress status")
        if current_level < 0 or current_level > 5:
            raise ValueError("current_level must be between 0 and 5")

        existing = self.get_progress(role, skill)
        if existing:
            existing.status = st
            existing.current_level = current_level
            self.session.flush()
            return existing

        p = Progress(role=role, skill=skill, status=st, current_level=current_level)
        self.session.add(p)
        self.session.flush()
        return p

    # PUBLIC_INTERFACE
    def get_progress(self, role: Role, skill: Skill) -> Optional[Progress]:
        """Get progress for a specific role/skill."""
        stmt = (
            select(Progress)
            .where(Progress.role_id == role.id)
            .where(Progress.skill_id == skill.id)
        )
        return self.session.scalars(stmt).first()

    # PUBLIC_INTERFACE
    def list_role_progress(self, role: Role) -> List[Progress]:
        """List all progress entries for a role."""
        stmt = select(Progress).where(Progress.role_id == role.id)
        return list(self.session.scalars(stmt).all())
