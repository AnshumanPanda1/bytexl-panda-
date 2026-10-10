import React, { useEffect, useState } from 'react';
import {
  CheckCircle,
  AlertCircle,
  Edit3,
  XCircle,
  FileCheck,
  RefreshCw,
  Search,
  Check,
  X,
  Layers,
  Sparkles,
  Quote,
  Pill,
  Activity,
  Tag,
  ShieldAlert,
} from 'lucide-react';
import { getDocumentFacts, correctFact } from '../../services/factsService';
import type {
  DocumentFactsResponse,
  FactCorrectionRequest,
  FactObservation,
  FactMedication,
  FactCondition,
} from '../../types/facts';

interface FactReviewCardProps {
  documentId: string;
  onFactUpdated?: () => void;
}

export function FactReviewCard({ documentId, onFactUpdated }: FactReviewCardProps) {
  const [facts, setFacts] = useState<DocumentFactsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFact, setSelectedFact] = useState<{
    type: 'observation' | 'medication' | 'condition';
    item: any;
  } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filterType, setFilterType] = useState<'all' | 'observation' | 'medication' | 'condition'>('all');

  // Form inputs for correction
  const [editValue, setEditValue] = useState<string>('');
  const [editUnit, setEditUnit] = useState<string>('');
  const [editName, setEditName] = useState<string>('');
  const [editStrength, setEditStrength] = useState<string>('');
  const [editRoute, setEditRoute] = useState<string>('');
  const [editDuration, setEditDuration] = useState<string>('');
  const [editMedStatus, setEditMedStatus] = useState<string>('ACTIVE');
  const [editIcd10, setEditIcd10] = useState<string>('');
  const [editVerificationStatus, setEditVerificationStatus] = useState<string>('confirmed');
  const [editClinicalStatus, setEditClinicalStatus] = useState<string>('active');
  const [editStatus, setEditStatus] = useState<'verified' | 'rejected' | 'corrected'>('verified');
  const [editReason, setEditReason] = useState<string>('Clinical review');

  const fetchFacts = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getDocumentFacts(documentId);
      setFacts(data);
    } catch (err: any) {
      console.error('Failed to load document facts:', err);
      setError(err?.response?.data?.detail || 'Failed to load extracted facts for this document.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (documentId) {
      fetchFacts();
    }
  }, [documentId]);

  const handleOpenCorrection = (type: 'observation' | 'medication' | 'condition', item: any) => {
    setSelectedFact({ type, item });
    if (type === 'observation') {
      const val = item.normalized_value ?? item.value_quantity?.value ?? item.raw_value ?? '';
      const unit = item.value_quantity?.unit ?? '';
      const name = item.code?.text || item.original_text || 'Observation';
      setEditValue(String(val));
      setEditUnit(unit);
      setEditName(name);
    } else if (type === 'medication') {
      const name = item.code?.text || item.original_text || 'Medication';
      setEditName(name);
      setEditValue(item.dosage || '');
      setEditStrength(item.strength || item.code?.strength || '');
      setEditRoute(item.route || item.code?.route || '');
      setEditDuration(item.duration || item.code?.duration || '');
      setEditMedStatus(item.status || 'ACTIVE');
      setEditUnit('');
    } else {
      setEditName(item.title || item.original_text || '');
      setEditIcd10(item.icd10_code || item.code || item.event_metadata?.icd10_code || '');
      setEditVerificationStatus(item.verification_status || item.event_metadata?.verification_status || 'confirmed');
      setEditClinicalStatus(item.clinical_status || item.event_metadata?.clinical_status || 'active');
      setEditValue('');
      setEditUnit('');
    }
    setEditStatus('verified');
    setEditReason('HITL Clinical validation');
    setIsModalOpen(true);
  };

  const handleQuickVerify = async (type: 'observation' | 'medication' | 'condition', item: any) => {
    try {
      setSaving(true);
      await correctFact({
        fact_type: type,
        fact_id: item.id,
        new_review_status: 'verified',
        correction_reason: 'Quick verified by clinician',
      });
      await fetchFacts();
      if (onFactUpdated) onFactUpdated();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to verify fact.');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFact) return;

    try {
      setSaving(true);
      const payload: FactCorrectionRequest = {
        fact_type: selectedFact.type,
        fact_id: selectedFact.item.id,
        new_review_status: editStatus,
        correction_reason: editReason,
        updates: {},
      };

      if (selectedFact.type === 'observation') {
        payload.corrected_value = editValue ? Number(editValue) || editValue : null;
        payload.corrected_unit = editUnit || null;
      } else if (selectedFact.type === 'medication') {
        payload.corrected_name = editName;
        payload.corrected_value = editValue || null; // dosage
        payload.updates = {
          strength: editStrength || null,
          route: editRoute || null,
          duration: editDuration || null,
          status: editMedStatus || 'ACTIVE',
        };
      } else if (selectedFact.type === 'condition') {
        payload.corrected_name = editName;
        payload.updates = {
          verification_status: editVerificationStatus || 'confirmed',
          clinical_status: editClinicalStatus || 'active',
          icd10_code: editIcd10 || null,
        };
      }

      await correctFact(payload);
      setIsModalOpen(false);
      setSelectedFact(null);
      await fetchFacts();
      if (onFactUpdated) onFactUpdated();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to submit correction.');
    } finally {
      setSaving(false);
    }
  };

  const getStatusBadge = (status: string | undefined) => {
    const s = (status || 'extracted').toLowerCase();
    switch (s) {
      case 'verified':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
            <CheckCircle className="w-3 h-3 mr-1" /> Verified
          </span>
        );
      case 'corrected':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">
            <Edit3 className="w-3 h-3 mr-1" /> Corrected
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
            <XCircle className="w-3 h-3 mr-1" /> Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
            <Sparkles className="w-3 h-3 mr-1" /> Extracted
          </span>
        );
    }
  };

  const getVerificationBadge = (vStatus: string | undefined) => {
    const v = (vStatus || '').toLowerCase();
    switch (v) {
      case 'confirmed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
            Confirmed
          </span>
        );
      case 'differential':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
            Differential
          </span>
        );
      case 'refuted':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
            Refuted
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
            {vStatus || 'Provisional'}
          </span>
        );
    }
  };

  const getClinicalStatusBadge = (cStatus: string | undefined) => {
    const c = (cStatus || 'active').toLowerCase();
    switch (c) {
      case 'resolved':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-700 dark:bg-dark-bg dark:text-gray-300">
            Resolved
          </span>
        );
      case 'remission':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-teal-50 text-teal-700 dark:bg-teal-900/20 dark:text-teal-300">
            Remission
          </span>
        );
      case 'relapse':
      case 'recurrence':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300">
            {c.charAt(0).toUpperCase() + c.slice(1)}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
            Active
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-xs border border-gray-100 dark:border-dark-border p-6 flex items-center justify-center space-x-3 text-gray-500">
        <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
        <span className="text-sm font-medium">Loading extracted clinical facts...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-xs border border-red-100 dark:border-red-900/30 p-6 text-red-600 dark:text-red-400 flex items-center space-x-3">
        <AlertCircle className="w-5 h-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  if (!facts) return null;

  const totalCount =
    facts.observations.length + facts.medications.length + facts.conditions.length;

  return (
    <div className="bg-white dark:bg-dark-surface rounded-2xl shadow-xs border border-gray-100 dark:border-dark-border p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100 dark:border-dark-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded-xl text-blue-600 dark:text-blue-400">
              <FileCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-dark-text tracking-tight flex items-center gap-2">
                Canonical Facts & Evidence Grounding
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 rounded-md">
                  AIML Validated
                </span>
              </h3>
              <p className="text-xs text-gray-500 dark:text-dark-muted">
                {totalCount} persisted clinical facts linked to this document with provenance quotes & HITL review
              </p>
            </div>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center space-x-1.5 bg-gray-100/70 dark:bg-dark-bg p-1 rounded-xl text-xs font-semibold">
          <button
            onClick={() => setFilterType('all')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              filterType === 'all'
                ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                : 'text-gray-600 dark:text-dark-muted hover:text-gray-900'
            }`}
          >
            All ({totalCount})
          </button>
          <button
            onClick={() => setFilterType('observation')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              filterType === 'observation'
                ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                : 'text-gray-600 dark:text-dark-muted hover:text-gray-900'
            }`}
          >
            Labs ({facts.observations.length})
          </button>
          <button
            onClick={() => setFilterType('medication')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              filterType === 'medication'
                ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                : 'text-gray-600 dark:text-dark-muted hover:text-gray-900'
            }`}
          >
            Meds ({facts.medications.length})
          </button>
          <button
            onClick={() => setFilterType('condition')}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              filterType === 'condition'
                ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                : 'text-gray-600 dark:text-dark-muted hover:text-gray-900'
            }`}
          >
            Diagnoses ({facts.conditions.length})
          </button>
        </div>
      </div>

      {totalCount === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-dark-muted">
          <Layers className="w-8 h-8 mx-auto mb-2 text-gray-400" />
          <p className="text-sm font-medium">No canonical facts persisted yet for this document.</p>
          <p className="text-xs text-gray-400 mt-1">
            Trigger re-extraction above to populate structured observations and diagnoses.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Observations Table */}
          {(filterType === 'all' || filterType === 'observation') && facts.observations.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-blue-500" />
                  Lab Observations & Biomarkers ({facts.observations.length})
                </h4>
              </div>
              <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-dark-border">
                <table className="min-w-full divide-y divide-gray-100 dark:divide-dark-border text-sm">
                  <thead className="bg-gray-50/80 dark:bg-dark-bg text-left text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Biomarker / Test</th>
                      <th className="px-4 py-3">Value</th>
                      <th className="px-4 py-3">Evidence Quote & Provenance</th>
                      <th className="px-4 py-3">Review Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-dark-border bg-white dark:bg-dark-surface">
                    {facts.observations.map((obs) => {
                      const displayTitle = obs.code?.text || obs.original_text || 'Observation';
                      const val = obs.normalized_value ?? obs.value_quantity?.value ?? obs.raw_value ?? '—';
                      const unit = obs.value_quantity?.unit || '';
                      const evidenceText = obs.evidence_text || obs.original_text;

                      return (
                        <tr key={obs.id} className="hover:bg-gray-50/50 dark:hover:bg-dark-bg/40 transition-colors">
                          <td className="px-4 py-3 font-semibold text-gray-900 dark:text-dark-text">
                            <div>{displayTitle}</div>
                            {obs.method && (
                              <span className="text-[10px] text-gray-400 font-normal">Method: {obs.method}</span>
                            )}
                          </td>
                          <td className="px-4 py-3 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">
                            {val} {unit}
                          </td>
                          <td className="px-4 py-3 max-w-md">
                            <div className="flex flex-col gap-1">
                              {evidenceText && (
                                <div className="flex items-start gap-1.5 bg-gray-50 dark:bg-dark-bg/80 p-2 rounded-lg border border-gray-100 dark:border-dark-border/60 text-xs text-gray-600 dark:text-dark-muted font-mono">
                                  <Quote className="w-3.5 h-3.5 text-blue-500 shrink-0 mt-0.5" />
                                  <span className="line-clamp-2" title={evidenceText}>
                                    "{evidenceText}"
                                  </span>
                                </div>
                              )}
                              <div className="flex items-center gap-2 text-[10px] text-gray-400">
                                <span className="font-semibold text-gray-500 dark:text-dark-muted">
                                  Pg {obs.page_number ?? 1}
                                </span>
                                {obs.confidence != null && (
                                  <span className="font-mono bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded font-bold">
                                    {(obs.confidence * 100).toFixed(0)}% conf
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">{getStatusBadge(obs.review_status)}</td>
                          <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                            {obs.review_status !== 'verified' && (
                              <button
                                onClick={() => handleQuickVerify('observation', obs)}
                                disabled={saving}
                                className="p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded-lg transition-colors"
                                title="Quick verify"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                            )}
                            <button
                              onClick={() => handleOpenCorrection('observation', obs)}
                              disabled={saving}
                              className="px-2.5 py-1 text-xs font-semibold text-gray-700 dark:text-dark-text border border-gray-200 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors active:scale-95"
                            >
                              Review
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Medications Table */}
          {(filterType === 'all' || filterType === 'medication') && facts.medications.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Pill className="w-3.5 h-3.5 text-emerald-500" />
                  Prescriptions & Medications ({facts.medications.length})
                </h4>
              </div>
              <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-dark-border">
                <table className="min-w-full divide-y divide-gray-100 dark:divide-dark-border text-sm">
                  <thead className="bg-gray-50/80 dark:bg-dark-bg text-left text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Medication</th>
                      <th className="px-4 py-3">Dosage / Strength</th>
                      <th className="px-4 py-3">Route / Duration</th>
                      <th className="px-4 py-3">Evidence Quote & Provenance</th>
                      <th className="px-4 py-3">Review Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-dark-border bg-white dark:bg-dark-surface">
                    {facts.medications.map((med) => {
                      const displayTitle = med.code?.text || med.original_text || 'Medication';
                      const strength = med.strength || med.code?.strength;
                      const route = med.route || med.code?.route;
                      const duration = med.duration || med.code?.duration;
                      const evidenceText = med.evidence_text || med.original_text;

                      return (
                        <tr key={med.id} className="hover:bg-gray-50/50 dark:hover:bg-dark-bg/40 transition-colors">
                          <td className="px-4 py-3 font-semibold text-gray-900 dark:text-dark-text">
                            <div>{displayTitle}</div>
                            {med.status && (
                              <span className="inline-block mt-0.5 px-1.5 py-0.2 rounded text-[10px] font-bold uppercase bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                                {med.status}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-700 dark:text-dark-text font-medium whitespace-nowrap">
                            <div>{med.dosage || 'Not specified'}</div>
                            {strength && (
                              <span className="inline-block text-[10px] font-mono text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950 px-1 rounded mt-0.5">
                                Str: {strength}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-600 dark:text-dark-muted whitespace-nowrap">
                            <div className="flex flex-col gap-0.5">
                              {route && (
                                <span className="text-[11px] font-medium text-gray-700 dark:text-gray-300 capitalize">
                                  Route: {route}
                                </span>
                              )}
                              {duration && (
                                <span className="text-[10px] text-gray-500 font-mono">
                                  Dur: {duration}
                                </span>
                              )}
                              {!route && !duration && <span className="text-gray-400">—</span>}
                            </div>
                          </td>
                          <td className="px-4 py-3 max-w-md">
                            <div className="flex flex-col gap-1">
                              {evidenceText && (
                                <div className="flex items-start gap-1.5 bg-gray-50 dark:bg-dark-bg/80 p-2 rounded-lg border border-gray-100 dark:border-dark-border/60 text-xs text-gray-600 dark:text-dark-muted font-mono">
                                  <Quote className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                                  <span className="line-clamp-2" title={evidenceText}>
                                    "{evidenceText}"
                                  </span>
                                </div>
                              )}
                              <div className="flex items-center gap-2 text-[10px] text-gray-400">
                                <span className="font-semibold text-gray-500 dark:text-dark-muted">
                                  Pg {med.page_number ?? 1}
                                </span>
                                {med.confidence != null && (
                                  <span className="font-mono bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded font-bold">
                                    {(med.confidence * 100).toFixed(0)}% conf
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">{getStatusBadge(med.review_status)}</td>
                          <td className="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                            {med.review_status !== 'verified' && (
                              <button
                                onClick={() => handleQuickVerify('medication', med)}
                                disabled={saving}
                                className="p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded-lg transition-colors"
                                title="Quick verify"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                            )}
                            <button
                              onClick={() => handleOpenCorrection('medication', med)}
                              disabled={saving}
                              className="px-2.5 py-1 text-xs font-semibold text-gray-700 dark:text-dark-text border border-gray-200 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors active:scale-95"
                            >
                              Review
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Conditions & Structured Diagnoses List */}
          {(filterType === 'all' || filterType === 'condition') && facts.conditions.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5 text-indigo-500" />
                  Diagnoses & Clinical Conditions ({facts.conditions.length})
                </h4>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {facts.conditions.map((cond) => {
                  const icd10 = cond.icd10_code || cond.code || cond.event_metadata?.icd10_code;
                  const vStatus = cond.verification_status || cond.event_metadata?.verification_status;
                  const cStatus = cond.clinical_status || cond.event_metadata?.clinical_status;
                  const evidenceText = cond.evidence_text || cond.original_text || cond.title;

                  return (
                    <div
                      key={cond.id}
                      className="p-4 rounded-xl border border-gray-100 dark:border-dark-border bg-gray-50/50 dark:bg-dark-bg/30 flex flex-col justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h5 className="text-sm font-bold text-gray-900 dark:text-dark-text leading-tight">
                              {cond.title}
                            </h5>
                            {icd10 && (
                              <span className="inline-block mt-1 font-mono text-[10px] bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 font-bold px-2 py-0.5 rounded border border-indigo-200/50">
                                ICD-10: {icd10}
                              </span>
                            )}
                          </div>
                          <div className="shrink-0">{getStatusBadge(cond.review_status)}</div>
                        </div>

                        {/* Status pills */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                          {getVerificationBadge(vStatus)}
                          {getClinicalStatusBadge(cStatus)}
                        </div>

                        {/* Evidence quote */}
                        {evidenceText && (
                          <div className="mt-2.5 p-2 rounded-lg bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border/80 text-xs text-gray-600 dark:text-dark-muted font-mono flex items-start gap-1.5">
                            <Quote className="w-3.5 h-3.5 text-indigo-500 shrink-0 mt-0.5" />
                            <span className="line-clamp-2" title={evidenceText}>
                              "{evidenceText}"
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-dark-border/40 text-[10px] text-gray-400">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-gray-500 dark:text-dark-muted">
                            Pg {cond.page_number ?? 1}
                          </span>
                          {cond.confidence != null && (
                            <span className="font-mono bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded font-bold">
                              {(cond.confidence * 100).toFixed(0)}% conf
                            </span>
                          )}
                        </div>

                        <div className="flex items-center space-x-1">
                          {cond.review_status !== 'verified' && (
                            <button
                              onClick={() => handleQuickVerify('condition', cond)}
                              disabled={saving}
                              className="p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded-lg transition-colors"
                              title="Quick verify"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => handleOpenCorrection('condition', cond)}
                            disabled={saving}
                            className="px-2.5 py-1 text-xs font-semibold text-gray-700 dark:text-dark-text border border-gray-200 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors active:scale-95"
                          >
                            Review
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Review & Correction Modal */}
      {isModalOpen && selectedFact && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white dark:bg-dark-surface rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-gray-100 dark:border-dark-border space-y-5">
            <div className="flex items-center justify-between border-b border-gray-100 dark:border-dark-border pb-4">
              <div className="flex items-center space-x-2">
                <Edit3 className="w-5 h-5 text-blue-600" />
                <h4 className="text-base font-bold text-gray-900 dark:text-dark-text">
                  Fact Review & HITL Correction
                </h4>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-dark-text"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitCorrection} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                  Name / Title
                </label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-medium"
                />
              </div>

              {selectedFact.type === 'observation' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                      Corrected Value
                    </label>
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                      Unit
                    </label>
                    <input
                      type="text"
                      value={editUnit}
                      onChange={(e) => setEditUnit(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-mono"
                    />
                  </div>
                </div>
              )}

              {selectedFact.type === 'medication' && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Dosage
                      </label>
                      <input
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        placeholder="e.g. 1 tablet"
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Strength
                      </label>
                      <input
                        type="text"
                        value={editStrength}
                        onChange={(e) => setEditStrength(e.target.value)}
                        placeholder="e.g. 500 mg"
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Route
                      </label>
                      <input
                        type="text"
                        value={editRoute}
                        onChange={(e) => setEditRoute(e.target.value)}
                        placeholder="e.g. oral"
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Duration
                      </label>
                      <input
                        type="text"
                        value={editDuration}
                        onChange={(e) => setEditDuration(e.target.value)}
                        placeholder="e.g. 7 days"
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Status
                      </label>
                      <select
                        value={editMedStatus}
                        onChange={(e) => setEditMedStatus(e.target.value)}
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      >
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="STOPPED">STOPPED</option>
                        <option value="DISCONTINUED">DISCONTINUED</option>
                        <option value="PRN">PRN</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {selectedFact.type === 'condition' && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                      ICD-10 Code
                    </label>
                    <input
                      type="text"
                      value={editIcd10}
                      onChange={(e) => setEditIcd10(e.target.value)}
                      placeholder="e.g. E11.9, I10"
                      className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-mono"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Verification Status
                      </label>
                      <select
                        value={editVerificationStatus}
                        onChange={(e) => setEditVerificationStatus(e.target.value)}
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      >
                        <option value="confirmed">Confirmed</option>
                        <option value="provisional">Provisional</option>
                        <option value="differential">Differential</option>
                        <option value="refuted">Refuted</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Clinical Status
                      </label>
                      <select
                        value={editClinicalStatus}
                        onChange={(e) => setEditClinicalStatus(e.target.value)}
                        className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                      >
                        <option value="active">Active</option>
                        <option value="recurrence">Recurrence</option>
                        <option value="relapse">Relapse</option>
                        <option value="remission">Remission</option>
                        <option value="resolved">Resolved</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                  Review Status
                </label>
                <select
                  value={editStatus}
                  onChange={(e: any) => setEditStatus(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text font-medium"
                >
                  <option value="verified">Verified (Approved)</option>
                  <option value="corrected">Corrected (Edited by user)</option>
                  <option value="rejected">Rejected (Clinical inaccuracy)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                  Reason for Correction
                </label>
                <input
                  type="text"
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  placeholder="e.g. OCR error correction, clinical dosage adjustment"
                  className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                />
              </div>

              <div className="pt-4 flex items-center justify-end space-x-3 border-t border-gray-100 dark:border-dark-border">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-gray-600 dark:text-dark-muted rounded-xl hover:bg-gray-100 dark:hover:bg-dark-bg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 text-xs font-bold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition-all shadow-xs active:scale-95 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Correction'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Universal Medical Disclaimer Banner */}
      <div className="rounded-xl border border-amber-200 bg-amber-50/70 dark:bg-amber-950/20 dark:border-amber-900/40 p-3.5 flex items-start gap-2.5">
        <ShieldAlert className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="text-xs text-amber-900 dark:text-amber-200/90 leading-relaxed">
          <span className="font-bold">Medical Disclaimer:</span> This software is for informational and hackathon demonstration purposes only. It does NOT provide medical diagnosis or act as a substitute for professional medical care. Always consult licensed medical professionals for health advice, diagnoses, or treatment decisions.
        </div>
      </div>
    </div>
  );
}
