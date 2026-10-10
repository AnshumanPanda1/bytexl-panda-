import React, { useState } from 'react';
import {
  X,
  FileCheck2,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Database,
  ArrowRight,
  ShieldCheck,
  Building2,
} from 'lucide-react';
import {
  previewMockAbdmRecord,
  confirmMockAbdmRecord,
  getMockAbdmSampleBundles,
} from '../../services/mockAbdmService';
import type {
  MockAbdmPreviewResponse,
  MockAbdmConfirmResponse,
  SyntheticRecordBundle,
} from '../../types/mockAbdm';

interface MockAbdmImportModalProps {
  patientId: string;
  isOpen: boolean;
  onClose: () => void;
  onImportCompleted?: () => void;
}

export function MockAbdmImportModal({
  patientId,
  isOpen,
  onClose,
  onImportCompleted,
}: MockAbdmImportModalProps) {
  const samplePresets = getMockAbdmSampleBundles();
  const [selectedPresetIndex, setSelectedPresetIndex] = useState<number>(0);
  const [currentBundle, setCurrentBundle] = useState<SyntheticRecordBundle>(samplePresets[0]);
  const [previewData, setPreviewData] = useState<MockAbdmPreviewResponse | null>(null);
  const [confirmData, setConfirmData] = useState<MockAbdmConfirmResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<'select' | 'preview' | 'completed'>('select');

  if (!isOpen) return null;

  const handleSelectPreset = (idx: number) => {
    setSelectedPresetIndex(idx);
    setCurrentBundle(samplePresets[idx]);
    setPreviewData(null);
    setConfirmData(null);
    setError(null);
  };

  const handlePreview = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await previewMockAbdmRecord(patientId, currentBundle);
      setPreviewData(res);
      setStep('preview');
    } catch (err: any) {
      console.error('Failed to preview ABDM bundle:', err);
      setError(err?.response?.data?.detail || 'Failed to preview ABDM import.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await confirmMockAbdmRecord(patientId, currentBundle);
      setConfirmData(res);
      setStep('completed');
      if (onImportCompleted) {
        onImportCompleted();
      }
    } catch (err: any) {
      console.error('Failed to confirm ABDM import:', err);
      setError(err?.response?.data?.detail || 'Failed to confirm ABDM import.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setStep('select');
    setPreviewData(null);
    setConfirmData(null);
    setError(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in">
      <div className="bg-white dark:bg-dark-surface rounded-3xl max-w-xl w-full p-6 lg:p-8 shadow-2xl border border-gray-100 dark:border-dark-border space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 dark:border-dark-border pb-4">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-gradient-to-tr from-emerald-500 to-teal-600 rounded-xl text-white shadow-xs">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-bold text-gray-900 dark:text-dark-text tracking-tight">
                  Simulated ABHA / ABDM Record Import
                </h3>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300 border border-purple-200 dark:border-purple-800/50">
                  Simulated Demo · Synthetic Cohort
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-dark-muted mt-0.5">
                Import and map interoperable external health data into canonical patient records
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-dark-text p-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Simulation Environment Notice */}
        <div className="p-3 rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/30 text-amber-800 dark:text-amber-200 text-xs flex items-start space-x-2.5">
          <ShieldCheck className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <p className="leading-relaxed">
            <span className="font-bold">Development Simulation:</span> This interface tests FHIR/ABDM synthetic record ingestion and deduplication. It is a local sandbox and is not connected to a live government ABDM gateway.
          </p>
        </div>

        {error && (
          <div className="p-3.5 rounded-2xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 text-red-600 text-xs flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Step 1: Select Preset */}
        {step === 'select' && (
          <div className="space-y-4">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
              Choose Simulated ABDM Bundle Preset:
            </p>

            <div className="space-y-3">
              {samplePresets.map((preset, idx) => (
                <div
                  key={preset.external_record_id}
                  onClick={() => handleSelectPreset(idx)}
                  className={`p-4 rounded-2xl border cursor-pointer transition-all ${
                    selectedPresetIndex === idx
                      ? 'border-emerald-500 bg-emerald-50/40 dark:bg-emerald-950/20 shadow-xs'
                      : 'border-gray-200 dark:border-dark-border hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Building2 className="w-4 h-4 text-emerald-600" />
                      <span className="text-sm font-bold text-gray-900 dark:text-dark-text">
                        {preset.facility_name}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono bg-gray-100 dark:bg-dark-bg px-2 py-0.5 rounded text-gray-600 dark:text-dark-muted">
                      {preset.external_record_id}
                    </span>
                  </div>

                  <div className="mt-2 text-xs text-gray-600 dark:text-dark-muted flex flex-wrap gap-3">
                    <span>
                      <strong>{preset.observations.length}</strong> Labs (
                      {preset.observations.map((o) => o.test_name).join(', ')})
                    </span>
                    <span>
                      <strong>{preset.medications.length}</strong> Rx (
                      {preset.medications.map((m) => m.name).join(', ')})
                    </span>
                    <span>
                      <strong>{preset.conditions.length}</strong> Diagnoses
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-4 flex justify-end">
              <button
                onClick={handlePreview}
                disabled={loading}
                className="flex items-center space-x-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 disabled:opacity-50"
              >
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <span>Preview Bundle</span>}
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Preview & Validation */}
        {step === 'preview' && previewData && (
          <div className="space-y-4">
            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-dark-bg border border-gray-100 dark:border-dark-border space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Source System:</span>
                <span className="text-xs font-bold text-gray-800 dark:text-dark-text uppercase">
                  {previewData.source_system}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Record ID:</span>
                <span className="text-xs font-mono text-gray-800 dark:text-dark-text">
                  {previewData.external_record_id}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Deduplication:</span>
                {previewData.is_duplicate ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">
                    <AlertTriangle className="w-3 h-3 mr-1" /> Duplicate Detected
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                    <ShieldCheck className="w-3 h-3 mr-1" /> Verified Unique Checksum
                  </span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-xl">
                <p className="text-lg font-bold text-blue-700 dark:text-blue-300">
                  {previewData.observation_count}
                </p>
                <p className="text-[10px] font-semibold text-gray-500 uppercase">Observations</p>
              </div>
              <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-xl">
                <p className="text-lg font-bold text-purple-700 dark:text-purple-300">
                  {previewData.medication_count}
                </p>
                <p className="text-[10px] font-semibold text-gray-500 uppercase">Medications</p>
              </div>
              <div className="p-3 bg-rose-50 dark:bg-rose-900/20 rounded-xl">
                <p className="text-lg font-bold text-rose-700 dark:text-rose-300">
                  {previewData.condition_count}
                </p>
                <p className="text-[10px] font-semibold text-gray-500 uppercase">Diagnoses</p>
              </div>
            </div>

            <p className="text-xs text-gray-500 dark:text-dark-muted">
              Confirming this import will persist canonical resources with ABHA provenance and automatically mark dependent patient summaries as stale.
            </p>

            <div className="pt-4 flex items-center justify-between border-t border-gray-100 dark:border-dark-border">
              <button
                onClick={handleReset}
                className="text-xs font-bold text-gray-500 hover:text-gray-800"
              >
                Back
              </button>
              <button
                onClick={handleConfirm}
                disabled={loading || previewData.is_duplicate}
                className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 disabled:opacity-50"
              >
                {loading ? 'Importing...' : 'Confirm & Persist Records'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Success Confirmation */}
        {step === 'completed' && confirmData && (
          <div className="py-6 text-center space-y-4">
            <div className="w-12 h-12 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-base font-bold text-gray-900 dark:text-dark-text">
                ABDM Record Successfully Imported!
              </h4>
              <p className="text-xs text-gray-500 mt-1">
                Observations, medications, and conditions were safely linked and prior summaries were invalidated.
              </p>
            </div>
            <div className="pt-4">
              <button
                onClick={onClose}
                className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-xs"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
