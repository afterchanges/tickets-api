from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued Enum suitable for JSON + SQLAlchemy."""

    def __str__(self) -> str:  # pragma: no cover
        return str(self.value)


class TicketStatus(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELED = "CANCELED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    AGENT = "AGENT"
    USER = "USER"
