from __future__ import annotations

from sqlalchemy import UUID, Boolean, Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TenantMixin, TimestampMixin, UserMixin, UUIDMixin


class AISummaryModel(Base, UUIDMixin, TenantMixin, UserMixin, TimestampMixin):
    """Stores AI-generated bilingual summaries with source-grounding metadata."""

    __tablename__ = "ai_summaries"

    patient_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    document_ids = Column(JSONB, nullable=False, default=list)  # list of UUID strings
    language = Column(String(10), nullable=False, default="en", index=True)  # "en" | "hi"
    sections = Column(JSONB, nullable=False, default=list)
    claims = Column(JSONB, nullable=False, default=list)
    caveat = Column(String(1000), nullable=False)
    prompt_version = Column(String(50), nullable=False, default="summary-v1")
    stale = Column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (
        Index("idx_ai_summaries_patient_lang", "patient_id", "language"),
        Index("idx_ai_summaries_tenant_stale", "tenant_id", "stale"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "document_ids": [str(d) for d in self.document_ids] if self.document_ids else [],
            "language": self.language,
            "sections": self.sections or [],
            "claims": self.claims or [],
            "caveat": self.caveat,
            "prompt_version": self.prompt_version,
            "stale": self.stale,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }
