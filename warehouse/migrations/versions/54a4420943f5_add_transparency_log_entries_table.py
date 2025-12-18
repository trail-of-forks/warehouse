# SPDX-License-Identifier: Apache-2.0
"""
Add transparency_log_entries table

Revision ID: 54a4420943f5
Revises: fe2e3d22b3fa
Create Date: 2025-12-18
"""
import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "54a4420943f5"
down_revision = "a6cae8e65f1a"


def upgrade():
    op.create_table(
        "transparency_log_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "log_entry", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["release_files.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transparency_log_entries_file_id",
        "transparency_log_entries",
        ["file_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_transparency_log_entries_file_id", table_name="transparency_log_entries"
    )
    op.drop_table("transparency_log_entries")
