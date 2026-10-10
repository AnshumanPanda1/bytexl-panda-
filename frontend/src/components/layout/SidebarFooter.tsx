import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Info } from 'lucide-react';
import packageJson from '../../../package.json';

const aboutPillClass =
  'inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-[13px] font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-blue-400 [&_svg]:size-4';
const aboutPillCompactClass =
  'inline-flex h-7 items-center gap-1 rounded-full px-3 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-blue-400 [&_svg]:size-3.5';

/**
 * Sidebar footer project block: MediBot app info, About navigation, and version.
 */
export function SidebarFooter({ collapsed, compact = false }: { collapsed: boolean; compact?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={() => navigate('/about')}
          title={t('common.about', 'About MediBot')}
          aria-label={t('common.about', 'About MediBot')}
          className="flex size-7 items-center justify-center rounded-full text-blue-600 transition-colors hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/40"
        >
          <Info className="size-4" />
        </button>
        <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
          v1.0.0
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-2">
      {compact ? (
        <div className="flex w-full items-center justify-between">
          <button
            type="button"
            onClick={() => navigate('/about')}
            className={aboutPillCompactClass}
          >
            <Info />
            {t('common.about', 'About MediBot')}
          </button>
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            v1.0.0
          </span>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1.5 w-full">
          <button
            type="button"
            onClick={() => navigate('/about')}
            className={aboutPillClass}
          >
            <Info />
            {t('common.about', 'About MediBot')}
          </button>
          <p className="text-xs font-medium text-gray-400 dark:text-gray-500">
            MediBot Health Copilot · v1.0.0
          </p>
        </div>
      )}
    </div>
  );
}
