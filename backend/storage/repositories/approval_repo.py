"""
Approval Gate Repository — manages gate state and review history.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import ApprovalGate, AuditLog

log = structlog.get_logger()


class ApprovalGateRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def upsert(
        self,
        *,
        session_id: str,
        gate_number: int,
        artifact_ids: list[str] | None = None,
        auto_review_id: str | None = None,
    ) -> ApprovalGate:
        """Create or reset a gate when an artifact is ready for review."""
        existing = await self.get(session_id, gate_number)
        if existing:
            await self._db.execute(
                update(ApprovalGate)
                .where(ApprovalGate.id == existing.id)
                .values(
                    status="pending",
                    artifact_ids=[uuid.UUID(a) for a in (artifact_ids or [])],
                    auto_review_id=uuid.UUID(auto_review_id) if auto_review_id else None,
                    reviewed_at=None,
                    reviewer_id=None,
                    comments=None,
                    redlines=None,
                )
            )
            return existing

        gate = ApprovalGate(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            gate_number=gate_number,
            artifact_ids=[uuid.UUID(a) for a in (artifact_ids or [])],
            status="pending",
            auto_review_id=uuid.UUID(auto_review_id) if auto_review_id else None,
        )
        self._db.add(gate)
        await self._db.flush()
        log.info("Approval gate created", session_id=session_id, gate=gate_number)
        return gate

    async def get(self, session_id: str, gate_number: int) -> ApprovalGate | None:
        result = await self._db.execute(
            select(ApprovalGate).where(
                ApprovalGate.session_id == uuid.UUID(session_id),
                ApprovalGate.gate_number == gate_number,
            )
        )
        return result.scalar_one_or_none()

    async def submit_decision(
        self,
        *,
        session_id: str,
        gate_number: int,
        status: str,           # approved | revision_requested | rejected
        reviewer_id: str,
        comments: str | None = None,
        redlines: dict | None = None,
        org_id: str | None = None,
    ) -> ApprovalGate | None:
        gate = await self.get(session_id, gate_number)
        if not gate:
            return None

        await self._db.execute(
            update(ApprovalGate)
            .where(ApprovalGate.id == gate.id)
            .values(
                status=status,
                reviewer_id=uuid.UUID(reviewer_id),
                reviewed_at=datetime.now(timezone.utc),
                comments=comments,
                redlines=redlines,
            )
        )

        # Audit the decision
        audit = AuditLog(
            org_id=uuid.UUID(org_id) if org_id else None,
            user_id=uuid.UUID(reviewer_id),
            session_id=uuid.UUID(session_id),
            action=f"gate.{status}",
            resource_type="approval_gate",
            resource_id=gate.id,
            metadata_={"gate_number": gate_number, "comments": comments},
        )
        self._db.add(audit)

        log.info(
            "Gate decision recorded",
            session_id=session_id,
            gate=gate_number,
            status=status,
            reviewer=reviewer_id,
        )
        return await self.get(session_id, gate_number)

    async def get_all_for_session(self, session_id: str) -> list[ApprovalGate]:
        result = await self._db.execute(
            select(ApprovalGate)
            .where(ApprovalGate.session_id == uuid.UUID(session_id))
            .order_by(ApprovalGate.gate_number.asc())
        )
        return list(result.scalars().all())
