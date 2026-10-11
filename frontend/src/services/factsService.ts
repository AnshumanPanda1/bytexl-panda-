import api from '../api/axios';
import type {
  DocumentFactsResponse,
  FactCorrectionRequest,
  FactCorrectionResponse,
} from '../types/facts';

export async function getDocumentFacts(documentId: string): Promise<DocumentFactsResponse> {
  const response = await api.get<DocumentFactsResponse>(`/facts/documents/${documentId}`);
  return response.data;
}

export async function correctFact(data: FactCorrectionRequest): Promise<FactCorrectionResponse> {
  const response = await api.post<FactCorrectionResponse>('/facts/correct', data);
  return response.data;
}
