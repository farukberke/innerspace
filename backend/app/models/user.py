import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class UserRole(StrEnum):
    ORG_ADMIN = "org_admin"
    CLINICIAN = "clinician"
    CLIENT = "client"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A member of exactly one organization. Credentials are added in Phase 2."""

    __tablename__ = "users"
    __table_args__ = (
        # Target of composite foreign keys: lets child tables guarantee that a referenced
        # user belongs to the same organization as the row itself.
        UniqueConstraint("id", "organization_id", name="uq_users_id_organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"))
