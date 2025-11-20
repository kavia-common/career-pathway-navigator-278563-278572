# career-pathway-navigator-278563-278572

Backend (FastAPI) key endpoints:
- GET /roles
- GET /roles/{role_name}
- GET /roles/{role_name}/progress
- POST /roles/{role_name}/progress?skill_name=&status=&current_level=
- GET /graph?fromRole=&toRole=
- GET /recommendations?roleId=&skillId=
- POST /assessments { currentRoleId, targetRoleId }

Generate OpenAPI: `python -m src.api.generate_openapi` (writes to career_navigator_backend/interfaces/openapi.json)