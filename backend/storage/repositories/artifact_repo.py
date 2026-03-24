"""
Artifact Repository — versioned storage for all product artifacts.
Handles BRD, PRD, FRD, Stories, Screen Specs, Review Packs, Handoff Packs.
"""
import uuid

import semver
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import Artifact, AuditLog

log = structlog.get_logger()


class ArtifactRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(
        self,
        *,
        session_id: str,
        artifact_type: str,
        content: dict,
        model_used: str | None = None,
        cost_usd: float = 0.0,
        created_by: str | None = None,
        lineage: list[str] | None = None,
    ) -> Artifact:
        """Create a new artifact at version 0.1.0."""
        artifact = Artifact(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            type=artifact_type,
            version="0.1.0",
            status="draft",
            content=content,
            model_used=model_used,
            cost_usd=cost_usd,
            created_by=uuid.UUID(created_by) if created_by else None,
            lineage=[uuid.UUID(lid) for lid in lineage] if lineage else None,
        )
        self._db.add(artifact)
        await self._db.flush()
        log.info("Artifact created", artifact_id=str(artifact.id), type=artifact_type, session_id=session_id)
        return artifact

    async def get_latest(self, session_id: str, artifact_type: str) -> Artifact | None:
        """Get the most recently created artifact of a given type for a session."""
        result = await self._db.execute(
            select(Artifact)
            .where(
                Artifact.session_id == uuid.UUID(session_id),
                Artifact.type == artifact_type,
            )
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_versions(self, session_id: str, artifact_type: str) -> list[Artifact]:
        """Get all versions of an artifact — for version history UI."""
        result = await self._db.execute(
            select(Artifact)
            .where(
                Artifact.session_id == uuid.UUID(session_id),
                Artifact.type == artifact_type,
            )
            .order_by(Artifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, artifact_id: str) -> Artifact | None:
        result = await self._db.execute(
            select(Artifact).where(Artifact.id == uuid.UUID(artifact_id))
        )
        return result.scalar_one_or_none()

    async def list_for_session(self, session_id: str) -> list[Artifact]:
        """Get all artifacts across all types for a session."""
        result = await self._db.execute(
            select(Artifact)
            .where(Artifact.session_id == uuid.UUID(session_id))
            .order_by(Artifact.created_at.asc())
        )
        return list(result.scalars().all())

    async def approve(self, artifact_id: str, approved_by: str) -> Artifact | None:
        """Mark artifact as approved and bump patch version."""
        from datetime import datetime, timezone
        from sqlalchemy import update

        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None

        # Bump version: 0.1.0 → 0.1.1 on approval
        try:
            bumped = str(semver.Version.parse(artifact.version).bump_patch())
        except ValueError:
            bumped = artifact.version

        await self._db.execute(
            update(Artifact)
            .where(Artifact.id == uuid.UUID(artifact_id))
            .values(
                status="approved",
                approved_by=uuid.UUID(approved_by),
                approved_at=datetime.now(timezone.utc),
                version=bumped,
            )
        )
        log.info("Artifact approved", artifact_id=artifact_id, version=bumped)
        return await self.get_by_id(artifact_id)

    async def request_revision(self, artifact_id: str) -> None:
        from sqlalchemy import update
        await self._db.execute(
            update(Artifact)
            .where(Artifact.id == uuid.UUID(artifact_id))
            .values(status="revision_requested")
        )

    async def create_revision(
        self,
        *,
        original_artifact_id: str,
        new_content: dict,
        model_used: str | None = None,
        cost_usd: float = 0.0,
    ) -> Artifact:
        """Create a new version of an existing artifact, bumping the minor version."""
        original = await self.get_by_id(original_artifact_id)
        if not original:
            raise ValueError(f"Original artifact {original_artifact_id} not found")

        try:
            bumped = str(semver.Version.parse(original.version).bump_minor())
        except ValueError:
            bumped = original.version

        revised = Artifact(
            id=uuid.uuid4(),
            session_id=original.session_id,
            type=original.type,
            version=bumped,
            status="draft",
            content=new_content,
            model_used=model_used,
            cost_usd=cost_usd,
            lineage=[original.id],
        )
        self._db.add(revised)
        await self._db.flush()
        log.info("Artifact revision created", artifact_id=str(revised.id), version=bumped, type=original.type)
        return revised
