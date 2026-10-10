export interface SyntheticObservation {
  test_name: string;
  value: number;
  unit: string;
  reference_range?: string;
  interpretation?: string;
  effective_datetime?: string;
}

export interface SyntheticMedication {
  name: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  instructions?: string;
}

export interface SyntheticCondition {
  name: string;
  clinical_status?: string;
  onset_datetime?: string;
  notes?: string;
}

export interface SyntheticRecordBundle {
  external_record_id: string;
  source_system: string;
  facility_name?: string;
  encounter_date?: string;
  observations: SyntheticObservation[];
  medications: SyntheticMedication[];
  conditions: SyntheticCondition[];
}

export interface MockAbdmPreviewResponse {
  is_duplicate: boolean;
  checksum: string;
  source_system: string;
  external_record_id: string;
  observation_count: number;
  medication_count: number;
  condition_count: number;
  observations_preview: SyntheticObservation[];
  medications_preview: SyntheticMedication[];
  conditions_preview: SyntheticCondition[];
  existing_record_id?: string | null;
  imported_at?: string | null;
}

export interface MockAbdmConfirmResponse {
  status: string;
  import_id: string;
  is_duplicate: boolean;
  created_resources: {
    observations?: string[];
    medications?: string[];
    conditions?: string[];
  };
}

export interface MockAbdmImportRecord {
  id: string;
  tenant_id: string;
  patient_id: string;
  external_record_id: string;
  source_system: string;
  facility_name?: string | null;
  bundle_checksum: string;
  status: string;
  imported_at: string;
}
