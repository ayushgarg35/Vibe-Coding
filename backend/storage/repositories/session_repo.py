"""
Session Repository — all database operations for sessions.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import AuditLog, Session

log = structlog.get_logger()


class SessionRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(
        self,
        *,
        org_id: str,
        created_by: str,
        entry_mode: str = "freeform",
        data_region: str = "US",
        product_name: str | None = None,
    ) -> Session:
        session = Session(
            id=uuid.uuid4(),
            org_id=uuid.UUID(org_id),
            created_by=uuid.UUID(created_by),
            entry_mode=entry_mode,
            data_region=data_region,
            product_name=product_name,
            current_phase="discovery",
            status="active",
        )
        self._db.add(session)
        await self._db.flush()
        await self._audit(
            org_id=org_id,
            user_id=created_by,
            session_id=str(session.id),
            action="session.created",
            resource_type="session",
            resource_id=str(session.id),
        )
        log.info("Session created", session_id=str(session.id), org_id=org_id)
        return session

    async def get(self, session_id: str) -> Session | None:
        result = await self._db.execute(
            select(Session).where(Session.id == uuid.UUID(session_id))
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, org_id: str, limit: int = 50, offset: int = 0) -> list[Session]:
        result = await self._db.execute(
            select(Session)
            .where(Session.org_id == uuid.UUID(org_id))
            .order_by(Session.last_activity.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_phase(self, session_id: str, phase: str) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == uuid.UUID(session_id))
            .values(current_phase=phase, last_activity=datetime.now(timezone.utc))
        )

    async def update_status(self, session_id: str, status: str) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == uuid.UUID(session_id))
            .values(status=status, last_activity=datetime.now(timezone.utc))
        )

    async def update_cost(self, session_id: str, additional_cost: float) -> None:
        session = await self.get(session_id)
        if session:
            new_cost = float(session.total_cost_usd or 0) + additional_cost
            await self._db.execute(
                update(Session)
                .where(Session.id == uuid.UUID(session_id))
                .values(total_cost_usd=new_cost)
            )

    async def update_product_name(self, session_id: str, name: str) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == uuid.UUID(session_id))
            .values(product_name=name, last_activity=datetime.now(timezone.utc))
        )

    async def touch(self, session_id: str) -> None:
        """Update last_activity — called on any user interaction."""
        await self._db.execute(
            update(Session)
            .where(Session.id == uuid.UUID(session_id))
            .values(last_activity=datetime.now(timezone.utc))
        )

    async def _audit(self, *, org_id: str, user_id: str, session_id: str, action: str,
                     resource_type: str, resource_id: str, metadata: dict | None = None) -> None:
        log_entry = AuditLog(
            org_id=uuid.UUID(org_id),
            user_id=uuid.UUID(user_id),
            session_id=uuid.UUID(session_id),
            action=action,
            resource_type=resource_type,
            resource_id=uuid.UUID(resource_id),
            metadata_=metadata,
        )
        self._db.add(log_entry)
