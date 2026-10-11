import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Database, Info, ExternalLink, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DataMiniPage } from './DataMiniPage';
import { ToolCallInfo } from '../../types/ai';
import { getObservation, listObservations } from '../../services/observationService';
import { getMedication, getCatalogMedication } from '../../services/medicationService';
import { getExamination } from '../../services/examinationService';
import { getEvent } from '../../services/clinicalEventService';
import { getDocument } from '../../services/documentService';
import biomarkerService from '../../services/biomarkerService';

interface CitationButtonProps {
  reference: string; // format: "type=uuid" or "tool_name"
  toolCalls: ToolCallInfo[];
}

export const CitationButton: React.FC<CitationButtonProps> = ({ reference, toolCalls }) => {
  const [showPopup, setShowPopup] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchedData, setFetchedData] = useState<any>(null);
  /** For dual-nature citations (medication today): tracks whether the fetched
   *  row was a patient-instance prescription or a catalog definition so
   *  `handleOpenOriginal` routes to the right page. null until fetched. */
  const [citationKind, setCitationKind] = useState<'instance' | 'catalog' | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ top: number, left: number, placement: 'top' | 'bottom' }>({ top: 0, left: 0, placement: 'top' });
  const buttonRef = useRef<HTMLSpanElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navigate = useNavigate();

  const isUUIDReference = reference.includes('=');
  let [type, uuid] = isUUIDReference 
    ? reference.split('=').map(s => s.trim()) 
    : [reference.trim(), null];

  // Handle case where UUID is actually a full URL (from LLM or user input)
  if (uuid && (uuid.includes('http') || uuid.includes('/'))) {
    const parts = uuid.split('/');
    uuid = parts[parts.length - 1];
  }

  // Handle truncated UUIDs from LLM (e.g. "uuid...")
  const isTruncated = uuid?.endsWith('...');
  const searchUuid = isTruncated ? uuid?.replace('...', '') : uuid;
  const isPlaceholderUuid = !searchUuid || searchUuid.toLowerCase() === 'uuid' || searchUuid.toLowerCase() === 'id';

  const handleMouseEnter = () => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
    setShowPopup(true);
    fetchData();
  };

  const handleMouseLeave = () => {
    closeTimeoutRef.current = setTimeout(() => {
      setShowPopup(false);
    }, 300);
  };

  // Find tool call matching reference name or containing our target UUID/category
  const toolCall = [...toolCalls].reverse().find(tc => {
    const nameMatch = tc.name.toLowerCase() === reference.toLowerCase();
    if (nameMatch) return true;
    
    // Category match if bare type
    const lowerType = type.toLowerCase();
    if (lowerType === 'observation' && (tc.name.includes('biomarker') || tc.name.includes('observation'))) return true;
    if (lowerType === 'biomarker' && (tc.name.includes('biomarker') || tc.name.includes('trends'))) return true;
    if (lowerType === 'medication' && tc.name.includes('medication')) return true;
    if (lowerType === 'examination' && tc.name.includes('examination')) return true;

    if (searchUuid && !isPlaceholderUuid && tc.result) {
      return tc.result.includes(searchUuid);
    }
    return false;
  });

  const updatePosition = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;
      const placement = (spaceAbove > 400 || spaceAbove > spaceBelow) ? 'top' : 'bottom';
      
      setPopupPosition({
        top: placement === 'top' ? rect.top - 12 : rect.bottom + 12,
        left: rect.left + (rect.width / 2),
        placement
      });
    }
  };

  useEffect(() => {
    if (showPopup) {
      const timer = setTimeout(updatePosition, 0);
      window.addEventListener('scroll', updatePosition, true);
      window.addEventListener('resize', updatePosition);
      return () => {
        clearTimeout(timer);
        window.removeEventListener('scroll', updatePosition, true);
        window.removeEventListener('resize', updatePosition);
      };
    }
  }, [showPopup]);

  // Extract matching records from tool execution results
  const findRecordInToolCalls = () => {
    if (!toolCalls || toolCalls.length === 0) return null;

    // 1. Search by UUID if we have one
    if (searchUuid && !isPlaceholderUuid) {
      for (const tc of toolCalls) {
        if (!tc.result) continue;
        try {
          const parsed = typeof tc.result === 'string' ? JSON.parse(tc.result) : tc.result;
          const list = Array.isArray(parsed) ? parsed : [parsed];
          const found = list.find((item: any) => 
            (item.id && (item.id === searchUuid || item.id.startsWith(searchUuid))) ||
            (item.biomarker_id && (item.biomarker_id === searchUuid || item.biomarker_id.startsWith(searchUuid)))
          );
          if (found) return found;
        } catch (e) {}
      }
    }

    // 2. Search category matches
    const lowerType = type.toLowerCase();
    for (const tc of [...toolCalls].reverse()) {
      if (!tc.result) continue;
      const lowerName = tc.name.toLowerCase();
      const matchesCategory = 
        (lowerType.includes('observation') || lowerType.includes('biomarker')) && (lowerName.includes('biomarker') || lowerName.includes('observation')) ||
        (lowerType.includes('medication')) && lowerName.includes('medication') ||
        (lowerType.includes('examination')) && lowerName.includes('examination') ||
        (lowerType.includes('document')) && lowerName.includes('document') ||
        (lowerType.includes('event')) && lowerName.includes('event');

      if (matchesCategory) {
        try {
          const parsed = typeof tc.result === 'string' ? JSON.parse(tc.result) : tc.result;
          if (Array.isArray(parsed) && parsed.length > 0) {
            return parsed;
          } else if (parsed && typeof parsed === 'object') {
            return parsed;
          }
        } catch (e) {}
      }
    }

    // 3. Fallback: direct match on tool name
    const directTc = toolCalls.find(tc => tc.name.toLowerCase() === reference.toLowerCase());
    if (directTc?.result) {
      try {
        return typeof directTc.result === 'string' ? JSON.parse(directTc.result) : directTc.result;
      } catch (e) {
        return directTc.result;
      }
    }

    return null;
  };

  const fetchData = async () => {
    if (fetchedData || loading) return;
    
    let finalUuid = searchUuid;

    // If truncated, try to resolve full UUID from tool results
    if (isTruncated && toolCall?.result) {
      try {
        const results = JSON.parse(toolCall.result);
        const items = Array.isArray(results) ? results : [results];
        const fullItem = items.find(item => 
          (item.id && item.id.startsWith(searchUuid)) || 
          (item.biomarker_id && item.biomarker_id.startsWith(searchUuid))
        );
        if (fullItem) {
          finalUuid = type === 'biomarker' ? (fullItem.biomarker_id || fullItem.id) : fullItem.id;
        }
      } catch (e) {}
    }

    setLoading(true);
    try {
      let data = null;

      // Primary: Try direct API lookup if valid UUID is present
      if (isUUIDReference && finalUuid && !isPlaceholderUuid) {
        try {
          if (type === 'observation') {
            data = await getObservation(finalUuid);
          } else if (type === 'biomarker') {
            data = await biomarkerService.getBiomarkerById(finalUuid);
          } else if (type === 'medication') {
            try {
              data = await getMedication(finalUuid);
              setCitationKind('instance');
            } catch (instanceErr: any) {
              if (instanceErr?.response?.status === 404) {
                data = await getCatalogMedication(finalUuid);
                setCitationKind('catalog');
              } else {
                throw instanceErr;
              }
            }
          } else if (type === 'examination') {
            data = await getExamination(finalUuid);
          } else if (type === 'event') {
            data = await getEvent(finalUuid);
          } else if (type === 'document') {
            data = await getDocument(finalUuid);
          }
        } catch (apiErr) {
          console.warn(`API lookup failed for ${reference}, checking tool execution results:`, apiErr);
        }
      }

      // Secondary: Fall back to records executed by tool calls in this session
      if (!data) {
        data = findRecordInToolCalls();
      }

      // Tertiary: If still empty and type is observation or biomarker, fetch recent patient observations
      if (!data && (type.toLowerCase().includes('observation') || type.toLowerCase().includes('biomarker'))) {
        try {
          const obsList = await listObservations(undefined, undefined, undefined, undefined, undefined, 5);
          if (obsList?.items?.length) {
            data = obsList.items;
          }
        } catch (e) {}
      }

      setFetchedData(data);
    } catch (err) {
      console.error(`Failed to fetch citation data for ${reference}`, err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenOriginal = () => {
    // Determine the full UUID even if the initial reference was truncated
    let finalUuid = searchUuid;
    if (isTruncated && toolCall?.result) {
      try {
        const results = JSON.parse(toolCall.result);
        const items = Array.isArray(results) ? results : [results];
        const fullItem = items.find(item => 
          (item.id && item.id.startsWith(searchUuid)) || 
          (item.biomarker_id && item.biomarker_id.startsWith(searchUuid))
        );
        if (fullItem) {
          finalUuid = type === 'biomarker' ? (fullItem.biomarker_id || fullItem.id) : fullItem.id;
        }
      } catch (e) {}
    }

    if (isUUIDReference && finalUuid) {
      if (type === 'examination') {
        navigate(`/examinations/${finalUuid}`);
      } else if (type === 'observation') {
        // Navigate to examination's biomarker tab and highlight this observation
        if (fetchedData?.examination_id) {
          navigate(`/examinations/${fetchedData.examination_id}/biomarkers?highlight=${finalUuid}`);
        } else {
          navigate(`/biomarkers`);
        }
      } else if (type === 'biomarker') {
        navigate(`/biomarkers/details/${finalUuid}`);
      } else if (type === 'medication') {
        // Dual-nature citation: route to the catalog workspace if the fetched
        // row was a catalog definition; otherwise the patient-prescription page.
        if (citationKind === 'catalog') {
          navigate(`/catalogs?type=medication&item=${finalUuid}`);
        } else {
          navigate(`/medications/details/${finalUuid}`);
        }
      } else if (type === 'event') {
        navigate(`/events/${finalUuid}`);
      } else if (type === 'document') {
        navigate(`/documents/${finalUuid}`);
      }
    } else if (toolCall) {
      // Legacy navigation logic
      try {
        const args = typeof toolCall.args === 'string' ? JSON.parse(toolCall.args) : toolCall.args;
        if (toolCall.name === 'get_examination_details' && args.examination_id) {
          navigate(`/examinations/${args.examination_id}`);
        } else if (toolCall.name === 'get_biomarker_details' && args.biomarker_id) {
          navigate(`/biomarkers/details/${args.biomarker_id}`);
        } else if (toolCall.name === 'get_aggregated_biomarker_trends') {
          // Prefer the biomarker UUID from the tool result; fall back to slug only if absent
          let bioId: string | undefined = args.biomarker_id;
          if (!bioId && toolCall.result) {
            try {
              const results = JSON.parse(toolCall.result);
              const items = Array.isArray(results) ? results : [results];
              const found = items.find((it: any) => it && (it.biomarker_id || it.id));
              bioId = found?.biomarker_id || found?.id;
            } catch (e) {}
          }
          if (bioId) {
            navigate(`/biomarkers/details/${bioId}`);
          } else if (args.biomarker_slug) {
            navigate(`/biomarkers/details/${args.biomarker_slug}`);
          } else {
            navigate('/biomarkers');
          }
        } else if (toolCall.name.includes('biomarker')) {
          navigate('/biomarkers');
        } else if (toolCall.name.includes('medication')) {
          navigate('/medications');
        }
      } catch (e) {}
    }
    const url = getOriginUrl();
    if (url && url !== '#') {
      navigate(url);
    }
    setShowPopup(false);
  };

  const getOriginUrl = () => {
    let finalUuid = searchUuid;
    if (isTruncated && toolCall?.result) {
      try {
        const results = JSON.parse(toolCall.result);
        const items = Array.isArray(results) ? results : [results];
        const fullItem = items.find(item => 
          (item.id && item.id.startsWith(searchUuid)) || 
          (item.biomarker_id && item.biomarker_id.startsWith(searchUuid))
        );
        if (fullItem) {
          finalUuid = type === 'biomarker' ? (fullItem.biomarker_id || fullItem.id) : fullItem.id;
        }
      } catch (e) {}
    }

    if (isUUIDReference && finalUuid && !isPlaceholderUuid) {
      if (type === 'examination') return `/examinations/${finalUuid}`;
      if (type === 'observation') {
        if (fetchedData?.examination_id) return `/examinations/${fetchedData.examination_id}/biomarkers?highlight=${finalUuid}`;
        return `/biomarkers`;
      }
      if (type === 'biomarker') return `/biomarkers/details/${finalUuid}`;
      if (type === 'medication') {
        return citationKind === 'catalog'
          ? `/catalogs?type=medication&item=${finalUuid}`
          : `/medications/details/${finalUuid}`;
      }
      if (type === 'event') return `/events/${finalUuid}`;
      if (type === 'document') return `/documents/${finalUuid}`;
    } else if (toolCall) {
      try {
        const args = typeof toolCall.args === 'string' ? JSON.parse(toolCall.args) : toolCall.args;
        if (toolCall.name === 'get_examination_details' && args.examination_id) return `/examinations/${args.examination_id}`;
        if (toolCall.name === 'get_biomarker_details' && args.biomarker_id) return `/biomarkers/details/${args.biomarker_id}`;
        if (toolCall.name === 'get_aggregated_biomarker_trends') {
          let bioId: string | undefined = args.biomarker_id;
          if (!bioId && toolCall.result) {
            try {
              const results = JSON.parse(toolCall.result);
              const items = Array.isArray(results) ? results : [results];
              const found = items.find((it: any) => it && (it.biomarker_id || it.id));
              bioId = found?.biomarker_id || found?.id;
            } catch (e) {}
          }
          if (bioId) return `/biomarkers/details/${bioId}`;
          if (args.biomarker_slug) return `/biomarkers/details/${args.biomarker_slug}`;
        }
      } catch (e) {}
    }

    // Category fallbacks
    const lowerType = type.toLowerCase();
    if (lowerType.includes('observation') || lowerType.includes('biomarker')) return '/biomarkers';
    if (lowerType.includes('medication')) return '/medications';
    if (lowerType.includes('examination')) return '/examinations';
    if (lowerType.includes('document')) return '/documents';
    if (lowerType.includes('event')) return '/events';

    return '#';
  };

  const displayName = isUUIDReference 
    ? (uuid && uuid.length < 20 && !isPlaceholderUuid ? uuid.replace(/-/g, ' ') : type)
    : reference.replace(/get_|recent_|history|_details/g, '').replace(/_/g, ' ');

  const isKnownClinicalType = ['observation', 'biomarker', 'medication', 'examination', 'document', 'event'].includes(type.toLowerCase());

  if (!isUUIDReference && !toolCall && !isKnownClinicalType) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-gray-50 dark:bg-dark-surface/50 text-gray-400 dark:text-dark-muted border border-gray-100 dark:border-white/5 text-[9px] font-black uppercase tracking-widest align-middle">
        <Info className="w-2.5 h-2.5" />
        {displayName}
      </span>
    );
  }

  const isMobile = typeof window !== 'undefined' && window.innerWidth < 640;
  const popupWidth = isMobile ? window.innerWidth - 24 : 320;
  const halfWidth = popupWidth / 2;
  
  // Constrain center point (left) so edges are at least 12px from window borders
  const minLeft = halfWidth + 12;
  const maxLeft = (typeof window !== 'undefined' ? window.innerWidth : 1000) - halfWidth - 12;
  const calculatedLeft = Math.min(Math.max(popupPosition.left, minLeft), maxLeft);
  
  // Arrow offset relative to popup center
  const arrowOffset = Math.min(Math.max(popupPosition.left - calculatedLeft, -halfWidth + 24), halfWidth - 24);

  return (
    <span ref={buttonRef} className="relative inline-block mx-0.5 align-middle">
      <span
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-800 text-[10px] font-black uppercase tracking-widest hover:bg-indigo-100 dark:hover:bg-indigo-800/50 transition-colors shadow-xs cursor-help"
      >
        <Database className="w-2.5 h-2.5" />
        {displayName}
      </span>

      {showPopup && createPortal(
        <div 
          ref={popupRef}
          className={`fixed z-modal w-[calc(100vw-24px)] sm:w-80 bg-white dark:bg-dark-surface rounded-2xl shadow-2xl border border-gray-100 dark:border-dark-border p-3 sm:p-4 animate-in fade-in zoom-in-95 duration-200 before:absolute before:-inset-4 before:z-[-1] before:content-['']`}
          style={{
            top: popupPosition.placement === 'top' ? 'auto' : `${popupPosition.top}px`,
            bottom: popupPosition.placement === 'top' ? `${window.innerHeight - popupPosition.top}px` : 'auto',
            left: `${calculatedLeft}px`,
            transform: 'translateX(-50%)'
          }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          {/* Arrow */}
          <div 
            className={`absolute left-1/2 border-8 border-transparent drop-shadow-xs ${
              popupPosition.placement === 'top' 
                ? 'top-full -mt-0.5 border-t-white dark:border-t-dark-surface' 
                : 'bottom-full -mb-0.5 border-b-white dark:border-b-dark-surface'
            }`} 
            style={{ 
              marginLeft: `${arrowOffset}px`,
              transform: 'translateX(-50%)'
            }}
          />
          
          <div className="flex items-center justify-between mb-2 sm:mb-3 pb-2 border-b border-gray-100 dark:border-white/5">
             <div className="flex items-center gap-1.5 sm:gap-2">
                <div className="p-1 sm:p-1.5 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-lg">
                   <Database className="w-3 sm:w-3.5 h-3 sm:h-3.5" />
                </div>
                <div>
                   <span className="text-[8px] sm:text-[10px] font-black uppercase tracking-widest text-gray-500 dark:text-dark-muted block leading-none mb-0.5">
                     Live Data
                   </span>
                   <span className="text-[8px] sm:text-[9px] font-mono text-indigo-600 dark:text-indigo-400 leading-none">{displayName}</span>
                </div>
             </div>
             <a 
               href={getOriginUrl()}
               onClick={(e) => {
                 e.preventDefault();
                 handleOpenOriginal();
               }}
               className="flex items-center gap-1 px-1.5 sm:px-2 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-[8px] sm:text-[9px] font-black uppercase tracking-widest transition-all shadow-md active:scale-95 whitespace-nowrap cursor-pointer"
             >
                <ExternalLink className="w-2.5 sm:w-3 h-2.5 sm:h-3" />
                Origin
             </a>
          </div>

          <div className="max-h-64 sm:max-h-56 overflow-auto custom-scrollbar bg-gray-50/50 dark:bg-dark-bg/20 rounded-xl sm:rounded-2xl p-2 sm:p-3 border border-gray-100 dark:border-white/5 shadow-inner min-h-[80px] flex flex-col items-center justify-center">
             {loading ? (
               <div className="flex flex-col items-center gap-2 py-4">
                 <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                 <span className="text-[10px] font-black uppercase text-gray-400 tracking-tighter">Fetching Clinical Record...</span>
               </div>
             ) : fetchedData ? (
               <DataMiniPage 
                  data={fetchedData} 
                  toolName={type} 
                  onClose={() => setShowPopup(false)}
               />
             ) : (
               <div className="py-3 text-center space-y-1.5 w-full">
                 <p className="text-[10px] font-bold text-gray-600 dark:text-gray-300">Synchronized Clinical Reference</p>
                 <p className="text-[9px] text-gray-400 italic">View complete patient metrics in the workspace.</p>
                 <button
                   onClick={handleOpenOriginal}
                   className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 text-[9px] font-black uppercase tracking-wider hover:bg-indigo-100 transition-colors"
                 >
                   <ExternalLink className="w-2.5 h-2.5" />
                   View in {type.toLowerCase().includes('observation') || type.toLowerCase().includes('biomarker') ? 'Biomarkers' : type}
                 </button>
               </div>
             )}
          </div>
        </div>,
        document.body
      )}
    </span>
  );
};
