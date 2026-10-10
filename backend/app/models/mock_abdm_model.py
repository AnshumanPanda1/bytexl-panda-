from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDMixin,
)


class MockAbdmImportRecord(Base, UUIDMixin, TenantMixin, AuditMixin, TimestampMixin):
    """Tracks simulated external health records imported via the Mock ABHA/ABDM workflow.

    Enforces checksum-based deduplication per tenant and maintains full provenance
    back to the synthetic external record identifier and facility.
    """

    __tablename__ = "mock_abdm_imports"

    patient_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("fhir_patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system = Column(
        String(100),
        nullable=False,
        default="mock_abdm",
        server_default="mock_abdm",
        index=True,
    )
    external_record_id = Column(String(255), nullable=False, index=True)
    checksum = Column(String(64), nullable=False, index=True)
    status = Column(
        String(50),
        nullable=False,
        default="imported",
        server_default="imported",
        index=True,
    )
    provenance = Column(JSONB, nullable=True, default=dict)
    raw_payload = Column(JSONB, nullable=True, default=dict)
    mapped_resources = Column(JSONB, nullable=True, default=dict)
    imported_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    patient = relationship("Patient", backref="mock_abdm_imports", lazy="selectin")

    __table_args__ = (
        Index("uq_mock_abdm_tenant_checksum", "tenant_id", "checksum", unique=True),
        Index("ix_mock_abdm_tenant_patient", "tenant_id", "patient_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id) if self.id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "patient_id": str(self.patient_id) if self.patient_id else None,
            "source_system": self.source_system,
            "external_record_id": self.external_record_id,
            "checksum": self.checksum,
            "status": self.status,
            "provenance": self.provenance or {},
            "raw_payload": self.raw_payload or {},
            "mapped_resources": self.mapped_resources or {},
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
