import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  RefreshCw,
  Globe,
  ShieldCheck,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Info,
} from 'lucide-react';
import {
  generateAISummary,
  invalidateAISummaries,
  type AISummaryResponse,
} from '../../services/aiSummaryService';

interface AISummaryCardProps {
  patientId: string;
  documentIds?: string[];
  className?: string;
}

export const AISummaryCard: React.FC<AISummaryCardProps> = ({
  patientId,
  documentIds,
  className = '',
}) => {
  const [language, setLanguage] = useState<'en' | 'hi'>('en');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AISummaryResponse | null>(null);

  const fetchSummary = async (force: boolean = false) => {
    if (!patientId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await generateAISummary({
        patient_id: patientId,
        document_ids: documentIds,
        language,
        force_regenerate: force,
      });
      setSummary(data);
    } catch (err: any) {
      console.error('Failed to generate AI summary:', err);
      setError(err?.response?.data?.detail || err?.message || 'Failed to generate summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (patientId) {
      fetchSummary(false);
    }
  }, [patientId, language]);

  return (
    <div
      className={`bg-white dark:bg-dark-surface border border-gray-100 dark:border-dark-border rounded-2xl shadow-lg p-6 ${className}`}
    >
      {/* Header & Language Toggle */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-gray-100 dark:border-dark-border">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-xl">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span>Bilingual AI Clinical Summary</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 font-semibold border border-emerald-200 dark:border-emerald-800">
                Grounded
              </span>
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Evidence-grounded patient summary with source provenance
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-stretch sm:self-auto justify-between sm:justify-end">
          {/* Language Toggle */}
          <div className="inline-flex rounded-xl bg-gray-100 dark:bg-dark-bg p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setLanguage('en')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                language === 'en'
                  ? 'bg-white dark:bg-dark-surface text-indigo-600 dark:text-indigo-400 shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:text-gray-400'
              }`}
            >
              English
            </button>
            <button
              type="button"
              onClick={() => setLanguage('hi')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                language === 'hi'
                  ? 'bg-white dark:bg-dark-surface text-indigo-600 dark:text-indigo-400 shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:text-gray-400'
              }`}
            >
              हिंदी (Hindi)
            </button>
          </div>

          {/* Regenerate Button */}
          <button
            type="button"
            onClick={() => fetchSummary(true)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-bg text-xs font-semibold text-gray-600 dark:text-gray-300 transition-all disabled:opacity-50"
            title="Regenerate summary"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && !summary && (
        <div className="py-12 flex flex-col items-center justify-center gap-3">
          <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Synthesizing grounded facts with Groq LPU inference...
          </p>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="my-4 p-4 rounded-xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Failed to generate summary</p>
            <p className="text-xs mt-0.5 opacity-90">{error}</p>
          </div>
        </div>
      )}

      {/* Summary Content */}
      {summary && (
        <div className="mt-4 space-y-4">
          {/* Medical Disclaimer Banner */}
          <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/40 text-amber-800 dark:text-amber-200 text-xs flex items-center gap-2.5">
            <ShieldCheck className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <span>{summary.caveat}</span>
          </div>

          {/* Sections */}
          <div className="space-y-3">
            {summary.sections.map((section, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl bg-gray-50 dark:bg-dark-bg/60 border border-gray-100 dark:border-dark-border"
              >
                <h4 className="text-sm font-bold text-gray-800 dark:text-gray-200 mb-1.5 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 dark:bg-indigo-400" />
                  {section.title}
                </h4>
                <div className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-line">
                  {section.text}
                </div>
              </div>
            ))}
          </div>

          {/* Factual Claims & Provenance Traceability */}
          {summary.claims && summary.claims.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-dark-border">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                <span>Verified Source Facts ({summary.claims.length})</span>
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {summary.claims.map((claim, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg bg-white dark:bg-dark-surface border border-gray-200/70 dark:border-dark-border text-xs flex items-start justify-between gap-2 shadow-2xs"
                  >
                    <span className="text-gray-700 dark:text-gray-300 font-medium leading-snug">
                      {claim.text}
                    </span>
                    {claim.source_page && (
                      <span className="shrink-0 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-dark-bg text-[10px] text-gray-500 font-semibold border border-gray-200 dark:border-dark-border flex items-center gap-1">
                        <FileText className="w-2.5 h-2.5" />
                        <span>p.{claim.source_page}</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
export default AISummaryCard;
