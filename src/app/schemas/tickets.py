from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import TicketPriority, TicketStatus


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=100_000)
    priority: TicketPriority = TicketPriority.MEDIUM
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    assignee_id: str | None = None


class TicketUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=100_000)
    priority: TicketPriority | None = None
    due_at: datetime | None = None
    tags: list[str] | None = None
    assignee_id: str | None = None


class TicketTransitionRequest(BaseModel):
    status: TicketStatus


class TicketOut(BaseModel):
    id: str
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    tags: list[str]
    reporter_id: str
    assignee_id: str | None
    due_at: datetime | None
    closed_at: datetime | None
    is_deleted: bool
    version: int
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    items: list[TicketOut]
    total: int
    limit: int
    offset: int


class TicketEventOut(BaseModel):
    id: str
    ticket_id: str
    actor_id: str
    event_type: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime


class TicketCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)


class TicketCommentOut(BaseModel):
    id: str
    ticket_id: str
    author_id: str
    body: str
    created_at: datetime
