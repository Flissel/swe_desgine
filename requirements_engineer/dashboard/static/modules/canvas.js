/**
 * RE System Dashboard - Canvas Module
 *
 * Pan, Zoom, and Edge Navigation functionality
 */

import { state, elements } from './state.js';

// ============================================
// Edge-Based Navigation State
// ============================================

let edgeNavState = {
    active: false,
    direction: { x: 0, y: 0 },
    animationId: null
};

// ============================================
// Edge Navigation
// ============================================

export function initEdgeNavigation(updateMinimapFn) {
    const edgeThreshold = 60;
    const panSpeed = 15;

    document.addEventListener('mousemove', (e) => {
        if (state.dragging.active) {
            stopEdgePan();
            return;
        }

        const rect = elements.canvasContainer.getBoundingClientRect();
        const x = e.clientX;
        const y = e.clientY;

        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            stopEdgePan();
            return;
        }

        let dirX = 0, dirY = 0;

        if (x - rect.left < edgeThreshold) {
            dirX = panSpeed * (1 - (x - rect.left) / edgeThreshold);
        } else if (rect.right - x < edgeThreshold) {
            dirX = -panSpeed * (1 - (rect.right - x) / edgeThreshold);
        }

        if (y - rect.top < edgeThreshold) {
            dirY = panSpeed * (1 - (y - rect.top) / edgeThreshold);
        } else if (rect.bottom - y < edgeThreshold) {
            dirY = -panSpeed * (1 - (rect.bottom - y) / edgeThreshold);
        }

        if (dirX !== 0 || dirY !== 0) {
            edgeNavState.direction = { x: dirX, y: dirY };
            if (!edgeNavState.active) {
                startEdgePan(updateMinimapFn);
            }
        } else {
            stopEdgePan();
        }
    });

    document.addEventListener('mouseleave', stopEdgePan);
}

function startEdgePan(updateMinimapFn) {
    if (edgeNavState.active) return;
    edgeNavState.active = true;

    function panFrame() {
        if (!edgeNavState.active) return;

        state.canvas.x += edgeNavState.direction.x;
        state.canvas.y += edgeNavState.direction.y;
        updateCanvasTransform();
        if (updateMinimapFn) updateMinimapFn();

        edgeNavState.animationId = requestAnimationFrame(panFrame);
    }

    edgeNavState.animationId = requestAnimationFrame(panFrame);
}

function stopEdgePan() {
    edgeNavState.active = false;
    edgeNavState.direction = { x: 0, y: 0 };
    if (edgeNavState.animationId) {
        cancelAnimationFrame(edgeNavState.animationId);
        edgeNavState.animationId = null;
    }
}

// ============================================
// Canvas Pan & Zoom
// ============================================

export function onCanvasMouseDown(e) {
    if (e.target === elements.canvasContainer || e.target.id === 'canvas-grid') {
        state.panning.active = true;
        state.panning.startX = e.clientX;
        state.panning.startY = e.clientY;
        state.panning.canvasStartX = state.canvas.x;
        state.panning.canvasStartY = state.canvas.y;
        elements.canvas.style.cursor = 'grabbing';
    }
}

export function onCanvasMouseMove(e, updateConnectionsFn, updateMinimapFn) {
    if (state.panning.active) {
        const dx = e.clientX - state.panning.startX;
        const dy = e.clientY - state.panning.startY;
        state.canvas.x = state.panning.canvasStartX + dx;
        state.canvas.y = state.panning.canvasStartY + dy;
        updateCanvasTransform();
        if (updateMinimapFn) updateMinimapFn();
    }

    if (state.dragging.active && state.dragging.node) {
        const dx = (e.clientX - state.dragging.startX) / state.canvas.zoom;
        const dy = (e.clientY - state.dragging.startY) / state.canvas.zoom;
        const newX = state.dragging.nodeStartX + dx;
        const newY = state.dragging.nodeStartY + dy;

        state.dragging.node.style.left = `${newX}px`;
        state.dragging.node.style.top = `${newY}px`;

        if (updateConnectionsFn) updateConnectionsFn();
    }
}

export function onCanvasMouseUp(e, sendMessageFn) {
    if (state.panning.active) {
        state.panning.active = false;
        elements.canvas.style.cursor = 'grab';
    }

    if (state.dragging.active && state.dragging.node) {
        state.dragging.node.classList.remove('dragging');

        const nodeId = state.dragging.node.dataset.nodeId;
        const x = parseFloat(state.dragging.node.style.left);
        const y = parseFloat(state.dragging.node.style.top);

        if (state.nodes[nodeId]) {
            state.nodes[nodeId].x = x;
            state.nodes[nodeId].y = y;
        }

        if (sendMessageFn) {
            sendMessageFn({
                type: 'update_node_position',
                node_id: nodeId,
                x: x,
                y: y
            });
        }

        state.dragging.active = false;
        state.dragging.node = null;
    }
}

export function onCanvasWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;

    const rect = elements.canvasContainer.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    zoomTowards(delta, mouseX, mouseY);
}

export function zoom(delta) {
    const rect = elements.canvasContainer.getBoundingClientRect();
    zoomTowards(delta, rect.width / 2, rect.height / 2);
}

export function zoomTowards(delta, targetX, targetY, updateMinimapFn) {
    const oldZoom = state.canvas.zoom;
    const newZoom = Math.min(state.canvas.maxZoom, Math.max(state.canvas.minZoom, oldZoom + delta));

    if (newZoom !== oldZoom) {
        const worldX = (targetX - state.canvas.x) / oldZoom;
        const worldY = (targetY - state.canvas.y) / oldZoom;

        state.canvas.zoom = newZoom;
        state.canvas.x = targetX - worldX * newZoom;
        state.canvas.y = targetY - worldY * newZoom;

        updateCanvasTransform();
        if (updateMinimapFn) updateMinimapFn();
    }
}

export function updateCanvasTransform() {
    elements.canvas.style.transform = `translate(${state.canvas.x}px, ${state.canvas.y}px) scale(${state.canvas.zoom})`;
    if (elements.zoomLevel) {
        elements.zoomLevel.textContent = `${Math.round(state.canvas.zoom * 100)}%`;
    }
}

export function resetView(updateMinimapFn) {
    state.canvas.zoom = 0.8;
    const containerRect = elements.canvasContainer.getBoundingClientRect();
    state.canvas.x = -3000 + containerRect.width / 2;
    state.canvas.y = -3000 + containerRect.height / 2;
    updateCanvasTransform();
    if (updateMinimapFn) updateMinimapFn();
}

export function fitToView(updateMinimapFn) {
    const nodeElements = elements.canvasNodes.querySelectorAll('.canvas-node');
    if (nodeElements.length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    nodeElements.forEach(node => {
        const x = parseFloat(node.style.left) || 0;
        const y = parseFloat(node.style.top) || 0;
        const w = node.offsetWidth;
        const h = node.offsetHeight;

        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x + w);
        maxY = Math.max(maxY, y + h);
    });

    const padding = 100;
    const contentWidth = maxX - minX + padding * 2;
    const contentHeight = maxY - minY + padding * 2;

    const containerRect = elements.canvasContainer.getBoundingClientRect();
    const zoomX = containerRect.width / contentWidth;
    const zoomY = containerRect.height / contentHeight;

    state.canvas.zoom = Math.min(1.5, Math.max(0.2, Math.min(zoomX, zoomY)));
    state.canvas.x = -minX * state.canvas.zoom + padding * state.canvas.zoom + (containerRect.width - contentWidth * state.canvas.zoom) / 2;
    state.canvas.y = -minY * state.canvas.zoom + padding * state.canvas.zoom + (containerRect.height - contentHeight * state.canvas.zoom) / 2;

    updateCanvasTransform();
    if (updateMinimapFn) updateMinimapFn();
}
