from typing import List, Optional

from pydantic import BaseModel, Field


class RecommendationOut(BaseModel):
    id: int = Field(..., description="Recommendation identifier")
    type: str = Field(..., description="Type of recommendation, e.g., course, project, kpi, guidance")
    title: str = Field(..., description="Title of recommendation")
    url: Optional[str] = Field(None, description="Optional URL")
    details: Optional[str] = Field(None, description="Additional information")
    priority: int = Field(..., ge=1, le=5, description="Priority 1..5 (1=high)")

    class Config:
        from_attributes = True


class SkillOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleSkillOut(BaseModel):
    skill: SkillOut
    required_level: int = Field(..., ge=1, le=5)
    recommendations: List[RecommendationOut] = []

    class Config:
        from_attributes = True


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleDetailOut(RoleOut):
    skills: List[RoleSkillOut] = []


class ProgressOut(BaseModel):
    role_id: int
    skill_id: int
    status: str = Field(..., pattern="^(not_started|working_on|complete)$")
    current_level: int = Field(..., ge=0, le=5)

    class Config:
        from_attributes = True
