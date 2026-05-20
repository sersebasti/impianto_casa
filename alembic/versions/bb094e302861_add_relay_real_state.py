"""add relay_real_state

Revision ID: bb094e302861
Revises: 3033ea2d4986
Create Date: 2026-05-20 11:38:11.221615
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'bb094e302861'
down_revision = '3033ea2d4986'
branch_labels = None
depends_on = None


def upgrade() -> None:

    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "PRAGMA table_info(sensor_measurement_snapshots)"
        )
    )

    columns = [
        row[1]
        for row in result
    ]

    if "relay_real_state" not in columns:

        op.add_column(
            "sensor_measurement_snapshots",
            sa.Column(
                "relay_real_state",
                sa.Integer(),
                nullable=True,
            ),
        )

def downgrade() -> None:
    pass