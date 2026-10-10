export interface PatientHealthSummary {
  id: string;
  tenant_id: string;
  patient_id: string;
  examination_id?: string | null;
  title: string;
  summary_text: string;
  language: string;
  is_stale: boolean;
  stale_reason?: string | null;
  stale_at?: string | null;
  source_references: Array<{
    type: string;
    id?: string;
    code?: string;
    name?: string;
    title?: string;
    value?: any;
    unit?: string;
    document_id?: string | null;
    [key: string]: any;
  }>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PatientHealthSummaryGenerateRequest {
  language?: string;
  examination_id?: string | null;
}
