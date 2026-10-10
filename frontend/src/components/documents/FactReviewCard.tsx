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
} from 'lucide-react';
import { getDocumentFacts, correctFact } from '../../services/factsService';
import type { DocumentFactsResponse, FactCorrectionRequest } from '../../types/facts';

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
      setEditUnit('');
    } else {
      setEditName(item.title || item.original_text || '');
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
      };

      if (selectedFact.type === 'observation') {
        payload.corrected_value = editValue ? Number(editValue) || editValue : null;
        payload.corrected_unit = editUnit || null;
      } else if (selectedFact.type === 'medication') {
        payload.corrected_name = editName;
        payload.corrected_value = editValue || null; // dosage
      } else if (selectedFact.type === 'condition') {
        payload.corrected_name = editName;
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
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
            <CheckCircle className="w-3 h-3 mr-1" /> Verified
          </span>
        );
      case 'corrected':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">
            <Edit3 className="w-3 h-3 mr-1" /> Corrected
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
            <XCircle className="w-3 h-3 mr-1" /> Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
            <Sparkles className="w-3 h-3 mr-1" /> Extracted
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
              <h3 className="text-lg font-bold text-gray-900 dark:text-dark-text tracking-tight">
                Canonical Facts & Human Review
              </h3>
              <p className="text-xs text-gray-500 dark:text-dark-muted">
                {totalCount} persisted clinical facts linked to this document with audit provenance
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
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                Lab Observations ({facts.observations.length})
              </h4>
              <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-dark-border">
                <table className="min-w-full divide-y divide-gray-100 dark:divide-dark-border text-sm">
                  <thead className="bg-gray-50/80 dark:bg-dark-bg text-left text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Biomarker / Test</th>
                      <th className="px-4 py-3">Value</th>
                      <th className="px-4 py-3">Original OCR Text</th>
                      <th className="px-4 py-3">Provenance</th>
                      <th className="px-4 py-3">Review Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-dark-border bg-white dark:bg-dark-surface">
                    {facts.observations.map((obs) => {
                      const displayTitle = obs.code?.text || obs.original_text || 'Observation';
                      const val = obs.normalized_value ?? obs.value_quantity?.value ?? obs.raw_value ?? '—';
                      const unit = obs.value_quantity?.unit || '';
                      return (
                        <tr key={obs.id} className="hover:bg-gray-50/50 dark:hover:bg-dark-bg/40 transition-colors">
                          <td className="px-4 py-3 font-semibold text-gray-900 dark:text-dark-text">
                            {displayTitle}
                          </td>
                          <td className="px-4 py-3 font-mono font-bold text-blue-600 dark:text-blue-400">
                            {val} {unit}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-dark-muted font-mono truncate max-w-xs">
                            {obs.original_text || '—'}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-dark-muted">
                            <span className="font-medium">Pg {obs.page_number ?? 1}</span>
                            {obs.confidence != null && (
                              <span className="ml-2 font-mono text-[10px] bg-gray-100 dark:bg-dark-bg px-1.5 py-0.5 rounded">
                                {(obs.confidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">{getStatusBadge(obs.review_status)}</td>
                          <td className="px-4 py-3 text-right space-x-2">
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
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                Medications ({facts.medications.length})
              </h4>
              <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-dark-border">
                <table className="min-w-full divide-y divide-gray-100 dark:divide-dark-border text-sm">
                  <thead className="bg-gray-50/80 dark:bg-dark-bg text-left text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Medication</th>
                      <th className="px-4 py-3">Dosage</th>
                      <th className="px-4 py-3">Original OCR Text</th>
                      <th className="px-4 py-3">Provenance</th>
                      <th className="px-4 py-3">Review Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50 dark:divide-dark-border bg-white dark:bg-dark-surface">
                    {facts.medications.map((med) => {
                      const displayTitle = med.code?.text || med.original_text || 'Medication';
                      return (
                        <tr key={med.id} className="hover:bg-gray-50/50 dark:hover:bg-dark-bg/40 transition-colors">
                          <td className="px-4 py-3 font-semibold text-gray-900 dark:text-dark-text">
                            {displayTitle}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-700 dark:text-dark-text font-medium">
                            {med.dosage || 'Not specified'}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-dark-muted font-mono truncate max-w-xs">
                            {med.original_text || '—'}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 dark:text-dark-muted">
                            <span className="font-medium">Pg {med.page_number ?? 1}</span>
                            {med.confidence != null && (
                              <span className="ml-2 font-mono text-[10px] bg-gray-100 dark:bg-dark-bg px-1.5 py-0.5 rounded">
                                {(med.confidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">{getStatusBadge(med.review_status)}</td>
                          <td className="px-4 py-3 text-right space-x-2">
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

          {/* Conditions List */}
          {(filterType === 'all' || filterType === 'condition') && facts.conditions.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                Diagnoses & Clinical Conditions ({facts.conditions.length})
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {facts.conditions.map((cond) => (
                  <div
                    key={cond.id}
                    className="p-4 rounded-xl border border-gray-100 dark:border-dark-border bg-gray-50/50 dark:bg-dark-bg/30 flex items-center justify-between gap-3"
                  >
                    <div>
                      <h5 className="text-sm font-bold text-gray-900 dark:text-dark-text leading-tight">
                        {cond.title}
                      </h5>
                      <p className="text-xs text-gray-400 mt-0.5 font-mono">
                        Source: {cond.original_text || cond.title}
                      </p>
                      <div className="mt-2">{getStatusBadge(cond.review_status)}</div>
                    </div>
                    <div className="flex items-center space-x-1">
                      {cond.review_status !== 'verified' && (
                        <button
                          onClick={() => handleQuickVerify('condition', cond)}
                          disabled={saving}
                          className="p-2 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 rounded-lg transition-colors"
                          title="Quick verify"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleOpenCorrection('condition', cond)}
                        disabled={saving}
                        className="px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-dark-text border border-gray-200 dark:border-dark-border rounded-lg hover:bg-gray-50 dark:hover:bg-dark-bg transition-colors active:scale-95"
                      >
                        Review
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Review & Correction Modal */}
      {isModalOpen && selectedFact && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white dark:bg-dark-surface rounded-3xl max-w-md w-full p-6 shadow-2xl border border-gray-100 dark:border-dark-border space-y-6">
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
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">
                    Dosage
                  </label>
                  <input
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-dark-border bg-gray-50 dark:bg-dark-bg text-gray-900 dark:text-dark-text"
                  />
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
    </div>
  );
}
