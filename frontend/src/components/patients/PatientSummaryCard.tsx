import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  RefreshCw,
  AlertTriangle,
  FileText,
  Languages,
  BookOpen,
  Info,
  CheckCircle2,
  Calendar,
} from 'lucide-react';
import {
  getPatientSummaries,
  generatePatientSummary,
} from '../../services/healthSummaryService';
import type { PatientHealthSummary } from '../../types/healthSummary';

interface PatientSummaryCardProps {
  patientId: string;
}

export function PatientSummaryCard({ patientId }: PatientSummaryCardProps) {
  const [summaries, setSummaries] = useState<PatientHealthSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedLang, setSelectedLang] = useState<'en' | 'hi'>('en');
  const [error, setError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);

  const loadSummaries = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPatientSummaries(patientId, undefined, true);
      setSummaries(data);
    } catch (err: any) {
      console.error('Failed to load health summaries:', err);
      setError(err?.response?.data?.detail || 'Failed to load health summaries.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (patientId) {
      loadSummaries();
    }
  }, [patientId]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      setError(null);
      const newSummary = await generatePatientSummary(patientId, {
        language: selectedLang,
      });
      // Prepend or update list
      setSummaries((prev) => [newSummary, ...prev]);
    } catch (err: any) {
      console.error('AI summary generation failed:', err);
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 503) {
        setError(
          detail ||
            'AI summary provider is not configured. Configure an LLM in Settings > AI Config or set OPENAI_API_KEY in the environment.',
        );
      } else {
        setError(detail || 'Failed to generate summary. Please try again.');
      }
    } finally {
      setGenerating(false);
    }
  };

  // Find latest summary for the selected language
  const currentSummary = summaries.find(
    (s) => (s.language || 'en').toLowerCase().startsWith(selectedLang),
  ) || summaries[0];

  return (
    <div className="bg-white dark:bg-dark-surface rounded-3xl shadow-xs border border-gray-100 dark:border-dark-border p-6 lg:p-8 space-y-6">
      {/* Header with Title and Language Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100 dark:border-dark-border pb-6">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-gradient-to-tr from-indigo-500 to-purple-600 rounded-2xl text-white shadow-md shadow-purple-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-dark-text tracking-tight flex items-center gap-2">
              Bilingual AI Health Summary
              {currentSummary && !currentSummary.is_stale && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> Fresh
                </span>
              )}
            </h3>
            <p className="text-xs text-gray-500 dark:text-dark-muted">
              Plain-language synthesis of patient lab trends, medications, and conditions
            </p>
          </div>
        </div>

        {/* Controls: Language Toggle & Generate Button */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center bg-gray-100 dark:bg-dark-bg p-1 rounded-xl text-xs font-bold">
            <button
              onClick={() => setSelectedLang('en')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                selectedLang === 'en'
                  ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:text-dark-muted'
              }`}
            >
              English
            </button>
            <button
              onClick={() => setSelectedLang('hi')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1 ${
                selectedLang === 'hi'
                  ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:text-dark-muted'
              }`}
            >
              <Languages className="w-3.5 h-3.5 mr-1" />
              हिंदी
            </button>
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl text-xs font-bold transition-all shadow-md shadow-blue-500/20 active:scale-95 disabled:opacity-50"
          >
            {generating ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Generating...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                <span>{currentSummary ? 'Regenerate' : 'Generate Summary'}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-4 rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/30 text-amber-800 dark:text-amber-300 text-xs flex items-start space-x-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
          <div className="space-y-1">
            <p className="font-bold">AI Provider Notice</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* Staleness Banner */}
      {currentSummary?.is_stale && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
            <span>
              <strong className="font-semibold">Summary is stale:</strong>{' '}
              {currentSummary.stale_reason || 'Underlying records were updated.'}
            </span>
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="text-[11px] font-bold text-amber-800 dark:text-amber-200 underline hover:no-underline ml-3 shrink-0"
          >
            Update now
          </button>
        </div>
      )}

      {/* Summary Content Body */}
      {loading ? (
        <div className="py-12 flex items-center justify-center space-x-3 text-gray-400">
          <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
          <span className="text-sm font-medium">Loading summary...</span>
        </div>
      ) : currentSummary ? (
        <div className="space-y-5">
          <div className="flex items-center justify-between text-xs text-gray-400 border-b border-gray-50 dark:border-dark-border/50 pb-2">
            <div className="flex items-center space-x-2">
              <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
              <span className="font-bold text-gray-700 dark:text-dark-text">
                {currentSummary.title}
              </span>
            </div>
            {currentSummary.created_at && (
              <span className="flex items-center space-x-1">
                <Calendar className="w-3 h-3" />
                <span>{new Date(currentSummary.created_at).toLocaleDateString()}</span>
              </span>
            )}
          </div>

          {/* Text Container with Markdown-like styling */}
          <div className="bg-gray-50/70 dark:bg-dark-bg/40 rounded-2xl p-6 border border-gray-100 dark:border-dark-border text-gray-800 dark:text-dark-text text-sm leading-relaxed whitespace-pre-line font-normal">
            {currentSummary.summary_text}
          </div>

          {/* Source References Accordion */}
          {currentSummary.source_references && currentSummary.source_references.length > 0 && (
            <div className="pt-2">
              <button
                onClick={() => setShowSources(!showSources)}
                className="flex items-center space-x-1.5 text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                <Info className="w-3.5 h-3.5" />
                <span>
                  {showSources ? 'Hide Source References' : `View Grounded Sources (${currentSummary.source_references.length})`}
                </span>
              </button>

              {showSources && (
                <div className="mt-3 p-4 bg-gray-50 dark:bg-dark-bg rounded-2xl border border-gray-100 dark:border-dark-border space-y-2">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                    Verified Citations & Records
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {currentSummary.source_references.map((ref, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 bg-white dark:bg-dark-surface rounded-xl border border-gray-100 dark:border-dark-border text-xs flex items-center justify-between"
                      >
                        <div className="truncate mr-2">
                          <p className="font-semibold text-gray-800 dark:text-dark-text truncate">
                            {ref.name || ref.title || ref.code || ref.filename || 'Record'}
                          </p>
                          <p className="text-[10px] text-gray-400 capitalize">
                            Type: {ref.type} {ref.value ? `(${ref.value} ${ref.unit || ''})` : ''}
                          </p>
                        </div>
                        <FileText className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="py-10 text-center text-gray-500 dark:text-dark-muted space-y-3">
          <BookOpen className="w-8 h-8 mx-auto text-gray-300 dark:text-gray-600" />
          <p className="text-sm font-medium">No plain-language summary generated yet.</p>
          <p className="text-xs text-gray-400 max-w-md mx-auto">
            Click &ldquo;Generate Summary&rdquo; above to create a grounded clinical summary in English or Hindi using the active patient records.
          </p>
        </div>
      )}
    </div>
  );
}
