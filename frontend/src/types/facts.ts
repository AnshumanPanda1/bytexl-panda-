export interface DocumentFactsResponse {
  document_id: string;
  filename: string;
  status: string;
  extracted_text: string | null;
  observations: Array<{
    id: string;
    code: any;
    value_quantity?: any;
    normalized_value?: number;
    review_status?: string;
    original_text?: string;
    page_number?: number;
    confidence?: number;
    [key: string]: any;
  }>;
  medications: Array<{
    id: string;
    code: any;
    dosage?: string;
    status?: string;
    review_status?: string;
    original_text?: string;
    page_number?: number;
    confidence?: number;
    [key: string]: any;
  }>;
  conditions: Array<{
    id: string;
    title: string;
    status?: string;
    review_status?: string;
    original_text?: string;
    confidence?: number;
    [key: string]: any;
  }>;
}

export interface FactCorrectionRequest {
  fact_type: 'observation' | 'medication' | 'condition';
  fact_id: string;
  corrected_value?: string | number | null;
  corrected_unit?: string | null;
  corrected_name?: string | null;
  correction_reason?: string | null;
  new_review_status?: 'verified' | 'rejected' | 'corrected';
}

export interface FactCorrectionResponse {
  message: string;
  fact_type: string;
  fact_id: string;
  old_value: Record<string, any>;
  new_value: Record<string, any>;
  updated_at: string;
}
