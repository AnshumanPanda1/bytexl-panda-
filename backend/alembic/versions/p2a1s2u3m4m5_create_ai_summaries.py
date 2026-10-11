"""Create ai_summaries table for Person 2 AI summary service.

Revision ID: p2a1s2u3m4m5
Revises: h5m2f3a4t6o7
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "p2a1s2u3m4m5"
down_revision = "h5m2f3a4t6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_summaries",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column(
            "document_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "claims",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("caveat", sa.String(length=1000), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=50),
            nullable=False,
            server_default="summary-v1",
        ),
        sa.Column(
            "stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_summaries_created_at"), "ai_summaries", ["created_at"], unique=False)
    op.create_index(op.f("ix_ai_summaries_language"), "ai_summaries", ["language"], unique=False)
    op.create_index(op.f("ix_ai_summaries_patient_id"), "ai_summaries", ["patient_id"], unique=False)
    op.create_index(op.f("ix_ai_summaries_stale"), "ai_summaries", ["stale"], unique=False)
    op.create_index(op.f("ix_ai_summaries_tenant_id"), "ai_summaries", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ai_summaries_updated_at"), "ai_summaries", ["updated_at"], unique=False)
    op.create_index(op.f("ix_ai_summaries_user_id"), "ai_summaries", ["user_id"], unique=False)
    op.create_index("idx_ai_summaries_patient_lang", "ai_summaries", ["patient_id", "language"], unique=False)
    op.create_index("idx_ai_summaries_tenant_stale", "ai_summaries", ["tenant_id", "stale"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ai_summaries_tenant_stale", table_name="ai_summaries")
    op.drop_index("idx_ai_summaries_patient_lang", table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_user_id"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_updated_at"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_tenant_id"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_stale"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_patient_id"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_language"), table_name="ai_summaries")
    op.drop_index(op.f("ix_ai_summaries_created_at"), table_name="ai_summaries")
    op.drop_table("ai_summaries")
