/**
 * Sidebar Component
 *
 * Displays:
 * - Project list (clickable)
 * - Statistics for current project
 */

import { useAppStore, useProjects, useCurrentProject, useNodes } from '../store/appStore';
import type { NodeType } from '../types';

// Node type icons
const nodeTypeIcons: Record<NodeType, string> = {
  requirement: '📋',
  epic: '🎯',
  'user-story': '📖',
  diagram: '📊',
  test: '🧪',
  api: '🔌',
  component: '🧩',
  screen: '📱',
  persona: '👤',
  'user-flow': '🔄',
  task: '✅',
  'tech-stack': '🛠️'
};

export function Sidebar() {
  const projects = useProjects();
  const currentProject = useCurrentProject();
  const nodes = useNodes();
  const { selectProject, loadProjects, toggleSidebar } = useAppStore();
  const sidebarCollapsed = useAppStore(state => state.sidebarCollapsed);

  // Count nodes by type
  const nodeCountByType = Object.values(nodes).reduce((acc, node) => {
    acc[node.type] = (acc[node.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // Calculate total
  const totalNodes = Object.values(nodes).length;
  const requirementCount = nodeCountByType['requirement'] || 0;
  const diagramCount = nodeCountByType['diagram'] || 0;

  if (sidebarCollapsed) {
    return (
      <aside className="w-12 bg-bg-secondary border-r border-border-color flex flex-col items-center py-4">
        <button
          onClick={toggleSidebar}
          className="p-2 hover:bg-bg-tertiary rounded"
          title="Sidebar öffnen"
        >
          ▶
        </button>
        <div className="mt-4 text-2xl">📊</div>
      </aside>
    );
  }

  return (
    <aside className="w-72 bg-bg-secondary border-r border-border-color flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border-color flex items-center justify-between">
        <h1 className="text-lg font-semibold flex items-center gap-2">
          📊 RE Dashboard
        </h1>
        <button
          onClick={toggleSidebar}
          className="p-1 hover:bg-bg-tertiary rounded text-text-secondary"
          title="Sidebar schließen"
        >
          ◀
        </button>
      </div>

      {/* Project List */}
      <div className="p-4 border-b border-border-color">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-text-secondary">
            📁 Projekte ({projects.length})
          </h2>
          <button
            onClick={loadProjects}
            className="px-2 py-1 text-xs bg-bg-tertiary rounded hover:bg-bg-primary"
            title="Projekte neu laden"
          >
            🔄
          </button>
        </div>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {projects.length === 0 ? (
            <div className="text-sm text-text-secondary text-center py-4">
              Keine Projekte gefunden
            </div>
          ) : (
            projects.map((p) => (
              <button
                key={p.name}
                onClick={() => selectProject(p.name)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                  currentProject === p.name
                    ? 'bg-accent-blue text-white'
                    : 'hover:bg-bg-tertiary'
                }`}
              >
                <div className="font-medium truncate">{p.name}</div>
                <div className="text-xs opacity-70">
                  {p.nodeCount} Nodes • {p.diagramCount} Diagramme
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Project Statistics */}
      {currentProject && (
        <div className="flex-1 overflow-y-auto">
          <div className="p-4">
            <h2 className="text-sm font-medium text-text-secondary mb-3">
              📈 Statistik: {currentProject.split('_')[0]}
            </h2>

            {/* Summary */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div className="bg-bg-tertiary rounded p-3 text-center">
                <div className="text-2xl font-bold">{totalNodes}</div>
                <div className="text-xs text-text-secondary">Gesamt</div>
              </div>
              <div className="bg-bg-tertiary rounded p-3 text-center">
                <div className="text-2xl font-bold">{requirementCount}</div>
                <div className="text-xs text-text-secondary">Requirements</div>
              </div>
              <div className="bg-bg-tertiary rounded p-3 text-center">
                <div className="text-2xl font-bold">{diagramCount}</div>
                <div className="text-xs text-text-secondary">Diagramme</div>
              </div>
              <div className="bg-bg-tertiary rounded p-3 text-center">
                <div className="text-2xl font-bold">
                  {Object.keys(nodeCountByType).length}
                </div>
                <div className="text-xs text-text-secondary">Typen</div>
              </div>
            </div>

            {/* Node types breakdown */}
            <h3 className="text-xs font-medium text-text-secondary mb-2">
              Nach Typ:
            </h3>
            <div className="space-y-1">
              {Object.entries(nodeCountByType)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div
                    key={type}
                    className="flex items-center justify-between text-sm px-2 py-1 bg-bg-tertiary rounded"
                  >
                    <span className="flex items-center gap-2">
                      <span>{nodeTypeIcons[type as NodeType] || '📄'}</span>
                      <span className="capitalize">{type.replace('-', ' ')}</span>
                    </span>
                    <span className="text-text-secondary">{count}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!currentProject && projects.length > 0 && (
        <div className="flex-1 flex items-center justify-center p-8 text-center text-text-secondary">
          <div>
            <div className="text-4xl mb-4">👆</div>
            <p>Wähle ein Projekt</p>
          </div>
        </div>
      )}
    </aside>
  );
}
