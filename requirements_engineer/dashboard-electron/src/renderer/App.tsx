/**
 * App Component
 *
 * Main application component that composes the dashboard layout.
 */

import { useEffect } from 'react';
import { useAppStore, useError, useLoading } from './store/appStore';
import { Sidebar } from './components/Sidebar';
import { Canvas } from './components/Canvas';
import { Toolbar } from './components/Toolbar';

export function App() {
  const { loadProjects, clearError } = useAppStore();
  const error = useError();
  const loading = useLoading();

  // Load projects on mount
  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  return (
    <div className="app-container flex h-screen bg-bg-primary text-text-primary overflow-hidden">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <Toolbar />

        {/* Global Error Banner */}
        {error && (
          <div className="bg-accent-red/20 border-b border-accent-red px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-accent-red">
              <span>❌</span>
              <span className="text-sm">{error}</span>
            </div>
            <button
              onClick={clearError}
              className="text-accent-red hover:text-white px-2"
              title="Fehler schließen"
            >
              ✕
            </button>
          </div>
        )}

        {/* Loading Overlay */}
        {loading && (
          <div className="absolute inset-0 bg-bg-primary/80 flex items-center justify-center z-50">
            <div className="flex flex-col items-center gap-4">
              <div className="animate-spin text-4xl">⏳</div>
              <div className="text-text-secondary">Laden...</div>
            </div>
          </div>
        )}

        {/* Canvas */}
        <Canvas />
      </main>
    </div>
  );
}

export default App;
