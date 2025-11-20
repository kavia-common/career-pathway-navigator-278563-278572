"""
API package initialization.

Re-exports the FastAPI app instance for external tooling (e.g., OpenAPI generation).
"""
from .main import app  # noqa: F401
