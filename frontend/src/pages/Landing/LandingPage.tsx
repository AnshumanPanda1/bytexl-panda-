import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Embedded Landing Page View for Tattva.
 * When users navigate to `/` (or `/landing`), they see the polished product showcase
 * seamlessly embedded. When clicking "Launch Copilot", "Explore Records", or "Dashboard",
 * it smoothly transitions straight into the live interactive clinical workspace.
 */
export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Intercept messages from embedded landing page iframe if any
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'NAVIGATE_TO_APP') {
        navigate(event.data.path || '/dashboard');
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [navigate]);

  return (
    <div className="relative w-full min-h-screen bg-[#070514] overflow-hidden text-white flex flex-col">
      {/* Floating Action Header Bar */}
      <div className="sticky top-0 z-50 flex items-center justify-between px-6 py-3.5 bg-[#09071c]/90 backdrop-blur-md border-b border-white/10 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center shadow-md shadow-indigo-500/20 font-bold text-white text-base">
            T
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-gray-100 to-indigo-200 bg-clip-text text-transparent">
              Tattva
            </span>
            <span className="ml-2 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
              Copilot Active
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/documents')}
            className="hidden sm:inline-flex items-center px-4 py-2 text-xs font-semibold rounded-xl text-gray-300 hover:text-white hover:bg-white/5 border border-white/10 transition-all duration-200"
          >
            Explore Records
          </button>
          <button
            onClick={() => navigate('/dashboard')}
            className="inline-flex items-center gap-2 px-5 py-2 text-xs font-bold rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-md shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200"
          >
            <span>Open Dashboard</span>
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        </div>
      </div>

      {/* Embedded High-Performance Astro Showcase */}
      <div className="flex-1 w-full relative">
        <iframe
          src="/portal/"
          title="Tattva Product Showcase"
          className="w-full h-[calc(100vh-60px)] border-0"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
        />
      </div>
    </div>
  );
};

export default LandingPage;
