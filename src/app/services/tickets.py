from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import NO_VALUE
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories import tickets as repo


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _snapshot(ticket: Ticket) -> dict:
    insp = inspect(ticket)

    def loaded(name: str):
        val = insp.attrs[name].loaded_value
        return None if val is NO_VALUE else val

    def iso(name: str) -> str | None:
        val = loaded(name)
        return val.isoformat() if val is not None else None

    return {
        "id": str(loaded("id")),
        "title": loaded("title"),
        "description": loaded("description"),
        "status": str(loaded("status")),
        "priority": str(loaded("priority")),
        "tags": list(loaded("tags") or []),
        "reporter_id": str(loaded("reporter_id")),
        "assignee_id": str(loaded("assignee_id")) if loaded("assignee_id") else None,
        "due_at": iso("due_at"),
        "closed_at": iso("closed_at"),
        "is_deleted": bool(loaded("is_deleted")),
        "version": loaded("version"),
        "created_at": iso("created_at"),
        "updated_at": iso("updated_at"),
    }


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _is_agent_or_admin(user: User) -> bool:
    return user.role in (UserRole.AGENT, UserRole.ADMIN)


def _can_access_ticket(user: User, ticket: Ticket) -> bool:
    if _is_agent_or_admin(user):
        return True
    return ticket.reporter_id == user.id


def _allowed_transition(old: TicketStatus, new: TicketStatus) -> bool:
    allowed: dict[TicketStatus, set[TicketStatus]] = {
        TicketStatus.NEW: {TicketStatus.IN_PROGRESS, TicketStatus.CANCELED},
        TicketStatus.IN_PROGRESS: {TicketStatus.DONE, TicketStatus.CANCELED},
        TicketStatus.DONE: set(),
        TicketStatus.CANCELED: set(),
    }
    return new in allowed.get(old, set())


def parse_sort(sort: str | None):
    from app.models.ticket import Ticket as TicketModel

    if not sort:
        return []
    mapping = {
        "created_at": TicketModel.created_at,
        "priority": TicketModel.priority,
        "status": TicketModel.status,
        "due_at": TicketModel.due_at,
        "updated_at": TicketModel.updated_at,
    }
    order = []
    for part in [p.strip() for p in sort.split(",") if p.strip()]:
        direction = "asc"
        name = part
        if part.startswith("-"):
            direction = "desc"
            name = part[1:]
        col = mapping.get(name)
        if col is None:
            continue
        order.append(desc(col) if direction == "desc" else col.asc())
    return order


async def create_ticket(
    db: AsyncSession,
    *,
    actor: User,
    title: str,
    description: str,
    priority,
    due_at,
    tags: list[str],
    assignee_id: uuid.UUID | None,
) -> Ticket:
    if actor.role == UserRole.USER and assignee_id is not None:
        raise PermissionError("user_cannot_assign")

    ticket = await repo.create_ticket(
        db,
        title=title,
        description=description,
        priority=priority,
        reporter_id=actor.id,
        assignee_id=assignee_id,
        due_at=due_at,
        tags=tags,
    )

    await repo.add_event(
        db,
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type="ticket.created",
        old_value=None,
        new_value=_snapshot(ticket),
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def list_tickets(
    db: AsyncSession,
    *,
    actor: User,
    filters: dict,
    sort: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    include_deleted = bool(filters.get("include_deleted", False))
    if include_deleted and not _is_admin(actor):
        raise PermissionError("include_deleted_forbidden")

    if actor.role == UserRole.USER:
        filters["reporter_id"] = actor.id

    order_by = parse_sort(sort)
    return await repo.list_tickets(db, sort=order_by, limit=limit, offset=offset, **filters)


async def get_ticket_or_404(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID, include_deleted: bool = False) -> Ticket:
    ticket = await repo.get_ticket(db, ticket_id)
    if ticket is None:
        raise LookupError("not_found")
    if ticket.is_deleted and not include_deleted:
        raise LookupError("not_found")
    if not _can_access_ticket(actor, ticket):
        raise LookupError("not_found")
    return ticket


async def update_ticket(
    db: AsyncSession,
    *,
    actor: User,
    ticket_id: uuid.UUID,
    patch: dict,
) -> Ticket:
    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if actor.role == UserRole.USER:
        if patch.get("assignee_id") is not None:
            raise PermissionError("user_cannot_assign")

    old = _snapshot(ticket)

    for field in ("title", "description", "priority", "due_at", "tags"):
        if field in patch and patch[field] is not None:
            setattr(ticket, field, patch[field])

    if "assignee_id" in patch and patch["assignee_id"] is not None:
        ticket.assignee_id = patch["assignee_id"]
    if "assignee_id" in patch and patch["assignee_id"] is None and _is_agent_or_admin(actor):
        ticket.assignee_id = None

    try:
        await db.flush()
    except StaleDataError as exc:
        raise RuntimeError("conflict") from exc

    await repo.add_event(
        db,
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type="ticket.updated",
        old_value=old,
        new_value=_snapshot(ticket),
    )

    await db.commit()
    await db.refresh(ticket)
    return ticket


async def transition_ticket(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID, new_status: TicketStatus) -> Ticket:
    if not _is_agent_or_admin(actor):
        raise PermissionError("transition_forbidden")

    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if ticket.is_deleted:
        raise LookupError("not_found")

    if not _allowed_transition(ticket.status, new_status):
        raise ValueError("invalid_transition")

    old = _snapshot(ticket)
    ticket.status = new_status
    if new_status == TicketStatus.DONE:
        ticket.closed_at = _utcnow()

    await db.flush()
    await repo.add_event(
        db,
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type="ticket.transition",
        old_value=old,
        new_value=_snapshot(ticket),
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def soft_delete_ticket(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID) -> None:
    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if ticket.is_deleted:
        return
    old = _snapshot(ticket)
    ticket.is_deleted = True
    await db.flush()
    await repo.add_event(
        db,
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type="ticket.deleted",
        old_value=old,
        new_value=_snapshot(ticket),
    )
    await db.commit()


async def list_events(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID):
    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if ticket.is_deleted and not _is_admin(actor):
        raise LookupError("not_found")
    return await repo.list_events(db, ticket_id=ticket.id)


async def add_comment(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID, body: str):
    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if ticket.is_deleted and not _is_admin(actor):
        raise LookupError("not_found")

    comment = await repo.add_comment(db, ticket_id=ticket.id, author_id=actor.id, body=body)
    await repo.add_event(
        db,
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type="ticket.comment.created",
        old_value=None,
        new_value={"comment_id": str(comment.id)},
    )
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(db: AsyncSession, *, actor: User, ticket_id: uuid.UUID):
    ticket = await get_ticket_or_404(db, actor=actor, ticket_id=ticket_id, include_deleted=_is_admin(actor))
    if ticket.is_deleted and not _is_admin(actor):
        raise LookupError("not_found")
    return await repo.list_comments(db, ticket_id=ticket.id)
