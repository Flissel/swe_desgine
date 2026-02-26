/**
 * Toolbar Component
 *
 * Top toolbar with:
 * - Layout mode selector
 * - Zoom controls
 * - Action buttons
 */

import { useAppStore, useCurrentProject, useLoading, useError } from '../store/appStore';
import type { LayoutMode } from '../types';

const layoutModes: { id: LayoutMode; label: string; icon: string }[] = [
  { id: 'package_link', label: 'Package+Link', icon: '📦' },
  { id: 'link_based', label: 'Hub-Spoke', icon: '🔗' },
  { id: 'flow_based', label: 'Flow', icon: '➡️' },
  { id: 'by_package', label: 'Packages', icon: '📁' },
  { id: 'raw_data', label: 'Roh', icon: '📄' }
];

export function Toolbar() {
  const currentProject = useCurrentProject();
  const loading = useLoading();
  const error = useError();
  const { layoutMode, setLayoutMode, zoom, setZoom, clearError } = useAppStore();

  return (
    <div className="px-4 py-3 bg-bg-secondary border-b border-border-color flex items-center gap-4">
      {/* Layout Mode Buttons */}
      <div className="flex gap-1">
        {layoutModes.map((mode) => (
          <button
            key={mode.id}
            onClick={() => setLayoutMode(mode.id)}
            className={`px-3 py-1.5 rounded text-sm flex items-center gap-1 transition-colors ${
              layoutMode === mode.id
                ? 'bg-accent-blue text-white'
                : 'bg-bg-tertiary hover:bg-bg-primary border border-border-color'
            }`}
          >
            <span>{mode.icon}</span>
            <span className="hidden lg:inline">{mode.label}</span>
          </button>
        ))}
      </div>

      {/* Divider */}
      <div className="w-px h-6 bg-border-color" />

      {/* Zoom Controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setZoom(zoom - 0.1)}
          className="px-2 py-1 bg-bg-tertiary border border-border-color rounded hover:bg-bg-primary"
          title="Zoom Out"
        >
          🔍-
        </button>
        <span className="text-sm text-text-secondary w-16 text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button
          onClick={() => setZoom(zoom + 0.1)}
          className="px-2 py-1 bg-bg-tertiary border border-border-color rounded hover:bg-bg-primary"
          title="Zoom In"
        >
          🔍+
        </button>
        <button
          onClick={() => setZoom(1)}
          className="px-2 py-1 text-sm bg-bg-tertiary border border-border-color rounded hover:bg-bg-primary"
          title="Reset Zoom"
        >
          100%
        </button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Project Info */}
      {currentProject && (
        <div className="text-sm text-text-secondary">
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin">⏳</span> Lädt...
            </span>
          ) : (
            <span>📂 {currentProject}</span>
          )}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-1 bg-accent-red/20 border border-accent-red rounded text-sm text-accent-red">
          <span>❌ {error}</span>
          <button onClick={clearError} className="hover:text-white">✕</button>
        </div>
      )}
    </div>
  );
}
