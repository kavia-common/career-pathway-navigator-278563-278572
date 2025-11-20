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

Environment
- DATABASE_URL (optional): defaults to sqlite:///./data/app.db
- ALLOW_ALL_CORS (optional): "true" by default, allows all origins without credentials.
- ALLOWED_CORS_ORIGINS (optional): comma-separated origins used when ALLOW_ALL_CORS is not true.

Troubleshooting 502
- Ensure backend container is running and /docs loads.
- If /roles or /graph return 502, check backend logs for unhandled exceptions.
- The app seeds a minimal dataset at startup; if seeding fails, the app still starts but roles may be empty.
- /graph requires valid fromRole and toRole IDs and they must be different.