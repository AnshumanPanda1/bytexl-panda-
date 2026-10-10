import { useEffect, ReactElement, cloneElement, isValidElement } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/slices/authSlice';
import { usePatientStore } from '../../store/slices/patientSlice';
import { useSettingsStore } from '../../store/slices/settingsSlice';
import { useTenantStore } from '../../store/slices/tenantSlice';
import { listPatients } from '../../services/patientService';
import { PatientSelect } from '../patients';
import { Search, Settings, Menu, X, Sparkles, ArrowLeft, Link as LinkIcon, Info, UserCircle, ListChecks } from 'lucide-react';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { useSyncStatus } from '../ui/SyncIndicator';
import { UserMenu, type UserMenuItem, type UserMenuStatus } from '../ui/user-menu';
import { NotificationBell } from './NotificationBell';
import { Breadcrumbs } from '../ui/Breadcrumbs';
import { useUIStore } from '../../store/slices/uiSlice';
import { useTenantSwitchStore } from '../../store/slices/tenantSwitchSlice';
import { UI_LANGUAGES } from '../../lib/uiLanguages';

function Header() {
  const { t } = useTranslation();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const { setPatients, setCurrentPatient } = usePatientStore();
  const { language, setLanguage, theme, setTheme } = useSettingsStore();
  const loadCurrentTenant = useTenantStore((s) => s.loadCurrentTenant);
  const clearTenant = useTenantStore((s) => s.clear);
  
  const sidebarOpen = useUIStore(state => state.sidebarOpen);
  const toggleSidebar = useUIStore(state => state.toggleSidebar);
  const toggleAIDrawer = useUIStore(state => state.toggleAIDrawer);
  const pageHeaderConfig = useUIStore(state => state.pageHeaderConfig);
  const pageSearchTerm = useUIStore(state => state.pageSearchTerm);
  const setPageSearchTerm = useUIStore(state => state.setPageSearchTerm);
  const isSearchLauncherOpen = useUIStore(state => state.isSearchLauncherOpen);

  // Helper to get page title from current path (fallback if no PageHeader is used)
  const getPageTitle = () => {
    if (pageHeaderConfig?.title) return pageHeaderConfig.title;
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') return t('common.dashboard');
    return 'MediBot';
  };

  // Load the current tenant's display name whenever the user changes
  // (login, tenant switch, exit-switch). The tenant name is not in the
  // JWT — it must be fetched via GET /tenants.
  useEffect(() => {
    if (user?.tenant_id) {
      loadCurrentTenant();
    } else {
      clearTenant();
    }
  }, [user?.tenant_id, loadCurrentTenant, clearTenant]);

  const switched = useTenantSwitchStore((s) => s.switched);

  useEffect(() => {
    const fetchPatients = async () => {
      try {
        // We explicitly omit the tenant_id parameter so the backend uses the
        // tenant_id from the active JWT (which handles switched admin sessions correctly).
        const response = await listPatients(undefined, 100);
        const items = response.items || [];
        setPatients(items);
        
        // Refresh or auto-select patient
        if (items.length > 0) {
          const current = usePatientStore.getState().currentPatient;
          
          // Logic 1: If current user is linked to a patient, that patient MUST be the context
          const linkedPatient = items.find((p: any) => p.user_id === user?.id);
          
          if (linkedPatient) {
            if (!current || current.id !== linkedPatient.id) {
              setCurrentPatient(linkedPatient);
              return; // Priority 1 satisfied
            }
          }

          // Logic 2: If no link but we have a stale context from another tenant, clear it
          if (current && !items.find(p => p.id === current.id)) {
            setCurrentPatient(null);
            return;
          }

          // Logic 3: If no patient is selected yet and we are an admin, we don't auto-select random patients
          // Only auto-select if it's the ONLY patient in the tenant (Home user context) or we are capturing screenshots
          if (!current && (items.length === 1 || window.__HA_SCREENSHOT_CAPTURE__)) {
            setCurrentPatient(items[0]);
          }
          
          // Update existing currentPatient data if it was already correct
          if (current) {
            const latest = items.find(p => p.id === current.id);
            if (latest) {
              // Update if there are meaningful differences
              if (latest.mrn !== current.mrn || 
                  latest.birth_date !== current.birth_date ||
                  JSON.stringify(latest.name) !== JSON.stringify(current.name)) {
                setCurrentPatient(latest);
              }
            }
          }
        } else {
          // No patients available at all
          setCurrentPatient(null);
        }
      } catch (error) {
        console.error("Failed to fetch patients for header dropdown:", error);
      }
    };
    
    fetchPatients();
  }, [user?.tenant_id, setPatients, setCurrentPatient, switched]); // Re-fetch when user tenant or switched status changes

  // Sync pill state (offline flag + Dexie outbox queue) — the same
  // signals the standalone SyncIndicator renders, mapped to the shared
  // UserMenu status contract.
  const { isOnline, pendingCount, syncingCount } = useSyncStatus();

  const menuStatus: UserMenuStatus = !isOnline
    ? { label: t('common.status_offline'), tone: 'warning' }
    : syncingCount > 0
      ? { label: t('common.status_syncing'), tone: 'info' }
      : pendingCount > 0
        ? { label: t('common.status_pending', { count: pendingCount }), tone: 'warning' }
        : { label: t('common.status_synced'), tone: 'success' };

  const roleBadgeLabel =
    user?.role === 'SYSTEM_ADMIN' ? t('admin.role_system_admin') :
    user?.role === 'ADMIN' ? t('admin.role_admin') :
    user?.role === 'MANAGER' ? t('admin.role_manager') :
    t('admin.role_user');

  const menuItems: UserMenuItem[] = [
    { id: '/profile', label: t('common.profile'), icon: UserCircle },
    { id: '/settings', label: t('common.settings'), icon: Settings },
    { id: '/about', label: t('common.about'), icon: Info },
  ];

  return (
    <header className="bg-white/95 dark:bg-dark-surface/95 backdrop-blur-md border-b border-gray-200/80 dark:border-dark-border px-4 md:px-6 py-2 safe-top flex items-center justify-between z-500 sticky top-0 shadow-xs transition-colors">
      <div className="flex items-center space-x-2 md:space-x-3 min-w-0">
        {/* Mobile/Tablet Sidebar Toggle */}
        <button 
          onClick={toggleSidebar}
          className="lg:hidden p-1.5 -ml-1 text-gray-400 hover:text-gray-700 dark:text-dark-muted dark:hover:text-dark-text transition-colors shrink-0 rounded-lg hover:bg-gray-100 dark:hover:bg-dark-bg"
        >
          {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>

        {/* Dynamic Header Section (Title/Icon/Back) */}
        <div className="flex items-center min-w-0 gap-2 sm:gap-3">
          {pageHeaderConfig?.showBackButton && (
            <button 
              onClick={() => navigate(-1)}
              className="flex w-8 h-8 items-center justify-center text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors hover:bg-gray-100 dark:hover:bg-dark-bg/80 rounded-lg shrink-0"
              title="Go Back"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}

          <div className="flex items-center gap-2.5 min-w-0">
            {pageHeaderConfig?.icon && (
              <div className={`hidden sm:flex w-8 h-8 ${isValidElement(pageHeaderConfig.icon) && pageHeaderConfig.icon.type === 'img' ? '' : 'bg-blue-600/10 text-blue-600 dark:text-blue-400 border border-blue-500/20'} rounded-lg items-center justify-center shrink-0 overflow-hidden`}>
                {isValidElement(pageHeaderConfig.icon) && pageHeaderConfig.icon.type === 'img' ? (
                  pageHeaderConfig.icon
                ) : (
                  cloneElement(pageHeaderConfig.icon as ReactElement, { className: "w-4 h-4" })
                )}
              </div>
            )}
            <div className="flex flex-col min-w-0">
              {pageHeaderConfig?.breadcrumbs && (
                <div className="hidden lg:block -mb-0.5">
                  <Breadcrumbs 
                    items={pageHeaderConfig.breadcrumbs} 
                    currentLabel={pageHeaderConfig.title}
                  />
                </div>
              )}
              <h1 className="text-sm sm:text-base font-semibold text-gray-900 dark:text-dark-text tracking-tight truncate">
                {getPageTitle()}
              </h1>
              {pageHeaderConfig?.subtitle && (
                <div className="hidden md:block text-xs text-gray-500 dark:text-dark-muted font-normal truncate" title={typeof pageHeaderConfig.subtitle === 'string' ? pageHeaderConfig.subtitle : undefined}>
                  {pageHeaderConfig.subtitle}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Center Section spacer */}
      <div className="flex-1 max-w-2xl mx-4 hidden md:flex items-center justify-center">
      </div>

      {/* Right Section: Global Tools ONLY */}
      <div className="flex items-center space-x-2 md:space-x-3">
        {/* Mobile Search Toggle */}
        <button 
          className={`md:hidden p-1.5 transition-colors relative rounded-lg hover:bg-gray-100 dark:hover:bg-dark-bg ${pageSearchTerm && !isSearchLauncherOpen ? 'text-blue-600 dark:text-blue-400' : 'text-gray-400 hover:text-gray-600'}`}
          onClick={() => useUIStore.getState().setSearchLauncherOpen(true)}
        >
          <Search className="h-4 w-4" />
          {pageSearchTerm && !isSearchLauncherOpen && (
            <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-blue-500 rounded-full" />
          )}
        </button>

        {/* Global Patient Selector */}
        <div className="hidden sm:flex items-center">
          <PatientSelect />
        </div>

        <div className="flex items-center space-x-1.5">
          {/* Desktop Search Launcher Button */}
          <div className="hidden md:flex items-center">
            {pageSearchTerm && !isSearchLauncherOpen ? (
              <div className="flex items-stretch bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg min-h-[32px]">
                <button
                  onClick={() => useUIStore.getState().setSearchLauncherOpen(true)}
                  className="flex items-center pl-2 pr-1.5 py-0.5 text-blue-700 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 rounded-l-lg transition-colors text-left"
                  title={t('common.edit_search', 'Edit search')}
                >
                  <Search className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-xs font-medium w-16 sm:w-24 md:w-28 truncate ml-1.5">
                    {pageSearchTerm}
                  </span>
                </button>
                <div className="w-px bg-blue-200 dark:bg-blue-800 my-1" />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setPageSearchTerm('');
                  }}
                  className="flex items-center justify-center px-1.5 hover:text-blue-600 dark:hover:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 rounded-r-lg transition-colors text-blue-400 shrink-0"
                  title={t('common.clear_search', 'Clear search')}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => useUIStore.getState().setSearchLauncherOpen(true)}
                className="flex items-center space-x-1.5 px-2.5 h-8 bg-gray-50 dark:bg-dark-bg/60 border border-gray-200 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-border-strong rounded-lg text-gray-500 dark:text-dark-muted transition-colors group"
                title={t('common.search', 'Search')}
              >
                <Search className="w-3.5 h-3.5 group-hover:text-blue-500 transition-colors" />
                <span className="text-xs font-normal">{t('common.search', 'Search...')}</span>
              </button>
            )}
          </div>

          <button 
            onClick={() => isMobile ? navigate('/ai-assistant') : toggleAIDrawer()}
            className="relative p-1.5 text-gray-500 hover:text-indigo-600 dark:text-dark-muted dark:hover:text-indigo-400 transition-colors rounded-lg hover:bg-gray-100 dark:hover:bg-dark-bg"
            title="AI Assistant"
          >
            <Sparkles className="h-4 w-4" />
            <span className="absolute top-1 right-1 flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-indigo-500"></span>
            </span>
          </button>

          <NotificationBell />

          <UserMenu
            user={{ email: user?.email, role: user?.role }}
            roleBadge={roleBadgeLabel}
            labels={{ openMenu: t('common.account'), account: t('common.account') }}
            switcher={
              <div className="flex flex-col gap-2">
                {/* Mobile/Compact Patient Selector in Menu */}
                <div className="sm:hidden">
                  <PatientSelect className="border-none bg-transparent shadow-none" align="right" />
                </div>
              </div>
            }
            status={menuStatus}
            language={language}
            onLanguageChange={setLanguage}
            languages={UI_LANGUAGES.map((language) => ({
              id: language.code,
              label: language.nativeName,
            }))}
            theme={theme === 'dark' ? 'dark' : 'light'}
            onThemeChange={(next) => setTheme(next === 'dark' ? 'dark' : 'light')}
            themeLabels={{ dark: t('common.dark_mode') }}
            items={menuItems}
            onItemSelect={(id) => navigate(id)}
            onLogout={() => { void logout(); }}
            logoutLabel={t('common.logout')}
            contentClassName="w-64 overflow-visible"
          />
        </div>
      </div>

      {/* Full Screen Mobile Search Overlay removed. Replaced by SearchLauncher. */}
    </header>
  );
}

export default Header;
