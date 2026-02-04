from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TicketPriority, TicketStatus

if TYPE_CHECKING:
    from app.models.ticket_comment import TicketComment
    from app.models.ticket_event import TicketEvent
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_reporter_id", "reporter_id"),
        Index("ix_tickets_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))

    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status"),
        nullable=False,
        server_default=text("'NEW'"),
    )
    priority: Mapped[TicketPriority] = mapped_column(
        SAEnum(TicketPriority, name="ticket_priority"),
        nullable=False,
        server_default=text("'MEDIUM'"),
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        server_default=text("'{}'::varchar[]"),
    )

    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": lambda v: 1 if v is None else v + 1,
    }

    reporter: Mapped["User"] = relationship(
        back_populates="reported_tickets",
        lazy="selectin",
        foreign_keys=[reporter_id],
    )
    assignee: Mapped["User | None"] = relationship(
        back_populates="assigned_tickets",
        lazy="selectin",
        foreign_keys=[assignee_id],
    )

    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    comments: Mapped[list["TicketComment"]] = relationship(
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
