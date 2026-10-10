import api from '../api/axios';
import type {
  MockAbdmConfirmResponse,
  MockAbdmImportRecord,
  MockAbdmPreviewResponse,
  SyntheticRecordBundle,
} from '../types/mockAbdm';

export async function previewMockAbdmRecord(
  patientId: string,
  bundle: SyntheticRecordBundle,
): Promise<MockAbdmPreviewResponse> {
  const response = await api.post<MockAbdmPreviewResponse>(
    `/mock-abdm/patient/${patientId}/preview`,
    bundle,
  );
  return response.data;
}

export async function confirmMockAbdmRecord(
  patientId: string,
  bundle: SyntheticRecordBundle,
): Promise<MockAbdmConfirmResponse> {
  const response = await api.post<MockAbdmConfirmResponse>(
    `/mock-abdm/patient/${patientId}/confirm`,
    bundle,
  );
  return response.data;
}

export async function listMockAbdmImports(params?: {
  patientId?: string;
  limit?: number;
}): Promise<MockAbdmImportRecord[]> {
  const response = await api.get<MockAbdmImportRecord[]>('/mock-abdm/imports', {
    params: {
      patient_id: params?.patientId || undefined,
      limit: params?.limit || 50,
    },
  });
  return response.data;
}

export function getMockAbdmSampleBundles(): SyntheticRecordBundle[] {
  return [
    {
      external_record_id: `ABDM-LAB-${Date.now().toString().slice(-6)}`,
      source_system: 'mock_abdm',
      facility_name: 'Max Healthcare Delhi',
      encounter_date: new Date().toISOString().split('T')[0],
      observations: [
        {
          test_name: 'Fasting Blood Sugar',
          value: 112,
          unit: 'mg/dL',
          reference_range: '70 - 99 mg/dL',
          interpretation: 'High',
        },
        {
          test_name: 'HbA1c',
          value: 6.4,
          unit: '%',
          reference_range: '4.0 - 5.6 %',
          interpretation: 'High',
        },
        {
          test_name: 'Serum Creatinine',
          value: 0.9,
          unit: 'mg/dL',
          reference_range: '0.7 - 1.3 mg/dL',
          interpretation: 'Normal',
        },
      ],
      medications: [
        {
          name: 'Metformin Hydrochloride',
          dosage: '500 mg',
          frequency: 'Twice daily after meals',
          duration: '30 days',
        },
      ],
      conditions: [
        {
          name: 'Impaired Fasting Glucose (Pre-diabetes)',
          clinical_status: 'active',
          notes: 'Diagnosed based on repeated elevated FBS values',
        },
      ],
    },
    {
      external_record_id: `ABDM-RX-${Date.now().toString().slice(-6)}`,
      source_system: 'mock_abdm',
      facility_name: 'Apollo Hospital Bangalore',
      encounter_date: new Date().toISOString().split('T')[0],
      observations: [
        {
          test_name: 'Systolic Blood Pressure',
          value: 138,
          unit: 'mmHg',
          reference_range: '90 - 120 mmHg',
          interpretation: 'Elevated',
        },
        {
          test_name: 'Diastolic Blood Pressure',
          value: 88,
          unit: 'mmHg',
          reference_range: '60 - 80 mmHg',
          interpretation: 'Elevated',
        },
      ],
      medications: [
        {
          name: 'Telmisartan',
          dosage: '40 mg',
          frequency: 'Once daily in the morning',
          duration: '60 days',
        },
      ],
      conditions: [
        {
          name: 'Essential Hypertension (Stage 1)',
          clinical_status: 'active',
        },
      ],
    },
  ];
}
