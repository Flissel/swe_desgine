/**
 * Canvas Component
 *
 * Main canvas area for displaying and interacting with nodes.
 * Supports:
 * - Pan and zoom
 * - Node rendering
 * - Connection lines (SVG)
 */

import { useRef, useState, useCallback, useEffect } from 'react';
import { useAppStore, useNodes, useConnections, useZoom, useSelectedNodeId } from '../store/appStore';
import { NodeCard } from './NodeCard';
import type { Connection } from '../types';

export function Canvas() {
  const nodes = useNodes();
  const connections = useConnections();
  const zoom = useZoom();
  const selectedNodeId = useSelectedNodeId();
  const { selectNode, setZoom } = useAppStore();

  const canvasRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Handle canvas click to deselect
  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    if (e.target === canvasRef.current) {
      selectNode(null);
    }
  }, [selectNode]);

  // Handle panning
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Only pan with middle mouse button or if clicking on canvas background
    if (e.button === 1 || (e.button === 0 && e.target === canvasRef.current)) {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  }, [pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isPanning) {
      setPan({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  }, [isPanning, panStart]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Handle zoom with mouse wheel
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      setZoom(Math.max(0.25, Math.min(2, zoom + delta)));
    }
  }, [zoom, setZoom]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        selectNode(null);
      }
      // Reset view with Home key
      if (e.key === 'Home') {
        setPan({ x: 0, y: 0 });
        setZoom(1);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectNode, setZoom]);

  const nodeArray = Object.values(nodes);

  return (
    <div
      ref={canvasRef}
      className="flex-1 relative overflow-hidden bg-bg-primary cursor-grab"
      style={{ cursor: isPanning ? 'grabbing' : 'grab' }}
      onClick={handleCanvasClick}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    >
      {/* Grid Background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)
          `,
          backgroundSize: `${50 * zoom}px ${50 * zoom}px`,
          backgroundPosition: `${pan.x}px ${pan.y}px`
        }}
      />

      {/* Transform container for pan and zoom */}
      <div
        className="absolute inset-0"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: '0 0'
        }}
      >
        {/* Connection Lines (SVG Layer) */}
        <svg
          className="absolute inset-0 pointer-events-none"
          style={{ width: '100%', height: '100%', overflow: 'visible' }}
        >
          <defs>
            {/* Arrow marker for connections */}
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon
                points="0 0, 10 3.5, 0 7"
                fill="rgba(88, 166, 255, 0.6)"
              />
            </marker>
          </defs>

          {connections.map((conn) => (
            <ConnectionLine
              key={conn.id}
              connection={conn}
              nodes={nodes}
            />
          ))}
        </svg>

        {/* Node Cards */}
        {nodeArray.map((node) => (
          <NodeCard
            key={node.id}
            node={node}
            isSelected={node.id === selectedNodeId}
          />
        ))}
      </div>

      {/* Empty State */}
      {nodeArray.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-text-secondary">
            <div className="text-4xl mb-4">📂</div>
            <div className="text-lg">Kein Projekt geladen</div>
            <div className="text-sm mt-2">
              Wähle ein Projekt in der Sidebar aus
            </div>
          </div>
        </div>
      )}

      {/* Zoom indicator */}
      <div className="absolute bottom-4 right-4 text-xs text-text-secondary bg-bg-secondary px-2 py-1 rounded">
        {Math.round(zoom * 100)}% | Pan: {Math.round(pan.x)}, {Math.round(pan.y)}
      </div>

      {/* Help tooltip */}
      <div className="absolute bottom-4 left-4 text-xs text-text-secondary bg-bg-secondary px-2 py-1 rounded">
        Ctrl+Scroll: Zoom | Drag: Pan | Home: Reset | Esc: Deselect
      </div>
    </div>
  );
}

/**
 * Connection line component
 */
interface ConnectionLineProps {
  connection: Connection;
  nodes: Record<string, { x: number; y: number; width: number; height: number }>;
}

function ConnectionLine({ connection, nodes }: ConnectionLineProps) {
  const fromNode = nodes[connection.from];
  const toNode = nodes[connection.to];

  // TypeScript ensures we check for undefined nodes!
  if (!fromNode || !toNode) {
    console.warn(`[ConnectionLine] Missing node: from=${connection.from}, to=${connection.to}`);
    return null;
  }

  // Calculate connection points (center of nodes)
  const fromX = fromNode.x + (fromNode.width || 350) / 2;
  const fromY = fromNode.y + (fromNode.height || 200) / 2;
  const toX = toNode.x + (toNode.width || 350) / 2;
  const toY = toNode.y + (toNode.height || 200) / 2;

  // Calculate control points for bezier curve
  const dx = toX - fromX;
  const dy = toY - fromY;
  const controlOffset = Math.min(Math.abs(dx), Math.abs(dy), 100);

  // Determine connection color based on type
  const strokeColor = connection.type === 'dependency'
    ? 'rgba(255, 165, 0, 0.6)'  // Orange for dependencies
    : connection.type === 'parent'
    ? 'rgba(138, 43, 226, 0.6)' // Purple for parent
    : 'rgba(88, 166, 255, 0.6)'; // Blue for trace

  return (
    <path
      d={`M ${fromX} ${fromY}
          C ${fromX + controlOffset} ${fromY},
            ${toX - controlOffset} ${toY},
            ${toX} ${toY}`}
      fill="none"
      stroke={strokeColor}
      strokeWidth="2"
      strokeDasharray={connection.type === 'dependency' ? '5,5' : undefined}
      markerEnd="url(#arrowhead)"
    />
  );
}

export default Canvas;
