from __future__ import annotations

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TestTable(Base):
    __tablename__ = "test_table"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_string: Mapped[str] = mapped_column(Text, nullable=False)