"""add run checkpoints

Revision ID: 0002_add_run_checkpoints
Revises: 0001_initial_schema
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_run_checkpoints"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_checkpoints",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("run_status", sa.String(length=40), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_checkpoints_kind"), "run_checkpoints", ["kind"], unique=False)
    op.create_index(op.f("ix_run_checkpoints_run_id"), "run_checkpoints", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_checkpoints_run_id"), table_name="run_checkpoints")
    op.drop_index(op.f("ix_run_checkpoints_kind"), table_name="run_checkpoints")
    op.drop_table("run_checkpoints")
