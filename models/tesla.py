from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, Index, Integer, String, Text  # aggiunto String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TeslaVehicleSnapshot(Base):
    __tablename__ = "tesla_vehicle_snapshots"
    __table_args__ = (
        Index("idx_tesla_vehicle_snapshots_vin_created_at", "vin", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(255), nullable=False, server_default="CURRENT_TIMESTAMP")
    vin: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    battery_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    charging_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    charge_limit_soc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    charger_power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inside_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outside_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    locked: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    charge_port_door_open: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    charge_port_latch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    charge_port_color: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conn_charge_cable: Mapped[Optional[str]] = mapped_column(Text, nullable=True)