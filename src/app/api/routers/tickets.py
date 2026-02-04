from __future__ import annotations

import uuid

import orjson
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.redis import redis_client
from app.db.session import get_db
from app.models.enums import TicketPriority, TicketStatus, UserRole
from app.schemas.tickets import (
    TicketCommentCreateRequest,
    TicketCommentOut,
    TicketCreateRequest,
    TicketEventOut,
    TicketListResponse,
    TicketOut,
    TicketTransitionRequest,
    TicketUpdateRequest,
)
from app.services import tickets as svc


router = APIRouter(prefix="/v1/tickets", tags=["tickets"])


def _err(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _ticket_out(t) -> TicketOut:
    return TicketOut(
        id=str(t.id),
        title=t.title,
        description=t.description,
        status=t.status,
        priority=t.priority,
        tags=list(t.tags or []),
        reporter_id=str(t.reporter_id),
        assignee_id=str(t.assignee_id) if t.assignee_id else None,
        due_at=t.due_at,
        closed_at=t.closed_at,
        is_deleted=bool(t.is_deleted),
        version=int(t.version),
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    payload: TicketCreateRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    redis_key = None
    if idempotency_key:
        redis_key = f"idemp:tickets:create:{user.id}:{idempotency_key}".encode()
        try:
            cached = await redis_client.get(redis_key)
        except RedisError:
            raise _err("redis_unavailable", "Idempotency store unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        if cached:
            data = orjson.loads(cached)
            return JSONResponse(status_code=int(data["status_code"]), content=data["body"])

    try:
        assignee_uuid = uuid.UUID(payload.assignee_id) if payload.assignee_id else None
    except ValueError:
        raise _err("invalid_assignee", "Invalid assignee_id", status.HTTP_422_UNPROCESSABLE_ENTITY)

    try:
        ticket = await svc.create_ticket(
            db,
            actor=user,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            due_at=payload.due_at,
            tags=payload.tags,
            assignee_id=assignee_uuid,
        )
    except PermissionError as exc:
        if str(exc) == "user_cannot_assign":
            raise _err("forbidden", "Users cannot assign tickets", status.HTTP_403_FORBIDDEN)
        raise

    body = _ticket_out(ticket).model_dump(mode="json")
    if redis_key:
        try:
            await redis_client.set(redis_key, orjson.dumps({"status_code": 201, "body": body}), ex=86400, nx=True)
        except RedisError:
            pass
    return JSONResponse(status_code=201, content=body)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = None,
    assignee_id: str | None = None,
    reporter_id: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    created_from=None,
    created_to=None,
    due_from=None,
    due_to=None,
    sort: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = False,
):
    def _parse_uuid(val: str | None) -> uuid.UUID | None:
        return uuid.UUID(val) if val else None

    filters = {
        "status": status_filter,
        "priority": priority,
        "assignee_id": _parse_uuid(assignee_id),
        "reporter_id": _parse_uuid(reporter_id),
        "tag": tag,
        "q": q,
        "created_from": created_from,
        "created_to": created_to,
        "due_from": due_from,
        "due_to": due_to,
        "include_deleted": include_deleted,
    }

    try:
        items, total = await svc.list_tickets(db, actor=user, filters=filters, sort=sort, limit=limit, offset=offset)
    except PermissionError:
        raise _err("forbidden", "include_deleted requires ADMIN", status.HTTP_403_FORBIDDEN)

    return TicketListResponse(
        items=[_ticket_out(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db), include_deleted: bool = False):
    if include_deleted and user.role != UserRole.ADMIN:
        raise _err("forbidden", "include_deleted requires ADMIN", status.HTTP_403_FORBIDDEN)
    try:
        ticket = await svc.get_ticket_or_404(db, actor=user, ticket_id=ticket_id, include_deleted=include_deleted)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    return _ticket_out(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def patch_ticket(ticket_id: uuid.UUID, payload: TicketUpdateRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    patch = payload.model_dump(exclude_unset=True)
    if "assignee_id" in patch:
        patch["assignee_id"] = uuid.UUID(patch["assignee_id"]) if patch["assignee_id"] else None
    try:
        ticket = await svc.update_ticket(db, actor=user, ticket_id=ticket_id, patch=patch)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    except PermissionError as exc:
        if str(exc) == "user_cannot_assign":
            raise _err("forbidden", "Users cannot assign tickets", status.HTTP_403_FORBIDDEN)
        raise
    except RuntimeError:
        raise _err("conflict", "Ticket was updated by someone else", status.HTTP_409_CONFLICT)
    return _ticket_out(ticket)


@router.post("/{ticket_id}/transition", response_model=TicketOut)
async def transition(ticket_id: uuid.UUID, payload: TicketTransitionRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        ticket = await svc.transition_ticket(db, actor=user, ticket_id=ticket_id, new_status=payload.status)
    except PermissionError:
        raise _err("forbidden", "Only AGENT/ADMIN can transition", status.HTTP_403_FORBIDDEN)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    except ValueError:
        raise _err("invalid_transition", "Invalid status transition", status.HTTP_400_BAD_REQUEST)
    return _ticket_out(ticket)


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await svc.soft_delete_ticket(db, actor=user, ticket_id=ticket_id)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    return {"ok": True}


@router.get("/{ticket_id}/events", response_model=list[TicketEventOut])
async def events(ticket_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        evs = await svc.list_events(db, actor=user, ticket_id=ticket_id)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    return [
        TicketEventOut(
            id=str(e.id),
            ticket_id=str(e.ticket_id),
            actor_id=str(e.actor_id),
            event_type=e.event_type,
            old_value=e.old_value,
            new_value=e.new_value,
            created_at=e.created_at,
        )
        for e in evs
    ]


@router.post("/{ticket_id}/comments", response_model=TicketCommentOut, status_code=201)
async def add_comment(ticket_id: uuid.UUID, payload: TicketCommentCreateRequest, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        c = await svc.add_comment(db, actor=user, ticket_id=ticket_id, body=payload.body)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    return TicketCommentOut(
        id=str(c.id),
        ticket_id=str(c.ticket_id),
        author_id=str(c.author_id),
        body=c.body,
        created_at=c.created_at,
    )


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentOut])
async def list_comments(ticket_id: uuid.UUID, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        comments = await svc.list_comments(db, actor=user, ticket_id=ticket_id)
    except LookupError:
        raise _err("not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
    return [
        TicketCommentOut(
            id=str(c.id),
            ticket_id=str(c.ticket_id),
            author_id=str(c.author_id),
            body=c.body,
            created_at=c.created_at,
        )
        for c in comments
    ]
