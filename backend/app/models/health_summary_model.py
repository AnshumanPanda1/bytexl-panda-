from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import (
    AuditMixin,
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDMixin,
    VersionedMixin,
)


class PatientHealthSummary(
    Base,
    UUIDMixin,
    TenantMixin,
    AuditMixin,
    VersionedMixin,
    TimestampMixin,
    SoftDeleteMixin,
):
    """Plain-language health summary for a patient with source provenance and staleness tracking.

    Supports multi-lingual generation (e.g. English and Hindi). Tracks staleness when underlying
    clinical facts (observations, medications, conditions) are updated or corrected.
    """

    __tablename__ = "patient_health_summaries"

    patient_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("fhir_patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    examination_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("examinations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False)
    summary_text = Column(Text, nullable=False)
    language = Column(String(10), nullable=False, default="en", server_default="en", index=True)
    is_stale = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    stale_reason = Column(Text, nullable=True)
    stale_at = Column(DateTime(timezone=True), nullable=True)
    source_references = Column(JSONB, nullable=True, default=list)

    # Relationships
    patient = relationship("Patient", backref="health_summaries", lazy="selectin")
    examination = relationship("ExaminationModel", backref="health_summaries", lazy="selectin")

    __table_args__ = (
        Index("ix_patient_health_summaries_patient_lang", "tenant_id", "patient_id", "language"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id) if self.id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "patient_id": str(self.patient_id) if self.patient_id else None,
            "examination_id": str(self.examination_id) if self.examination_id else None,
            "title": self.title,
            "summary_text": self.summary_text,
            "language": self.language,
            "is_stale": self.is_stale,
            "stale_reason": self.stale_reason,
            "stale_at": self.stale_at.isoformat() if self.stale_at else None,
            "source_references": self.source_references or [],
            "created_by": str(self.created_by) if self.created_by else None,
            "updated_by": str(self.updated_by) if self.updated_by else None,
            "version": self.version or 1,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
