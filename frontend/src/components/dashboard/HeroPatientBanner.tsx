import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, FileText, Activity, MessageSquare, Share2, CheckCircle2, User } from 'lucide-react';
import { usePatientStore } from '../../store/slices/patientSlice';
import { listPatients } from '../../services/patientService';

export const HeroPatientBanner: React.FC = () => {
  const navigate = useNavigate();
  const { currentPatient, setCurrentPatient, setPatients } = usePatientStore();

  const isHeroSelected =
    currentPatient?.name?.given?.includes('Rajesh') ||
    currentPatient?.name?.family === 'Sharma';

  const selectHeroPatient = async () => {
    try {
      const res = await listPatients(undefined, 50, 0);
      const items = res.items || [];
      if (items.length > 0) {
        setPatients(items);
        const hero =
          items.find((p) => p.name?.given?.includes('Rajesh') || p.name?.family === 'Sharma') ||
          items[0];
        setCurrentPatient(hero);
      }
    } catch (e) {
      console.error('Failed to auto-select hero patient:', e);
    }
  };

  if (!isHeroSelected) {
    return (
      <div className="mb-6 p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white shadow-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-blue-400/30 animate-in fade-in">
        <div className="flex items-center space-x-3.5">
          <div className="w-10 h-10 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center shrink-0 border border-white/25">
            <Sparkles className="w-5 h-5 text-amber-300" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-400 text-amber-950">
                Judging Showcase
              </span>
              <span className="text-xs font-semibold text-blue-100">Recommended 3-Act Narrative</span>
            </div>
            <h3 className="text-base font-bold text-white mt-0.5">
              Hero Patient Demo: Rajesh Kumar Sharma
            </h3>
            <p className="text-xs text-blue-100/90 max-w-lg">
              Type 2 Diabetes longitudinal cohort with handwritten OPD prescription, 12-month HbA1c trajectory, and bilingual AI summaries.
            </p>
          </div>
        </div>

        <button
          onClick={selectHeroPatient}
          className="w-full sm:w-auto px-4 py-2.5 bg-white text-indigo-700 hover:bg-blue-50 font-bold text-xs rounded-xl shadow-lg transition-all active:scale-95 flex items-center justify-center gap-2 shrink-0"
        >
          <User className="w-4 h-4" />
          Load Hero Patient Story
        </button>
      </div>
    );
  }

  return (
    <div className="mb-6 p-5 sm:p-6 rounded-3xl bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-950 text-white shadow-2xl border border-indigo-500/20 space-y-4 animate-in fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-2xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-300 shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                Active Hero Story
              </span>
              <span className="text-xs font-medium text-slate-400">Rajesh Kumar Sharma · 52y M (Type 2 Diabetes)</span>
            </div>
            <h2 className="text-lg font-black text-white tracking-tight mt-0.5">
              The Big 4 Value Moments
            </h2>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
            Synthetic Cohort Demo
          </span>
        </div>
      </div>

      {/* 4 Interactive Big Value Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Moment 1 */}
        <button
          onClick={() => navigate('/documents')}
          className="p-3.5 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-left transition-all group flex flex-col justify-between space-y-2 hover:border-blue-400/50"
        >
          <div className="flex items-center justify-between w-full">
            <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">Act 1: Problem</span>
            <FileText className="w-4 h-4 text-blue-400 group-hover:scale-110 transition-transform" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white group-hover:text-blue-200">1. Ingest Prescription</h4>
            <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
              Multi-modal OCR with local Tesseract fallback & human verification.
            </p>
          </div>
        </button>

        {/* Moment 2 */}
        <button
          onClick={() => navigate('/biomarkers')}
          className="p-3.5 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-left transition-all group flex flex-col justify-between space-y-2 hover:border-emerald-400/50"
        >
          <div className="flex items-center justify-between w-full">
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400">Act 2: Action</span>
            <Activity className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white group-hover:text-emerald-200">2. Biomarker Trajectory</h4>
            <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
              12-month HbA1c & Glucose line charts replacing loose papers.
            </p>
          </div>
        </button>

        {/* Moment 3 */}
        <button
          onClick={() => navigate('/ai-assistant')}
          className="p-3.5 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-left transition-all group flex flex-col justify-between space-y-2 hover:border-purple-400/50"
        >
          <div className="flex items-center justify-between w-full">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400">Act 3: Outcome</span>
            <MessageSquare className="w-4 h-4 text-purple-400 group-hover:scale-110 transition-transform" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white group-hover:text-purple-200">3. Bilingual Copilot</h4>
            <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
              Plain-language English ↔ Hindi summaries & grounded clinical chat.
            </p>
          </div>
        </button>

        {/* Moment 4 */}
        <button
          onClick={() => navigate('/settings/export-import')}
          className="p-3.5 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 text-left transition-all group flex flex-col justify-between space-y-2 hover:border-amber-400/50"
        >
          <div className="flex items-center justify-between w-full">
            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">Interoperability</span>
            <Share2 className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white group-hover:text-amber-200">4. FHIR & Mock ABHA</h4>
            <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
              1-click Apollo Clinic simulated import & FHIR R4 JSON export.
            </p>
          </div>
        </button>
      </div>
    </div>
  );
};
