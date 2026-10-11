import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { usePatientStore } from '../../store/slices/patientSlice';
import { useAuthStore } from '../../store/slices/authSlice';
import { useUIStore } from '../../store/slices/uiSlice';
import { listPatients, deletePatient } from '../../services/patientService';
import { useNavigate } from 'react-router-dom';
import { Search, Plus, User, Edit2, Trash2, Calendar, Fingerprint, ChevronRight, Users, Sparkles } from 'lucide-react';
import { calculateAge, formatAge } from '../../utils/dateUtils';
import { PageHeader } from '../../components/ui/PageHeader';
import { StickyToolbar } from '../../components/ui/StickyToolbar';
import { useCreateIntent } from '../../hooks/useCreateIntent';
import { PatientFormWizard } from '../../components/patients/PatientFormWizard';
import { getTestPatients } from '../../data/testPatients';

function Patients() {
  const { t } = useTranslation();
  const { patients, setPatients, setCurrentPatient } = usePatientStore();
  const { user } = useAuthStore();
  const showConfirmation = useUIStore(state => state.showConfirmation);
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPatient, setEditingPatient] = useState<any>(null);
  const searchTerm = useUIStore(state => state.pageSearchTerm);
  const setSearchTerm = useUIStore(state => state.setPageSearchTerm);
  const setIsPageSearchSupported = useUIStore(state => state.setIsPageSearchSupported);

  const fetchPatients = async () => {
    setLoading(true);
    try {
      const response = await listPatients(undefined, 200);
      setPatients(response.items || []);
    } catch (error) {
      console.error('Failed to load patients:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPatients();
  }, []);

  useEffect(() => {
    setIsPageSearchSupported(true);
    return () => {
      setIsPageSearchSupported(false);
      setSearchTerm('');
    };
  }, [setIsPageSearchSupported, setSearchTerm]);

  const handleOpenModal = (patient: any = null) => {
    setEditingPatient(patient || null);
    setIsModalOpen(true);
  };

  // Open the create modal automatically when arrived via ?new=patient
  useCreateIntent(() => handleOpenModal(), 'patient');

  const handleWizardSaved = async () => {
    await fetchPatients();
    setIsModalOpen(false);
  };

  const handleDelete = (id: string, name: string) => {
    showConfirmation({
      title: t('patients.delete_patient'),
      message: t('patients.delete_confirm', { name }),
      confirmLabel: t('common.delete'),
      confirmVariant: 'danger',
      onConfirm: async () => {
        try {
          await deletePatient(id);
          await fetchPatients();
        } catch (err) {
          console.error('Failed to delete patient:', err);
          alert(t('patients.failed_delete'));
        }
      }
    });
  };

  const filteredPatients = patients.filter(p => {
    const fullName = `${p.name?.given?.join(' ')} ${p.name?.family}`.toLowerCase();
    return fullName.includes(searchTerm.toLowerCase()) || p.mrn?.toLowerCase().includes(searchTerm.toLowerCase());
  });

  const getGenderColor = (gender: string) => {
    switch(gender?.toLowerCase()) {
      case 'male': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400';
      case 'female': return 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-400';
      default: return 'bg-gray-100 dark:bg-dark-bg text-gray-700 dark:text-dark-muted';
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('patients.directory')}
        subtitle={t('patients.manage_profiles')}
        icon={<Users className="size-5" />}
        breadcrumbs={[]}
      />

      <StickyToolbar
        actions={
          <div className="flex items-center space-x-2.5">
            <button 
              onClick={() => {
                const demoCohort = getTestPatients();
                setPatients(demoCohort);
              }}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:hover:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 rounded-lg transition-colors text-xs font-medium"
              title="Load rich demo patient cohort showcasing chronic disease, respiratory, thyroid, and geriatric profiles"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>Load Demo Showcase</span>
            </button>
            <button 
              onClick={() => handleOpenModal()}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-xs font-medium shadow-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{t('patients.add_patient')}</span>
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-3"></div>
          <p className="text-gray-500 dark:text-dark-muted text-sm">{t('patients.loading_data')}</p>
        </div>
      ) : filteredPatients.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {filteredPatients.map((patient) => (
            <div 
              key={patient.id} 
              className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200/80 dark:border-dark-border overflow-hidden hover:border-gray-300 dark:hover:border-dark-border-strong hover:shadow-xs transition-all group flex flex-col justify-between"
            >
              <div className="p-5">
                <div className="flex justify-between items-start mb-3">
                  <div className="w-10 h-10 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-lg flex items-center justify-center shrink-0">
                    <User className="w-5 h-5" />
                  </div>
                  <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      onClick={() => handleOpenModal(patient)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-dark-bg rounded-lg transition-colors"
                      title={t('patients.edit_patient')}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button 
                      onClick={() => handleDelete(patient.id, `${patient.name?.given?.[0]} ${patient.name?.family}`)}
                      className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                      title={t('patients.delete_patient')}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="cursor-pointer" onClick={() => navigate(`/patients/${patient.id}`)}>
                  <h3 className="text-base font-semibold text-gray-900 dark:text-dark-text group-hover:text-blue-600 transition-colors truncate">
                    {patient.name?.given?.join(' ')} {patient.name?.family}
                  </h3>
                  
                  <div className="flex items-center space-x-1.5 mt-2 flex-wrap gap-y-1">
                    <span className={`px-2 py-0.5 text-[11px] font-medium rounded-md ${getGenderColor(patient.gender)}`}>
                      {patient.gender}
                    </span>
                    {patient.mrn && (
                      <span className="px-2 py-0.5 text-[11px] font-medium bg-gray-100 dark:bg-dark-bg text-gray-600 dark:text-dark-muted rounded-md">
                        {t('patients.mrn')}: {patient.mrn}
                      </span>
                    )}
                    {patient.id?.startsWith('33333333-3333-') && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                        <Sparkles className="w-2.5 h-2.5 mr-1" />
                        Demo Cohort
                      </span>
                    )}
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="flex items-center text-xs text-gray-500 dark:text-dark-muted">
                      <Calendar className="w-3.5 h-3.5 mr-1.5 text-gray-400 shrink-0" />
                      <span>
                        {t('patients.born')}: {patient.birth_date || 'Unknown'} 
                        { patient.birth_date && (
                          <span className="ml-1 text-gray-400 font-normal">
                            ({formatAge(patient.birth_date)})
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center text-xs text-gray-500 dark:text-dark-muted">
                      <Fingerprint className="w-3.5 h-3.5 mr-1.5 text-gray-400 shrink-0" />
                      <span className="truncate font-mono text-[11px]">ID: {patient.id.substring(0, 8)}...</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="px-5 py-3 bg-gray-50/50 dark:bg-dark-bg/30 border-t border-gray-100 dark:border-dark-border flex items-center justify-between">
                <button 
                  onClick={() => navigate(`/patients/${patient.id}`)}
                  className="text-xs font-medium text-blue-600 dark:text-blue-400 flex items-center hover:underline"
                >
                  {t('patients.view_profile')}
                  <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 bg-gray-50 dark:bg-dark-bg/30 rounded-3xl border-2 border-dashed border-gray-200 dark:border-dark-border">
          <div className="w-16 h-16 bg-white dark:bg-dark-surface rounded-full flex items-center justify-center shadow-xs mb-4">
            <Users className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-bold text-gray-900 dark:text-dark-text">{t('patients.no_patients')}</h3>
          <p className="text-gray-500 mt-1 mb-6 text-center max-w-xs">
            {searchTerm ? t('patients.no_results', { term: searchTerm }) : t('patients.start_adding')}
          </p>
          <div className="flex items-center space-x-3">
            {searchTerm ? (
              <button 
                onClick={() => setSearchTerm('')} 
                className="px-8 py-2.5 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-all shadow-lg shadow-blue-200/50 dark:shadow-none active:scale-95"
              >
                {t('common.reset')}
              </button>
            ) : (
              <>
                <button 
                  onClick={() => {
                    const demoCohort = getTestPatients();
                    setPatients(demoCohort);
                  }}
                  className="flex items-center space-x-2 px-6 py-2.5 bg-emerald-600 text-white rounded-xl font-bold hover:bg-emerald-700 transition-all shadow-lg shadow-emerald-200/50 dark:shadow-none active:scale-95"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Load Demo Showcase</span>
                </button>
                <button 
                  onClick={() => handleOpenModal()} 
                  className="px-6 py-2.5 bg-gray-100 dark:bg-dark-surface border border-gray-200 dark:border-dark-border text-gray-800 dark:text-dark-text rounded-xl font-bold hover:bg-gray-200 transition-all"
                >
                  {t('patients.add_first')}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Patient multi-step create/edit wizard */}
      <PatientFormWizard
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        patient={editingPatient}
        onSaved={handleWizardSaved}
      />
    </div>
  );
}

export default Patients;
