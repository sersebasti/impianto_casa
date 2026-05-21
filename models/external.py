from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class HostStatusSnapshot(Base):
    __tablename__ = "host_status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, server_default="CURRENT_TIMESTAMP")
    device_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ok: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hostname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    macaddress: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SensorSnapshot(Base):
    __tablename__ = "sensor_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    sensor_name: Mapped[str] = mapped_column(Text, nullable=False)
    sensor_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    macaddress: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ok: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)