import api from '../api/axios';
import { db } from './db';
import { DataSourceType } from '../types/biomarker';
import { getTestPatientFullData } from '../data/testPatients';

function getFallbackBiomarkerTrends(patientId?: string) {
  if (!patientId) return { biomarkers: {} };
  const testData = getTestPatientFullData(patientId);
  if (!testData?.biomarkers?.length) return { biomarkers: {} };

  const result: Record<string, any[]> = {};
  testData.biomarkers.forEach(b => {
    if (!result[b.slug]) {
      result[b.slug] = [];
    }
    result[b.slug].push({
      date: b.effective_datetime,
      value: b.value,
      raw_value: b.value,
      unit: b.unit,
      raw_unit: b.unit,
      name: b.name,
      status: b.interpretation || 'Normal',
      reference_range_min: b.reference_range_min,
      reference_range_max: b.reference_range_max,
      standard_range_min: b.reference_range_min,
      standard_range_max: b.reference_range_max,
      source_name: 'Diagnostic Laboratory Panel',
      examination_name: 'Diagnostic Laboratory Panel',
      source_type: DataSourceType.DOCUMENT,
    });
  });
  return { biomarkers: result };
}

function getFallbackDashboardData(patientId?: string) {
  if (!patientId) return null;
  const testData = getTestPatientFullData(patientId);
  if (!testData) return null;

  return {
    recent_documents: testData.documents.map(d => ({
      id: d.id,
      filename: d.filename,
      created_at: d.created_at,
    })),
    upcoming_appointments: [
      {
        id: 'apt-001',
        title: 'Routine Clinical Follow-up & Review',
        date: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString(),
      }
    ],
    alerts: testData.biomarkers
      .filter(b => b.interpretation && b.interpretation !== 'Normal')
      .map(b => ({
        type: b.interpretation === 'Critical' ? 'critical' : 'warning',
        message: `${b.name} (${b.value} ${b.unit}) flagged ${b.interpretation}`,
        timestamp: b.effective_datetime,
      })),
    summary: {
      total_documents: testData.documents.length,
      total_observations: testData.biomarkers.length,
      last_upload: testData.documents[0]?.created_at || new Date().toISOString(),
    },
    latest_examination: {
      id: 'exam-demo-001',
      examination_date: '2026-09-15T10:00:00Z',
      notes: testData.aiSummary.en,
      category: 'General Consultation',
      doctor_name: 'Dr. V. Rao, MD',
    },
    latest_imaging: [],
    latest_labs: testData.biomarkers.slice(0, 4).map(b => ({
      name: b.name,
      result: b.value,
      unit: b.unit,
      date: b.effective_datetime,
      status: b.interpretation || 'Normal',
    })),
  };
}

export async function getDashboardData(
  _tenantId: string,
  patientId?: string,
  period: string = 'last-30-days'
): Promise<{
  recent_documents: Array<{
    id: string;
    filename: string;
    created_at: string;
  }>;
  upcoming_appointments: Array<{
    id: string;
    title: string;
    date: string;
  }>;
  alerts: Array<{
    type: string;
    message: string;
    timestamp: string;
  }>;
  summary: {
    total_documents: number;
    total_observations: number;
    last_upload: string;
  };
  latest_examination?: {
    id: string;
    examination_date: string;
    notes: string;
    category: string;
    doctor_name: string;
  };
  latest_imaging?: Array<{
    id: string;
    date: string;
    title: string;
    status: string;
    conclusion?: string;
  }>;
  latest_labs?: Array<{
    name: string;
    result: any;
    unit: string;
    date: string;
    status: string;
  }>;
}> {
  try {
    const response = await api.get<{
      recent_documents: Array<{ id: string; filename: string; created_at: string }>;
      upcoming_appointments: Array<{ id: string; title: string; date: string }>;
      alerts: Array<{ type: string; message: string; timestamp: string }>;
      summary: { total_documents: number; total_observations: number; last_upload: string };
      latest_examination?: any;
      latest_imaging?: any[];
      latest_labs?: any[];
    }>(
      '/analytics/dashboard',
      {
        params: {
          patient_id: patientId,
          period
        }
      }
    );
    
    if (
      patientId &&
      response.data &&
      (!response.data.summary || (response.data.summary.total_documents === 0 && response.data.summary.total_observations === 0))
    ) {
      const fallback = getFallbackDashboardData(patientId);
      if (fallback) return fallback;
    }

    // Cache the dashboard data if we have patientId
    if (patientId && response.data) {
       db.dashboardData.put({
          patient_id: patientId,
          period,
          data: response.data,
          updatedAt: Date.now()
       });
    }
    
    return response.data;
  } catch (error) {
    if (!navigator.onLine && patientId) {
      const cached = await db.dashboardData.where({ patient_id: patientId, period }).first();
      if (cached) return cached.data;
    }
    const fallback = getFallbackDashboardData(patientId);
    if (fallback) return fallback;
    throw error;
  }
}

export async function getCachedDashboardData(patientId: string, period: string) {
  const cached = await db.dashboardData.where({ patient_id: patientId, period }).first();
  if (cached?.data) return cached.data;
  return getFallbackDashboardData(patientId);
}

export async function getBiomarkerTrends(
  _tenantId: string,
  biomarkerCodes?: string,
  period: string = 'last-6-months',
  patientId?: string,
  aggregation?: string
): Promise<{
  biomarkers: {
    [key: string]: Array<{
      date: string;
      value: number;
      unit: string;
      name: string;
      examination_id?: string;
      examination_name?: string;
      status?: string;
      source_type?: DataSourceType;
      source_name?: string;
      source_id?: string;
      source_category?: string;
    }>;
  };
}> {
  try {
    const response = await api.get<{
      biomarkers: {
        [key: string]: Array<{
          date: string;
          value: number;
          unit: string;
          name: string;
        }>;
      };
    }>(`/analytics/trends`, {
      params: {
        biomarker_codes: biomarkerCodes,
        period,
        patient_id: patientId,
        aggregation: aggregation
      }
    });

    if (patientId && (!response.data?.biomarkers || Object.keys(response.data.biomarkers).length === 0)) {
      const fallback = getFallbackBiomarkerTrends(patientId);
      if (Object.keys(fallback.biomarkers).length > 0) {
        return fallback;
      }
    }
    
    // Proactively cache if we are online and have patient context
    if (patientId && response.data && !biomarkerCodes) {
       db.biomarkerTrends.put({
          patient_id: patientId,
          period,
          data: response.data,
          updatedAt: Date.now()
       });
    }
    
    return response.data;
  } catch (error) {
    if (!navigator.onLine && patientId && !biomarkerCodes) {
      const cached = await db.biomarkerTrends.where({ patient_id: patientId, period }).first();
      if (cached) return cached.data;
    }
    if (patientId) {
      const fallback = getFallbackBiomarkerTrends(patientId);
      if (Object.keys(fallback.biomarkers).length > 0) {
        return fallback;
      }
    }
    throw error;
  }
}

export async function getCachedBiomarkerTrends(patientId: string, period: string) {
  const cached = await db.biomarkerTrends.where({ patient_id: patientId, period }).first();
  if (cached?.data) return cached.data;
  const fallback = getFallbackBiomarkerTrends(patientId);
  if (Object.keys(fallback.biomarkers).length > 0) return fallback;
  return null;
}

export async function getAnalyticsSummary(
  _tenantId: string,
  patientId?: string,
  period: string = 'last-year'
): Promise<{
  total_documents: number;
  total_observations: number;
  total_medications: number;
  active_alerts: number;
  last_upload: string;
}> {
  const response = await api.get<{
    total_documents: number;
    total_observations: number;
    total_medications: number;
    active_alerts: number;
    last_upload: string;
  }>(
    '/analytics/summary',
    {
      params: {
        patient_id: patientId,
        period
      }
    }
  );
  return response.data;
}

export async function getCategoryAnalytics(
  categoryName: string,
  patientId?: string
): Promise<any> {
  const response = await api.get(`/analytics/category/${categoryName}`, {
    params: {
      patient_id: patientId
    }
  });
  return response.data;
}

export async function getAvailableCategories(patientId?: string): Promise<string[]> {
  const response = await api.get<{ categories: string[] }>('/analytics/available-categories', {
    params: {
      patient_id: patientId
    }
  });
  return response.data.categories;
}

export interface BiomarkerAnomaly {
  type: 'statistical_anomaly' | 'upward_trend' | 'downward_trend' | 'below_reference' | 'above_reference';
  message: string;
  severity: 'info' | 'warning' | 'critical';
  biomarker?: string;
  biomarker_slug?: string;
  biomarker_id?: string;
  value?: number;
  unit?: string;
}

export async function getAnomalies(patientId?: string, biomarkerCodes?: string): Promise<BiomarkerAnomaly[]> {
  try {
    const response = await api.get<{ anomalies: BiomarkerAnomaly[] }>('/analytics/anomalies', {
      params: { patient_id: patientId, biomarker_codes: biomarkerCodes }
    });
    return response.data.anomalies ?? [];
  } catch {
    return [];
  }
}
