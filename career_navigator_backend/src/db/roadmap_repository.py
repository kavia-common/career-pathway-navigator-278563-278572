import json
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Roadmap

logger = logging.getLogger(__name__)


class RoadmapRepository:
    """Repository for Roadmap persistence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # PUBLIC_INTERFACE
    def create(
        self,
        name: str,
        user_identifier: Optional[str],
        from_role_id: int,
        to_role_id: int,
        graph_payload: dict,
        notes: Optional[str] = None,
    ) -> Roadmap:
        """Create a new roadmap entry with validated fields."""
        nm = (name or "").strip()
        if not nm:
            raise ValueError("name is required")
        if not isinstance(from_role_id, int) or from_role_id < 1:
            raise ValueError("from_role_id must be a positive integer")
        if not isinstance(to_role_id, int) or to_role_id < 1:
            raise ValueError("to_role_id must be a positive integer")
        # Serialize payload deterministically
        try:
            payload_str = json.dumps(graph_payload or {}, separators=(",", ":"), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("graph_payload must be JSON-serializable") from exc

        rm = Roadmap(
            name=nm,
            user_identifier=(user_identifier or None),
            from_role_id=from_role_id,
            to_role_id=to_role_id,
            graph_payload=payload_str,
            notes=(notes or None),
        )
        self.session.add(rm)
        self.session.flush()
        return rm

    # PUBLIC_INTERFACE
    def list(self, user_identifier: Optional[str] = None) -> List[Roadmap]:
        """List roadmaps, optionally filtered by user_identifier."""
        stmt = select(Roadmap).order_by(Roadmap.updated_at.desc())
        if user_identifier and user_identifier.strip():
            stmt = stmt.where(Roadmap.user_identifier == user_identifier.strip())
        return list(self.session.scalars(stmt).all())

    # PUBLIC_INTERFACE
    def get(self, roadmap_id: int, user_identifier: Optional[str] = None) -> Optional[Roadmap]:
        """Fetch a roadmap by ID, optionally ensuring ownership by user_identifier."""
        if not roadmap_id or int(roadmap_id) < 1:
            return None
        stmt = select(Roadmap).where(Roadmap.id == int(roadmap_id))
        if user_identifier and user_identifier.strip():
            stmt = stmt.where(Roadmap.user_identifier == user_identifier.strip())
        return self.session.scalars(stmt).first()

    # PUBLIC_INTERFACE
    def update(
        self,
        roadmap: Roadmap,
        name: Optional[str] = None,
        graph_payload: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> Roadmap:
        """Update mutable fields of a Roadmap."""
        if name is not None:
            nm = name.strip()
            if not nm:
                raise ValueError("name cannot be empty")
            roadmap.name = nm
        if graph_payload is not None:
            try:
                roadmap.graph_payload = json.dumps(graph_payload, separators=(",", ":"), ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("graph_payload must be JSON-serializable") from exc
        if notes is not None:
            roadmap.notes = notes or None
        self.session.flush()
        return roadmap

    # PUBLIC_INTERFACE
    def delete(self, roadmap: Roadmap) -> None:
        """Delete a roadmap."""
        self.session.delete(roadmap)
        self.session.flush()
