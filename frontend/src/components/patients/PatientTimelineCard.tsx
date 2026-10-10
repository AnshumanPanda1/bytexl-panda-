import React, { useEffect, useState } from 'react';
import {
  Clock,
  Calendar,
  FileText,
  Activity,
  Pill,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Tag,
  Stethoscope,
} from 'lucide-react';
import { getPatientTimeline } from '../../services/timelineService';
import type { TimelineItem } from '../../types/timeline';

interface PatientTimelineCardProps {
  patientId: string;
}

export function PatientTimelineCard({ patientId }: PatientTimelineCardProps) {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchTimeline = async (category = selectedCategory) => {
    try {
      setLoading(true);
      setError(null);
      const params = category !== 'all' ? { categories: [category] } : undefined;
      const data = await getPatientTimeline(patientId, params);
      setItems(data.items || []);
    } catch (err: any) {
      console.error('Failed to load patient timeline:', err);
      setError(err?.response?.data?.detail || 'Failed to load chronological timeline.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (patientId) {
      fetchTimeline(selectedCategory);
    }
  }, [patientId, selectedCategory]);

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'examination':
        return <Stethoscope className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />;
      case 'document':
        return <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />;
      case 'observation':
        return <Activity className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />;
      case 'medication':
        return <Pill className="w-4 h-4 text-purple-600 dark:text-purple-400" />;
      case 'condition':
        return <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getEventBg = (type: string) => {
    switch (type) {
      case 'examination':
        return 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/40';
      case 'document':
        return 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800/40';
      case 'observation':
        return 'bg-indigo-50 dark:bg-indigo-950/30 border-indigo-200 dark:border-indigo-800/40';
      case 'medication':
        return 'bg-purple-50 dark:bg-purple-950/30 border-purple-200 dark:border-purple-800/40';
      case 'condition':
        return 'bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800/40';
      default:
        return 'bg-gray-50 dark:bg-dark-bg border-gray-200 dark:border-dark-border';
    }
  };

  const categories = [
    { id: 'all', label: 'All Records' },
    { id: 'observation', label: 'Labs' },
    { id: 'medication', label: 'Medications' },
    { id: 'condition', label: 'Diagnoses' },
    { id: 'examination', label: 'Examinations' },
    { id: 'document', label: 'Documents' },
  ];

  return (
    <div className="bg-white dark:bg-dark-surface rounded-xl shadow-xs border border-gray-200/80 dark:border-dark-border p-5 lg:p-6 space-y-5">
      {/* Header & Filter Pills */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-100 dark:border-dark-border pb-4">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 rounded-lg flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-dark-text tracking-tight">
              Chronological Health Timeline
            </h3>
            <p className="text-xs text-gray-500 dark:text-dark-muted">
              Unified historical view of exams, lab tests, prescriptions, and conditions
            </p>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1 bg-gray-100 dark:bg-dark-bg p-0.5 rounded-lg border border-gray-200 dark:border-dark-border text-xs font-medium">
          {categories.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedCategory(c.id)}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                selectedCategory === c.id
                  ? 'bg-white dark:bg-dark-surface text-gray-900 dark:text-white shadow-xs font-semibold'
                  : 'text-gray-500 hover:text-gray-900 dark:text-dark-muted'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline Stream */}
      {loading ? (
        <div className="py-10 flex items-center justify-center space-x-2.5 text-gray-400">
          <RefreshCw className="w-4 h-4 animate-spin text-blue-500" />
          <span className="text-xs font-medium">Loading chronological timeline...</span>
        </div>
      ) : error ? (
        <div className="p-3.5 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/40 text-red-600 text-xs">
          {error}
        </div>
      ) : items.length === 0 ? (
        <div className="py-10 text-center text-gray-400 space-y-1.5">
          <Calendar className="w-7 h-7 mx-auto text-gray-300 dark:text-gray-600" />
          <p className="text-sm font-medium">No timeline events recorded yet.</p>
          <p className="text-xs text-gray-400">
            Uploaded clinical documents and imported records will appear here automatically.
          </p>
        </div>
      ) : (
        <div className="relative pl-6 space-y-4 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-px before:bg-gray-200 dark:before:bg-dark-border">
          {items.map((item) => {
            const isExpanded = expandedId === item.id;
            return (
              <div key={item.id} className="relative group">
                {/* Node icon dot */}
                <div
                  className={`absolute -left-6 top-1.5 w-6 h-6 rounded-full flex items-center justify-center border-2 border-white dark:border-dark-surface shadow-xs ${getEventBg(
                    item.event_type,
                  )}`}
                >
                  {getEventIcon(item.event_type)}
                </div>

                {/* Event Card */}
                <div className="ml-3 p-3.5 rounded-xl border border-gray-200/60 dark:border-dark-border bg-gray-50/50 dark:bg-dark-bg/30 hover:border-blue-200 dark:hover:border-blue-900/50 transition-colors space-y-1.5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <div className="flex items-center space-x-2">
                      <span className="text-[11px] font-semibold text-gray-500 dark:text-dark-muted uppercase tracking-wider capitalize">
                        {item.event_type}
                      </span>
                      {item.review_status && (
                        <span
                          className={`text-[10px] font-medium px-1.5 py-0.5 rounded-md uppercase ${
                            item.review_status === 'verified'
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                              : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                          }`}
                        >
                          {item.review_status}
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-mono text-gray-500 dark:text-dark-muted">
                      {item.timestamp || item.dt ? new Date(item.timestamp || item.dt!).toLocaleDateString() : 'Date recorded'}
                    </span>
                  </div>

                  <h4 className="text-sm font-semibold text-gray-900 dark:text-dark-text leading-tight">
                    {item.title}
                  </h4>

                  <p className="text-xs text-gray-600 dark:text-dark-muted leading-relaxed">
                    {item.summary}
                  </p>

                  {/* Expand details trigger */}
                  {item.details && Object.keys(item.details).length > 0 && (
                    <div className="pt-0.5">
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : item.id)}
                        className="flex items-center space-x-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        <span>{isExpanded ? 'Hide details' : 'View details'}</span>
                        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      </button>

                      {isExpanded && (
                        <div className="mt-2 p-2.5 rounded-lg bg-white dark:bg-dark-surface border border-gray-200/60 dark:border-dark-border text-xs space-y-1">
                          {Object.entries(item.details).map(([k, v]) => (
                            <div key={k} className="flex justify-between text-gray-600 dark:text-dark-muted">
                              <span className="font-medium capitalize">{k.replace('_', ' ')}:</span>
                              <span className="font-mono text-gray-900 dark:text-dark-text">{String(v ?? '—')}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
