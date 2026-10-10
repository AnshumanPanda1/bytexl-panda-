export interface FactObservation {
  id: string;
  code: any;
  value_quantity?: any;
  normalized_value?: number;
  raw_value?: number;
  review_status?: string;
  original_text?: string;
  evidence_text?: string;
  page_number?: number;
  confidence?: number;
  observation_date?: string;
  method?: string;
  interpretation?: string;
  biomarker_slug?: string;
  [key: string]: any;
}

export interface FactMedication {
  id: string;
  code: any;
  dosage?: string;
  strength?: string;
  route?: string;
  duration?: string;
  status?: string;
  review_status?: string;
  original_text?: string;
  evidence_text?: string;
  page_number?: number;
  confidence?: number;
  start_date?: string;
  end_date?: string;
  reason?: string;
  [key: string]: any;
}

export interface FactCondition {
  id: string;
  title: string;
  status?: string;
  clinical_status?: 'active' | 'recurrence' | 'relapse' | 'remission' | 'resolved' | string;
  verification_status?: 'confirmed' | 'provisional' | 'differential' | 'refuted' | string;
  icd10_code?: string;
  review_status?: string;
  original_text?: string;
  evidence_text?: string;
  page_number?: number;
  confidence?: number;
  onset_date?: string;
  evidence?: Array<any>;
  [key: string]: any;
}

export interface DocumentFactsResponse {
  document_id: string;
  filename: string;
  status: string;
  extracted_text: string | null;
  observations: FactObservation[];
  medications: FactMedication[];
  conditions: FactCondition[];
}

export interface FactCorrectionRequest {
  fact_type: 'observation' | 'medication' | 'condition';
  fact_id: string;
  corrected_value?: string | number | null;
  corrected_unit?: string | null;
  corrected_name?: string | null;
  correction_reason?: string | null;
  new_review_status?: 'verified' | 'rejected' | 'corrected';
  updates?: Record<string, any>;
}

export interface FactCorrectionResponse {
  message: string;
  fact_type: string;
  fact_id: string;
  old_value: Record<string, any>;
  new_value: Record<string, any>;
  updated_at: string;
}
