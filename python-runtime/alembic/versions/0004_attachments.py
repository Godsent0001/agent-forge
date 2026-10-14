"""Project attachment metadata (D-22).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("declared_mime", sa.String(length=255), nullable=True),
        sa.Column("detected_mime", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="quarantined"),
        sa.Column("scanner_version", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
    )
    op.create_index(
        "ix_attachments_project_created",
        "attachments",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_project_created", table_name="attachments")
    op.drop_table("attachments")
