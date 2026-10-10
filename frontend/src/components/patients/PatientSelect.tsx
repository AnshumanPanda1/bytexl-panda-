import React, { useState, useRef, useEffect } from 'react';
import { Search, ChevronDown, Check, User, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { usePatientStore } from '../../store/slices/patientSlice';
import { formatAge } from '../../utils/dateUtils';
import { useNavigate } from 'react-router-dom';

interface Props {
  className?: string;
  showIcon?: boolean;
  align?: 'left' | 'right';
}

export const PatientSelect: React.FC<Props> = ({
  className = "",
  showIcon = true,
  align = 'left'
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { patients, currentPatient, setCurrentPatient } = usePatientStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filteredPatients = patients.filter(p => {
    const given = p.name?.given?.join(' ') || '';
    const family = p.name?.family || '';
    const fullName = `${given} ${family}`.toLowerCase();
    const id = p.id?.toLowerCase() || '';
    const mrn = p.mrn?.toLowerCase() || '';
    return fullName.includes(searchTerm.toLowerCase()) || 
           id.includes(searchTerm.toLowerCase()) ||
           mrn.includes(searchTerm.toLowerCase());
  });

  const handlePatientSelect = (patient: any) => {
    setCurrentPatient(patient);
    setIsOpen(false);
    setSearchTerm('');
  };

  const getPatientName = (patient: any) => {
    const given = patient.name?.given?.join(' ') || '';
    const family = patient.name?.family || '';
    const name = `${given} ${family}`.trim();
    return name || `Patient ${patient.id.substring(0, 8)}`;
  };

  const containerClasses = className.includes('border-none') 
    ? "w-full min-h-[36px] px-0 py-1 bg-transparent text-gray-900 dark:text-dark-text cursor-pointer flex gap-2 items-center"
    : "w-full min-h-[36px] px-2.5 py-1 bg-gray-50/80 dark:bg-dark-bg/60 border border-gray-200 dark:border-dark-border rounded-lg shadow-xs text-gray-900 dark:text-dark-text focus-within:ring-2 focus-within:ring-blue-500/20 cursor-pointer flex gap-2 items-center transition-colors hover:border-gray-300 dark:hover:border-dark-border-strong";

  return (
    <div className={`relative ${className.replace('border-none', '')}`} ref={dropdownRef}>
      <div 
        className={containerClasses}
        onClick={() => setIsOpen(!isOpen)}
      >
        {showIcon && (
          <div className="w-6 h-6 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-md flex items-center justify-center shrink-0">
            <User className="w-3.5 h-3.5" />
          </div>
        )}
        
        {currentPatient ? (
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-gray-900 dark:text-dark-text truncate leading-tight">
              {getPatientName(currentPatient)}
            </div>
            <div className="text-[10px] text-gray-500 dark:text-dark-muted font-normal leading-tight mt-0.5 truncate">
              {formatAge(currentPatient.birth_date)}
            </div>
          </div>
        ) : (
          <span className="text-gray-400 dark:text-dark-muted text-xs font-normal flex-1 truncate">
            {t('common.select_patient')}
          </span>
        )}
        
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
      </div>

      {isOpen && (
        <div className={`absolute z-600 w-72 mt-1.5 bg-white dark:bg-dark-surface border border-gray-200 dark:border-dark-border rounded-xl shadow-xl overflow-hidden animate-in fade-in slide-in-from-top-1 duration-150 ${align === 'right' ? 'right-0' : 'left-0'}`}>
          <div className="p-2.5 border-b border-gray-100 dark:border-dark-border sticky top-0 bg-white/95 dark:bg-dark-surface/95 backdrop-blur-md z-10">
            <div className="flex items-center justify-between mb-1.5 px-0.5">
              <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{t('common.patients')}</span>
              <span className="text-[10px] font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-1.5 py-0.5 rounded-full">{patients.length} {t('common.total', { defaultValue: 'Total' })}</span>
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                autoFocus
                placeholder={t('patients.search_placeholder')}
                className="w-full pl-8 pr-3 py-1.5 bg-gray-50 dark:bg-dark-bg/60 border border-gray-200 dark:border-dark-border rounded-lg text-xs outline-hidden focus:ring-2 focus:ring-blue-500/20 dark:text-dark-text transition-colors"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>
          
          <div className="max-h-64 overflow-y-auto custom-scrollbar p-1">
            {filteredPatients.length > 0 ? (
              filteredPatients.map((patient) => {
                const isSelected = currentPatient?.id === patient.id;
                return (
                  <div
                    key={patient.id}
                    className={`group px-2.5 py-2 text-sm flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-dark-bg/60 rounded-lg transition-colors mb-0.5 ${isSelected ? 'bg-blue-50/80 dark:bg-blue-900/20' : ''}`}
                    onClick={() => handlePatientSelect(patient)}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 text-xs font-semibold ${isSelected ? 'bg-blue-600 text-white' : 'bg-gray-100 dark:bg-dark-bg text-gray-600 dark:text-dark-muted'}`}>
                        {patient.name?.given?.[0]?.[0]}{patient.name?.family?.[0]}
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className={`text-xs font-medium truncate ${isSelected ? 'text-blue-600 dark:text-blue-400 font-semibold' : 'text-gray-800 dark:text-dark-text'}`}>
                          {getPatientName(patient)}
                        </span>
                        <div className="flex items-center space-x-1.5 mt-0.5 text-[10px] text-gray-400 dark:text-dark-muted">
                          <span>{formatAge(patient.birth_date)}</span>
                          {patient.mrn && (
                            <>
                              <span>•</span>
                              <span>{patient.mrn}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    {isSelected && <Check className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 shrink-0" />}
                  </div>
                );
              })
            ) : (
              <div className="px-4 py-8 text-xs text-gray-400 italic text-center">
                <Users className="w-10 h-10 mx-auto mb-3 opacity-10" />
                <p className="font-bold uppercase tracking-widest text-[10px] opacity-60">{t('patients.no_patients')}</p>
              </div>
            )}
          </div>
          
          <div className="p-2 border-t border-gray-50 dark:border-dark-border bg-gray-50/30 dark:bg-dark-bg/20">
            <button 
              className="w-full py-2.5 px-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/30 transition-all text-center flex items-center justify-center space-x-2"
              onClick={() => {
                navigate('/patients');
                setIsOpen(false);
              }}
            >
              <Users className="w-3.5 h-3.5" />
              <span>{t('patients.directory')}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
