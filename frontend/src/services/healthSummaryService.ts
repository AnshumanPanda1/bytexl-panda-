import api from '../api/axios';
import type {
  PatientHealthSummary,
  PatientHealthSummaryGenerateRequest,
} from '../types/healthSummary';

export async function getPatientSummaries(
  patientId: string,
  language?: string,
  includeStale = true,
): Promise<PatientHealthSummary[]> {
  const response = await api.get<PatientHealthSummary[]>(`/summaries/patient/${patientId}`, {
    params: {
      language: language || undefined,
      include_stale: includeStale,
    },
  });
  return response.data;
}

export async function generatePatientSummary(
  patientId: string,
  request?: PatientHealthSummaryGenerateRequest,
): Promise<PatientHealthSummary> {
  const response = await api.post<PatientHealthSummary>(
    `/summaries/patient/${patientId}/generate`,
    request || { language: 'en' },
  );
  return response.data;
}

export async function invalidateSummary(
  summaryId: string,
  reason = 'Clinical data updated',
): Promise<PatientHealthSummary> {
  const response = await api.post<PatientHealthSummary>(
    `/summaries/${summaryId}/invalidate`,
    null,
    {
      params: { reason },
    },
  );
  return response.data;
}
