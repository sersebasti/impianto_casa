"""add test table

Revision ID: 3033ea2d4986
Revises: 20260519_0001
Create Date: 2026-05-19 16:53:39.076439
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '3033ea2d4986'
down_revision = '20260519_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('test_table',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('test_string', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('test_table')