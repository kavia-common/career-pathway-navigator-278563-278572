import json
import os
import logging

from src.api.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _write_openapi() -> None:
    """Generate and write OpenAPI schema JSON."""
    try:
        openapi_schema = app.openapi()
        output_dir = "interfaces"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "openapi.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, indent=2)
        logger.info("OpenAPI schema generated at %s", output_path)
    except Exception:
        logger.exception("Failed to generate OpenAPI")


if __name__ == "__main__":
    _write_openapi()
