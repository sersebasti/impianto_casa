from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        Index("idx_auth_tokens_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="CURRENT_TIMESTAMP"
    )
    token: Mapped[str] = mapped_column(Text, nullable=False)
    login_payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class UserInfoSnapshot(Base):
    __tablename__ = "user_info_snapshots"
    __table_args__ = (
        Index("idx_user_info_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="CURRENT_TIMESTAMP"
    )
    token: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)