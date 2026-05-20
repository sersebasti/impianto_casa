from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SensorMeasurementsConfig(Base):
    __tablename__ = "sensor_measurements_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    call_type: Mapped[str] = mapped_column(Text, nullable=False)
    http_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True, server_default=text("'GET'"))
    endpoint_query: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_structure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default=text("1"))
    port: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("80"))


class SensorMeasurementSnapshot(Base):
    __tablename__ = "sensor_measurement_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    measurement_config_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ok: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    apparent_power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relay_real_state: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    total_power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SensorStatusSnapshot(Base):
    __tablename__ = "sensor_status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ip_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wifi_ssid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wifi_rssi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uptime_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    heap_free: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RelayStatusSnapshot(Base):
    __tablename__ = "relay_status_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    relay_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_on: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    real_state: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback_invert: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback_pin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    relay_pin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)