import type { LucideIcon } from 'lucide-react';
import {
  LayoutDashboard,
  FileText,
  Sparkles,
  Clock,
  Activity,
  Share2,
} from 'lucide-react';

export interface MainNavSubItem {
  path: string;
  labelKey: string;
  roles?: string[];
  /** When set, renders a section divider above this sub-item. */
  section?: string;
  /** Resolved dynamically — e.g. /patient-info becomes /patients/{id} or /patients. */
  dynamicPath?: 'patient-detail';
}

export interface MainNavItem {
  path: string;
  labelKey: string;
  icon: LucideIcon;
  subItems?: MainNavSubItem[];
  requiresPatient?: boolean;
  roles?: string[];
}

/**
 * Streamlined MediBot Copilot Navigation:
 * Focused on Document Ingestion, Fact Review, Bilingual AI Summary,
 * Patient Timeline, Biomarker Trends, and FHIR Interop.
 */
export const MAIN_NAV: MainNavItem[] = [
  // 1. Ingestion Hub & Overview
  {
    path: '/dashboard',
    labelKey: 'common.dashboard',
    icon: LayoutDashboard,
  },

  // 2. Document Extraction & Review
  {
    path: '/documents',
    labelKey: 'common.documents_explorer',
    icon: FileText,
  },

  // 3. Bilingual AI Summaries & Copilot
  {
    path: '/ai-assistant',
    labelKey: 'common.ai_assistant',
    icon: Sparkles,
  },

  // 4. Patient Health Timeline
  {
    path: '/events',
    labelKey: 'events.title',
    icon: Clock,
  },

  // 5. Biomarker Trends (Good to have)
  {
    path: '/biomarkers',
    labelKey: 'common.biomarkers',
    icon: Activity,
  },

  // 6. FHIR Export & Mock ABHA Interop (Good to have)
  {
    path: '/settings/export-import',
    labelKey: 'settings.export_import_title',
    icon: Share2,
  },
];

/** Resolve a sub-item path (handles the /patient-info dynamic token). */
export function resolveSubPath(path: string, currentPatientId?: string | number): string {
  if (path === '/patient-info') {
    return currentPatientId != null ? `/patients/${currentPatientId}` : '/patients';
  }
  return path;
}

/**
 * Role-filter the registry, preserving section dividers on the first
 * surviving item of each section and dropping groups whose items are all
 * filtered out. undefined role = unauthenticated = only ungated items.
 */
export function filterNavByRole(items: MainNavItem[], role?: string): MainNavItem[] {
  const allowed = (itemRoles?: string[]) =>
    !itemRoles || (role != null && itemRoles.includes(role));

  return items
    .filter((item) => allowed(item.roles))
    .map((item) => {
      if (!item.subItems) return item;
      const filteredSubItems = item.subItems.filter((sub) => allowed(sub.roles));
      const seenSections = new Set<string>();
      const recomputed = filteredSubItems.map((sub) => {
        if (sub.section && seenSections.has(sub.section)) {
          const { section: _section, ...rest } = sub;
          return rest as MainNavSubItem;
        }
        if (sub.section) seenSections.add(sub.section);
        return sub;
      });
      if (recomputed.length === 0) return item;
      return { ...item, subItems: recomputed };
    })
    .filter((item) => {
      if (item.roles && item.subItems !== undefined && item.subItems.length === 0) return false;
      return true;
    });
}

/**
 * Resolve the active nav id from the location.
 */
export function resolveActiveNavId(
  pathname: string,
  search: string,
  currentPatientId?: string | number,
  role?: string,
): string | null {
  const isSubActive = (sub: MainNavSubItem): boolean => {
    if (sub.dynamicPath === 'patient-detail') {
      return /^\/patients\/[^/]+/.test(pathname);
    }
    if (sub.path === '/patients') {
      return pathname === '/patients';
    }
    if (sub.path.includes('?')) {
      const [base, query] = sub.path.split('?');
      const expected = new URLSearchParams(query).get('type');
      const actual = new URLSearchParams(search).get('type');
      return pathname === base && (!expected || actual === expected);
    }
    return pathname === sub.path || pathname.startsWith(sub.path + '/');
  };

  for (const item of filterNavByRole(MAIN_NAV, role)) {
    if (item.subItems) {
      const active = item.subItems.find(isSubActive);
      if (active) return resolveSubPath(active.path, currentPatientId);
      continue;
    }
    if (item.path === '/dashboard') {
      if (pathname === '/dashboard' || pathname === '/') return item.path;
      continue;
    }
    if (pathname === item.path || pathname.startsWith(item.path + '/')) return item.path;
  }
  return null;
}
