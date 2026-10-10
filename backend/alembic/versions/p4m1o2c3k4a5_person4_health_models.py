"""Add Person 4 canonical health models, summaries, and mock ABDM import tables.

Revision ID: p4m1o2c3k4a5
Revises: h5m2f3a4t6o7
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p4m1o2c3k4a5"
down_revision = "h5m2f3a4t6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Observation fact extensions
    with op.batch_alter_table("fhir_observations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("page_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("review_status", sa.String(length=50), nullable=True, server_default="extracted")
        )

    # 2. Medication fact extensions and source document linkage
    with op.batch_alter_table("fhir_medications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("document_id", sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("page_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("review_status", sa.String(length=50), nullable=True, server_default="extracted")
        )
        batch_op.create_foreign_key(
            "fk_fhir_medications_document_id_documents",
            "documents",
            ["document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_fhir_medications_document_id", ["document_id"], unique=False)

    # 3. Clinical events condition fact extensions
    with op.batch_alter_table("clinical_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("document_id", sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("page_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("review_status", sa.String(length=50), nullable=True, server_default="extracted")
        )
        batch_op.add_column(sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.create_foreign_key(
            "fk_clinical_events_document_id_documents",
            "documents",
            ["document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_clinical_events_document_id", ["document_id"], unique=False)

    # 4. Patient plain-language summaries with staleness tracking
    op.create_table(
        "patient_health_summaries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("examination_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), server_default="en", nullable=False),
        sa.Column("is_stale", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["fhir_patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["examination_id"], ["examinations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_patient_health_summaries_patient_id", "patient_health_summaries", ["patient_id"])
    op.create_index("ix_patient_health_summaries_tenant_id", "patient_health_summaries", ["tenant_id"])
    op.create_index(
        "ix_patient_health_summaries_patient_lang",
        "patient_health_summaries",
        ["tenant_id", "patient_id", "language"],
    )

    # 5. Mock ABHA/ABDM simulated imports
    op.create_table(
        "mock_abdm_imports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.String(length=100), server_default="mock_abdm", nullable=False),
        sa.Column("external_record_id", sa.String(length=255), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="imported", nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mapped_resources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["fhir_patients.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_mock_abdm_tenant_checksum",
        "mock_abdm_imports",
        ["tenant_id", "checksum"],
        unique=True,
    )
    op.create_index("ix_mock_abdm_tenant_patient", "mock_abdm_imports", ["tenant_id", "patient_id"])


def downgrade() -> None:
    op.drop_table("mock_abdm_imports")
    op.drop_table("patient_health_summaries")

    with op.batch_alter_table("clinical_events", schema=None) as batch_op:
        batch_op.drop_constraint("fk_clinical_events_document_id_documents", type_="foreignkey")
        batch_op.drop_index("ix_clinical_events_document_id")
        batch_op.drop_column("evidence")
        batch_op.drop_column("review_status")
        batch_op.drop_column("confidence")
        batch_op.drop_column("page_number")
        batch_op.drop_column("original_text")
        batch_op.drop_column("document_id")

    with op.batch_alter_table("fhir_medications", schema=None) as batch_op:
        batch_op.drop_constraint("fk_fhir_medications_document_id_documents", type_="foreignkey")
        batch_op.drop_index("ix_fhir_medications_document_id")
        batch_op.drop_column("review_status")
        batch_op.drop_column("confidence")
        batch_op.drop_column("page_number")
        batch_op.drop_column("original_text")
        batch_op.drop_column("document_id")

    with op.batch_alter_table("fhir_observations", schema=None) as batch_op:
        batch_op.drop_column("review_status")
        batch_op.drop_column("confidence")
        batch_op.drop_column("page_number")
        batch_op.drop_column("original_text")
