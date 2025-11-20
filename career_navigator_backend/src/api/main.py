import logging
import os
import re
import urllib.parse
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from src.db.database import Base, engine, get_db, ensure_sqlite_schema_compatibility
from src.db.models import Recommendation, Role, RoleSkill
from src.db.repositories import ProgressRepository, RoleRepository
from src.db.seed import seed_minimal_dataset_idempotent
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

# Allowed CORS configuration:
# - When ALLOW_ALL_CORS=true (default for preview), allow all origins/methods/headers with allow_credentials=False
# - Otherwise, use ALLOWED_CORS_ORIGINS (comma-separated), falling back to defaults for localhost/preview.
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    # Default preview origin (update as needed)
    "https://vscode-internal-11652-beta.beta01.cloud.kavia.ai:3000",
]
_env_allow_all = os.environ.get("ALLOW_ALL_CORS", "true").strip().lower()  # default to true for preview convenience
ALLOW_ALL_CORS = _env_allow_all in {"1", "true", "yes", "y"}

_env_origins = os.environ.get("ALLOWED_CORS_ORIGINS")
if _env_origins:
    # sanitize and split, ignore empty parts
    ALLOWED_ORIGINS = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = DEFAULT_ALLOWED_ORIGINS

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

# Configure CORS.
# If ALLOW_ALL_CORS is enabled, use wildcard origins/methods/headers and keep allow_credentials False
# to comply with CORS rules (wildcard cannot be combined with credentials).
if ALLOW_ALL_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # must be False when using wildcard origins
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Explicit list of allowed origins; adjust via ALLOWED_CORS_ORIGINS env var.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,  # set True only if cookies/auth are required and not using "*"
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def on_startup() -> None:
    """
    Initialize database, create tables, run lightweight schema migrations, and always run idempotent seeding.
    Seeding is safe to run repeatedly; it upserts by stable names.
    """
    try:
        Base.metadata.create_all(bind=engine)

        # Ensure runtime SQLite schema is compatible with current models (adds missing columns)
        ensure_sqlite_schema_compatibility()

        # Ensure we have a session and handle its lifecycle robustly
        db_gen = get_db()
        session = next(db_gen)  # type: ignore[assignment]
        try:
            # Always run idempotent seeding regardless of current data
            seed_minimal_dataset_idempotent(session)
            session.commit()
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
            try:
                session.close()
            except Exception:
                logger.warning("Error closing DB session on startup")
    except Exception:  # noqa: BLE001
        logger.exception("Startup initialization failed")
        # Do not crash the app; it can still run, but dataset may be incomplete


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
    except SQLAlchemyError:
        logger.exception("DB error while listing roles")
        raise HTTPException(status_code=500, detail="Database error while listing roles")
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
    try:
        # Decode %20 and other encodings, then sanitize
        clean_name = _sanitize(urllib.parse.unquote(role_name))

        # Eager load nested relationships to avoid lazy-load after session issues
        role: Optional[Role] = (
            db.query(Role)
            .options(
                joinedload(Role.skills).joinedload(RoleSkill.recommendations),
                joinedload(Role.skills).joinedload(RoleSkill.skill),
            )
            .filter(Role.name == clean_name)
            .first()
        )
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        return role  # type: ignore[return-value]
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("DB error while fetching role detail")
        raise HTTPException(status_code=500, detail="Database error while fetching role")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch role detail")
        raise HTTPException(status_code=500, detail="Unable to fetch role")


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
    clean_name = _sanitize(urllib.parse.unquote(role_name))
    role = rrepo.get_role_by_name(clean_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        return prepo.list_role_progress(role)
    except SQLAlchemyError:
        logger.exception("DB error while listing progress")
        raise HTTPException(status_code=500, detail="Database error while listing progress")
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
    role = rrepo.get_role_by_name(_sanitize(urllib.parse.unquote(role_name)))
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
    except SQLAlchemyError:
        logger.exception("DB error while setting progress")
        raise HTTPException(status_code=500, detail="Database error while setting progress")
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

    Deterministic gap enforcement:
    - Compute natural gaps where target requires a higher level than current.
    - If fewer than desired minimum (2), deterministically add highest-priority
      target skills to highlight as forced gaps in the response ONLY (no DB writes).
    - Forced gaps are chosen by: equal-level skills (sorted by target required level desc),
      then remaining highest target skills if still needed.

    The response also includes meta.stats counters: gapLinks, gapNodes, naturalGaps, forcedGaps,
    and desiredMinGaps/desiredMaxGaps to aid verification.
    """
    # early param guard
    if fromRole == toRole:
        raise HTTPException(status_code=400, detail="fromRole and toRole must be different")
    try:
        # Load roles eagerly (with skills->skill) to avoid lazy-load issues during serialization
        current: Optional[Role] = (
            db.query(Role)
            .options(joinedload(Role.skills).joinedload(RoleSkill.skill))
            .filter(Role.id == int(fromRole))
            .first()
        )
        target: Optional[Role] = (
            db.query(Role)
            .options(joinedload(Role.skills).joinedload(RoleSkill.skill))
            .filter(Role.id == int(toRole))
            .first()
        )
        if not current or not target:
            raise HTTPException(status_code=404, detail="Role not found")

        # Prepare map for quick lookup of required levels
        current_req: Dict[str, int] = {rs.skill.name: int(rs.required_level) for rs in current.skills}
        target_req: Dict[str, int] = {rs.skill.name: int(rs.required_level) for rs in target.skills}

        # Determine natural gaps (target requires more)
        natural_gap_skills = [s for s, t_level in target_req.items() if t_level > int(current_req.get(s, 0))]

        # Enforce deterministic minimum of 2 gaps (prefer up to 3 for richer visuals)
        DESIRED_MIN_GAPS = 2
        DESIRED_MAX_GAPS = 3
        final_gap_skills = list(dict.fromkeys(natural_gap_skills))  # preserve order

        if len(final_gap_skills) < DESIRED_MIN_GAPS:
            # Candidates where levels are equal (no natural gap); prefer higher required levels first
            equal_candidates = [
                s for s in target_req.keys() if s not in final_gap_skills and target_req[s] == int(current_req.get(s, 0))
            ]
            equal_candidates.sort(key=lambda s: int(target_req[s]), reverse=True)
            for s in equal_candidates:
                if len(final_gap_skills) >= DESIRED_MIN_GAPS:
                    break
                final_gap_skills.append(s)

        if len(final_gap_skills) < DESIRED_MIN_GAPS:
            # As a last resort, pick remaining target skills by highest required level
            remainder = [s for s in target_req.keys() if s not in final_gap_skills]
            remainder.sort(key=lambda s: int(target_req[s]), reverse=True)
            for s in remainder:
                if len(final_gap_skills) >= DESIRED_MIN_GAPS:
                    break
                final_gap_skills.append(s)

        # Optionally limit to 3 for visual clarity (while still >=2)
        if len(final_gap_skills) > DESIRED_MAX_GAPS:
            final_gap_skills = final_gap_skills[:DESIRED_MAX_GAPS]

        forced_gap_skills = [s for s in final_gap_skills if s not in natural_gap_skills]

        # Nodes: two roles + union of skills
        nodes: List[Dict[str, object]] = []
        links: List[Dict[str, object]] = []

        # Add role nodes
        nodes.append({"id": f"role:{current.id}", "type": "role", "label": current.name})
        nodes.append({"id": f"role:{target.id}", "type": "role", "label": target.name})

        # Build fast map for role-skill annotations where available (unused for decisioning, but preserves explicit colors)
        def rs_map(role_obj: Role) -> Dict[str, RoleSkill]:
            out: Dict[str, RoleSkill] = {}
            for rs in role_obj.skills:
                out[rs.skill.name] = rs
            return out

        current_rs_by_skill = rs_map(current)
        target_rs_by_skill = rs_map(target)

        # Skills are unified from both roles
        all_skill_names = set(list(current_req.keys()) + list(target_req.keys()))
        GAP_COLOR = "#ef4444"
        for sname in sorted(all_skill_names):
            c_level = int(current_req.get(sname, 0))
            t_level = int(target_req.get(sname, 0))
            is_gap = sname in final_gap_skills

            # Node color: force red for gaps; otherwise use explicit role-skill color if present
            node_color: Optional[str] = GAP_COLOR if is_gap else None
            if not is_gap:
                if sname in target_rs_by_skill and target_rs_by_skill[sname].color:
                    node_color = target_rs_by_skill[sname].color
                elif sname in current_rs_by_skill and current_rs_by_skill[sname].color:
                    node_color = current_rs_by_skill[sname].color

            nodes.append(
                {
                    "id": f"skill:{sname}",
                    "type": "skill",
                    "label": sname,
                    "color": node_color,
                    "is_gap": bool(is_gap),
                }
            )

            # Link current role -> skill with required level if present
            if sname in current_req:
                cur_color = current_rs_by_skill.get(sname).color if current_rs_by_skill.get(sname) else None
                links.append(
                    {
                        "source": f"role:{current.id}",
                        "target": f"skill:{sname}",
                        "type": "requires",
                        "level": c_level,
                        "from": "current",
                        "color": cur_color,
                        "is_gap": False,
                    }
                )
            # Link target role -> skill
            if sname in target_req:
                # Force red and is_gap for final gap skills
                tgt_color = GAP_COLOR if is_gap else None
                # If not a gap, preserve any explicit color set in role-skill
                if not is_gap and target_rs_by_skill.get(sname) and target_rs_by_skill[sname].color:
                    tgt_color = target_rs_by_skill[sname].color

                links.append(
                    {
                        "source": f"role:{target.id}",
                        "target": f"skill:{sname}",
                        "type": "requires",
                        "level": t_level,
                        "from": "target",
                        "color": tgt_color,
                        "is_gap": bool(is_gap),
                    }
                )

        # Stats to quickly verify minimum gaps
        gap_link_count = sum(1 for l in links if l.get("from") == "target" and l.get("is_gap") is True)
        gap_node_count = sum(1 for n in nodes if n.get("type") == "skill" and n.get("is_gap") is True)

        meta = {
            "fromRole": {"id": current.id, "name": current.name},
            "toRole": {"id": target.id, "name": target.name},
            "stats": {
                "skillsCurrent": len(current_req),
                "skillsTarget": len(target_req),
                "skillsUnion": len(all_skill_names),
                "gapLinks": int(gap_link_count),
                "gapNodes": int(gap_node_count),
                "naturalGaps": int(len(natural_gap_skills)),
                "forcedGaps": int(len(forced_gap_skills)),
                "desiredMinGaps": int(DESIRED_MIN_GAPS),
                "desiredMaxGaps": int(DESIRED_MAX_GAPS),
            },
        }
        return {"nodes": nodes, "links": links, "meta": meta}  # type: ignore[return-value]
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("DB error while constructing graph")
        raise HTTPException(status_code=500, detail="Database error while building graph")
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
    except SQLAlchemyError:
        logger.exception("DB error while fetching recommendations")
        raise HTTPException(status_code=500, detail="Database error while fetching recommendations")
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
            gaps.append({"skill": sname, "current": 0, "required": int(t_level), "gap": int(t_level)})
        else:
            diff = int(t_level) - int(c_level)
            if diff > 0:
                gaps.append({"skill": sname, "current": int(c_level), "required": int(t_level), "gap": diff})
            else:
                strengths.append({"skill": sname, "current": int(c_level), "required": int(t_level), "gap": diff})

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
