# These tables currently store the raw and flattened state snapshots
# produced from the Manyi inverter/device state flow.

from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base




class DeviceSnapshot(Base):
    __tablename__ = "device_snapshots"
    __table_args__ = (
        Index("idx_device_snapshots_device_row_key", "device_row_key"),
        Index("idx_device_snapshots_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_row_key: Mapped[str] = mapped_column(String(255), nullable=False)
    update_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    json_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(255), nullable=False, server_default="CURRENT_TIMESTAMP")


class DeviceSnapshotFlat(Base):
    __tablename__ = "device_snapshots_flat"
    __table_args__ = (
        Index("idx_device_snapshots_flat_device_row_key", "device_row_key"),
        Index("idx_device_snapshots_flat_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_row_key: Mapped[str] = mapped_column(String(255), nullable=False)
    update_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inverter_program_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    internal_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_voltage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_frequency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_voltage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_frequency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    battery_voltage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    battery_capacity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inverter_charging_current: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    load_percentage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_temp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    machine_status_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_run_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_operation_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    battery_number_in_series: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_program_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pv_voltage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_charging_current: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_temp: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_status_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_connection_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_charging_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inverter_charge_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    battery_voltage_is_full: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_malfunction_alarm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    controller_warning_alarm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inverter_fault_alarm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inverter_warning_alarm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(255), nullable=False, server_default="CURRENT_TIMESTAMP")