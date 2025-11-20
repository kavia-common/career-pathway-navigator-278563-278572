import logging
import re
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.db.database import Base, engine, get_db
from src.db.models import Recommendation, Role, RoleSkill
from src.db.repositories import ProgressRepository, RoleRepository
from src.db.seed import seed_minimal_dataset
from src.schemas.schemas import (
    AssessmentIn,
    AssessmentOut,
    GraphOut,
    ProgressOut,
    RecommendationOut,
    RoleDetailOut,
    RoleOut,
)

# Configure basic logging; in production, integrate with structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Allowed CORS origin for local React app
ALLOWED_ORIGINS = ["http://localhost:3000"]

app = FastAPI(
    title="Career Navigator Backend",
    description="Backend API for role/skill mappings, recommendations, and progress tracking.",
    version="0.1.0",
    openapi_tags=[
        {"name": "health", "description": "Service health and metadata"},
        {"name": "roles", "description": "Role and role details APIs"},
        {"name": "progress", "description": "Progress tracking APIs"},
        {"name": "graph", "description": "Graph construction APIs for D3"},
        {"name": "assessments", "description": "Role gap assessment APIs"},
        {"name": "recommendations", "description": "Recommendations APIs"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialize database, create tables, and seed minimal dataset if empty."""
    try:
        Base.metadata.create_all(bind=engine)
        with next(get_db()) as session:  # type: ignore[assignment]
            # Seed only if DB is empty of roles
            if not RoleRepository(session).list_roles():
                seed_minimal_dataset(session)
                session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Startup initialization failed")
        # Do not crash the app; it can still run, but dataset may be empty


# PUBLIC_INTERFACE
@app.get("/", tags=["health"], summary="Health Check")
def health_check() -> dict:
    """Return a simple health payload."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.get(
    "/roles",
    tags=["roles"],
    response_model=List[RoleOut],
    summary="List roles",
    description="Returns all available roles.",
)
def list_roles(db: Session = Depends(get_db)) -> List[RoleOut]:
    """List all roles."""
    try:
        repo = RoleRepository(db)
        return repo.list_roles()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to list roles")
        raise HTTPException(status_code=500, detail="Unable to list roles")


# PUBLIC_INTERFACE
@app.get(
    "/roles/{role_name}",
    tags=["roles"],
    response_model=RoleDetailOut,
    summary="Get role detail",
    description="Return role details, including required skills and recommendations.",
)
def get_role_detail(role_name: str, db: Session = Depends(get_db)) -> RoleDetailOut:
    """Fetch a role with its required skills and recommendations."""
    repo = RoleRepository(db)
    role: Optional[Role] = repo.get_role_by_name(_sanitize(role_name))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    # Trigger lazy relationships to serialize nested content
    _ = [rs.recommendations for rs in role.skills]  # noqa: F841
    return role  # type: ignore[return-value]


# PUBLIC_INTERFACE
@app.get(
    "/roles/{role_name}/progress",
    tags=["progress"],
    response_model=List[ProgressOut],
    summary="List progress by role",
    description="Returns progress entries for a given role.",
)
def get_role_progress(role_name: str, db: Session = Depends(get_db)) -> List[ProgressOut]:
    """List progress items for a given role."""
    rrepo = RoleRepository(db)
    prepo = ProgressRepository(db)
    role = rrepo.get_role_by_name(_sanitize(role_name))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        return prepo.list_role_progress(role)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to list progress")
        raise HTTPException(status_code=500, detail="Unable to list progress")


# PUBLIC_INTERFACE
@app.post(
    "/roles/{role_name}/progress",
    tags=["progress"],
    response_model=ProgressOut,
    summary="Set progress",
    description="Create or update progress for a skill within the specified role.",
)
def set_progress(
    role_name: str,
    skill_name: str = Query(..., min_length=2, max_length=200, description="Skill name"),
    status: str = Query(..., pattern="^(not_started|working_on|complete)$", description="Progress status"),
    current_level: int = Query(..., ge=0, le=5, description="Current skill level"),
    db: Session = Depends(get_db),
) -> ProgressOut:
    """
    Create or update a progress entry for a given role and skill.

    Parameters:
    - role_name: The role to associate the progress with.
    - skill_name: The skill name to update progress for.
    - status: One of not_started, working_on, complete.
    - current_level: An integer between 0 and 5.
    """
    rrepo = RoleRepository(db)
    role = rrepo.get_role_by_name(_sanitize(role_name))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Validate skill is part of the role's required skills
    clean_skill = _sanitize(skill_name)
    rs: Optional[RoleSkill] = next((x for x in role.skills if x.skill.name == clean_skill), None)  # type: ignore[attr-defined]
    if not rs:
        # Provide a clear validation error and include valid skills for UI hints
        valid = sorted({x.skill.name for x in role.skills})
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid skill_name for this role. Only role-required skills are allowed.",
                "invalid_skill": clean_skill,
                "role": role.name,
                "valid_skills": valid,
            },
        )

    prepo = ProgressRepository(db)
    try:
        progress = prepo.set_progress(role, rs.skill, status=_sanitize(status), current_level=int(current_level))
        db.commit()
        return progress  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:  # noqa: BLE001
        logger.exception("Failed to set progress")
        raise HTTPException(status_code=500, detail="Unable to set progress")


# PUBLIC_INTERFACE
@app.get(
    "/graph",
    tags=["graph"],
    response_model=GraphOut,
    summary="Generate role transition graph",
    description="Returns D3-friendly {nodes, links, meta} graph from a current role to a target role.",
)
def get_graph(
    fromRole: int = Query(..., ge=1, description="Current role ID"),
    toRole: int = Query(..., ge=1, description="Target role ID"),
    db: Session = Depends(get_db),
) -> GraphOut:
    """
    Build a D3-friendly graph showing current role, target role, skill nodes,
    and links encoding required levels and gaps.
    """
    try:
        rrepo = RoleRepository(db)
        current = _get_role_by_id(rrepo, fromRole)
        target = _get_role_by_id(rrepo, toRole)
        if not current or not target:
            raise HTTPException(status_code=404, detail="Role not found")

        # Prepare map for quick lookup of required levels
        current_req: Dict[str, int] = {rs.skill.name: rs.required_level for rs in current.skills}
        target_req: Dict[str, int] = {rs.skill.name: rs.required_level for rs in target.skills}

        # Nodes: two roles + union of skills
        nodes = []
        links = []

        # Add role nodes
        nodes.append({"id": f"role:{current.id}", "type": "role", "label": current.name})
        nodes.append({"id": f"role:{target.id}", "type": "role", "label": target.name})

        # Skills are unified from both roles
        all_skill_names = set(list(current_req.keys()) + list(target_req.keys()))
        for sname in sorted(all_skill_names):
            # Skill node
            nodes.append({"id": f"skill:{sname}", "type": "skill", "label": sname})

            # Link current role -> skill with required level if present
            if sname in current_req:
                links.append(
                    {
                        "source": f"role:{current.id}",
                        "target": f"skill:{sname}",
                        "type": "requires",
                        "level": current_req[sname],
                        "from": "current",
                    }
                )
            # Link target role -> skill
            if sname in target_req:
                links.append(
                    {
                        "source": f"role:{target.id}",
                        "target": f"skill:{sname}",
                        "type": "requires",
                        "level": target_req[sname],
                        "from": "target",
                    }
                )

        meta = {
            "fromRole": {"id": current.id, "name": current.name},
            "toRole": {"id": target.id, "name": target.name},
            "stats": {
                "skillsCurrent": len(current_req),
                "skillsTarget": len(target_req),
                "skillsUnion": len(all_skill_names),
            },
        }
        return {"nodes": nodes, "links": links, "meta": meta}  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Failed to construct graph")
        raise HTTPException(status_code=500, detail="Unable to build graph")


# PUBLIC_INTERFACE
@app.get(
    "/recommendations",
    tags=["recommendations"],
    response_model=List[RecommendationOut],
    summary="List recommendations for a role and skill",
    description="Returns recommendations given a roleId and a skillId.",
)
def get_recommendations(
    roleId: int = Query(..., ge=1, description="Role ID"),
    skillId: int = Query(..., ge=1, description="Skill ID"),
    db: Session = Depends(get_db),
) -> List[RecommendationOut]:
    """
    Fetch actionable recommendations for the role-skill mapping.
    """
    repo = RoleRepository(db)
    role = _get_role_by_id(repo, roleId)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    # find the role-skill mapping
    rs = next((x for x in role.skills if x.skill_id == skillId), None)
    if not rs:
        raise HTTPException(status_code=404, detail="Role-skill not found")
    try:
        # Return list of Recommendation models, Pydantic will convert
        recs: List[Recommendation] = rs.recommendations
        return recs  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch recommendations")
        raise HTTPException(status_code=500, detail="Unable to fetch recommendations")


# PUBLIC_INTERFACE
@app.post(
    "/assessments",
    tags=["assessments"],
    response_model=AssessmentOut,
    summary="Assess strengths and gaps from current role to target role",
    description="Compares required levels and returns strengths and gaps.",
)
def assess_roles(payload: AssessmentIn, db: Session = Depends(get_db)) -> AssessmentOut:
    """
    Compute strengths and gaps comparing required levels between current and target roles.
    """
    rrepo = RoleRepository(db)
    current = _get_role_by_id(rrepo, int(payload.currentRoleId))
    target = _get_role_by_id(rrepo, int(payload.targetRoleId))
    if not current or not target:
        raise HTTPException(status_code=404, detail="Role not found")

    # Dict skill -> level
    current_req: Dict[str, int] = {rs.skill.name: rs.required_level for rs in current.skills}
    target_req: Dict[str, int] = {rs.skill.name: rs.required_level for rs in target.skills}

    strengths: List[Dict[str, object]] = []
    gaps: List[Dict[str, object]] = []

    for sname, t_level in target_req.items():
        c_level = current_req.get(sname)
        if c_level is None:
            gaps.append({"skill": sname, "current": 0, "required": t_level, "gap": t_level})
        else:
            diff = t_level - c_level
            if diff > 0:
                gaps.append({"skill": sname, "current": c_level, "required": t_level, "gap": diff})
            else:
                strengths.append({"skill": sname, "current": c_level, "required": t_level, "gap": diff})

    meta = {"currentRole": {"id": current.id, "name": current.name}, "targetRole": {"id": target.id, "name": target.name}}
    return {"strengths": strengths, "gaps": gaps, "meta": meta}  # type: ignore[return-value]


def _get_role_by_id(repo: RoleRepository, role_id: int) -> Optional[Role]:
    """Helper to find a role by ID using list cache; SQLAlchemy simple approach."""
    if role_id is None or role_id < 1:
        return None
    roles = repo.list_roles()
    for r in roles:
        if r.id == role_id:
            return r
    return None


def _sanitize(value: str) -> str:
    """Basic sanitization for string inputs to avoid odd characters and trim."""
    if value is None:
        return ""
    v = value.strip()
    # remove control characters
    return re.sub(r"[\x00-\x1f\x7f]+", "", v)
