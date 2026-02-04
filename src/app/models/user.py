from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.ticket_comment import TicketComment
    from app.models.ticket_event import TicketEvent


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        server_default=text("'USER'"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reported_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="reporter",
        lazy="selectin",
        foreign_keys="Ticket.reporter_id",
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assignee",
        lazy="selectin",
        foreign_keys="Ticket.assignee_id",
    )

    ticket_events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="actor",
        lazy="selectin",
    )
    ticket_comments: Mapped[list["TicketComment"]] = relationship(
        back_populates="author",
        lazy="selectin",
    )
