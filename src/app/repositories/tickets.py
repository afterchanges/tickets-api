from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.models.ticket_event import TicketEvent


def _uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(value)


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID, *, include_related: bool = False) -> Ticket | None:
    stmt: Select[tuple[Ticket]] = select(Ticket).where(Ticket.id == ticket_id)
    if include_related:
        stmt = stmt.options(selectinload(Ticket.reporter), selectinload(Ticket.assignee))
    return await db.scalar(stmt)


async def list_tickets(
    db: AsyncSession,
    *,
    status=None,
    priority=None,
    assignee_id: uuid.UUID | None = None,
    reporter_id: uuid.UUID | None = None,
    tag: str | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    include_deleted: bool = False,
    sort: list = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    stmt = select(Ticket)

    conditions = []
    if not include_deleted:
        conditions.append(Ticket.is_deleted.is_(False))
    if status is not None:
        conditions.append(Ticket.status == status)
    if priority is not None:
        conditions.append(Ticket.priority == priority)
    if assignee_id is not None:
        conditions.append(Ticket.assignee_id == assignee_id)
    if reporter_id is not None:
        conditions.append(Ticket.reporter_id == reporter_id)
    if tag is not None:
        conditions.append(Ticket.tags.any(tag))
    if q:
        like = f"%{q}%"
        conditions.append(or_(Ticket.title.ilike(like), Ticket.description.ilike(like)))
    if created_from is not None:
        conditions.append(Ticket.created_at >= created_from)
    if created_to is not None:
        conditions.append(Ticket.created_at <= created_to)
    if due_from is not None:
        conditions.append(Ticket.due_at >= due_from)
    if due_to is not None:
        conditions.append(Ticket.due_at <= due_to)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(await db.scalar(count_stmt) or 0)

    if sort:
        stmt = stmt.order_by(*sort)
    else:
        stmt = stmt.order_by(Ticket.created_at.desc())

    stmt = stmt.limit(limit).offset(offset)
    items = list((await db.scalars(stmt)).all())
    return items, total


async def create_ticket(
    db: AsyncSession,
    *,
    title: str,
    description: str,
    priority,
    reporter_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
    due_at: datetime | None,
    tags: list[str],
) -> Ticket:
    ticket = Ticket(
        title=title,
        description=description,
        priority=priority,
        reporter_id=reporter_id,
        assignee_id=assignee_id,
        due_at=due_at,
        tags=tags,
    )
    db.add(ticket)
    await db.flush()
    return ticket


async def add_event(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    actor_id: uuid.UUID,
    event_type: str,
    old_value: dict | None,
    new_value: dict | None,
) -> TicketEvent:
    ev = TicketEvent(
        ticket_id=ticket_id,
        actor_id=actor_id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(ev)
    await db.flush()
    return ev


async def list_events(db: AsyncSession, *, ticket_id: uuid.UUID) -> list[TicketEvent]:
    stmt = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id).order_by(TicketEvent.created_at.asc())
    return list((await db.scalars(stmt)).all())


async def add_comment(db: AsyncSession, *, ticket_id: uuid.UUID, author_id: uuid.UUID, body: str) -> TicketComment:
    comment = TicketComment(ticket_id=ticket_id, author_id=author_id, body=body)
    db.add(comment)
    await db.flush()
    return comment


async def list_comments(db: AsyncSession, *, ticket_id: uuid.UUID) -> list[TicketComment]:
    stmt = select(TicketComment).where(TicketComment.ticket_id == ticket_id).order_by(TicketComment.created_at.asc())
    return list((await db.scalars(stmt)).all())
