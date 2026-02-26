/**
 * RE System Dashboard - Layout Module Index
 *
 * Central layout management and configuration
 *
 * SIMPLIFIED: Only Matrix layout supported
 */

import { state, elements, log } from '../state.js';
import { updateConnections } from '../connections.js';

// Re-export grouping module for easy access
export * from './grouping.js';

// ============================================
// Layout Mode (Matrix only)
// ============================================

export const LAYOUT_MODES = {
    BY_MATRIX: 'by_matrix'
};

export let currentLayout = LAYOUT_MODES.BY_MATRIX;
export let packageIndex = {};

// ============================================
// Work Package Column Configuration
// ============================================

export const WORKPACKAGE_COLUMNS = [
    // Detail level (many incoming links)
    { id: 'task', name: 'Tasks', order: 0, width: 320, color: '#f59e0b' },
    { id: 'test', name: 'Tests', order: 1, width: 320, color: '#f4212e' },
    { id: 'component', name: 'Components', order: 2, width: 320, color: '#84cc16' },
    { id: 'screen', name: 'Screens', order: 3, width: 320, color: '#8b5cf6' },
    { id: 'api', name: 'API', order: 4, width: 320, color: '#ff7a00' },
    // Diagrams (alle Typen in einer Column)
    { id: 'diagram', name: 'Diagrams', order: 5, width: 320, color: '#ffd400', isDiagram: true },
    // Middle level
    { id: 'user-flow', name: 'User Flows', order: 6, width: 320, color: '#ec4899' },
    { id: 'persona', name: 'Personas', order: 7, width: 320, color: '#f97316' },
    { id: 'user-story', name: 'User Stories', order: 8, width: 320, color: '#00ba7c' },
    // Abstract level (few links, roots)
    { id: 'epic', name: 'Epics', order: 9, width: 320, color: '#7856ff' },
    { id: 'requirement', name: 'Requirements', order: 10, width: 320, color: '#1d9bf0' },
    // Data Model (Entities - own work package)
    { id: 'entity', name: 'Data Model', order: 11, width: 320, color: '#14b8a6' },
    { id: 'tech-stack', name: 'Tech Stack', order: 12, width: 320, color: '#06b6d4' }
];

export const DIAGRAM_TYPE_ORDER = {
    'flowchart': 0,
    'class': 1,
    'sequence': 2,
    'er': 3,
    'c4': 4,
    'state': 5
};

// Track work package state
export let currentWorkPackages = [];

// ============================================
// Callback References (set by app.js)
// ============================================

let callbacks = {
    updateMinimap: () => {},
    reRenderAllDiagrams: () => {},
    fitToView: () => {},
    calculateNodePosition: (type, id) => ({ x: 0, y: 0 })
};

export function setLayoutCallbacks(cbs) {
    callbacks = { ...callbacks, ...cbs };
}

// ============================================
// Layout Switching (Matrix only)
// ============================================

export function setLayout(mode, layoutFunctions = {}) {
    currentLayout = LAYOUT_MODES.BY_MATRIX;
    log('info', `[Layout] Using Matrix layout`);

    const { reorganizeNodesMatrix } = layoutFunctions;

    // Clean up previous layout structures
    cleanupLayoutStructures();

    // Apply matrix layout
    if (reorganizeNodesMatrix) {
        reorganizeNodesMatrix();
    }

    // Update UI
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.layout === 'by_matrix');
    });

    // Fit to view after layout change
    setTimeout(() => callbacks.fitToView(), 150);
}

/**
 * Clean up layout-specific DOM structures.
 */
function cleanupLayoutStructures() {
    // Remove matrix grid structure (hide, don't remove - it gets recreated)
    const matrixGrid = document.getElementById('matrix-grid-structure');
    if (matrixGrid) matrixGrid.style.display = 'none';
}

// ============================================
// Column Link Statistics
// ============================================

export function calculateColumnLinkStats() {
    const columnStats = {};

    WORKPACKAGE_COLUMNS.filter(col => !col.isDiagram).forEach(col => {
        const nodesInColumn = Object.entries(state.nodes)
            .filter(([id, node]) => getWorkPackageColumn(node) === col.id)
            .map(([id, node]) => id);

        let totalIncoming = 0;
        let totalOutgoing = 0;

        nodesInColumn.forEach(nodeId => {
            totalIncoming += state.connections.filter(c => c.to === nodeId).length;
            totalOutgoing += state.connections.filter(c => c.from === nodeId).length;
        });

        const total = totalIncoming + totalOutgoing;
        const score = total === 0 ? 0 : (totalIncoming - totalOutgoing) / total;

        columnStats[col.id] = {
            incoming: totalIncoming,
            outgoing: totalOutgoing,
            nodeCount: nodesInColumn.length,
            score: score
        };
    });

    return columnStats;
}

export function getSortedColumns() {
    const stats = calculateColumnLinkStats();

    const diagramCols = WORKPACKAGE_COLUMNS.filter(col => col.isDiagram);
    const otherCols = WORKPACKAGE_COLUMNS.filter(col => !col.isDiagram);

    const sortedOtherCols = [...otherCols].sort((a, b) => {
        const scoreA = stats[a.id]?.score ?? 0;
        const scoreB = stats[b.id]?.score ?? 0;
        return scoreA - scoreB;
    });

    const midPoint = Math.floor(sortedOtherCols.length / 2);
    const result = [
        ...sortedOtherCols.slice(0, midPoint),
        ...diagramCols,
        ...sortedOtherCols.slice(midPoint)
    ];

    console.log('[Matrix] Column link stats:', stats);
    console.log('[Matrix] Sorted column order:', result.map(c => `${c.id}(${stats[c.id]?.score?.toFixed(2) ?? 'diag'})`).join(' → '));

    return result;
}

// ============================================
// Work Package Column Mapping
// ============================================

export function getDiagramType(data) {
    const code = data?.mermaid_code || '';
    if (code.startsWith('classDiagram')) return 'class';
    if (code.startsWith('sequenceDiagram')) return 'sequence';
    if (code.startsWith('erDiagram')) return 'er';
    if (code.startsWith('C4')) return 'c4';
    if (code.startsWith('stateDiagram')) return 'state';
    return 'flowchart';
}

export function getWorkPackageColumn(node) {
    const type = node.type;

    // Alle Diagrams in eine Column (unabhaengig vom Typ)
    if (type === 'diagram') {
        return 'diagram';
    }

    // Entity type goes to own Data Model column
    if (type === 'entity') {
        return 'entity';
    }

    const typeToColumn = {
        'requirement': 'requirement',
        'epic': 'epic',
        'user-story': 'user-story',
        'test': 'test',
        'api': 'api',
        'persona': 'persona',
        'user-flow': 'user-flow',
        'screen': 'screen',
        'component': 'component',
        'task': 'task',
        'tech-stack': 'tech-stack'
    };

    return typeToColumn[type] || 'requirement';
}

// ============================================
// Work Package Detection
// ============================================

export function detectWorkPackages() {
    const nodeIds = Object.keys(state.nodes);
    if (nodeIds.length === 0) return [];

    const adjacency = {};
    nodeIds.forEach(id => adjacency[id] = new Set());

    state.connections.forEach(conn => {
        if (state.nodes[conn.from] && state.nodes[conn.to]) {
            adjacency[conn.from].add(conn.to);
            adjacency[conn.to].add(conn.from);
        }
    });

    const rootTypes = ['requirement', 'epic', 'tech-stack'];
    const potentialRoots = nodeIds.filter(id => {
        const node = state.nodes[id];
        const type = node.type;
        if (rootTypes.includes(type)) {
            const hasOutgoingToRoot = state.connections.some(conn =>
                conn.from === id && rootTypes.includes(state.nodes[conn.to]?.type)
            );
            return !hasOutgoingToRoot;
        }
        return false;
    });

    let roots = potentialRoots;
    if (roots.length === 0) {
        const connectivity = {};
        nodeIds.forEach(id => connectivity[id] = adjacency[id].size);
        const sortedByConnectivity = [...nodeIds].sort((a, b) => connectivity[b] - connectivity[a]);
        roots = sortedByConnectivity.slice(0, Math.max(1, Math.ceil(nodeIds.length / 10)));
    }

    const visited = new Set();
    const workPackages = [];

    roots.forEach(rootId => {
        if (visited.has(rootId)) return;

        const package_ = {
            id: rootId,
            name: state.nodes[rootId].data?.title || state.nodes[rootId].data?.id || rootId,
            rootType: state.nodes[rootId].type,
            nodes: []
        };

        const queue = [rootId];
        while (queue.length > 0) {
            const nodeId = queue.shift();
            if (visited.has(nodeId)) continue;
            visited.add(nodeId);

            const nodeData = state.nodes[nodeId];
            if (nodeData) {
                package_.nodes.push({
                    id: nodeId,
                    type: nodeData.type,
                    data: nodeData.data,
                    element: nodeData.element
                });
            }

            adjacency[nodeId].forEach(connectedId => {
                if (!visited.has(connectedId)) {
                    queue.push(connectedId);
                }
            });
        }

        if (package_.nodes.length > 0) {
            workPackages.push(package_);
        }
    });

    const orphans = nodeIds.filter(id => !visited.has(id));
    if (orphans.length > 0) {
        workPackages.push({
            id: '__orphans__',
            name: 'Unverlinkt',
            rootType: 'orphan',
            isOrphanPackage: true,
            nodes: orphans.map(id => ({
                id,
                type: state.nodes[id].type,
                data: state.nodes[id].data,
                element: state.nodes[id].element
            }))
        });
    }

    currentWorkPackages = workPackages;
    return workPackages;
}

// ============================================
// Cluster Detection (used by matrix for grouping)
// ============================================

export function detectClusters() {
    const clusters = [];
    const visited = new Set();

    const adjacency = {};
    Object.keys(state.nodes).forEach(id => adjacency[id] = new Set());

    state.connections.forEach(conn => {
        if (state.nodes[conn.from] && state.nodes[conn.to]) {
            adjacency[conn.from].add(conn.to);
            adjacency[conn.to].add(conn.from);
        }
    });

    Object.keys(state.nodes).forEach(startId => {
        if (visited.has(startId)) return;

        const cluster = [];
        const stack = [startId];

        while (stack.length > 0) {
            const nodeId = stack.pop();
            if (visited.has(nodeId)) continue;

            visited.add(nodeId);
            cluster.push(nodeId);

            adjacency[nodeId].forEach(connectedId => {
                if (!visited.has(connectedId)) {
                    stack.push(connectedId);
                }
            });
        }

        if (cluster.length > 0) {
            clusters.push(cluster);
        }
    });

    return clusters;
}

// ============================================
// Utility: Find Connected Components
// ============================================

export function findConnectedComponents() {
    const visited = new Set();
    const clusters = [];

    const adjacency = {};
    Object.keys(state.nodes).forEach(id => adjacency[id] = new Set());

    state.connections.forEach(conn => {
        if (state.nodes[conn.from] && state.nodes[conn.to]) {
            adjacency[conn.from].add(conn.to);
            adjacency[conn.to].add(conn.from);
        }
    });

    Object.keys(state.nodes).forEach(startId => {
        if (visited.has(startId)) return;

        const cluster = [];
        const stack = [startId];

        while (stack.length > 0) {
            const nodeId = stack.pop();
            if (visited.has(nodeId)) continue;

            visited.add(nodeId);
            cluster.push(nodeId);

            adjacency[nodeId].forEach(connectedId => {
                if (!visited.has(connectedId)) {
                    stack.push(connectedId);
                }
            });
        }

        if (cluster.length > 0) {
            clusters.push(cluster);
        }
    });

    return clusters;
}
