"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_call_id", sa.String(length=120), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_run_id"), "messages", ["run_id"], unique=False)

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_entries_type"), "memory_entries", ["type"], unique=False)

    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("tool_call_id", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("assistant_message", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pending_approvals_run_id"), "pending_approvals", ["run_id"], unique=False)
    op.create_index(op.f("ix_pending_approvals_status"), "pending_approvals", ["status"], unique=False)

    op.create_table(
        "trace_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trace_events_run_id"), "trace_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_trace_events_type"), "trace_events", ["type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trace_events_type"), table_name="trace_events")
    op.drop_index(op.f("ix_trace_events_run_id"), table_name="trace_events")
    op.drop_table("trace_events")
    op.drop_index(op.f("ix_pending_approvals_status"), table_name="pending_approvals")
    op.drop_index(op.f("ix_pending_approvals_run_id"), table_name="pending_approvals")
    op.drop_table("pending_approvals")
    op.drop_index(op.f("ix_memory_entries_type"), table_name="memory_entries")
    op.drop_table("memory_entries")
    op.drop_index(op.f("ix_messages_run_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_table("agent_runs")
