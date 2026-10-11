export interface TimelineItem {
  id: string;
  event_type: 'examination' | 'document' | 'observation' | 'medication' | 'condition';
  timestamp?: string | null;
  dt?: string | null;
  date_source?: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  review_status?: string | null;
  confidence?: number | null;
  details?: Record<string, any>;
  source_document_id?: string | null;
  examination_id?: string | null;
}

export interface PatientTimelineResponse {
  patient_id: string;
  total: number;
  items: TimelineItem[];
}

