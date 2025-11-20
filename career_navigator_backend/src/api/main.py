import logging
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.db.database import Base, engine, get_db
from src.db.models import Role, RoleSkill
from src.db.repositories import ProgressRepository, RoleRepository
from src.db.seed import seed_minimal_dataset
from src.schemas.schemas import ProgressOut, RoleDetailOut, RoleOut

# Configure basic logging; in production, integrate with structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Career Navigator Backend",
    description="Backend API for role/skill mappings, recommendations, and progress tracking.",
    version="0.1.0",
    openapi_tags=[
        {"name": "health", "description": "Service health and metadata"},
        {"name": "roles", "description": "Role and role details APIs"},
        {"name": "progress", "description": "Progress tracking APIs"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict origins via env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialize database, create tables, and seed minimal dataset."""
    try:
        Base.metadata.create_all(bind=engine)
        with next(get_db()) as session:  # type: ignore[assignment]
            seed_minimal_dataset(session)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Startup initialization failed: %s", exc)
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
    repo = RoleRepository(db)
    return repo.list_roles()


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
    role: Optional[Role] = repo.get_role_by_name(role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    # Eager-like access to include nested relationships in response
    # SQLAlchemy 2.0 will lazy load by default in this structure
    _ = [rs.recommendations for rs in role.skills]  # touch to ensure serialization has nested data
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
    role = rrepo.get_role_by_name(role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return prepo.list_role_progress(role)


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
    role = rrepo.get_role_by_name(role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Validate skill is part of the role's required skills
    rs: Optional[RoleSkill] = next((rs for rs in role.skills if rs.skill.name == skill_name), None)  # type: ignore[attr-defined]
    if not rs:
        raise HTTPException(status_code=400, detail="Skill not required for this role")

    prepo = ProgressRepository(db)
    try:
        progress = prepo.set_progress(role, rs.skill, status=status, current_level=current_level)
        db.commit()
        return progress  # type: ignore[return-value]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
