/**
 * RE System Dashboard - Connections Module
 *
 * Connection rendering, path routing, and arrow markers
 */

import { state, elements } from './state.js';
import { findNodeGroup, isGroupCollapsed, detectNodeGroups, getParentIdFromDiagramId } from './layouts/grouping.js';

// ============================================
// Module State
// ============================================

let connectionUpdateScheduled = false;
let connectionUpdateTimeout = null;
let resizeObserver = null;
let observedNodes = new Set();

// Edge padding for variable card widths (280-380px)
const EDGE_PADDING = 4;

// ============================================
// Performance: Drag Optimization
// ============================================

// Track which node is being dragged for partial updates
let currentDragNodeId = null;

// Cache for SVG path elements: connectionKey -> { path: SVGElement, d: string }
const connectionPathCache = new Map();

/**
 * Set the currently dragged node ID for optimized partial updates.
 * Call with null when drag ends.
 */
export function setDragNode(nodeId) {
    currentDragNodeId = nodeId;
}

/**
 * Clear the drag node and trigger a full refresh.
 */
export function clearDragNode() {
    currentDragNodeId = null;
}

// Layout reference (set by app.js after layout module loads)
let layoutConfig = {
    currentLayout: 'BY_PACKAGE',
    LAYOUT_MODES: { BY_HIERARCHY: 'BY_HIERARCHY' },
    renderClusterBackgrounds: () => {}
};

/**
 * Set layout configuration reference
 */
export function setLayoutConfig(config) {
    layoutConfig = { ...layoutConfig, ...config };
}

// Cache for detected groups (refreshed on each connection update)
let cachedGroups = null;

/**
 * Find the group element for a node that might be hidden in a collapsed group.
 * Returns the group element if the node is collapsed in a group, or null otherwise.
 * @param {string} nodeId - Node ID to check
 * @returns {HTMLElement|null} Group element or null
 */
function findGroupElementForNode(nodeId) {
    if (!cachedGroups) return null;

    // Check if this node is in a collapsed group
    const groupKey = findNodeGroup(nodeId, cachedGroups);
    if (!groupKey) return null;

    // Check if the group is collapsed
    if (!isGroupCollapsed(groupKey, cachedGroups)) return null;

    // Find the group node element
    const groupElement = document.querySelector(`[data-group-id="${groupKey}"]`);
    return groupElement;
}

/**
 * Get bounds for a node, considering group nodes for hidden nodes.
 * If the node is hidden in a collapsed group, returns the group's bounds.
 * @param {string} nodeId - Node ID
 * @param {Object} node - Node data from state.nodes
 * @returns {Object|null} Bounds object or null
 */
function getNodeBoundsWithGroupFallback(nodeId, node) {
    if (!node || !node.element) return null;

    const el = node.element;

    // Check if element is hidden (display: none)
    const isHidden = el.style.display === 'none' || el.offsetWidth === 0;

    if (isHidden) {
        // Try to find a group element for this node
        const groupEl = findGroupElementForNode(nodeId);
        if (groupEl && groupEl.offsetWidth > 0) {
            return {
                left: parseFloat(groupEl.style.left) || 0,
                top: parseFloat(groupEl.style.top) || 0,
                right: (parseFloat(groupEl.style.left) || 0) + groupEl.offsetWidth,
                bottom: (parseFloat(groupEl.style.top) || 0) + groupEl.offsetHeight,
                centerX: (parseFloat(groupEl.style.left) || 0) + groupEl.offsetWidth / 2,
                centerY: (parseFloat(groupEl.style.top) || 0) + groupEl.offsetHeight / 2,
                isGroupNode: true
            };
        }
        // Node is hidden but no group found - skip this connection
        return null;
    }

    // Node is visible, use its bounds directly
    return {
        left: parseFloat(el.style.left),
        top: parseFloat(el.style.top),
        right: parseFloat(el.style.left) + el.offsetWidth,
        bottom: parseFloat(el.style.top) + el.offsetHeight,
        centerX: parseFloat(el.style.left) + el.offsetWidth / 2,
        centerY: parseFloat(el.style.top) + el.offsetHeight / 2,
        isGroupNode: false
    };
}

/**
 * Initialize ResizeObserver for dynamic node size changes
 */
function initResizeObserver() {
    if (resizeObserver) return;

    resizeObserver = new ResizeObserver((entries) => {
        // Schedule update when any node resizes
        scheduleConnectionUpdateDebounced(100);
    });
}

/**
 * Observe a node element for size changes
 */
export function observeNodeResize(element) {
    if (!element) return;
    initResizeObserver();

    if (!observedNodes.has(element)) {
        resizeObserver.observe(element);
        observedNodes.add(element);
    }
}

/**
 * Stop observing a node element
 */
export function unobserveNodeResize(element) {
    if (!element || !resizeObserver) return;
    resizeObserver.unobserve(element);
    observedNodes.delete(element);
}

/**
 * CRASH FIX: Pause ResizeObserver to prevent cascading updates during modal rendering
 * Call this when opening modals with large SVG content
 */
export function pauseResizeObserver() {
    if (resizeObserver) {
        console.log('[Connections] Pausing ResizeObserver');
        resizeObserver.disconnect();
    }
}

/**
 * CRASH FIX: Resume ResizeObserver after modal closes
 * Re-observes all previously tracked nodes
 */
export function resumeResizeObserver() {
    if (resizeObserver && observedNodes.size > 0) {
        console.log('[Connections] Resuming ResizeObserver for', observedNodes.size, 'nodes');
        observedNodes.forEach(node => {
            try {
                resizeObserver.observe(node);
            } catch (e) {
                // Node may no longer exist
                observedNodes.delete(node);
            }
        });
    }
}

// ============================================
// Connection Management
// ============================================

export function addConnection(fromId, toId, relationType = 'default') {
    const exists = state.connections.some(c => c.from === fromId && c.to === toId);
    if (exists) return;
    state.connections.push({ from: fromId, to: toId, type: relationType });
}

/**
 * Schedule a batched connection update using requestAnimationFrame.
 */
export function scheduleConnectionUpdate() {
    if (connectionUpdateScheduled) return;
    connectionUpdateScheduled = true;

    requestAnimationFrame(() => {
        updateConnectionsInternal();
        connectionUpdateScheduled = false;
    });
}

/**
 * Debounced version for rapid updates (e.g., during drag, resize).
 * @param {number} delay - Delay in ms (default: 16ms for 60fps)
 */
export function scheduleConnectionUpdateDebounced(delay = 16) {
    if (connectionUpdateTimeout) {
        clearTimeout(connectionUpdateTimeout);
    }
    connectionUpdateTimeout = setTimeout(() => {
        updateConnectionsInternal();
        connectionUpdateTimeout = null;
    }, delay);
}

/**
 * Update connections - uses RAF scheduling by default for performance.
 * @param {boolean} immediate - If true, update immediately (for final state, not during drag)
 */
export function updateConnections(immediate = false) {
    if (immediate) {
        updateConnectionsInternal();
    } else {
        scheduleConnectionUpdate();
    }
}

// ============================================
// Path Routing
// ============================================

/**
 * Route an orthogonal path from start to end.
 * @param {boolean} forceHorizontalFirst - If true, always use horizontal-first L-path (for cross-column connections)
 */
function routeOrthogonalPath(startX, startY, endX, endY, fromBounds, toBounds, nodeBounds, fromId, toId, offset, forceHorizontalFirst = false) {
    const channelOffset = offset || 0;
    const isNearlyHorizontal = Math.abs(endY - startY) < 30;
    const isNearlyVertical = Math.abs(endX - startX) < 30;
    const dx = Math.abs(endX - startX);
    const dy = Math.abs(endY - startY);

    // For tree layout (hierarchical): ALWAYS use L-path regardless of angle
    // This check must come FIRST to ensure hierarchical layout works correctly
    if (layoutConfig.currentLayout === layoutConfig.LAYOUT_MODES.BY_HIERARCHY) {
        const bendX = startX + 40 + channelOffset;
        return `M ${startX} ${startY} L ${bendX} ${startY} L ${bendX} ${endY} L ${endX} ${endY}`;
    }

    // For other layouts: use simple straight paths for nearly-aligned connections
    if (isNearlyHorizontal || isNearlyVertical) {
        return `M ${startX} ${startY} L ${endX} ${endY}`;
    }

    // For Matrix/Package layouts: Use simple L-path (shortest route)
    // Force horizontal-first for cross-column connections (req→diagram, etc.)
    if (forceHorizontalFirst || dx >= dy) {
        // Horizontal-first L-path: go right/left first, then vertical
        return `M ${startX} ${startY} L ${endX} ${startY} L ${endX} ${endY}`;
    } else {
        // Vertical-first L-path: go down/up first, then horizontal
        return `M ${startX} ${startY} L ${startX} ${endY} L ${endX} ${endY}`;
    }
}

// ============================================
// Connection Rendering
// ============================================

function updateConnectionsInternal() {
    // OPTIMIZATION: During drag, only update paths involving the dragged node
    if (currentDragNodeId && connectionPathCache.size > 0) {
        updateDraggedNodeConnections();
        return;
    }

    // Full update: clear cache and rebuild
    connectionPathCache.clear();
    elements.connectionsLayer.innerHTML = '';

    // Detect node groups for collapsed group handling
    cachedGroups = detectNodeGroups();

    // Render cluster backgrounds if available
    if (layoutConfig.renderClusterBackgrounds) {
        layoutConfig.renderClusterBackgrounds();
    }

    const connectionColors = {
        'epic-story': '#7856ff',
        'epic-req': '#9333ea',
        'req-story': '#1d9bf0',
        'story-test': '#00ba7c',
        'req-diagram': '#ffd400',
        'persona-story': '#f97316',
        'flow-screen': '#ec4899',
        'screen-component': '#84cc16',
        'story-screen': '#8b5cf6',
        'feature-task': '#f59e0b',
        // Phase 4: All link types with distinct colors
        'persona-screen': '#f97316',
        'req-api': '#ff7a00',
        'api-screen': '#8b5cf6',
        'comp-api': '#ff7a00',
        'test-api': '#f4212e',
        'api-entity': '#6366f1',
        'req-entity': '#6366f1',
        'screen-entity': '#84cc16',
        'entity-api': '#6366f1',
        'diagram-entity': '#ffd400',
        'tech-comp': '#06b6d4',
        'feature-story': '#10b981',
        'default': '#536471'
    };

    // Collect all node bounding boxes
    const nodeBounds = [];
    Object.values(state.nodes).forEach(node => {
        if (node.element) {
            const el = node.element;
            nodeBounds.push({
                left: parseFloat(el.style.left) || 0,
                top: parseFloat(el.style.top) || 0,
                right: (parseFloat(el.style.left) || 0) + el.offsetWidth,
                bottom: (parseFloat(el.style.top) || 0) + el.offsetHeight,
                id: el.dataset.nodeId
            });
        }
    });

    const connectionGroups = groupConnectionsByPath();

    // Detect requirement stacks (multiple reqs -> same user story)
    const requirementStacks = detectRequirementStacks();
    const stackedConnections = new Set();  // Track which connections are stacked
    const renderedStacks = new Set();      // Track which stacks we've already rendered

    // Mark connections that are part of a stack
    Object.entries(requirementStacks).forEach(([storyId, reqIds]) => {
        reqIds.forEach(reqId => {
            stackedConnections.add(`${reqId}|${storyId}`);
        });
    });

    // Detect diagram stacks (multiple diagrams <- same requirement)
    const diagramStacks = detectDiagramStacks();
    const stackedDiagramConnections = new Set();  // Track which diagram connections are stacked
    const renderedDiagramStacks = new Set();      // Track which diagram stacks we've rendered

    // Mark connections that are part of a diagram stack
    Object.entries(diagramStacks).forEach(([reqId, diagramIds]) => {
        diagramIds.forEach(diagId => {
            stackedDiagramConnections.add(`${reqId}|${diagId}`);
        });
    });

    let pathsCreated = 0;
    let pathsFailed = 0;
    let stacksRendered = 0;

    // Track rendered group connections to avoid duplicates
    // (e.g., REQ-001 → 6 diagrams should become 1 line to diagram group)
    const renderedGroupConnections = new Set();

    state.connections.forEach((conn, index) => {
        const fromNode = state.nodes[conn.from];
        const toNode = state.nodes[conn.to];

        if (fromNode && toNode && fromNode.element && toNode.element) {
            // Get bounds with group fallback for hidden nodes
            const fromBounds = getNodeBoundsWithGroupFallback(conn.from, fromNode);
            const toBounds = getNodeBoundsWithGroupFallback(conn.to, toNode);

            // Skip if either node is hidden without a group fallback
            if (!fromBounds || !toBounds) {
                return;
            }

            // Skip duplicate connections to same collapsed group
            // (e.g., REQ-001 has 6 diagram connections, but only 1 line to the group)
            if (toBounds.isGroupNode) {
                const toGroupKey = findNodeGroup(conn.to, cachedGroups);
                if (toGroupKey) {
                    const groupConnectionKey = `${conn.from}|${toGroupKey}`;
                    if (renderedGroupConnections.has(groupConnectionKey)) {
                        return; // Skip - already rendered connection to this group
                    }
                    renderedGroupConnections.add(groupConnectionKey);
                }
            }

            // Same for source node in collapsed group
            if (fromBounds.isGroupNode) {
                const fromGroupKey = findNodeGroup(conn.from, cachedGroups);
                if (fromGroupKey) {
                    const groupConnectionKey = `${fromGroupKey}|${conn.to}`;
                    if (renderedGroupConnections.has(groupConnectionKey)) {
                        return; // Skip - already rendered connection from this group
                    }
                    renderedGroupConnections.add(groupConnectionKey);
                }
            }

            // Check if this is a stacked requirement->user-story connection
            const isReqToStory = fromNode.type === 'requirement' && toNode.type === 'user-story';
            const stackKey = `${conn.from}|${conn.to}`;
            const isPartOfStack = stackedConnections.has(stackKey);

            if (isPartOfStack && isReqToStory) {
                // Check if we already rendered this stack
                if (renderedStacks.has(conn.to)) {
                    // Skip - already rendered as a stacked connection
                    return;
                }
                // Mark this stack as rendered
                renderedStacks.add(conn.to);
                stacksRendered++;
            }

            // Check if this is a stacked requirement->diagram connection
            const isReqToDiagram = fromNode.type === 'requirement' && toNode.type === 'diagram';
            const diagramStackKey = `${conn.from}|${conn.to}`;
            const isPartOfDiagramStack = stackedDiagramConnections.has(diagramStackKey);

            // Track diagram stack index for vertical offset
            let diagramStackIndex = 0;
            let diagramStackTotal = 1;

            if (isPartOfDiagramStack && isReqToDiagram) {
                // Check if we already rendered this diagram stack
                if (renderedDiagramStacks.has(conn.from)) {
                    // Skip - already rendered as a stacked diagram connection
                    return;
                }
                // Mark this diagram stack as rendered
                renderedDiagramStacks.add(conn.from);

                // Calculate index for vertical positioning of this stack's badge
                diagramStackIndex = renderedDiagramStacks.size - 1;
                diagramStackTotal = Object.keys(diagramStacks).length;
            }

            // For group nodes, use the group's parent ID as the key
            const effectiveFromId = fromBounds.isGroupNode ? getParentIdFromDiagramId(conn.from) || conn.from : conn.from;
            const effectiveToId = toBounds.isGroupNode ? getParentIdFromDiagramId(conn.to) || conn.to : conn.to;

            const groupKey = getConnectionGroupKey(effectiveFromId, effectiveToId);
            const groupConnections = connectionGroups[groupKey] || [];
            const groupIndex = groupConnections.indexOf(index);
            const groupSize = groupConnections.length;
            const offsetStep = 8;
            const offset = isPartOfStack ? 0 : (groupIndex * offsetStep - ((groupSize - 1) * offsetStep) / 2);

            const goingRight = toBounds.centerX > fromBounds.centerX;
            const goingDown = toBounds.centerY > fromBounds.centerY;
            const dx = Math.abs(toBounds.centerX - fromBounds.centerX);
            const dy = Math.abs(toBounds.centerY - fromBounds.centerY);

            let startX, startY, endX, endY;

            // Determine connection direction
            // For cross-column connections (req→diagram, req→story, epic→req, etc.), prefer horizontal
            const isCrossColumn = (fromNode.type === 'requirement' && toNode.type === 'diagram') ||
                                  (fromNode.type === 'requirement' && toNode.type === 'user-story') ||
                                  (fromNode.type === 'epic' && toNode.type === 'user-story') ||
                                  (fromNode.type === 'epic' && toNode.type === 'requirement') ||
                                  (fromNode.type === 'user-story' && toNode.type === 'test');

            // Use horizontal connection for cross-column or when horizontal distance is larger
            const useHorizontal = isCrossColumn || dx > dy || dx > 100;

            if (useHorizontal) {
                // Horizontal connection (left/right edges)
                if (goingRight) {
                    startX = fromBounds.right - EDGE_PADDING;
                    startY = fromBounds.centerY + offset;
                    endX = toBounds.left + EDGE_PADDING;
                    // For diagram connections: use SAME Y level as source for pure horizontal line
                    // This ensures each requirement's line goes straight to its diagram group
                    if (isReqToDiagram) {
                        endY = startY;  // Pure horizontal line
                    } else {
                        endY = toBounds.centerY + offset;
                    }
                } else {
                    startX = fromBounds.left + EDGE_PADDING;
                    startY = fromBounds.centerY + offset;
                    endX = toBounds.right - EDGE_PADDING;
                    if (isReqToDiagram) {
                        endY = startY;  // Pure horizontal line
                    } else {
                        endY = toBounds.centerY + offset;
                    }
                }
            } else {
                // Vertical connection (top/bottom edges) - only for same-column connections
                if (goingDown) {
                    startX = fromBounds.centerX + offset;
                    startY = fromBounds.bottom - EDGE_PADDING;
                    endX = toBounds.centerX + offset;
                    endY = toBounds.top + EDGE_PADDING;
                } else {
                    startX = fromBounds.centerX + offset;
                    startY = fromBounds.top + EDGE_PADDING;
                    endX = toBounds.centerX + offset;
                    endY = toBounds.bottom - EDGE_PADDING;
                }
            }

            let colorKey = 'default';
            if (fromNode.type === 'epic' && toNode.type === 'user-story') colorKey = 'epic-story';
            else if (fromNode.type === 'epic' && toNode.type === 'requirement') colorKey = 'epic-req';
            else if (fromNode.type === 'requirement' && toNode.type === 'epic') colorKey = 'epic-req';
            else if (fromNode.type === 'requirement' && toNode.type === 'user-story') colorKey = 'req-story';
            else if (fromNode.type === 'user-story' && toNode.type === 'test') colorKey = 'story-test';
            else if (fromNode.type === 'requirement' && toNode.type === 'diagram') colorKey = 'req-diagram';
            else if (fromNode.type === 'persona' && toNode.type === 'user-story') colorKey = 'persona-story';
            else if (fromNode.type === 'persona' && toNode.type === 'screen') colorKey = 'persona-screen';
            else if (fromNode.type === 'user-flow' && toNode.type === 'screen') colorKey = 'flow-screen';
            else if (fromNode.type === 'screen' && toNode.type === 'component') colorKey = 'screen-component';
            else if (fromNode.type === 'user-story' && toNode.type === 'screen') colorKey = 'story-screen';
            else if ((fromNode.type === 'feature' || fromNode.type === 'epic') && toNode.type === 'task') colorKey = 'feature-task';
            // API links
            else if (fromNode.type === 'requirement' && toNode.type === 'api') colorKey = 'req-api';
            else if (fromNode.type === 'api' && toNode.type === 'requirement') colorKey = 'req-api';
            else if (fromNode.type === 'api' && toNode.type === 'screen') colorKey = 'api-screen';
            else if (fromNode.type === 'component' && toNode.type === 'api') colorKey = 'comp-api';
            else if (fromNode.type === 'test' && toNode.type === 'api') colorKey = 'test-api';
            // Entity links
            else if (fromNode.type === 'api' && toNode.type === 'entity') colorKey = 'api-entity';
            else if (fromNode.type === 'entity' && toNode.type === 'api') colorKey = 'entity-api';
            else if (fromNode.type === 'requirement' && toNode.type === 'entity') colorKey = 'req-entity';
            else if (fromNode.type === 'screen' && toNode.type === 'entity') colorKey = 'screen-entity';
            else if (fromNode.type === 'diagram' && toNode.type === 'entity') colorKey = 'diagram-entity';
            // Tech & Feature
            else if (fromNode.type === 'tech-stack' && toNode.type === 'component') colorKey = 'tech-comp';

            const color = connectionColors[colorKey];

            // For stacked connections, calculate the source position from stacked requirements
            let stackedStartX = startX;
            let stackedStartY = startY;
            let stackCount = 1;

            if (isPartOfStack && requirementStacks[conn.to]) {
                stackCount = requirementStacks[conn.to].length;

                // Calculate center position of all stacked requirements
                const reqIds = requirementStacks[conn.to];
                let sumX = 0, sumY = 0, validCount = 0;

                reqIds.forEach(reqId => {
                    const reqNode = state.nodes[reqId];
                    if (reqNode && reqNode.element) {
                        const reqEl = reqNode.element;
                        sumX += parseFloat(reqEl.style.left) + reqEl.offsetWidth / 2;
                        sumY += parseFloat(reqEl.style.top) + reqEl.offsetHeight / 2;
                        validCount++;
                    }
                });

                if (validCount > 0) {
                    // Use center of stacked requirements as start point
                    const avgX = sumX / validCount;
                    const avgY = sumY / validCount;

                    // Adjust start position based on direction
                    if (Math.abs(toBounds.centerX - avgX) > Math.abs(toBounds.centerY - avgY)) {
                        stackedStartX = avgX > toBounds.centerX ? avgX - 100 : avgX + 100;
                        stackedStartY = avgY;
                    } else {
                        stackedStartX = avgX;
                        stackedStartY = avgY > toBounds.centerY ? avgY - 60 : avgY + 60;
                    }
                }
            }

            // Use stacked start position if applicable
            const actualStartX = isPartOfStack ? stackedStartX : startX;
            const actualStartY = isPartOfStack ? stackedStartY : startY;

            // Validate coordinates BEFORE computing path
            if (isNaN(actualStartX) || isNaN(actualStartY) || isNaN(endX) || isNaN(endY)) {
                pathsFailed++;
                console.warn(`[Connections] Invalid coordinates for ${conn.from} -> ${conn.to}`);
                return;
            }

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

            const d = routeOrthogonalPath(
                actualStartX, actualStartY, endX, endY,
                fromBounds, toBounds,
                nodeBounds, conn.from, conn.to,
                offset,
                useHorizontal  // Force horizontal-first for cross-column connections
            );

            path.setAttribute('d', d);
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', color);

            // Calculate diagram stack count
            let diagramStackCount = 1;
            if (isPartOfDiagramStack && diagramStacks[conn.from]) {
                diagramStackCount = diagramStacks[conn.from].length;
            }

            // Thicker stroke for stacked connections (requirements or diagrams)
            const isAnyStack = isPartOfStack || isPartOfDiagramStack;
            const effectiveStackCount = isPartOfStack ? stackCount : diagramStackCount;
            const strokeWidth = isAnyStack ? Math.min(4 + effectiveStackCount, 8) : 2;
            path.setAttribute('stroke-width', strokeWidth.toString());
            path.setAttribute('stroke-opacity', isAnyStack ? '0.9' : '0.7');
            path.setAttribute('marker-end', `url(#arrow-${colorKey})`);
            path.dataset.from = conn.from;
            path.dataset.to = conn.to;
            path.classList.add('connection-path');

            if (isPartOfStack) {
                path.classList.add('connection-stacked');
            }
            if (isPartOfDiagramStack) {
                path.classList.add('connection-diagram-stacked');
            }

            elements.connectionsLayer.appendChild(path);
            pathsCreated++;

            // Cache the path for partial updates during drag
            const cacheKey = `${conn.from}|${conn.to}`;
            connectionPathCache.set(cacheKey, {
                path: path,
                from: conn.from,
                to: conn.to,
                type: conn.type
            });

            // Add stack badge for stacked connections
            if (isPartOfStack && stackCount > 1) {
                const badgeX = (actualStartX + endX) / 2;
                const badgeY = (actualStartY + endY) / 2;
                const badge = renderStackBadge(badgeX, badgeY, stackCount, color);
                elements.connectionsLayer.appendChild(badge);
            }

            // Add diagram stack badge - positioned along the connection line
            // Uses the same vertical offset as the connection endpoint for proper alignment
            if (isPartOfDiagramStack && diagramStackCount > 1) {
                // Position badge at 30% along the connection path
                const badgeX = startX + (endX - startX) * 0.3;
                // Use the actual endY (which has the vertical offset applied) for consistent spacing
                // Interpolate Y position: 30% towards endY from startY
                const badgeY = startY + (endY - startY) * 0.3;
                const badge = renderDiagramStackBadge(badgeX, badgeY, diagramStackCount, color, conn.from);
                elements.connectionsLayer.appendChild(badge);
            }
        } else {
            pathsFailed++;
        }
    });

    console.log(`[Connections] Created ${pathsCreated} paths, ${stacksRendered} req-stacks, ${renderedDiagramStacks.size} diagram-stacks, failed ${pathsFailed}`);

    elements.connectionsLayer.setAttribute('width', '20000');
    elements.connectionsLayer.setAttribute('height', '15000');
    elements.connectionsLayer.setAttribute('viewBox', '0 0 20000 15000');
    elements.connectionsLayer.style.overflow = 'visible';

    addArrowMarkers();
}

/**
 * PERFORMANCE: Update only connections involving the dragged node.
 * This is much faster than full redraw during drag operations.
 */
function updateDraggedNodeConnections() {
    if (!currentDragNodeId) return;

    const draggedNode = state.nodes[currentDragNodeId];
    if (!draggedNode || !draggedNode.element) return;

    // Get current bounds of dragged node
    const el = draggedNode.element;
    const draggedBounds = {
        left: parseFloat(el.style.left) || 0,
        top: parseFloat(el.style.top) || 0,
        right: (parseFloat(el.style.left) || 0) + el.offsetWidth,
        bottom: (parseFloat(el.style.top) || 0) + el.offsetHeight,
        centerX: (parseFloat(el.style.left) || 0) + el.offsetWidth / 2,
        centerY: (parseFloat(el.style.top) || 0) + el.offsetHeight / 2
    };

    // Update only paths involving the dragged node
    connectionPathCache.forEach((cached, cacheKey) => {
        if (cached.from !== currentDragNodeId && cached.to !== currentDragNodeId) {
            return; // Skip - not connected to dragged node
        }

        const otherNodeId = cached.from === currentDragNodeId ? cached.to : cached.from;
        const otherNode = state.nodes[otherNodeId];
        if (!otherNode || !otherNode.element) return;

        const otherEl = otherNode.element;
        const otherBounds = {
            left: parseFloat(otherEl.style.left) || 0,
            top: parseFloat(otherEl.style.top) || 0,
            right: (parseFloat(otherEl.style.left) || 0) + otherEl.offsetWidth,
            bottom: (parseFloat(otherEl.style.top) || 0) + otherEl.offsetHeight,
            centerX: (parseFloat(otherEl.style.left) || 0) + otherEl.offsetWidth / 2,
            centerY: (parseFloat(otherEl.style.top) || 0) + otherEl.offsetHeight / 2
        };

        // Determine from/to bounds based on connection direction
        const fromBounds = cached.from === currentDragNodeId ? draggedBounds : otherBounds;
        const toBounds = cached.to === currentDragNodeId ? draggedBounds : otherBounds;

        // Quick path calculation (simplified for drag performance)
        const goingRight = toBounds.centerX > fromBounds.centerX;
        const dx = Math.abs(toBounds.centerX - fromBounds.centerX);
        const dy = Math.abs(toBounds.centerY - fromBounds.centerY);

        let startX, startY, endX, endY;

        if (dx > dy) {
            // Horizontal connection
            startX = goingRight ? fromBounds.right - EDGE_PADDING : fromBounds.left + EDGE_PADDING;
            startY = fromBounds.centerY;
            endX = goingRight ? toBounds.left + EDGE_PADDING : toBounds.right - EDGE_PADDING;
            endY = toBounds.centerY;
        } else {
            // Vertical connection
            const goingDown = toBounds.centerY > fromBounds.centerY;
            startX = fromBounds.centerX;
            startY = goingDown ? fromBounds.bottom - EDGE_PADDING : fromBounds.top + EDGE_PADDING;
            endX = toBounds.centerX;
            endY = goingDown ? toBounds.top + EDGE_PADDING : toBounds.bottom - EDGE_PADDING;
        }

        // Simple L-path for fast rendering
        const d = dx > dy
            ? `M ${startX} ${startY} L ${endX} ${startY} L ${endX} ${endY}`
            : `M ${startX} ${startY} L ${startX} ${endY} L ${endX} ${endY}`;

        // Update path d attribute only (no DOM recreation)
        cached.path.setAttribute('d', d);
    });
}

function groupConnectionsByPath() {
    const groups = {};

    state.connections.forEach((conn, index) => {
        const key = getConnectionGroupKey(conn.from, conn.to);
        if (!groups[key]) groups[key] = [];
        groups[key].push(index);
    });

    return groups;
}

function getConnectionGroupKey(from, to) {
    return [from, to].sort().join('|');
}

/**
 * Detect stacked requirements - multiple Requirements connecting to the same User Story.
 * Returns a map of userStoryId -> [requirementIds]
 */
function detectRequirementStacks() {
    const stacks = {};  // userStoryId -> [requirementIds]

    state.connections.forEach(conn => {
        const fromNode = state.nodes[conn.from];
        const toNode = state.nodes[conn.to];

        // Requirement -> User Story connections
        if (fromNode?.type === 'requirement' && toNode?.type === 'user-story') {
            if (!stacks[conn.to]) stacks[conn.to] = [];
            stacks[conn.to].push(conn.from);
        }
    });

    // Only return stacks with more than 1 requirement
    const multiStacks = {};
    Object.entries(stacks).forEach(([storyId, reqIds]) => {
        if (reqIds.length > 1) {
            multiStacks[storyId] = reqIds;
        }
    });

    return multiStacks;
}

/**
 * Detect diagram stacks - multiple Diagrams belonging to the same Requirement.
 * Groups diagrams by their parent requirement (extracted from ID pattern like REQ-001-flowchart).
 * Returns a map of requirementId -> [diagramIds]
 */
function detectDiagramStacks() {
    const stacks = {};  // requirementId -> [diagramIds]

    // Find all diagram nodes
    Object.entries(state.nodes).forEach(([nodeId, node]) => {
        if (node.type !== 'diagram') return;

        // Extract parent requirement from diagram ID
        // Pattern: REQ-XXX-flowchart, REQ-XXX-sequence, etc.
        const parentReqId = extractParentRequirementId(nodeId);
        if (!parentReqId) return;

        if (!stacks[parentReqId]) stacks[parentReqId] = [];
        stacks[parentReqId].push(nodeId);
    });

    // Only return stacks with more than 1 diagram
    const multiStacks = {};
    Object.entries(stacks).forEach(([reqId, diagramIds]) => {
        if (diagramIds.length > 1) {
            multiStacks[reqId] = diagramIds;
        }
    });

    console.log(`[Connections] Found ${Object.keys(multiStacks).length} diagram stacks`);
    return multiStacks;
}

/**
 * Extract parent requirement ID from diagram ID.
 * Supports multiple formats:
 * - "REQ-001-flowchart" -> "REQ-001" (hyphen separator)
 * - "WA-AUTH-001_flowchart" -> "WA-AUTH-001" (underscore separator)
 * - "REQ-f359e5-000-a-sequenceDiagram" -> "REQ-f359e5-000-a"
 */
function extractParentRequirementId(diagramId) {
    if (!diagramId) return null;

    // Known diagram type suffixes
    const diagramTypes = ['flowchart', 'sequence', 'class', 'er', 'state', 'c4',
                          'sequenceDiagram', 'classDiagram', 'erDiagram', 'stateDiagram', 'C4Context'];

    // First try: Underscore separator (new format: WA-AUTH-001_flowchart)
    const underscoreParts = diagramId.split('_');
    if (underscoreParts.length > 1) {
        const lastPart = underscoreParts[underscoreParts.length - 1].toLowerCase();
        if (diagramTypes.some(t => t.toLowerCase() === lastPart)) {
            return underscoreParts.slice(0, -1).join('_');
        }
    }

    // Second try: Hyphen separator (old format: REQ-001-flowchart)
    // Look for diagram type at the end after last hyphen
    const hyphenParts = diagramId.split('-');
    if (hyphenParts.length > 1) {
        const lastPart = hyphenParts[hyphenParts.length - 1].toLowerCase();
        if (diagramTypes.some(t => t.toLowerCase() === lastPart)) {
            return hyphenParts.slice(0, -1).join('-');
        }
    }

    // Third try: Regex pattern match for complex IDs
    const reqMatch = diagramId.match(/^([A-Z]+-[a-zA-Z0-9-]+?)[-_](flowchart|sequenceDiagram|classDiagram|erDiagram|stateDiagram|C4Context|sequence|class|er|state|c4)/i);
    if (reqMatch) {
        return reqMatch[1];
    }

    // Fallback: check connections to find the parent
    for (const conn of state.connections) {
        if (conn.to === diagramId) {
            const fromNode = state.nodes[conn.from];
            if (fromNode?.type === 'requirement') {
                return conn.from;
            }
        }
    }

    return null;
}

// Track which diagram stacks are collapsed (default: all collapsed)
const collapsedDiagramStacks = new Set();

/**
 * Toggle diagram stack collapse state.
 */
export function toggleDiagramStack(reqId) {
    if (collapsedDiagramStacks.has(reqId)) {
        collapsedDiagramStacks.delete(reqId);
    } else {
        collapsedDiagramStacks.add(reqId);
    }
    updateConnections();
}

/**
 * Check if a diagram stack is collapsed.
 */
export function isDiagramStackCollapsed(reqId) {
    return collapsedDiagramStacks.has(reqId);
}

/**
 * Get all diagrams belonging to a requirement.
 * @param {string} reqId - Requirement ID
 * @returns {Array} Array of [diagramId, node] tuples
 */
function getDiagramsForRequirement(reqId) {
    return Object.entries(state.nodes)
        .filter(([id, node]) => {
            if (node.type !== 'diagram') return false;
            // Check if diagram ID starts with requirement ID
            return id.startsWith(reqId + '-') || id.startsWith(reqId + '_');
        })
        .sort(([a], [b]) => a.localeCompare(b));  // Alphabetical sort
}

/**
 * Toggle visibility of diagram stack.
 * Shows/hides diagram elements and updates connections.
 * @param {string} reqId - Requirement ID that owns the diagrams
 */
export function toggleDiagramStackVisibility(reqId) {
    const diagrams = getDiagramsForRequirement(reqId);

    if (diagrams.length === 0) {
        console.log(`[Diagrams] No diagrams found for ${reqId}`);
        return;
    }

    if (collapsedDiagramStacks.has(reqId)) {
        // EXPAND: Show all diagrams
        collapsedDiagramStacks.delete(reqId);
        diagrams.forEach(([id, node]) => {
            if (node.element) {
                node.element.style.display = '';
                node.element.classList.remove('diagram-collapsed');
            }
        });
        console.log(`[Diagrams] Expanded ${diagrams.length} diagrams for ${reqId}`);
    } else {
        // COLLAPSE: Hide all except first
        collapsedDiagramStacks.add(reqId);
        diagrams.forEach(([id, node], index) => {
            if (node.element && index > 0) {
                node.element.style.display = 'none';
                node.element.classList.add('diagram-collapsed');
            }
        });
        console.log(`[Diagrams] Collapsed ${diagrams.length - 1} diagrams for ${reqId}`);
    }

    // Redraw connections
    updateConnections();
}

// Listen for diagram stack toggle events
if (typeof window !== 'undefined') {
    window.addEventListener('diagram:stack-toggle', (e) => {
        const { reqId } = e.detail;
        if (reqId) {
            toggleDiagramStackVisibility(reqId);
        }
    });
}

/**
 * Render a stack badge showing the count of stacked connections.
 */
function renderStackBadge(x, y, count, color) {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.classList.add('stack-badge-group');

    // Badge background
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x - 12);
    rect.setAttribute('y', y - 10);
    rect.setAttribute('width', '24');
    rect.setAttribute('height', '20');
    rect.setAttribute('rx', '10');
    rect.setAttribute('fill', color);
    rect.setAttribute('stroke', '#1a1a2e');
    rect.setAttribute('stroke-width', '2');

    // Badge text
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x);
    text.setAttribute('y', y + 4);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-weight', 'bold');
    text.setAttribute('fill', '#ffffff');
    text.textContent = `${count}×`;

    group.appendChild(rect);
    group.appendChild(text);

    return group;
}

/**
 * Render a diagram stack badge showing the count of diagrams.
 * Clickable to expand/collapse the diagram group.
 */
function renderDiagramStackBadge(x, y, count, color, reqId) {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.classList.add('diagram-stack-badge-group');
    group.style.cursor = 'pointer';
    group.style.pointerEvents = 'all';  // Enable click events on SVG
    group.dataset.reqId = reqId;

    // Badge background - slightly larger for diagram icon
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x - 20);
    rect.setAttribute('y', y - 12);
    rect.setAttribute('width', '40');
    rect.setAttribute('height', '24');
    rect.setAttribute('rx', '12');
    rect.setAttribute('fill', color);
    rect.setAttribute('stroke', '#1a1a2e');
    rect.setAttribute('stroke-width', '2');

    // Diagram icon (simplified)
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    icon.setAttribute('x', x - 10);
    icon.setAttribute('y', y + 5);
    icon.setAttribute('font-size', '12');
    icon.setAttribute('fill', '#1a1a2e');
    icon.textContent = '📊';

    // Badge text
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x + 10);
    text.setAttribute('y', y + 5);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '12');
    text.setAttribute('font-weight', 'bold');
    text.setAttribute('fill', '#1a1a2e');
    text.textContent = `${count}`;

    group.appendChild(rect);
    group.appendChild(icon);
    group.appendChild(text);

    // Add click handler for expand/collapse
    group.addEventListener('click', (e) => {
        e.stopPropagation();
        console.log(`[Connections] Toggling diagram stack for ${reqId}`);
        // Dispatch event for diagram expansion
        window.dispatchEvent(new CustomEvent('diagram:stack-toggle', {
            detail: { reqId, count }
        }));
    });

    return group;
}

function addArrowMarkers() {
    let defs = elements.connectionsLayer.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        elements.connectionsLayer.prepend(defs);
    }
    defs.innerHTML = '';

    const colors = {
        'epic-story': '#7856ff',
        'epic-req': '#9333ea',
        'req-story': '#1d9bf0',
        'story-test': '#00ba7c',
        'req-diagram': '#ffd400',
        'persona-story': '#f97316',
        'flow-screen': '#ec4899',
        'screen-component': '#84cc16',
        'story-screen': '#8b5cf6',
        'feature-task': '#f59e0b',
        'persona-screen': '#f97316',
        'req-api': '#ff7a00',
        'api-screen': '#8b5cf6',
        'comp-api': '#ff7a00',
        'test-api': '#f4212e',
        'api-entity': '#6366f1',
        'req-entity': '#6366f1',
        'screen-entity': '#84cc16',
        'entity-api': '#6366f1',
        'diagram-entity': '#ffd400',
        'tech-comp': '#06b6d4',
        'feature-story': '#10b981',
        'default': '#536471'
    };

    Object.entries(colors).forEach(([key, color]) => {
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', `arrow-${key}`);
        marker.setAttribute('viewBox', '0 0 10 10');
        marker.setAttribute('refX', '9');
        marker.setAttribute('refY', '5');
        marker.setAttribute('markerWidth', '6');
        marker.setAttribute('markerHeight', '6');
        marker.setAttribute('orient', 'auto-start-reverse');

        const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrowPath.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
        arrowPath.setAttribute('fill', color);

        marker.appendChild(arrowPath);
        defs.appendChild(marker);
    });
}
