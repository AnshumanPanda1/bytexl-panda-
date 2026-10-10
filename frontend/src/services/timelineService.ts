import api from '../api/axios';
import type { PatientTimelineResponse } from '../types/timeline';

export interface TimelineParams {
  categories?: string[];
  limit?: number;
  offset?: number;
}

export async function getPatientTimeline(
  patientId: string,
  params?: TimelineParams,
): Promise<PatientTimelineResponse> {
  const categoriesParam = params?.categories && params.categories.length > 0
    ? params.categories.join(',')
    : undefined;

  const response = await api.get<PatientTimelineResponse>(`/timeline/patient/${patientId}`, {
    params: {
      categories: categoriesParam,
      limit: params?.limit || 100,
      offset: params?.offset || 0,
    },
  });
  return response.data;
}
