/**
 * Shared Tailwind classes for consistent card styling across the application.
 */
export const CardStyles = {
  // Main container for cards in a list
  container: (isSelected: boolean, isSelectable: boolean = false) => `
    relative group border transition-all duration-200 cursor-pointer overflow-hidden rounded-xl
    ${isSelected 
      ? 'bg-blue-50/50 dark:bg-blue-900/10 shadow-xs border-blue-300 dark:border-blue-800 ring-1 ring-blue-500/20 z-10' 
      : 'bg-white dark:bg-dark-surface border-gray-200/80 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-border-strong hover:shadow-xs'
    }
    ${isSelectable ? 'pl-2' : ''}
  `,
  
  // Compact variant for sidebar/smaller contexts
  compact: (isSelected: boolean) => `
    group relative bg-white dark:bg-dark-surface p-3.5 rounded-xl border transition-all cursor-pointer hover:shadow-xs
    ${isSelected 
      ? 'bg-blue-50/50 dark:bg-blue-900/10 border-blue-400 dark:border-blue-700 shadow-xs ring-1 ring-blue-500/20' 
      : 'border-gray-200/80 dark:border-dark-border hover:border-gray-300 dark:hover:border-dark-border-strong'
    }
  `,

  // Inner padding for standard list cards
  inner: "p-4",
  
  // Header section (Date, Badge, etc.)
  header: "flex items-center justify-between mb-2.5",
  
  // Date text style
  date: (isSelected: boolean) => `text-xs font-medium ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-dark-muted'}`,
  
  // Title text style
  title: (isSelected: boolean) => `font-semibold text-sm ${isSelected ? 'text-gray-900 dark:text-dark-text' : 'text-gray-800 dark:text-gray-200'}`,
  
  // Subtitle/Description text style
  description: "text-xs text-gray-500 dark:text-dark-muted mt-1"
};
