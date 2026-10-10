import type { LucideIcon } from 'lucide-react';
import {
  LayoutDashboard,
  FileText,
  Sparkles,
  Clock,
  Activity,
  Settings,
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

  // 6. Settings (Appearance, Preferences, Export & Import)
  {
    path: '/settings',
    labelKey: 'common.settings',
    icon: Settings,
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
 * Filter nav by role (simplified for demo — all items accessible).
 */
export function filterNavByRole(items: MainNavItem[], _role?: string): MainNavItem[] {
  return items;
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
    if (item.path === '/settings') {
      if (pathname.startsWith('/settings')) return item.path;
      continue;
    }
    if (pathname === item.path || pathname.startsWith(item.path + '/')) return item.path;
  }
  return null;
}
