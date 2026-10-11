import api from '../api/axios';

export interface FactualClaim {
  text: string;
  source_document_id?: string;
  source_page?: number;
  confidence?: number;
}

export interface SummarySection {
  title: string;
  text: string;
}

export interface AISummaryRequest {
  patient_id: string;
  document_ids?: string[];
  language?: 'en' | 'hi';
  force_regenerate?: boolean;
}

export interface AISummaryResponse {
  id: string;
  patient_id: string;
  document_ids: string[];
  language: 'en' | 'hi';
  sections: SummarySection[];
  claims: FactualClaim[];
  caveat: string;
  prompt_version: string;
  stale: boolean;
  created_at: string;
}

export const generateAISummary = async (
  request: AISummaryRequest
): Promise<AISummaryResponse> => {
  const response = await api.post<AISummaryResponse>('/ai/summaries/generate', request);
  return response.data;
};

export const invalidateAISummaries = async (
  patientId?: string,
  documentId?: string
): Promise<{ status: string; invalidated_count: number }> => {
  const response = await api.post<{ status: string; invalidated_count: number }>(
    '/ai/summaries/invalidate',
    { patient_id: patientId, document_id: documentId }
  );
  return response.data;
};
