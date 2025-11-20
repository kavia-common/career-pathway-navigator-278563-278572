from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


class TimestampMixin:
    """Common created_at/updated_at fields."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        nullable=False,
    )


class Role(TimestampMixin, Base):
    """Represents a career role (e.g., Chief Architect, CTO)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    skills: Mapped[List[RoleSkill]] = relationship(
        "RoleSkill", back_populates="role", cascade="all, delete-orphan"
    )

    progress: Mapped[List[Progress]] = relationship(
        "Progress", back_populates="role", cascade="all, delete-orphan"
    )


class Skill(TimestampMixin, Base):
    """Represents a skill or competency."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    roles: Mapped[List[RoleSkill]] = relationship(
        "RoleSkill", back_populates="skill", cascade="all, delete-orphan"
    )

    progress: Mapped[List[Progress]] = relationship(
        "Progress", back_populates="skill", cascade="all, delete-orphan"
    )


class RoleSkill(TimestampMixin, Base):
    """
    Association table capturing the level a role requires for a given skill.
    """

    __tablename__ = "role_skills"
    __table_args__ = (
        UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),
        CheckConstraint("required_level BETWEEN 1 AND 5", name="chk_required_level_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1..5 scale
    # Gap annotation fields (nullable for backward compatibility)
    is_gap: Mapped[Optional[bool]] = mapped_column(Integer, nullable=True, default=None)  # stored as 0/1 by SQLite
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # e.g., "#ef4444"

    role: Mapped[Role] = relationship("Role", back_populates="skills")
    skill: Mapped[Skill] = relationship("Skill", back_populates="roles")

    recommendations: Mapped[List[Recommendation]] = relationship(
        "Recommendation", back_populates="role_skill", cascade="all, delete-orphan"
    )


class Recommendation(TimestampMixin, Base):
    """Actionable recommendations tied to a role-skill requirement."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role_skill_id: Mapped[int] = mapped_column(
        ForeignKey("role_skills.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # course, project, kpi, guidance
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # 1=high, 3=normal, 5=low

    role_skill: Mapped[RoleSkill] = relationship("RoleSkill", back_populates="recommendations")


class Progress(TimestampMixin, Base):
    """
    Basic progress tracking for a role/skill combination for a (future) user context.
    MVP keeps it generic (no users); extend with user_id later.
    """

    __tablename__ = "progress"
    __table_args__ = (
        UniqueConstraint("role_id", "skill_id", name="uq_progress_role_skill"),
        CheckConstraint("status IN ('not_started','working_on','complete')", name="chk_progress_status"),
        CheckConstraint("current_level BETWEEN 0 AND 5", name="chk_current_level_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    role: Mapped[Role] = relationship("Role", back_populates="progress")
    skill: Mapped[Skill] = relationship("Skill", back_populates="progress")
