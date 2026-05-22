from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, String, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class TeslaChargeConfig(Base):
    __tablename__ = "tesla_charge_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    config_value: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(TIMESTAMP, nullable=True, server_default=func.current_timestamp(), onupdate=func.current_timestamp())