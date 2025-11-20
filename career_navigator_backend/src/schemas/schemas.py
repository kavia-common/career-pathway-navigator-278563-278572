from typing import Dict, List, Optional

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


# Graph schemas to support D3 mapper contract
class GraphNode(BaseModel):
    id: str = Field(..., description="Unique identifier used by D3 (e.g., role:1 or skill:Communication)")
    type: str = Field(..., description="Node type, e.g., role or skill")
    label: str = Field(..., description="Human-readable label")


class GraphLink(BaseModel):
    source: str = Field(..., description="Source node id")
    target: str = Field(..., description="Target node id")
    type: str = Field(..., description="Link type, e.g., requires")
    level: Optional[int] = Field(None, ge=0, le=5, description="Required level when applicable")
    from_: Optional[str] = Field(None, alias="from", description="Origin (current|target) for requires link")


class GraphMeta(BaseModel):
    fromRole: Dict[str, object]
    toRole: Dict[str, object]
    stats: Dict[str, int]


class GraphOut(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    meta: GraphMeta


# Assessment input/output
class AssessmentIn(BaseModel):
    currentRoleId: int = Field(..., ge=1, description="Current role ID")
    targetRoleId: int = Field(..., ge=1, description="Target role ID")


class AssessmentItem(BaseModel):
    skill: str
    current: int
    required: int
    gap: int


class AssessmentOut(BaseModel):
    strengths: List[AssessmentItem]
    gaps: List[AssessmentItem]
    meta: Dict[str, object]
