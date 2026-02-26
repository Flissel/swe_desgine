/**
 * MermaidDiagram Component
 *
 * Renders Mermaid diagrams with proper TypeScript error handling.
 * Unlike the Vanilla JS version, this component:
 * - Shows explicit error states instead of silent failures
 * - Has typed props and state
 * - Provides retry functionality
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import mermaid from 'mermaid';

// Initialize mermaid with dark theme
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: 'basis'
  },
  sequence: {
    useMaxWidth: true,
    wrap: true
  }
});

interface MermaidDiagramProps {
  id: string;
  code: string;
  type?: string;
  onRenderSuccess?: () => void;
  onRenderError?: (error: Error) => void;
}

type RenderState =
  | { status: 'loading' }
  | { status: 'success'; svg: string }
  | { status: 'error'; message: string; code: string };

export function MermaidDiagram({
  id,
  code,
  type = 'flowchart',
  onRenderSuccess,
  onRenderError
}: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderState, setRenderState] = useState<RenderState>({ status: 'loading' });
  const [retryCount, setRetryCount] = useState(0);

  const renderDiagram = useCallback(async () => {
    // Validate inputs - TypeScript ensures these checks happen
    if (!code || !code.trim()) {
      setRenderState({
        status: 'error',
        message: 'No diagram code provided',
        code: ''
      });
      return;
    }

    if (!containerRef.current) {
      setRenderState({
        status: 'error',
        message: 'Container element not found',
        code
      });
      return;
    }

    setRenderState({ status: 'loading' });

    try {
      // Sanitize the code
      const sanitizedCode = sanitizeMermaidCode(code);

      // Generate unique ID for this render
      const rendererId = `mermaid-${id}-${Date.now()}`;

      // Render the diagram
      const { svg } = await mermaid.render(rendererId, sanitizedCode);

      setRenderState({ status: 'success', svg });
      onRenderSuccess?.();

    } catch (err) {
      // TypeScript forces us to handle the error properly
      const error = err instanceof Error ? err : new Error(String(err));
      const errorMessage = extractMermaidError(error);

      console.error(`[MermaidDiagram] Render failed for ${id}:`, errorMessage);

      setRenderState({
        status: 'error',
        message: errorMessage,
        code
      });

      onRenderError?.(error);
    }
  }, [id, code, onRenderSuccess, onRenderError]);

  // Render on mount and when code changes
  useEffect(() => {
    renderDiagram();
  }, [renderDiagram, retryCount]);

  const handleRetry = () => {
    setRetryCount(prev => prev + 1);
  };

  // Loading state
  if (renderState.status === 'loading') {
    return (
      <div className="flex items-center justify-center h-32 bg-bg-tertiary rounded-lg">
        <div className="flex items-center gap-2 text-text-secondary">
          <span className="animate-spin text-lg">⏳</span>
          <span>Lade {type}...</span>
        </div>
      </div>
    );
  }

  // Error state - EXPLICIT, not silent!
  if (renderState.status === 'error') {
    return (
      <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-medium text-red-400 flex items-center gap-2">
            <span>❌</span>
            Render-Fehler
          </span>
          <button
            onClick={handleRetry}
            className="px-2 py-1 text-xs bg-red-500/20 hover:bg-red-500/30
                       border border-red-500/50 rounded transition-colors"
          >
            🔄 Retry
          </button>
        </div>
        <pre className="text-sm text-red-300 overflow-auto max-h-24 mb-2">
          {renderState.message}
        </pre>
        <details className="text-xs text-text-secondary">
          <summary className="cursor-pointer hover:text-text-primary">
            Code anzeigen
          </summary>
          <pre className="mt-2 p-2 bg-bg-primary rounded overflow-auto max-h-32">
            {renderState.code}
          </pre>
        </details>
      </div>
    );
  }

  // Success state
  return (
    <div
      ref={containerRef}
      className="mermaid-container bg-white rounded-lg p-2 overflow-auto"
      dangerouslySetInnerHTML={{ __html: renderState.svg }}
    />
  );
}

/**
 * Sanitize mermaid code to fix common issues
 */
function sanitizeMermaidCode(code: string): string {
  let sanitized = code.trim();

  // Remove HTML comments
  sanitized = sanitized.replace(/<!--[\s\S]*?-->/g, '');

  // Fix common bracket issues
  const openBrackets = (sanitized.match(/\{/g) || []).length;
  const closeBrackets = (sanitized.match(/\}/g) || []).length;
  if (openBrackets > closeBrackets) {
    sanitized += '}'.repeat(openBrackets - closeBrackets);
  }

  // Ensure diagram type declaration exists
  const diagramTypes = ['flowchart', 'graph', 'sequenceDiagram', 'classDiagram',
                        'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'C4'];
  const hasType = diagramTypes.some(t =>
    sanitized.toLowerCase().startsWith(t.toLowerCase())
  );

  if (!hasType) {
    // Default to flowchart if no type specified
    sanitized = `flowchart TD\n${sanitized}`;
  }

  return sanitized;
}

/**
 * Extract readable error message from mermaid error
 */
function extractMermaidError(error: Error): string {
  const message = error.message || String(error);

  // Parse common mermaid errors
  if (message.includes('Syntax error')) {
    const match = message.match(/Syntax error in .* at line (\d+)/);
    if (match) {
      return `Syntax-Fehler in Zeile ${match[1]}`;
    }
  }

  if (message.includes('Parse error')) {
    return 'Mermaid Parse-Fehler: Ungültige Diagramm-Syntax';
  }

  if (message.includes('Unknown diagram type')) {
    return 'Unbekannter Diagramm-Typ';
  }

  // Return first 200 chars of message
  return message.length > 200 ? message.slice(0, 200) + '...' : message;
}

export default MermaidDiagram;
