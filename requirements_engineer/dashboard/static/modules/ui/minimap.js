/**
 * RE System Dashboard - Minimap Module
 *
 * Handles minimap rendering and viewport indicator.
 */

import { state, elements } from '../state.js';

// ============================================
// Minimap Cache
// ============================================

// Cache for minimap dot elements - reuse instead of recreate
const minimapDots = new Map();

// RAF throttling for minimap updates
let minimapUpdateScheduled = false;

// ============================================
// Minimap Updates
// ============================================

/**
 * Schedule a minimap update using requestAnimationFrame for performance.
 * This prevents blocking the main thread during rapid updates (drag/pan).
 */
export function updateMinimap() {
    if (minimapUpdateScheduled) return;
    minimapUpdateScheduled = true;

    requestAnimationFrame(() => {
        updateMinimapInternal();
        minimapUpdateScheduled = false;
    });
}

/**
 * Internal minimap update - does the actual rendering work.
 */
function updateMinimapInternal() {
    if (!elements.minimapContent) return;

    // Only show VISIBLE nodes (not hidden in collapsed groups)
    const visibleNodes = Object.entries(state.nodes).filter(([id, node]) => {
        // Node must have position
        if (node.x === undefined || node.y === undefined) return false;
        // Node must be visible (not hidden by collapsed group)
        if (node.element && node.element.style.display === 'none') return false;
        return true;
    });

    if (visibleNodes.length === 0) {
        // Clear all dots if no visible nodes
        minimapDots.forEach(dot => dot.remove());
        minimapDots.clear();
        return;
    }

    // Calculate bounding box of visible nodes only
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    visibleNodes.forEach(([id, node]) => {
        minX = Math.min(minX, node.x);
        minY = Math.min(minY, node.y);
        maxX = Math.max(maxX, node.x + 300);  // Approximate node width
        maxY = Math.max(maxY, node.y + 200);  // Approximate node height
    });

    // Minimap dimensions (from CSS)
    const minimapWidth = 200;
    const minimapHeight = 150;
    const padding = 10;

    // Calculate scale to fit all nodes in minimap
    const contentWidth = maxX - minX;
    const contentHeight = maxY - minY;
    const scaleX = (minimapWidth - 2 * padding) / contentWidth;
    const scaleY = (minimapHeight - 2 * padding) / contentHeight;
    const scale = Math.min(scaleX, scaleY, 0.05);  // Cap scale to prevent too large dots

    // Track which node IDs are visible
    const visibleNodeIds = new Set(visibleNodes.map(([id]) => id));

    // Update or create dots for visible nodes only
    visibleNodes.forEach(([nodeId, node]) => {
        let dot = minimapDots.get(nodeId);

        if (!dot) {
            dot = document.createElement('div');
            dot.className = 'minimap-node';
            dot.style.width = '3px';
            dot.style.height = '3px';
            elements.minimapContent.appendChild(dot);
            minimapDots.set(nodeId, dot);
        }

        // Position relative to bounding box
        const dotX = (node.x - minX) * scale + padding;
        const dotY = (node.y - minY) * scale + padding;
        dot.style.left = `${dotX}px`;
        dot.style.top = `${dotY}px`;
    });

    // Remove dots for hidden/deleted nodes
    minimapDots.forEach((dot, nodeId) => {
        if (!visibleNodeIds.has(nodeId)) {
            dot.remove();
            minimapDots.delete(nodeId);
        }
    });

    // Update viewport indicator
    if (elements.canvasContainer && elements.minimapViewport) {
        const containerRect = elements.canvasContainer.getBoundingClientRect();
        const viewportWidth = containerRect.width / state.canvas.zoom * scale;
        const viewportHeight = containerRect.height / state.canvas.zoom * scale;
        const viewX = -state.canvas.x / state.canvas.zoom;
        const viewY = -state.canvas.y / state.canvas.zoom;
        const viewportX = (viewX - minX) * scale + padding;
        const viewportY = (viewY - minY) * scale + padding;

        elements.minimapViewport.style.left = `${viewportX}px`;
        elements.minimapViewport.style.top = `${viewportY}px`;
        elements.minimapViewport.style.width = `${viewportWidth}px`;
        elements.minimapViewport.style.height = `${viewportHeight}px`;
    }
}

/**
 * Clear all minimap dots
 */
export function clearMinimap() {
    minimapDots.forEach(dot => dot.remove());
    minimapDots.clear();
}

/**
 * Get minimap statistics
 * @returns {Object} Stats about minimap state
 */
export function getMinimapStats() {
    return {
        dotCount: minimapDots.size,
        nodeCount: Object.keys(state.nodes).length
    };
}
