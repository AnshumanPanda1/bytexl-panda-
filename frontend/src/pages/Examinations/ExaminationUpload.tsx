import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { uploadDocument } from '../../services/documentService';
import { createExamination, getExaminationCategories, createExaminationCategory } from '../../services/examinationService';
import { listDoctors, createDoctor, Doctor } from '../../services/doctorService';
import { usePatientStore } from '../../store/slices/patientSlice';
import { useUIStore } from '../../store/slices/uiSlice';
import { offlineService } from '../../services/offlineService';
import { RichTextEditor } from '../../components/ui/RichTextEditor';
import { Check, X, FileText, RotateCcw, Sparkles, Plus, Info, Camera, Upload, AlertCircle } from 'lucide-react';
import { NoPatientState } from '../../components/ui/NoPatientState';
import { ActiveTaskBadge } from '../../components/ui/ActiveTaskBadge';
import { AIMagicFillModal } from '../../components/ui/AIMagicFillModal';
import { AIAssistButton } from '../../components/ui/AIAssistButton';
import { DoctorSelector } from '../../components/ui/DoctorSelector';
import { OrganizationSelector } from '../../components/ui/OrganizationSelector';
import { CategorySelector } from '../../components/ui/CategorySelector';
import { listOrganizations, createOrganization, Organization } from '../../services/organizationService';
import { DynamicIcon } from '../../components/ui/DynamicIcon';
import { ExaminationGroupManager, type ExamGroup, type FileWithGroup } from './ExaminationGroupManager';
import { isMobileDevice } from '../../utils/deviceUtils';
import { getTempPreviewUrl } from '../../services/documentService';
import { FilePreviewManager } from '../../components/ui/FilePreviewManager';
import { DocumentCard } from '../../components/ui/DocumentCard';
import { PageHeader } from '../../components/ui/PageHeader';
import { StickyToolbar } from '../../components/ui/StickyToolbar';
import { DatePicker } from '../../components/ui/DatePicker';

function ExaminationUpload() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { currentPatient } = usePatientStore();
  const showConfirmation = useUIStore(state => state.showConfirmation);
  const [files, setFiles] = useState<{file: File, include: boolean, groupIndex?: number}[]>([]);
  const [activePreview, setActivePreview] = useState<{ url: string; name: string; type: string; isBackendProcessed?: boolean; localFile?: File } | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [patientId, setPatientId] = useState('');
  const [examinationDate, setExaminationDate] = useState<string | undefined>(new Date().toISOString().split('T')[0]);
  const [notes, setNotes] = useState('');
  const [patientNotes, setPatientNotes] = useState('');
  const [category, setCategory] = useState('');
  const [dynamicCategories, setDynamicCategories] = useState<any[]>([]);
  const [isCustomCategory, setIsCustomCategory] = useState(false);
  const [availableDoctors, setAvailableDoctors] = useState<Doctor[]>([]);
  const [availableOrganizations, setAvailableOrganizations] = useState<Organization[]>([]);
  const [selectedDoctorIds, setSelectedDoctorIds] = useState<string[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [hasDraft, setHasDraft] = useState(false);
  const [isMagicFillOpen, setIsMagicFillOpen] = useState(false);
  const [discoveredDoctors, setDiscoveredDoctors] = useState<string[]>([]);
  const [isCreatingDoctor, setIsCreatingDoctor] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [createdExamId, setCreatedExamId] = useState<string | null>(null);
  const [uploadedFileKeys, setUploadedFileKeys] = useState<Set<string>>(new Set());
  const [createdBulkExamMap, setCreatedBulkExamMap] = useState<Record<string, string>>({});

  // New states for Smart Mode and Bulk Create
  const [isSmartMode, setIsSmartMode] = useState(true);
  const [isBulkMode, setIsBulkMode] = useState(false);
  
  // States for new Bulk Upload Manager
  const [bulkFiles, setBulkFiles] = useState<FileWithGroup[]>([]);
  const [bulkGroups, setBulkGroups] = useState<ExamGroup[]>([]);

  // Initialize first group if bulk mode or smart mode is activated
  useEffect(() => {
    if ((isBulkMode || isSmartMode) && bulkGroups.length === 0) {
      setBulkGroups([{
        id: Math.random().toString(36).substr(2, 9),
        name: 'Examination 1',
        date: new Date().toISOString().split('T')[0],
        category: 'Clinical',
        doctorIds: [],
        notes: '',
        patientNotes: ''
      }]);
    }
  }, [isBulkMode, isSmartMode]);

  // Sync legacy files with bulkFiles whenever legacy files change
  useEffect(() => {
    if (files.length > 0) {
      const bulkFileNames = new Set(bulkFiles.map(f => f.file.name));
      const newToSync = files.filter(f => !bulkFileNames.has(f.file.name));
      
      if (newToSync.length > 0) {
        const newBulkFiles = newToSync.map(f => ({
          id: Math.random().toString(36).substr(2, 9),
          file: f.file,
          groupId: isSmartMode ? (bulkGroups[0]?.id || null) : null,
          includeInExtraction: f.include
        }));
        setBulkFiles(prev => [...prev, ...newBulkFiles]);
      }
    }
  }, [files, isSmartMode, bulkGroups]);

  // Sync back from bulkFiles to legacy files when in manual mode
  useEffect(() => {
    if (!isSmartMode && !isBulkMode && bulkFiles.length > 0) {
      const legacyFileNames = new Set(files.map(f => f.file.name));
      const newToSync = bulkFiles.filter(f => !legacyFileNames.has(f.file.name));
      
      if (newToSync.length > 0) {
        const newLegacyFiles = newToSync.map(f => ({
          file: f.file,
          include: f.includeInExtraction
        }));
        setFiles(prev => [...prev, ...newLegacyFiles]);
      }
    }
  }, [bulkFiles, isSmartMode, isBulkMode]);

  // Auto-save draft logic (excluding Files for now to keep it lightweight)
  useEffect(() => {
    const draftData = {
      patientId,
      examinationDate,
      notes,
      patientNotes,
      category,
      selectedDoctorIds,
    };
    
    const timer = setTimeout(() => {
      if (notes || patientNotes || selectedDoctorIds.length > 0 || files.length > 0) {
        offlineService.saveDraft('new-examination', 'examination', draftData);
      }
    }, 2000);
    
    return () => clearTimeout(timer);
  }, [patientId, examinationDate, notes, patientNotes, category, selectedDoctorIds, files.length]);

  useEffect(() => {
    const checkDraft = async () => {
      const draft = await offlineService.getDraft('new-examination');
      if (draft) setHasDraft(true);
    };
    checkDraft();
  }, []);

  const restoreDraft = async () => {
    const draft = await offlineService.getDraft('new-examination');
    if (draft) {
      const { data } = draft;
      setPatientId(data.patientId);
      setExaminationDate(data.examinationDate);
      setNotes(data.notes || '');
      setPatientNotes(data.patientNotes || '');
      setCategory(data.category);
      setSelectedDoctorIds(data.selectedDoctorIds || []);
      setHasDraft(false);
    }
  };

  useEffect(() => {
    // If the user navigates here and a patient is globally selected, auto-fill it
    if (currentPatient?.id) {
      setPatientId(currentPatient.id);
    }
  }, [currentPatient]);

  useEffect(() => {
    // Reset partial submission tracking when patient changes
    setCreatedExamId(null);
    setUploadedFileKeys(new Set());
    setCreatedBulkExamMap({});
    setSaveError(null);
  }, [patientId]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [cats, docs, orgs] = await Promise.all([
          getExaminationCategories(),
          listDoctors(),
          listOrganizations()
        ]);
        setDynamicCategories(cats);
        setAvailableDoctors(docs);
        setAvailableOrganizations(orgs);
      } catch (err) {
        console.error('Failed to fetch initial data:', err);
      }
    };

    fetchData();
  }, []);

  const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.dcm', '.txt', '.md', '.bmp', '.webp', '.tiff', '.tif', '.gif'];
  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  const validateAndAddFiles = (selectedFiles: File[]) => {
    setFileError(null);
    const validFiles: File[] = [];
    const errorMessages: string[] = [];

    for (const file of selectedFiles) {
      const lastDot = file.name.lastIndexOf('.');
      const ext = lastDot !== -1 ? file.name.slice(lastDot).toLowerCase() : '';
      if (!ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
        errorMessages.push(`"${file.name}": Unsupported format. Allowed: PDF, PNG, JPG, JPEG, DICOM, TXT.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        errorMessages.push(`"${file.name}": Exceeds 50MB maximum size limit.`);
        continue;
      }
      validFiles.push(file);
    }

    if (errorMessages.length > 0) {
      setFileError(errorMessages.join(' '));
    }

    if (validFiles.length > 0) {
      const newFiles = validFiles.map(file => ({
        file,
        include: true,
        groupIndex: 0
      }));
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      validateAndAddFiles(Array.from(e.target.files));
    }
    // Reset the input value so the same file can be selected again if needed
    e.target.value = '';
  };

  const toggleFileInclusion = (index: number) => {
    setFiles((prev) => prev.map((f, i) => i === index ? { ...f, include: !f.include } : f));
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const openPreview = async (file: File) => {
    const isDicom = file.name.toLowerCase().endsWith('.dcm');
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    
    if (isDicom || isPdf) {
      setIsPreviewLoading(true);
      try {
        const result = await getTempPreviewUrl(file);
        setActivePreview({ 
          url: result.url, 
          name: file.name, 
          type: file.type || (isPdf ? 'application/pdf' : 'application/dicom'),
          isBackendProcessed: true,
          localFile: file
        });
      } catch (err) {
        console.error("Failed to generate temp preview:", err);
        const url = URL.createObjectURL(file);
        setActivePreview({ url, name: file.name, type: file.type });
      } finally {
        setIsPreviewLoading(false);
      }
    } else {
      const url = URL.createObjectURL(file);
      const isImg = file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
      const type = file.type || (isImg ? 'image/jpeg' : 'application/octet-stream');
      setActivePreview({ url, name: file.name, type });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!patientId) {
      alert('Please select a patient from the top navigation bar before saving an examination.');
      return;
    }

    if (!navigator.onLine && (files.length > 0 || bulkFiles.length > 0)) {
       alert('You are currently offline. New examinations with file uploads require an active connection. Your current notes have been saved as a draft.');
       return;
    }

    if (isBulkMode) {
      const unassignedCount = bulkFiles.filter(f => f.groupId === null).length;
      if (unassignedCount > 0) {
        showConfirmation({
          title: 'Unassigned Documents',
          message: `You have ${unassignedCount} document(s) that are not assigned to any examination group. These will NOT be uploaded. Do you want to continue?`,
          confirmLabel: 'Upload Anyway',
          cancelLabel: 'Go Back',
          confirmVariant: 'danger',
          onConfirm: () => executeSubmit()
        });
        return;
      }
    }

    executeSubmit();
  };

  const getFileKey = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;

  const executeSubmit = async () => {
    setUploading(true);
    setSaveError(null);
    try {
      if (isBulkMode) {
        // Bulk Create: Create multiple examinations based on groups
        const newExamMap = { ...createdBulkExamMap };
        const newUploadedKeys = new Set(uploadedFileKeys);

        for (const group of bulkGroups) {
          const groupFiles = bulkFiles.filter(f => f.groupId === group.id);
          // Only create examination if it has files OR has notes
          if (groupFiles.length === 0 && !group.notes && !group.patientNotes) continue;

          let examId = newExamMap[group.id];
          if (!examId) {
            // Create Examination for this group
            const exam = await createExamination({
              patient_id: patientId,
              examination_date: isSmartMode ? undefined : group.date,
              notes: isSmartMode ? undefined : group.notes || undefined,
              patient_notes: group.patientNotes || undefined,
              category: isSmartMode ? 'Clinical' : group.category,
              doctor_ids: isSmartMode ? [] : group.doctorIds,
              organization_id: isSmartMode ? undefined : (selectedOrganizationId || undefined),
              auto_extract_metadata: isSmartMode
            });
            examId = exam.id;
            newExamMap[group.id] = examId;
            setCreatedBulkExamMap({ ...newExamMap });
          }

          // Upload all files associated with this group's examination (skip already uploaded)
          for (const { file, includeInExtraction } of groupFiles) {
            const key = getFileKey(file);
            if (!newUploadedKeys.has(key)) {
              await uploadDocument(file, patientId, examId, includeInExtraction);
              newUploadedKeys.add(key);
              setUploadedFileKeys(new Set(newUploadedKeys));
            }
          }
        }
        
        // Clear draft
        await offlineService.deleteDraft('new-examination');
        
        // Redirect to the examination list for bulk uploads
        navigate('/examinations');
      } else {
        // Single Examination Create: Reuse already-created exam if retrying after upload failure
        let examId = createdExamId;
        if (!examId) {
          const exam = await createExamination({
            patient_id: patientId,
            examination_date: isSmartMode ? undefined : examinationDate,
            notes: isSmartMode ? undefined : notes || undefined,
            patient_notes: patientNotes || undefined, // Patient notes are always sent if present
            category: isSmartMode ? (category || undefined) : category,
            doctor_ids: isSmartMode ? [] : selectedDoctorIds,
            organization_id: isSmartMode ? undefined : (selectedOrganizationId || undefined),
            auto_extract_metadata: isSmartMode
          });
          examId = exam.id;
          setCreatedExamId(examId);
        }

        // 2. Upload all files associated with this examination (skip already uploaded)
        const filesToUpload = isSmartMode 
          ? bulkFiles.map(f => ({ file: f.file, include: f.includeInExtraction }))
          : files;

        const newUploadedKeys = new Set(uploadedFileKeys);
        for (const { file, include } of filesToUpload) {
          const key = getFileKey(file);
          if (!newUploadedKeys.has(key)) {
            await uploadDocument(file, patientId, examId || undefined, include);
            newUploadedKeys.add(key);
            setUploadedFileKeys(new Set(newUploadedKeys));
          }
        }
        
        // Clear draft
        await offlineService.deleteDraft('new-examination');
        
        // Redirect to the examination detail page
        navigate(`/examinations/${examId}`);
      }
    } catch (error: any) {
      console.error('Save examination failed:', error);
      const errorDetail =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        (typeof error?.response?.data === 'string' ? error.response.data : null) ||
        error?.message ||
        'Upload failed. Please check the network connection and try again.';
      const displayMsg = typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail);
      setSaveError(displayMsg);
      alert(`Save failed: ${displayMsg}`);
    } finally {
      setUploading(false);
    }
  };

  const handleAIFill = (data: any) => {
    if (data.examination_date) setExaminationDate(data.examination_date);
    if (data.notes) setNotes(data.notes);
    if (data.patient_notes) setPatientNotes(data.patient_notes);
    if (data.category) {
      setCategory(data.category);
      setIsCustomCategory(!dynamicCategories.find(c => c.name === data.category || c.slug === data.category));
    }
    if (data.doctor_names && data.doctor_names.length > 0) {
      const matchedIds: string[] = [];
      const unknown: string[] = [];

      data.doctor_names.forEach((rawName: string) => {
        const name = rawName.replace(/^(dr\.?\s*)+/i, '').trim();
        const match = availableDoctors.find(doc => 
          doc.name.toLowerCase().includes(name.toLowerCase()) || 
          name.toLowerCase().includes(doc.name.toLowerCase())
        );
        if (match) matchedIds.push(match.id);
        else unknown.push(name);
      });
      
      if (matchedIds.length > 0) {
        setSelectedDoctorIds(Array.from(new Set([...selectedDoctorIds, ...matchedIds])));
      }
      if (unknown.length > 0) {
        setDiscoveredDoctors(prev => Array.from(new Set([...prev, ...unknown])));
      }
    }
  };

  const handleCreateDoctor = async (name: string) => {
    setIsCreatingDoctor(true);
    try {
      const newDoc = await createDoctor({ name });
      setAvailableDoctors(prev => [...prev, newDoc]);
      setSelectedDoctorIds(prev => [...prev, newDoc.id]);
      setDiscoveredDoctors(prev => prev.filter(d => d !== name));
    } catch (err) {
      console.error("Failed to create doctor", err);
      alert("Failed to add doctor to system.");
    } finally {
      setIsCreatingDoctor(false);
    }
  };

  const handleCreateOrganization = async (name: string) => {
    try {
      const newOrg = await createOrganization({ name, active: true });
      setAvailableOrganizations(prev => [...prev, newOrg]);
      setSelectedOrganizationId(newOrg.id);
    } catch (err) {
      console.error("Failed to create organization", err);
      alert(t('organizations.failed_save'));
    }
  };

  const handleCreateCategory = async (name: string) => {
    try {
      const newCat = await createExaminationCategory({ name, slug: name.toLowerCase().replace(/\s+/g, '-') });
      setDynamicCategories(prev => [...prev, newCat]);
      setCategory(newCat.name);
    } catch (err) {
      console.error("Failed to create category", err);
      alert("Failed to create category");
    }
  };

  const headerIcon = useMemo(() => <FileText className="w-8 h-8" />, []);

  if (!currentPatient) {
    return <NoPatientState icon={FileText} contextKey="examination_upload" />;
  }

  return (
    <div className={`${isBulkMode ? 'max-w-5xl' : 'max-w-3xl'} mx-auto transition-all duration-300`}>
      <PageHeader
        title="New Examination"
        subtitle="Upload and analyze clinical documents"
        icon={headerIcon}
        showBackButton={true}
      />

      <StickyToolbar
        actions={
          <div className="flex items-center gap-2">
            {hasDraft && (
              <button 
                type="button"
                onClick={restoreDraft}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400 rounded-lg text-xs font-semibold border border-amber-200 dark:border-amber-800 transition-colors hover:bg-amber-100"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Restore Draft</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsMagicFillOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold text-xs transition-colors shadow-xs"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Magic Fill</span>
            </button>
          </div>
        }
      />

      <form onSubmit={handleSubmit} className="bg-white dark:bg-dark-surface rounded-xl border border-gray-200/80 dark:border-dark-border shadow-xs p-4 sm:p-5 space-y-4">
        {/* Mode Controls Bar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 px-3 bg-gray-50/80 dark:bg-dark-bg/60 border border-gray-200 dark:border-dark-border rounded-lg">
          {/* Smart Extraction AI Toggle */}
          <div className="flex items-center justify-between sm:justify-start gap-3 flex-1">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-500 shrink-0" />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-gray-900 dark:text-dark-text">
                    {t('ai_labels.smart_extraction_ai', 'Smart Extraction AI')}
                  </span>
                  <ActiveTaskBadge taskType="ocr" className="scale-90 origin-left" />
                </div>
                <p className="text-[11px] text-gray-500 dark:text-dark-muted hidden sm:block">
                  {t('ai_labels.smart_extraction_hint', 'Auto-fill date, doctors, and notes from documents')}
                </p>
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={isSmartMode}
              onClick={() => setIsSmartMode(!isSmartMode)}
              className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-hidden ${isSmartMode ? 'bg-blue-600' : 'bg-gray-200 dark:bg-dark-border'}`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${isSmartMode ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </button>
          </div>

          <div className="w-px bg-gray-200 dark:bg-dark-border h-7 hidden sm:block" />

          {/* Bulk Create Toggle */}
          <div className="flex items-center justify-between sm:justify-start gap-3 flex-1 sm:pl-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-indigo-500 shrink-0" />
              <div>
                <span className="text-xs font-semibold text-gray-900 dark:text-dark-text block">
                  Bulk Create
                </span>
                <p className="text-[11px] text-gray-500 dark:text-dark-muted hidden sm:block">
                  Group documents for multiple visits
                </p>
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={isBulkMode}
              onClick={() => {
                const newBulk = !isBulkMode;
                setIsBulkMode(newBulk);
                if (newBulk) setIsSmartMode(true);
              }}
              className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-hidden ${isBulkMode ? 'bg-indigo-600' : 'bg-gray-200 dark:bg-dark-border'}`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${isBulkMode ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>

        {isBulkMode && (
          <div className="flex items-center gap-2 p-2.5 bg-indigo-50/60 dark:bg-indigo-900/15 border border-indigo-100 dark:border-indigo-900/30 rounded-lg">
            <Info className="w-4 h-4 text-indigo-500 shrink-0" />
            <p className="text-xs text-indigo-700 dark:text-indigo-400">
              <strong>Bulk Mode:</strong> Add documents, then drag them into examination bubbles below.
            </p>
          </div>
        )}

        {isBulkMode || isSmartMode ? (
          <ExaminationGroupManager 
            files={bulkFiles}
            setFiles={setBulkFiles}
            groups={bulkGroups}
            setGroups={setBulkGroups}
            availableDoctors={availableDoctors}
            onAddDoctor={handleCreateDoctor}
            isSmartMode={isSmartMode}
            isSingleMode={!isBulkMode && isSmartMode}
            categories={dynamicCategories}
          />
        ) : (
          <>
            {/* 1. Primary Action: Document Upload Front & Center */}
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <label className="block text-xs font-bold text-gray-900 dark:text-dark-text">
                      Upload Medical Document or Prescription
                    </label>
                    <ActiveTaskBadge workflow="full_reconstruction" size="sm" showText={false} />
                  </div>
                  <span className="text-[11px] text-gray-400 dark:text-dark-muted">
                    PDF, PNG, JPG, JPEG (Max 50MB)
                  </span>
                </div>

                {/* File Dropzone */}
                <div 
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (e.dataTransfer.files) {
                      validateAndAddFiles(Array.from(e.dataTransfer.files));
                    }
                  }}
                  className="relative"
                >
                  <input
                    type="file"
                    multiple
                    onChange={handleFileChange}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                    accept=".pdf,.png,.jpg,.jpeg,.dcm,.txt,.md,image/png,image/jpeg,application/pdf"
                    id="file-upload"
                  />
                  <label
                    htmlFor="file-upload"
                    className="flex flex-col items-center justify-center gap-2.5 p-6 sm:p-8 border-2 border-dashed border-blue-200 dark:border-blue-900/50 rounded-xl hover:border-blue-500 dark:hover:border-blue-400 bg-blue-50/20 dark:bg-blue-950/10 hover:bg-blue-50/40 transition-all cursor-pointer text-center group"
                  >
                    <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center group-hover:scale-110 transition-transform">
                      <Upload className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-800 dark:text-dark-text">
                        {files.length === 0 ? 'Click to upload or drag & drop prescription / lab report' : 'Click to add more documents'}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-dark-muted mt-1">
                        AI will transcribe handwriting and extract medications & biomarkers automatically
                      </p>
                    </div>
                  </label>
                </div>

                {/* Mobile Camera Option */}
                {isMobileDevice() && (
                  <div className="relative mt-2">
                    <input
                      type="file"
                      accept="image/*"
                      capture="environment"
                      onChange={handleFileChange}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      id="camera-upload"
                    />
                    <label
                      htmlFor="camera-upload"
                      className="flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-indigo-200 dark:border-indigo-900/30 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-900/10 transition-colors cursor-pointer text-indigo-600 dark:text-indigo-400 font-semibold text-xs"
                    >
                      <Camera className="h-4 w-4" />
                      <span>Take Photo</span>
                    </label>
                  </div>
                )}

                {/* Format or Size Error Banner */}
                {fileError && (
                  <div className="mt-2 flex items-center justify-between p-2 px-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-lg text-xs text-red-600 dark:text-red-400">
                    <div className="flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 text-red-500" />
                      <span>{fileError}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFileError(null)}
                      className="text-red-400 hover:text-red-600 dark:hover:text-red-300 p-0.5 ml-2"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}

                {/* Document Cards Preview */}
                {files.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-3">
                    {files.map((f, i) => (
                      <DocumentCard 
                        key={i}
                        file={f.file}
                        onRemove={() => removeFile(i)}
                        onPreview={() => openPreview(f.file)}
                        onToggleInclusion={() => toggleFileInclusion(i)}
                        includeInExtraction={f.include}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Examination Date (Compact) */}
              <div className="w-full sm:w-72">
                <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted mb-1">
                  Examination / Visit Date <span className="text-red-500">*</span>
                </label>
                <DatePicker
                  placeholder={t('common.select_date', 'Select date')}
                  required
                  value={examinationDate}
                  onChange={setExaminationDate}
                />
              </div>
            </div>

            {/* 2. Optional Visit Details Collapsible Accordion */}
            <details className="group border border-gray-200 dark:border-dark-border rounded-xl bg-gray-50/40 dark:bg-dark-bg/20 transition-all">
              <summary className="flex items-center justify-between p-3.5 px-4 cursor-pointer text-xs font-semibold text-gray-700 dark:text-dark-text select-none hover:bg-gray-50 dark:hover:bg-dark-bg/40 rounded-xl">
                <span className="flex items-center gap-2">
                  <Plus className="w-4 h-4 text-blue-600 group-open:rotate-45 transition-transform" />
                  <span>Additional Visit Details (Physician, Facility, Notes) — Optional</span>
                </span>
                <span className="text-[11px] text-gray-400 font-normal">
                  Click to {notes || patientNotes || selectedDoctorIds.length > 0 ? 'edit' : 'expand'}
                </span>
              </summary>

              <div className="p-4 pt-1 space-y-4 border-t border-gray-100 dark:border-dark-border/40">
                {/* Category, Facility, Physician */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-2">
                  {/* Category */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-semibold text-gray-700 dark:text-dark-muted">
                        Category
                      </label>
                      <AIAssistButton 
                        taskType="magic_fill_examination"
                        context={{ patientId }}
                        showLabel={false}
                        placeholder="Describe visit to categorize..."
                        onSuggestedData={(data) => {
                          if (data.category) setCategory(data.category);
                        }}
                      />
                    </div>
                    <CategorySelector
                      categories={dynamicCategories}
                      selectedName={category}
                      onSelect={(name) => setCategory(name)}
                      onCreate={handleCreateCategory}
                      placeholder={t('examination_detail.header.select_category', 'Select category')}
                    />
                  </div>

                  {/* Facility / Organization */}
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted">
                      Medical Facility
                    </label>
                    <OrganizationSelector
                      organizations={availableOrganizations}
                      selectedId={selectedOrganizationId}
                      onSelect={(id) => setSelectedOrganizationId(id)}
                      onCreate={handleCreateOrganization}
                    />
                  </div>

                  {/* Attending Physician */}
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted">
                      Attending Physician
                    </label>
                    
                    {discoveredDoctors.length > 0 && (
                      <div className="mb-1 flex flex-wrap gap-1">
                        {discoveredDoctors.map(name => (
                          <button
                            key={name}
                            type="button"
                            disabled={isCreatingDoctor}
                            onClick={() => handleCreateDoctor(name)}
                            className="flex items-center gap-1 px-2 py-0.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 rounded text-[11px] font-medium border border-indigo-100 dark:border-indigo-900/30 hover:bg-indigo-100 transition-colors"
                          >
                            <Sparkles className="w-2.5 h-2.5" />
                            <span>+ Dr. {name}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    <DoctorSelector
                      doctors={availableDoctors}
                      selectedIds={selectedDoctorIds}
                      onSelect={(id) => setSelectedDoctorIds(prev => [...prev, id])}
                      onDeselect={(id) => setSelectedDoctorIds(prev => prev.filter(i => i !== id))}
                      onCreateDoctor={handleCreateDoctor}
                      placeholder={t('examinations.attending_physician', 'Select physician')}
                    />
                  </div>
                </div>

                {/* Clinical Notes */}
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted mb-1">
                    Clinical Notes
                  </label>
                  <RichTextEditor 
                    value={notes} 
                    onChange={setNotes} 
                    placeholder="Add clinical observations, diagnosis, or treatment notes..." 
                    minHeight="100px"
                  />
                </div>

                {/* Patient Notes */}
                <div className="space-y-1">
                  <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted">
                    Patient Notes
                  </label>
                  <textarea
                    value={patientNotes}
                    onChange={(e) => setPatientNotes(e.target.value)}
                    placeholder="Patient observations, reported symptoms, or reasons for visit..."
                    rows={2}
                    className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 dark:border-dark-border rounded-lg focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-dark-bg/50 text-gray-900 dark:text-dark-text placeholder-gray-400 dark:placeholder-gray-500 outline-hidden transition-all resize-y min-h-[50px]"
                  />
                </div>
              </div>
            </details>
          </>
        )}

        {isSmartMode && !isBulkMode && (
          <div className="space-y-3 pt-2 border-t border-gray-100 dark:border-dark-border/60">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-gray-700 dark:text-dark-muted">
                  {t('examination_detail.header.category', 'Category')} <span className="text-gray-400 font-normal">(Optional — AI auto-extracts)</span>
                </label>
                <AIAssistButton
                  taskType="magic_fill_examination"
                  context={{ patientId }}
                  showLabel={false}
                  placeholder="Describe the visit to categorize..."
                  onSuggestedData={(data) => {
                    if (data.category) {
                      setCategory(data.category);
                    }
                  }}
                />
              </div>
              <CategorySelector
                categories={dynamicCategories}
                selectedName={category}
                onSelect={(name) => setCategory(name)}
                onCreate={handleCreateCategory}
                placeholder={t('examination_detail.header.select_category', 'Select category')}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-gray-700 dark:text-dark-muted">
                Patient Notes <span className="text-gray-400 font-normal">(Optional)</span>
              </label>
              <textarea
                value={patientNotes}
                onChange={(e) => setPatientNotes(e.target.value)}
                placeholder="Patient observations, reported symptoms, or reasons for visit..."
                rows={2}
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 dark:border-dark-border rounded-lg focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-dark-bg/50 text-gray-900 dark:text-dark-text placeholder-gray-400 dark:placeholder-gray-500 outline-hidden transition-all resize-y min-h-[60px]"
              />
            </div>
          </div>
        )}

        {/* Save Error Alert Banner */}
        {saveError && (
          <div className="flex items-start justify-between p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg text-xs text-red-600 dark:text-red-400">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-500 mt-0.5" />
              <div>
                <p className="font-semibold">Examination Save Failed</p>
                <p className="text-[11px] text-red-600 dark:text-red-400 mt-0.5">{saveError}</p>
                {createdExamId && (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1">
                    An examination record was created. Retrying will upload remaining files without duplicating the examination.
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSaveError(null)}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300 p-0.5 ml-2 shrink-0"
              aria-label="Dismiss error"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Action Buttons: Save & Cancel clearly visible */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-100 dark:border-dark-border/60">
          <button
            type="button"
            onClick={() => navigate('/examinations')}
            className="px-4 py-2 border border-gray-300 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-bg text-gray-700 dark:text-dark-text text-xs sm:text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={uploading}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs sm:text-sm font-bold shadow-md shadow-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
          >
            {uploading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>{(files.length > 0 || bulkFiles.length > 0) ? 'Analyzing & Ingesting...' : 'Saving...'}</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-blue-200" />
                <span>
                  {files.length > 0 || bulkFiles.length > 0
                    ? 'Upload & Analyze Records'
                    : isBulkMode ? 'Save Examinations' : 'Save Examination'}
                </span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Previews */}
      {isPreviewLoading && (
        <div className="fixed inset-0 z-modal flex items-center justify-center bg-black/60 backdrop-blur-xs animate-in fade-in duration-300">
           <div className="flex flex-col items-center gap-6">
              <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-indigo-500"></div>
              <p className="text-white font-black text-xs uppercase tracking-[0.3em] animate-pulse">Initializing Diagnostic Preview</p>
           </div>
        </div>
      )}

      {activePreview && (
        <FilePreviewManager 
          url={activePreview.url} 
          filename={activePreview.name} 
          type={activePreview.type} 
          isBackendProcessed={activePreview.isBackendProcessed}
          localFile={activePreview.localFile}
          onClose={() => {
            URL.revokeObjectURL(activePreview.url);
            setActivePreview(null);
          }} 
        />
      )}

      <AIMagicFillModal 
        isOpen={isMagicFillOpen} 
        onClose={() => setIsMagicFillOpen(false)} 
        onSuggestedData={handleAIFill}
        taskType="magic_fill_examination"
        context={{ patientId }}
        title="Magic Fill"
        subtitle="Clinical Extraction"
        description="Describe the visit in natural language. Tattva AI will extract the date, category, doctors, and notes automatically."
        placeholder="e.g. Yesterday I visited Dr. Smith for a checkup..."
      />
    </div>
  );
}

export default ExaminationUpload;
