/**
 * NodeCard Component
 *
 * Renders a single node on the canvas.
 * Supports dragging and selection.
 */

import { useRef, useState, useCallback } from 'react';
import { useAppStore } from '../store/appStore';
import type { CanvasNode, NodeType } from '../types';

// Node type styling
const nodeTypeStyles: Record<NodeType, { bg: string; border: string; icon: string }> = {
  requirement: { bg: 'bg-blue-900/30', border: 'border-blue-500', icon: '📋' },
  epic: { bg: 'bg-purple-900/30', border: 'border-purple-500', icon: '🎯' },
  'user-story': { bg: 'bg-green-900/30', border: 'border-green-500', icon: '📖' },
  diagram: { bg: 'bg-yellow-900/30', border: 'border-yellow-500', icon: '📊' },
  test: { bg: 'bg-red-900/30', border: 'border-red-500', icon: '🧪' },
  api: { bg: 'bg-orange-900/30', border: 'border-orange-500', icon: '🔌' },
  component: { bg: 'bg-lime-900/30', border: 'border-lime-500', icon: '🧩' },
  screen: { bg: 'bg-violet-900/30', border: 'border-violet-500', icon: '📱' },
  persona: { bg: 'bg-amber-900/30', border: 'border-amber-500', icon: '👤' },
  'user-flow': { bg: 'bg-pink-900/30', border: 'border-pink-500', icon: '🔄' },
  task: { bg: 'bg-cyan-900/30', border: 'border-cyan-500', icon: '✅' },
  'tech-stack': { bg: 'bg-teal-900/30', border: 'border-teal-500', icon: '🛠️' }
};

interface NodeCardProps {
  node: CanvasNode;
  isSelected: boolean;
}

export function NodeCard({ node, isSelected }: NodeCardProps) {
  const { selectNode, updateNodePosition } = useAppStore();
  const nodeRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  const style = nodeTypeStyles[node.type] || nodeTypeStyles.requirement;

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return; // Only left click

    selectNode(node.id);
    setIsDragging(true);
    setDragOffset({
      x: e.clientX - node.x,
      y: e.clientY - node.y
    });

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newX = moveEvent.clientX - dragOffset.x;
      const newY = moveEvent.clientY - dragOffset.y;
      updateNodePosition(node.id, newX, newY);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [node.id, node.x, node.y, dragOffset, selectNode, updateNodePosition]);

  // Status badge
  const statusBadge = node.data.validation_status ? (
    <span className={`px-2 py-0.5 text-xs rounded-full ${
      node.data.validation_status === 'approved' ? 'bg-green-500/20 text-green-400' :
      node.data.validation_status === 'review' ? 'bg-yellow-500/20 text-yellow-400' :
      node.data.validation_status === 'rejected' ? 'bg-red-500/20 text-red-400' :
      'bg-gray-500/20 text-gray-400'
    }`}>
      {node.data.validation_status}
    </span>
  ) : null;

  return (
    <div
      ref={nodeRef}
      className={`
        absolute rounded-lg border-2 shadow-lg cursor-move
        transition-shadow duration-200
        ${style.bg} ${style.border}
        ${isSelected ? 'ring-2 ring-accent-blue shadow-xl' : ''}
        ${isDragging ? 'opacity-90' : ''}
      `}
      style={{
        left: node.x,
        top: node.y,
        width: node.width,
        minHeight: 120
      }}
      onMouseDown={handleMouseDown}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10">
        <span className="text-lg">{style.icon}</span>
        <span className="text-xs text-text-secondary font-mono">
          {node.data.requirement_id || node.id}
        </span>
        {statusBadge}
      </div>

      {/* Title / Content */}
      <div className="px-3 py-2">
        {node.type === 'diagram' ? (
          <>
            <h3 className="font-medium text-sm leading-tight">
              {node.data.diagram_type?.toUpperCase() || 'Diagram'}
            </h3>
            <div className="mt-2 text-xs text-text-secondary">
              <span className="inline-block px-2 py-1 bg-bg-tertiary rounded">
                📊 {node.data.diagram_type || 'chart'}
              </span>
              {node.data.parent_requirement && (
                <span className="ml-2 opacity-70">
                  → {node.data.parent_requirement.split('-').slice(-1)[0]}
                </span>
              )}
            </div>
            {node.data.mermaid_code && (
              <div className="mt-2 text-xs text-text-secondary font-mono bg-bg-tertiary p-1 rounded overflow-hidden max-h-12">
                {node.data.mermaid_code.substring(0, 50)}...
              </div>
            )}
          </>
        ) : (
          <>
            <h3 className="font-medium text-sm leading-tight">
              {node.data.title || 'Untitled'}
            </h3>
            {node.data.description && (
              <p className="mt-1 text-xs text-text-secondary line-clamp-2">
                {node.data.description}
              </p>
            )}
          </>
        )}
      </div>

      {/* Footer / Scores */}
      {(node.data.completeness_score !== undefined || node.data.testability_score !== undefined) && (
        <div className="px-3 py-2 border-t border-white/10 flex gap-2 text-xs">
          {node.data.completeness_score !== undefined && (
            <span className="text-text-secondary">
              Vollst.: {Math.round(node.data.completeness_score * 100)}%
            </span>
          )}
          {node.data.testability_score !== undefined && (
            <span className="text-text-secondary">
              Test.: {Math.round(node.data.testability_score * 100)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
