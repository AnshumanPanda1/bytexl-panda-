import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getPatient, deletePatient } from '../../services/patientService';
import { Patient } from '../../types/patient';
import { Edit2, Trash2, Fingerprint, User, Download, Database } from 'lucide-react';
import { useUIStore } from '../../store/slices/uiSlice';
import { usePatientStore } from '../../store/slices/patientSlice';
import { MedicationSummary } from '../../components/patients/MedicationSummary';
import { PatientFormWizard } from '../../components/patients/PatientFormWizard';
import BiomarkerSummary from '../../components/patients/BiomarkerSummary';
import ExaminationSummary from '../../components/patients/ExaminationSummary';
import ClinicalEventSummary from '../../components/patients/ClinicalEventSummary';
import { PatientSummaryCard } from '../../components/patients/PatientSummaryCard';
import { PatientTimelineCard } from '../../components/patients/PatientTimelineCard';
import { MockAbdmImportModal } from '../../components/patients/MockAbdmImportModal';
import { downloadPatientFhirBundle } from '../../services/backupService';
import { formatAge } from '../../utils/dateUtils';
import { PageHeader } from '../../components/ui/PageHeader';
import { StickyToolbar } from '../../components/ui/StickyToolbar';
import { SetupChecklistCard } from '../../components/setup/SetupChecklistCard';

function PatientDetail() {
  const { t } = useTranslation();
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const showConfirmation = useUIStore(state => state.showConfirmation);
  const { currentPatient, setCurrentPatient } = usePatientStore();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);

  // Sync global patient when this patient is loaded
  useEffect(() => {
    if (patient && (!currentPatient || currentPatient.id !== patient.id)) {
      setCurrentPatient(patient);
    }
  }, [patient, currentPatient, setCurrentPatient]);

  // Edit state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAbdmModalOpen, setIsAbdmModalOpen] = useState(false);
  const [exportingFhir, setExportingFhir] = useState(false);

  const handleExportFhir = async () => {
    if (!patientId || !patient) return;
    try {
      setExportingFhir(true);
      await downloadPatientFhirBundle(patientId, `fhir-bundle-${patient.mrn || patient.id}.json`);
    } catch (err) {
      console.error('Failed to export FHIR bundle:', err);
      alert('Failed to export FHIR bundle');
    } finally {
      setExportingFhir(false);
    }
  };

  useEffect(() => {
    if (patientId) {
      loadData();
    }
  }, [patientId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const patientData = await getPatient(patientId!);
      setPatient(patientData);
    } catch (error) {
      console.error('Failed to load patient details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenEditModal = () => {
    setIsModalOpen(true);
  };

  const handleDeletePatient = () => {
    if (!patient) return;
    const fullName = `${patient.name?.given?.join(' ')} ${patient.name?.family}`;
    showConfirmation({
      title: t('patients.delete_profile_title'),
      message: t('patients.delete_profile_confirm', { name: fullName }),
      confirmLabel: t('patients.delete_permanently'),
      confirmVariant: 'danger',
      onConfirm: async () => {
        try {
          await deletePatient(patientId!);
          navigate('/patients');
        } catch (err) {
          console.error('Failed to delete patient:', err);
          alert(t('patients.failed_delete'));
        }
      }
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!patient) {
    return <div className="text-center py-10 text-gray-500">{t('patients.patient_not_found')}</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${patient.name?.given?.join(' ') ?? ''} ${patient.name?.family ?? ''}`.trim()}
        subtitle={
          <div className="flex items-center">
            <Fingerprint className="w-3 h-3 mr-1" />
            {t('patients.patient_id')}: {patient.id}
          </div>
        }
        icon={<User className="size-5" />}
        breadcrumbs={[
          { label: t('patients.directory'), href: '/patients' }
        ]}
        showBackButton={true}
      />

      <StickyToolbar
        actions={
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsAbdmModalOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:hover:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/50 rounded-lg transition-colors text-xs font-medium"
            >
              <Database className="w-3.5 h-3.5 text-emerald-600" />
              <span>Simulate ABDM Import</span>
            </button>
            <button
              onClick={handleExportFhir}
              disabled={exportingFhir}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/30 dark:hover:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800/50 rounded-lg transition-colors text-xs font-medium disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-blue-600" />
              <span>{exportingFhir ? 'Exporting...' : 'Export FHIR (R4)'}</span>
            </button>
            <button 
              onClick={handleOpenEditModal}
              className="flex items-center space-x-1.5 px-3 py-1.5 border border-gray-200 dark:border-dark-border text-gray-700 dark:text-dark-text rounded-lg hover:bg-gray-50 dark:hover:bg-dark-surface transition-colors text-xs font-medium"
            >
              <Edit2 className="w-3.5 h-3.5" />
              <span>{t('patients.edit_profile')}</span>
            </button>
            <button 
              onClick={handleDeletePatient}
              className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
              title={t('patients.delete_patient')}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 2xl:grid-cols-4 gap-6 items-start">
        {/* Main Content Area: Content & Summaries */}
        <div className="2xl:col-span-3 order-2 2xl:order-1 space-y-6 min-w-0">
          
          {/* AI Bilingual Plain-Language Health Summary */}
          {patientId && <PatientSummaryCard patientId={patientId} />}

          {/* Middle Section: Quick Clinical Overview */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {patientId && <MedicationSummary patientId={patientId} />}
            {patientId && <BiomarkerSummary patientId={patientId} />}
          </div>

          {/* Unified Chronological Health Timeline */}
          {patientId && <PatientTimelineCard patientId={patientId} />}

          {/* Activity Overview: Document & Event Records */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {patientId && <ExaminationSummary patientId={patientId} />}
            {patientId && <ClinicalEventSummary patientId={patientId} />}
          </div>
        </div>

        {/* Sidebar: Personal Info (Top on small, Side on wide) */}
        <div className="2xl:col-span-1 order-1 2xl:order-2">
          <div className="bg-white dark:bg-dark-surface rounded-xl p-5 border border-gray-200/80 dark:border-dark-border shadow-xs">
            <div className="flex items-center space-x-2 mb-4">
              <User className="w-4 h-4 text-gray-400" />
              <h4 className="text-xs font-semibold text-gray-500 dark:text-dark-muted uppercase tracking-wider">{t('patients.personal_info')}</h4>
            </div>

            <div className="grid grid-cols-2 gap-4 2xl:block 2xl:space-y-4">
              <div>
                <p className="text-[11px] font-medium text-gray-400 dark:text-dark-muted mb-1">{t('patients.mrn')}</p>
                <div className="flex items-baseline">
                  <span className="text-xs font-mono font-medium bg-gray-50 dark:bg-dark-bg px-2.5 py-1 rounded-md border border-gray-200 dark:border-dark-border text-gray-800 dark:text-dark-text">{patient.mrn || '—'}</span>
                </div>
              </div>

              <div>
                <p className="text-[11px] font-medium text-gray-400 dark:text-dark-muted mb-1">{t('patients.dob')}</p>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-gray-800 dark:text-dark-text leading-tight">
                    {patient.birth_date || '—'}
                  </span>
                  {patient.birth_date && (
                    <span className="text-[11px] text-blue-600 dark:text-blue-400 font-medium mt-0.5">
                      {formatAge(patient.birth_date)}
                    </span>
                  )}
                </div>
              </div>

              <div className="pt-0 2xl:pt-3 border-t-0 2xl:border-t border-gray-100 dark:border-dark-border col-span-2 2xl:col-span-1">
                <p className="text-[11px] font-medium text-gray-400 dark:text-dark-muted mb-1">{t('patients.gender')}</p>
                <p className="text-sm font-medium text-gray-800 dark:text-dark-text capitalize leading-tight">
                  {patient.gender || t('patients.unknown')}
                </p>
              </div>
            </div>
          </div>

          {/* Setup completion card — backend-derived checklist */}
          <div className="mt-4">
            <SetupChecklistCard patientId={patient.id} />
          </div>
        </div>
      </div>

      <PatientFormWizard
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        patient={patient}
        onSaved={(updated) => { setPatient(updated); setIsModalOpen(false); }}
      />

      <MockAbdmImportModal
        isOpen={isAbdmModalOpen}
        onClose={() => setIsAbdmModalOpen(false)}
        patientId={patient.id}
        onImportCompleted={() => {
          loadData();
        }}
      />
    </div>
  );
}

export default PatientDetail;
