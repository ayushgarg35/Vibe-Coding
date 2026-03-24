"""
Decision Repository — maintains the decision ledger and assumption register.
Every confirmed fact, inferred assumption, and unresolved question is stored here.
This is the traceability backbone of the system.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import Assumption, Decision

log = structlog.get_logger()


class DecisionRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    # ── Decisions ─────────────────────────────────────────────────

    async def add_decision(
        self,
        *,
        session_id: str,
        decision_type: str,   # confirmed | assumed | unresolved
        category: str,
        statement: str,
        source: str,          # user_input | agent_inferred | system_default
        raised_by: str | None = None,
        affects_artifacts: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Decision:
        decision = Decision(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            type=decision_type,
            category=category,
            statement=statement,
            source=source,
            raised_by=uuid.UUID(raised_by) if raised_by else None,
            affects_artifacts=affects_artifacts,
            metadata_=metadata,
        )
        self._db.add(decision)
        await self._db.flush()
        return decision

    async def resolve_decision(self, decision_id: str, resolved_by: str) -> None:
        await self._db.execute(
            update(Decision)
            .where(Decision.id == uuid.UUID(decision_id))
            .values(
                type="confirmed",
                resolved_by=uuid.UUID(resolved_by),
                resolved_at=datetime.now(timezone.utc),
            )
        )

    async def get_decisions(
        self,
        session_id: str,
        decision_type: str | None = None,
    ) -> list[Decision]:
        stmt = select(Decision).where(Decision.session_id == uuid.UUID(session_id))
        if decision_type:
            stmt = stmt.where(Decision.type == decision_type)
        stmt = stmt.order_by(Decision.raised_at.asc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def sync_from_agent(self, session_id: str, decisions: list[dict]) -> None:
        """
        Bulk-sync decisions from agent output.
        Used after intake and gap detection to persist structured decisions.
        """
        for d in decisions:
            await self.add_decision(
                session_id=session_id,
                decision_type=d.get("type", "unresolved"),
                category=d.get("category", "general"),
                statement=d.get("statement", ""),
                source=d.get("source", "agent_inferred"),
                affects_artifacts=d.get("affects_artifacts"),
                metadata=d.get("metadata"),
            )

    # ── Assumptions ───────────────────────────────────────────────

    async def add_assumption(
        self,
        *,
        session_id: str,
        assumption: str,
        risk_if_wrong: str | None = None,
        owner: str | None = None,
    ) -> Assumption:
        record = Assumption(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            assumption=assumption,
            risk_if_wrong=risk_if_wrong,
            owner=uuid.UUID(owner) if owner else None,
            status="active",
        )
        self._db.add(record)
        await self._db.flush()
        return record

    async def validate_assumption(self, assumption_id: str) -> None:
        await self._db.execute(
            update(Assumption)
            .where(Assumption.id == uuid.UUID(assumption_id))
            .values(status="validated", validated_at=datetime.now(timezone.utc))
        )

    async def invalidate_assumption(self, assumption_id: str) -> None:
        await self._db.execute(
            update(Assumption)
            .where(Assumption.id == uuid.UUID(assumption_id))
            .values(status="invalidated")
        )

    async def get_assumptions(self, session_id: str, status: str | None = None) -> list[Assumption]:
        stmt = select(Assumption).where(Assumption.session_id == uuid.UUID(session_id))
        if status:
            stmt = stmt.where(Assumption.status == status)
        stmt = stmt.order_by(Assumption.created_at.asc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def sync_assumptions_from_agent(self, session_id: str, assumptions: list[dict]) -> None:
        """Bulk-sync assumptions from agent output."""
        for a in assumptions:
            await self.add_assumption(
                session_id=session_id,
                assumption=a.get("assumption", ""),
                risk_if_wrong=a.get("risk_if_wrong"),
            )
