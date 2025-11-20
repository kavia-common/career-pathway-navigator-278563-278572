from typing import Dict, List, Optional, Literal

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
    # Gap annotation fields
    is_gap: Optional[bool] = Field(None, description="True when this role requires the skill and it is considered a gap")
    color: Optional[str] = Field(None, description="Hex color for this role-skill (e.g., '#ef4444' for gaps)")
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
    # New optional entity identifier for detail fetching on the client
    entity_id: Optional[int] = Field(None, description="Entity ID for this node (Role.id or Skill.id)")
    color: Optional[str] = Field(None, description="Optional color hex for this node")
    is_gap: Optional[bool] = Field(None, description="If true, this node represents a gap for the current role")
    # Progress state on node (frontend editable)
    progress: Optional[Literal["not_started", "in_progress", "completed"]] = Field(
        None, description="Progress status for this skill node"
    )
    percent_complete: Optional[int] = Field(
        None, ge=0, le=100, description="Optional numeric percent complete for this skill node"
    )


class GraphLink(BaseModel):
    source: str = Field(..., description="Source node id")
    target: str = Field(..., description="Target node id")
    type: str = Field(..., description="Link type, e.g., requires")
    level: Optional[int] = Field(None, ge=0, le=5, description="Required level when applicable")
    from_: Optional[str] = Field(None, alias="from", description="Origin (current|target) for requires link")
    color: Optional[str] = Field(None, description="Optional color hex for this link")
    is_gap: Optional[bool] = Field(None, description="If true, this link represents a gap for current role")


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


# Skill detail (reverse view of role requirements)
class SkillRoleOut(BaseModel):
    role: RoleOut
    required_level: int = Field(..., ge=1, le=5)
    is_gap: Optional[bool] = Field(None, description="If present, indicates gap annotation on role-skill")
    color: Optional[str] = Field(None, description="Optional color hex for this role-skill")

    class Config:
        from_attributes = True


class SkillDetailOut(SkillOut):
    roles: List[SkillRoleOut] = []


class RoadmapIn(BaseModel):
    """Input schema for creating/updating a roadmap."""

    name: str = Field(..., min_length=1, max_length=200, description="Human-readable roadmap name")
    user_identifier: Optional[str] = Field(None, max_length=200, description="Demo user identifier")
    from_role_id: int = Field(..., ge=1, description="Current role id")
    to_role_id: int = Field(..., ge=1, description="Target role id")
    graph_payload: Dict[str, object] = Field(..., description="Graph JSON including nodes/links/meta")
    notes: Optional[str] = Field(None, description="Optional notes")


class RoadmapOut(BaseModel):
    """Output schema for roadmap entries."""

    id: int
    name: str
    user_identifier: Optional[str] = None
    from_role_id: int
    to_role_id: int
    graph_payload: Dict[str, object]
    notes: Optional[str] = None

    class Config:
        from_attributes = True
