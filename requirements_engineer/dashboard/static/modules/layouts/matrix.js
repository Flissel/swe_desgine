/**
 * RE System Dashboard - Matrix Layout Module
 *
 * Work Package (Arbeitspakete) Matrix Layout
 * Rows = Work packages, Columns = Node types sorted by link direction
 */

import { state, elements, log, escapeHtml } from '../state.js';
import { updateConnections } from '../connections.js';
import {
    WORKPACKAGE_COLUMNS,
    currentWorkPackages,
    detectWorkPackages,
    getSortedColumns,
    getWorkPackageColumn,
    detectNodeGroups,
    isGroupCollapsed,
    findNodeGroup,
    getGroupStats,
    GROUPING_RULES,
    DIAGRAM_TYPES,
    getDiagramTypeFromId
} from './index.js';
import { renderDiagramThumbnail } from '../mermaidRenderer.js';

// ============================================
// Callback References
// ============================================

let callbacks = {
    updateMinimap: () => {},
    reRenderAllDiagrams: () => {}
};

export function setMatrixCallbacks(cbs) {
    callbacks = { ...callbacks, ...cbs };
}

// ============================================
// Matrix Layout
// ============================================

// Node size configuration
const NODE_SIZES = {
    'diagram': { width: 200, height: 160 },      // Collapsed group
    'diagram-group': { width: 200, height: 160 },
    'test': { width: 180, height: 120 },
    'test-group': { width: 180, height: 120 },
    'user-story': { width: 280, height: 150 },
    'user-story-group': { width: 220, height: 140 },
    'user-story-test-group': { width: 180, height: 120 },  // Tests under user story
    'requirement': { width: 320, height: 180 },
    'requirement-group': { width: 250, height: 150 },  // Collapsed requirements under epic
    'data-requirement-group': { width: 220, height: 140 },  // Data requirements under epic
    'task-group': { width: 200, height: 130 },         // Collapsed tasks under epic
    'epic': { width: 350, height: 200 },
    'persona': { width: 250, height: 160 },
    'entity': { width: 220, height: 120 },             // Data model entity
    'entity-group': { width: 220, height: 140 },       // Grouped entities
    'default': { width: 280, height: 160 }
};

/**
 * Check if a test is linked to a user story (should be hidden and shown as metadata)
 * @param {string} testId - Test node ID
 * @param {Object} testNode - Test node data
 * @returns {boolean} True if linked to a user story
 */
function isTestLinkedToUserStory(testId, testNode) {
    // 1. Check linked_user_story field
    if (testNode.data?.linked_user_story) {
        return true;
    }

    // 2. Check ID pattern (TC-US-001 → linked to US-001)
    if (testId.match(/TC-US-?\d+/i)) {
        return true;
    }

    // 3. Check connections to user stories
    const connections = state.connections || [];
    for (const conn of connections) {
        const otherNodeId = conn.from === testId ? conn.to : (conn.to === testId ? conn.from : null);
        if (otherNodeId) {
            const otherNode = state.nodes[otherNodeId];
            if (otherNode?.type === 'user-story') {
                return true;
            }
        }
    }

    return false;
}

// Gap between Arbeitspakete (Epics) within a Feature
const EPIC_GAP = 50;

/**
 * Find the parent Epic for a node via connections
 * @param {string} nodeId - Node ID to find parent for
 * @returns {string|null} Epic ID or null
 */
function findParentEpic(nodeId) {
    const connections = state.connections || [];
    const visited = new Set();
    const queue = [nodeId];

    while (queue.length > 0) {
        const currentId = queue.shift();
        if (visited.has(currentId)) continue;
        visited.add(currentId);

        const currentNode = state.nodes[currentId];
        if (currentNode?.type === 'epic') {
            return currentId;
        }

        // Follow connections to find Epic
        for (const conn of connections) {
            if (conn.from === currentId && !visited.has(conn.to)) {
                queue.push(conn.to);
            }
            if (conn.to === currentId && !visited.has(conn.from)) {
                queue.push(conn.from);
            }
        }
    }

    return null;
}

/**
 * Group nodes within a work package by their parent Epic
 * @param {Array} wpNodes - Nodes in the work package
 * @returns {Object} { epicGroups: Map, orphanNodes: Array }
 */
function groupNodesByEpic(wpNodes) {
    const epicGroups = new Map(); // epicId -> { epic, children: [] }
    const orphanNodes = [];

    // First, identify all Epics in this work package
    wpNodes.forEach(node => {
        const nodeData = state.nodes[node.id];
        if (nodeData?.type === 'epic') {
            epicGroups.set(node.id, {
                epic: node,
                epicData: nodeData,
                children: []
            });
        }
    });

    // Then, assign non-Epic nodes to their parent Epic
    wpNodes.forEach(node => {
        const nodeData = state.nodes[node.id];
        if (!nodeData || nodeData.type === 'epic') return;

        const parentEpicId = findParentEpic(node.id);

        if (parentEpicId && epicGroups.has(parentEpicId)) {
            epicGroups.get(parentEpicId).children.push(node);
        } else {
            orphanNodes.push(node);
        }
    });

    return { epicGroups, orphanNodes };
}

// Track created group nodes for cleanup
let createdGroupNodes = new Set();

export function reorganizeNodesMatrix() {
    const baseX = 3200;
    const baseY = 3200;
    const padding = 40;
    const rowHeaderWidth = 220;
    const rowGap = 140;  // Increased for work package separator banners
    const minRowHeight = 280;

    // Clean up old group nodes
    cleanupGroupNodes();

    // Detect work packages
    let workPackages = detectWorkPackages();
    log('info', `Detected ${workPackages.length} work packages`);

    // Detect node groups (diagrams, tests, etc.)
    const groups = detectNodeGroups();
    state.groupState.groups = groups;
    log('info', `Detected ${Object.keys(groups).length} collapsible groups`);

    // Sort work packages: Epics first, then by requirement ID, orphans at end
    workPackages.sort((a, b) => {
        if (a.isOrphanPackage) return 1;
        if (b.isOrphanPackage) return -1;

        // Epics before requirements
        if (a.rootType === 'epic' && b.rootType !== 'epic') return -1;
        if (b.rootType === 'epic' && a.rootType !== 'epic') return 1;

        const getSortKey = (wp) => {
            const rootNode = state.nodes[wp.id];
            return rootNode?.data?.id || wp.id || wp.name;
        };

        const idA = getSortKey(a);
        const idB = getSortKey(b);

        return idA.localeCompare(idB, undefined, { numeric: true, sensitivity: 'base' });
    });

    // Get columns with enhanced sorting (personas at edge)
    const sortedColumns = getEnhancedSortedColumns();

    // Calculate column positions with persona edge positioning
    let columnX = baseX + rowHeaderWidth;
    const columnPositions = {};

    // Check if persona column should be at edge
    const personaCol = sortedColumns.find(c => c.id === 'persona');

    sortedColumns.forEach(col => {
        // Skip persona for now if it needs edge positioning
        if (col.id === 'persona' && personaCol) {
            columnPositions[col.id] = {
                x: baseX - col.width - 50,  // Left edge
                width: col.width,
                name: col.name,
                color: col.color,
                isDiagram: false,
                isEdge: true
            };
        } else {
            columnPositions[col.id] = {
                x: columnX,
                width: col.width,
                name: col.name,
                color: col.color,
                isDiagram: col.isDiagram || false
            };
            columnX += col.width;
        }
    });

    const totalWidth = columnX - baseX;

    // Calculate layout for each work package
    let currentY = baseY + 80;
    const workPackageLayouts = [];

    workPackages.forEach((wp, wpIndex) => {
        // Group nodes by their parent Epic
        const { epicGroups, orphanNodes } = groupNodesByEpic(wp.nodes);

        const wpStartY = currentY;
        const epicPositions = [];
        let totalWpHeight = 0;

        // Process each Epic group as a horizontal band
        const epicEntries = Array.from(epicGroups.entries());

        // Sort epics by their ID for consistent ordering
        epicEntries.sort((a, b) => {
            const idA = state.nodes[a[0]]?.data?.id || a[0];
            const idB = state.nodes[b[0]]?.data?.id || b[0];
            return idA.localeCompare(idB, undefined, { numeric: true });
        });

        epicEntries.forEach(([epicId, epicGroup], epicIndex) => {
            const epicBandStartY = currentY;

            // Organize this Epic's children by column
            const nodesByColumn = {};
            sortedColumns.forEach(col => nodesByColumn[col.id] = []);

            // Add the Epic itself to the epic column
            const epicNode = epicGroup.epic;
            const epicNodeData = state.nodes[epicId];
            if (epicNodeData) {
                nodesByColumn['epic'] = [epicNode];
            }

            // Track which groups we've added for this Epic
            const addedGroups = new Set();

            // Process children of this Epic
            epicGroup.children.forEach(node => {
                const nodeData = state.nodes[node.id];
                if (!nodeData) return;

                // Check if node is part of a collapsed group
                const groupKey = findNodeGroup(node.id, groups);

                if (groupKey && isGroupCollapsed(groupKey, groups)) {
                    if (!addedGroups.has(groupKey)) {
                        addedGroups.add(groupKey);
                        const group = groups[groupKey];

                        const colId = group.childType === 'diagram' ? 'diagram' :
                                      group.childType === 'test' ? 'test' :
                                      group.childType === 'user-story' ? 'user-story' :
                                      group.childType === 'entity' ? 'entity' :
                                      'requirement';

                        if (nodesByColumn[colId]) {
                            nodesByColumn[colId].push({
                                id: groupKey,
                                isGroup: true,
                                group: group,
                                type: `${group.childType}-group`
                            });
                        }
                    }

                    if (nodeData.element) {
                        nodeData.element.style.display = 'none';
                    }
                } else {
                    // Check if test linked to user story
                    if (nodeData.type === 'test') {
                        const isLinkedToUserStory = isTestLinkedToUserStory(node.id, nodeData);
                        if (isLinkedToUserStory) {
                            if (nodeData.element) {
                                nodeData.element.style.display = 'none';
                            }
                            return;
                        }
                    }

                    if (nodeData.element) {
                        nodeData.element.style.display = '';
                    }

                    const colId = getWorkPackageColumn(nodeData);
                    if (nodesByColumn[colId]) {
                        nodesByColumn[colId].push(node);
                    } else {
                        nodesByColumn['requirement'].push(node);
                    }
                }
            });

            // Calculate max height for this Epic band
            let maxColHeight = 0;
            sortedColumns.forEach(col => {
                const colNodes = nodesByColumn[col.id] || [];
                let colHeight = padding;

                colNodes.forEach(node => {
                    const sizeKey = node.isGroup ? node.type : (col.isDiagram ? 'diagram' : col.id);
                    const nodeSize = NODE_SIZES[sizeKey] || NODE_SIZES.default;
                    colHeight += nodeSize.height + padding;
                });

                maxColHeight = Math.max(maxColHeight, colHeight);
            });

            const epicBandHeight = Math.max(minRowHeight, maxColHeight);

            // Position nodes within this Epic band
            sortedColumns.forEach(col => {
                const colData = columnPositions[col.id];
                if (!colData) return;

                const colNodes = nodesByColumn[col.id] || [];
                let nodeY = epicBandStartY + padding;

                colNodes.forEach((node, nodeIndex) => {
                    const sizeKey = node.isGroup ? node.type : (col.isDiagram ? 'diagram' : col.id);
                    const nodeSize = NODE_SIZES[sizeKey] || NODE_SIZES.default;
                    const x = colData.x + padding;
                    const y = nodeY;

                    if (node.isGroup) {
                        createOrUpdateGroupNode(node.id, node.group, x, y, nodeSize);
                    } else {
                        const nodeData = state.nodes[node.id];
                        if (nodeData && nodeData.element) {
                            nodeData.x = x;
                            nodeData.y = y;
                            nodeData.element.style.left = `${x}px`;
                            nodeData.element.style.top = `${y}px`;
                        }
                    }

                    nodeY += nodeSize.height + padding;
                });
            });

            // Track Epic position for separators
            epicPositions.push({
                id: epicId,
                name: epicNodeData?.data?.title || epicNodeData?.data?.id || epicId,
                y: epicBandStartY,
                height: epicBandHeight
            });

            // Move to next Epic band with gap
            currentY += epicBandHeight;
            if (epicIndex < epicEntries.length - 1) {
                currentY += EPIC_GAP;
            }
        });

        // Handle orphan nodes (not connected to any Epic)
        if (orphanNodes.length > 0) {
            const orphanStartY = currentY;
            const nodesByColumn = {};
            sortedColumns.forEach(col => nodesByColumn[col.id] = []);

            const addedGroups = new Set();

            orphanNodes.forEach(node => {
                const nodeData = state.nodes[node.id];
                if (!nodeData) return;

                const groupKey = findNodeGroup(node.id, groups);

                if (groupKey && isGroupCollapsed(groupKey, groups)) {
                    if (!addedGroups.has(groupKey)) {
                        addedGroups.add(groupKey);
                        const group = groups[groupKey];
                        const colId = group.childType === 'diagram' ? 'diagram' :
                                      group.childType === 'test' ? 'test' :
                                      group.childType === 'user-story' ? 'user-story' :
                                      group.childType === 'entity' ? 'entity' :
                                      'requirement';
                        if (nodesByColumn[colId]) {
                            nodesByColumn[colId].push({
                                id: groupKey,
                                isGroup: true,
                                group: group,
                                type: `${group.childType}-group`
                            });
                        }
                    }
                    if (nodeData.element) nodeData.element.style.display = 'none';
                } else {
                    if (nodeData.type === 'test' && isTestLinkedToUserStory(node.id, nodeData)) {
                        if (nodeData.element) nodeData.element.style.display = 'none';
                        return;
                    }
                    if (nodeData.element) nodeData.element.style.display = '';
                    const colId = getWorkPackageColumn(nodeData);
                    if (nodesByColumn[colId]) {
                        nodesByColumn[colId].push(node);
                    } else {
                        nodesByColumn['requirement'].push(node);
                    }
                }
            });

            let maxColHeight = 0;
            sortedColumns.forEach(col => {
                const colNodes = nodesByColumn[col.id] || [];
                let colHeight = padding;
                colNodes.forEach(node => {
                    const sizeKey = node.isGroup ? node.type : (col.isDiagram ? 'diagram' : col.id);
                    const nodeSize = NODE_SIZES[sizeKey] || NODE_SIZES.default;
                    colHeight += nodeSize.height + padding;
                });
                maxColHeight = Math.max(maxColHeight, colHeight);
            });

            const orphanBandHeight = Math.max(minRowHeight / 2, maxColHeight);

            sortedColumns.forEach(col => {
                const colData = columnPositions[col.id];
                if (!colData) return;
                const colNodes = nodesByColumn[col.id] || [];
                let nodeY = orphanStartY + padding;
                colNodes.forEach(node => {
                    const sizeKey = node.isGroup ? node.type : (col.isDiagram ? 'diagram' : col.id);
                    const nodeSize = NODE_SIZES[sizeKey] || NODE_SIZES.default;
                    const x = colData.x + padding;
                    if (node.isGroup) {
                        createOrUpdateGroupNode(node.id, node.group, x, nodeY, nodeSize);
                    } else {
                        const nodeData = state.nodes[node.id];
                        if (nodeData && nodeData.element) {
                            nodeData.x = x;
                            nodeData.y = nodeY;
                            nodeData.element.style.left = `${x}px`;
                            nodeData.element.style.top = `${nodeY}px`;
                        }
                    }
                    nodeY += nodeSize.height + padding;
                });
            });

            currentY += orphanBandHeight;
        }

        const totalHeight = currentY - wpStartY;

        workPackageLayouts.push({
            id: wp.id,
            name: wp.name,
            rootType: wp.rootType,
            isOrphanPackage: wp.isOrphanPackage || false,
            y: wpStartY,
            height: totalHeight,
            nodeCount: wp.nodes.length,
            epicPositions: epicPositions
        });

        currentY += rowGap;
    });

    // Render the grid structure
    renderWorkPackageGridStructure(baseX, baseY, columnPositions, workPackageLayouts, totalWidth, sortedColumns);

    updateConnections();
    callbacks.updateMinimap();
    log('info', `Matrix layout applied: ${workPackages.length} packages, ${Object.keys(groups).length} groups`);

    // Render thumbnails for diagram groups after layout
    setTimeout(() => {
        renderGroupThumbnails();
        callbacks.reRenderAllDiagrams();
    }, 500);
}

/**
 * Get enhanced sorted columns with fixed order
 */
function getEnhancedSortedColumns() {
    // Fixed column order based on abstraction hierarchy
    const COLUMN_ORDER = [
        'persona',       // Edge position (left)
        'epic',          // High-level
        'requirement',   // Mid-level
        'entity',        // Data model
        'user-story',    // Mid-level
        'user-flow',     // Mid-level
        'diagram',       // Visual artifacts
        'screen',        // UI
        'component',     // Technical
        'test',          // Quality
        'task',          // Work items
        'api',           // Technical
        'tech-stack'     // Infrastructure
    ];

    return WORKPACKAGE_COLUMNS
        .filter(col => {
            // Check if any nodes exist for this column type
            const hasNodes = Object.values(state.nodes).some(n => getWorkPackageColumn(n) === col.id);
            return hasNodes || col.id === 'diagram' || col.id === 'requirement';
        })
        .sort((a, b) => {
            const orderA = COLUMN_ORDER.indexOf(a.id);
            const orderB = COLUMN_ORDER.indexOf(b.id);
            return (orderA === -1 ? 99 : orderA) - (orderB === -1 ? 99 : orderB);
        });
}

/**
 * Clean up previously created group nodes
 */
function cleanupGroupNodes() {
    createdGroupNodes.forEach(groupId => {
        const element = document.querySelector(`[data-group-id="${groupId}"]`);
        if (element) {
            element.remove();
        }
    });
    createdGroupNodes.clear();
}

/**
 * Create or update a collapsed group node
 */
function createOrUpdateGroupNode(groupKey, group, x, y, size) {
    let groupNode = document.querySelector(`[data-group-id="${groupKey}"]`);

    if (!groupNode) {
        groupNode = document.createElement('div');
        groupNode.className = `canvas-node node-group node-group-${group.childType}`;
        groupNode.dataset.groupId = groupKey;
        groupNode.dataset.parentId = group.parentId;
        groupNode.dataset.childType = group.childType;

        const stats = getGroupStats(group);

        // Build content based on group type
        let content = '';

        if (group.childType === 'diagram') {
            // Diagram group with mini thumbnails
            const previewDiagrams = group.children.slice(0, 4);
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-thumbnails">
                    ${previewDiagrams.map(id => {
                        const type = getDiagramTypeFromId(id);
                        const icon = DIAGRAM_TYPES[type]?.icon || '📊';
                        return `<div class="thumb-cell" data-diagram-id="${escapeHtml(id)}" title="${type}">
                            <span class="thumb-icon">${icon}</span>
                        </div>`;
                    }).join('')}
                </div>
                <div class="group-expand" onclick="window.openDiagramGallery('${escapeHtml(group.parentId)}')">
                    Alle anzeigen →
                </div>
            `;
        } else if (group.childType === 'test') {
            // Test group
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-stats">
                    <span>${stats.scenarioCount || 0} Scenarios</span>
                </div>
                <div class="group-expand" onclick="window.openTestCasesModal('${escapeHtml(group.parentId)}')">
                    Alle anzeigen →
                </div>
            `;
        } else if (group.childType === 'user-story') {
            // User story group (for epics)
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-expand" onclick="window.openUserStoriesModal('${escapeHtml(group.parentId)}')">
                    Alle anzeigen →
                </div>
            `;
        } else if (group.childType === 'requirement') {
            // Requirement group (for epics)
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-preview">
                    ${group.children.slice(0, 3).map(id => {
                        const node = state.nodes[id];
                        const title = node?.data?.title || node?.data?.id || id;
                        return `<div class="group-preview-item" title="${escapeHtml(title)}">${escapeHtml(title.slice(0, 25))}${title.length > 25 ? '...' : ''}</div>`;
                    }).join('')}
                    ${group.children.length > 3 ? `<div class="group-preview-more">+${group.children.length - 3} weitere</div>` : ''}
                </div>
                <div class="group-expand" onclick="window.openRequirementsModal('${escapeHtml(group.parentId)}', '${escapeHtml(groupKey)}')">
                    Alle anzeigen →
                </div>
            `;
        } else if (group.childType === 'task') {
            // Task group (for epics)
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-expand" onclick="window.openTasksModal('${escapeHtml(group.parentId)}', '${escapeHtml(groupKey)}')">
                    Alle anzeigen →
                </div>
            `;
        } else if (group.childType === 'entity') {
            // Entity group (for requirements)
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
                <div class="group-expand" onclick="window.openEntitiesModal('${escapeHtml(group.parentId)}', '${escapeHtml(groupKey)}')">
                    Alle anzeigen →
                </div>
            `;
        } else {
            // Generic group
            content = `
                <div class="group-header">
                    <span class="group-icon">${stats.icon}</span>
                    <span class="group-count">${stats.text}</span>
                </div>
            `;
        }

        groupNode.innerHTML = content;

        // Add to canvas
        const container = document.getElementById('canvas-nodes');
        if (container) {
            container.appendChild(groupNode);
        }

        createdGroupNodes.add(groupKey);
    }

    // Position the group node
    groupNode.style.left = `${x}px`;
    groupNode.style.top = `${y}px`;
    groupNode.style.width = `${size.width}px`;
    groupNode.style.minHeight = `${size.height}px`;
}

/**
 * Render diagram thumbnails for all group nodes
 */
async function renderGroupThumbnails() {
    const thumbCells = document.querySelectorAll('.thumb-cell[data-diagram-id]');

    for (const cell of thumbCells) {
        if (cell.dataset.rendered === 'true') continue;

        const diagramId = cell.dataset.diagramId;
        const node = state.nodes[diagramId];

        if (node?.data?.mermaid_code) {
            try {
                await renderDiagramThumbnail(diagramId, node.data.mermaid_code, cell, 40);
                cell.dataset.rendered = 'true';
            } catch (e) {
                // Keep icon on error
                console.warn(`[Matrix] Thumbnail error for ${diagramId}:`, e);
            }
        }
    }
}

// ============================================
// Grid Structure Rendering
// ============================================

function renderWorkPackageGridStructure(baseX, baseY, columnPositions, workPackageLayouts, totalWidth, sortedColumns) {
    const existing = document.getElementById('matrix-grid-structure');
    if (existing) existing.remove();

    const container = document.getElementById('canvas-nodes');
    if (!container) return;

    const gridStructure = document.createElement('div');
    gridStructure.id = 'matrix-grid-structure';
    gridStructure.className = 'matrix-grid-structure workpackage-layout';

    const rowHeaderWidth = 220;

    const totalHeight = workPackageLayouts.reduce((sum, wp) => sum + wp.height, 0) +
                       workPackageLayouts.length * 60 + 100;

    // Column headers
    sortedColumns.forEach((col, index) => {
        const colData = columnPositions[col.id];
        const header = document.createElement('div');
        header.className = 'matrix-column-header workpackage-col-header';
        header.style.left = `${colData.x}px`;
        header.style.top = `${baseY}px`;
        header.style.width = `${colData.width - 10}px`;
        header.style.borderBottomColor = col.color;
        header.textContent = col.name;
        gridStructure.appendChild(header);

        if (index > 0) {
            const line = document.createElement('div');
            line.className = 'matrix-grid-line-vertical workpackage-col-line';
            line.style.left = `${colData.x}px`;
            line.style.top = `${baseY + 50}px`;
            line.style.height = `${totalHeight}px`;
            gridStructure.appendChild(line);
        }
    });

    // Row headers and backgrounds with Feature separators
    workPackageLayouts.forEach((wp, index) => {
        const rootCol = WORKPACKAGE_COLUMNS.find(c => c.id === wp.rootType);
        const wpColor = rootCol ? rootCol.color : '#7856ff';

        // Count epics (Arbeitspakete) within this feature
        const epicCount = wp.nodes ? wp.nodes.filter(n => {
            const nodeData = state.nodes[n.id];
            return nodeData?.type === 'epic';
        }).length : 0;

        // Feature Separator Banner (full width)
        const separator = document.createElement('div');
        separator.className = 'workpackage-separator feature-separator';
        separator.style.left = `${baseX}px`;
        separator.style.top = `${wp.y - 35}px`;
        separator.style.width = `${totalWidth}px`;
        separator.style.borderColor = wpColor;
        separator.innerHTML = `
            <span class="wp-badge feature-badge" style="background: ${wpColor}">🎯 Feature ${index + 1}</span>
            <span class="wp-name">${wp.name}</span>
            <span class="wp-stats">${epicCount > 0 ? `${epicCount} Arbeitspakete` : ''} · ${wp.nodeCount} Elemente</span>
        `;
        gridStructure.appendChild(separator);

        // Row header (left side)
        const header = document.createElement('div');
        header.className = `matrix-row-header workpackage-row-header ${wp.isOrphanPackage ? 'orphan-package' : ''}`;
        header.style.left = `${baseX}px`;
        header.style.top = `${wp.y}px`;
        header.style.width = `${rowHeaderWidth - 10}px`;
        header.style.height = `${Math.min(wp.height, 80)}px`;
        header.style.borderLeftColor = wpColor;

        header.innerHTML = `
            <span class="row-label">${wp.name}</span>
            <span class="row-count">${wp.nodeCount} Nodes</span>
        `;
        gridStructure.appendChild(header);

        // Row background with gradient based on work package color
        const rowBg = document.createElement('div');
        rowBg.className = `matrix-row-bg ${wp.isOrphanPackage ? 'orphan-row-bg' : ''}`;
        rowBg.style.left = `${baseX + rowHeaderWidth}px`;
        rowBg.style.top = `${wp.y}px`;
        rowBg.style.width = `${totalWidth - rowHeaderWidth}px`;
        rowBg.style.height = `${wp.height}px`;
        rowBg.style.background = wp.isOrphanPackage
            ? 'rgba(255, 100, 100, 0.08)'
            : `linear-gradient(90deg, ${wpColor}08 0%, transparent 30%)`;
        rowBg.style.borderLeft = `3px solid ${wpColor}40`;
        gridStructure.appendChild(rowBg);

        // Horizontal separator line
        const line = document.createElement('div');
        line.className = 'matrix-grid-line-horizontal workpackage-divider';
        line.style.left = `${baseX}px`;
        line.style.top = `${wp.y}px`;
        line.style.width = `${totalWidth}px`;
        line.style.borderTopColor = wpColor;
        gridStructure.appendChild(line);

        // Epic (Arbeitspaket) bands and separators within this Feature
        const epicPositions = wp.epicPositions || [];
        if (epicPositions.length > 0) {
            const epicColData = columnPositions['epic'];
            const epicColX = epicColData ? epicColData.x : baseX + rowHeaderWidth;

            epicPositions.forEach((epic, epicIndex) => {
                // Add subtle background band for each Epic section
                const bandBg = document.createElement('div');
                bandBg.className = 'epic-band-bg';
                bandBg.style.left = `${baseX + rowHeaderWidth}px`;
                bandBg.style.top = `${epic.y}px`;
                bandBg.style.width = `${totalWidth - rowHeaderWidth}px`;
                bandBg.style.height = `${epic.height}px`;
                bandBg.style.background = epicIndex % 2 === 0
                    ? 'rgba(120, 86, 255, 0.03)'
                    : 'rgba(120, 86, 255, 0.06)';
                gridStructure.appendChild(bandBg);

                // Add separator AFTER each Epic band (except the last one)
                if (epicIndex < epicPositions.length - 1) {
                    const separatorY = epic.y + epic.height + (EPIC_GAP / 2) - 12;

                    const epicSeparator = document.createElement('div');
                    epicSeparator.className = 'epic-separator arbeitspaket-separator';
                    epicSeparator.style.left = `${baseX}px`;
                    epicSeparator.style.top = `${separatorY}px`;
                    epicSeparator.style.width = `${totalWidth}px`;
                    epicSeparator.innerHTML = `
                        <span class="ap-separator-badge">📦 AP ${epicIndex + 2}</span>
                        <span class="ap-separator-name">${epicPositions[epicIndex + 1].name}</span>
                    `;
                    gridStructure.appendChild(epicSeparator);
                }
            });
        }
    });

    // Bottom border
    if (workPackageLayouts.length > 0) {
        const lastWp = workPackageLayouts[workPackageLayouts.length - 1];
        const bottomLine = document.createElement('div');
        bottomLine.className = 'matrix-grid-line-horizontal';
        bottomLine.style.left = `${baseX}px`;
        bottomLine.style.top = `${lastWp.y + lastWp.height}px`;
        bottomLine.style.width = `${totalWidth}px`;
        gridStructure.appendChild(bottomLine);
    }

    container.insertBefore(gridStructure, container.firstChild);
}

// ============================================
// Real-Time Matrix Node Updates
// ============================================

/**
 * Handle real-time matrix node additions from the pipeline.
 * Listens for 'matrix:node-added' events and updates the layout.
 */
let matrixUpdateDebounceTimer = null;

window.addEventListener('matrix:node-added', (event) => {
    const nodeData = event.detail;
    log('info', `Matrix node added: ${nodeData.id} (${nodeData.type}) -> row:${nodeData.row}`);

    // Debounce layout updates to avoid excessive redraws during batch operations
    if (matrixUpdateDebounceTimer) {
        clearTimeout(matrixUpdateDebounceTimer);
    }

    matrixUpdateDebounceTimer = setTimeout(() => {
        // Check if matrix layout is currently active
        const matrixBtn = document.querySelector('[data-layout="by_matrix"]');
        if (matrixBtn && matrixBtn.classList.contains('active')) {
            log('info', 'Refreshing matrix layout for new nodes...');
            requestAnimationFrame(() => reorganizeNodesMatrix());
        }
    }, 500); // Wait 500ms for batch updates
});

/**
 * Handle matrix step completion events.
 * Shows a notification when a pipeline step completes.
 */
window.addEventListener('matrix:step-complete', (event) => {
    const { step_number, step_name, node_count } = event.detail;
    log('info', `Step ${step_number}/15 complete: ${step_name} (${node_count} nodes)`);
});

// ============================================
// Group Modal Functions
// ============================================

/**
 * Show modal with list of grouped requirements
 */
window.openRequirementsModal = function(parentId, groupKey) {
    const groups = state.groupState?.groups || {};
    const group = groups[groupKey];
    if (!group) return;

    showGroupModal('Requirements', '📝', group.children, (nodeId) => {
        const node = state.nodes[nodeId];
        const title = node?.data?.title || 'Untitled';
        const id = node?.data?.id || nodeId;
        const description = node?.data?.description || '';
        const priority = node?.data?.priority || 'medium';

        return `
            <div class="modal-item requirement-item" onclick="window.focusNode('${escapeHtml(nodeId)}')" data-node-id="${escapeHtml(nodeId)}">
                <div class="item-header">
                    <span class="item-type-tag" style="background: #1d9bf0">REQ</span>
                    <span class="item-id">${escapeHtml(id)}</span>
                    <span class="item-priority priority-${priority}">${priority}</span>
                </div>
                <div class="item-title">${escapeHtml(title)}</div>
                ${description ? `<div class="item-description">${escapeHtml(description.slice(0, 100))}${description.length > 100 ? '...' : ''}</div>` : ''}
            </div>
        `;
    });
};

/**
 * Show modal with list of grouped tasks
 */
window.openTasksModal = function(parentId, groupKey) {
    const groups = state.groupState?.groups || {};
    const group = groups[groupKey];
    if (!group) return;

    showGroupModal('Tasks', '📋', group.children, (nodeId) => {
        const node = state.nodes[nodeId];
        const title = node?.data?.title || 'Untitled';
        const taskType = node?.data?.task_type || 'general';
        const hours = node?.data?.estimated_hours || '?';
        const complexity = node?.data?.complexity || 'medium';

        return `
            <div class="modal-item task-item" onclick="window.focusNode('${escapeHtml(nodeId)}')" data-node-id="${escapeHtml(nodeId)}">
                <div class="item-header">
                    <span class="item-type-tag" style="background: #f59e0b">TASK</span>
                    <span class="item-task-type">${escapeHtml(taskType)}</span>
                    <span class="item-hours">${hours}h</span>
                </div>
                <div class="item-title">${escapeHtml(title)}</div>
                <div class="item-meta">Complexity: ${escapeHtml(complexity)}</div>
            </div>
        `;
    });
};

/**
 * Show modal with list of grouped entities
 */
window.openEntitiesModal = function(parentId, groupKey) {
    const groups = state.groupState?.groups || {};
    const group = groups[groupKey];
    if (!group) return;

    showGroupModal('Entities', '💾', group.children, (nodeId) => {
        const node = state.nodes[nodeId];
        const name = node?.data?.name || node?.data?.title || 'Unnamed';
        const description = node?.data?.description || '';
        const fieldCount = node?.data?.fields?.length || 0;

        return `
            <div class="modal-item entity-item" onclick="window.focusNode('${escapeHtml(nodeId)}')" data-node-id="${escapeHtml(nodeId)}">
                <div class="item-header">
                    <span class="item-type-tag" style="background: #14b8a6">ENT</span>
                    <span class="item-name">${escapeHtml(name)}</span>
                    ${fieldCount > 0 ? `<span class="item-field-count">${fieldCount} fields</span>` : ''}
                </div>
                ${description ? `<div class="item-description">${escapeHtml(description.slice(0, 80))}${description.length > 80 ? '...' : ''}</div>` : ''}
            </div>
        `;
    });
};

/**
 * Show modal with list of grouped user stories
 */
window.openUserStoriesModal = function(parentId) {
    const groups = state.groupState?.groups || {};
    const groupKey = `${parentId}-user-story`;
    const group = groups[groupKey];
    if (!group) return;

    showGroupModal('User Stories', '📖', group.children, (nodeId) => {
        const node = state.nodes[nodeId];
        const title = node?.data?.title || 'Untitled';
        const persona = node?.data?.persona || 'user';
        const action = node?.data?.action || '';

        return `
            <div class="modal-item story-item" onclick="window.focusNode('${escapeHtml(nodeId)}')" data-node-id="${escapeHtml(nodeId)}">
                <div class="item-header">
                    <span class="item-type-tag" style="background: #00ba7c">US</span>
                    <span class="item-persona">As ${escapeHtml(persona)}</span>
                </div>
                <div class="item-title">${escapeHtml(title)}</div>
                ${action ? `<div class="item-action">"${escapeHtml(action.slice(0, 60))}${action.length > 60 ? '...' : ''}"</div>` : ''}
            </div>
        `;
    });
};

/**
 * Generic function to create and show a group modal
 */
function showGroupModal(title, icon, children, renderItem) {
    // Remove existing modal
    const existingModal = document.getElementById('group-modal');
    if (existingModal) existingModal.remove();

    // Create modal
    const modal = document.createElement('div');
    modal.id = 'group-modal';
    modal.className = 'group-modal';

    const itemsHtml = children.map(nodeId => renderItem(nodeId)).join('');

    modal.innerHTML = `
        <div class="modal-backdrop" onclick="window.closeGroupModal()"></div>
        <div class="modal-content">
            <div class="modal-header">
                <span class="modal-icon">${icon}</span>
                <span class="modal-title">${title} (${children.length})</span>
                <button class="modal-close" onclick="window.closeGroupModal()">×</button>
            </div>
            <div class="modal-body">
                ${itemsHtml}
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Animate in
    requestAnimationFrame(() => {
        modal.classList.add('visible');
    });
}

/**
 * Close the group modal
 */
window.closeGroupModal = function() {
    const modal = document.getElementById('group-modal');
    if (modal) {
        modal.classList.remove('visible');
        setTimeout(() => modal.remove(), 200);
    }
};

/**
 * Focus on a node and optionally show its detail panel
 */
window.focusNode = function(nodeId) {
    // Close modal first
    window.closeGroupModal();

    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    // If node is hidden (in collapsed group), expand the group first
    if (nodeData.element && nodeData.element.style.display === 'none') {
        // Find and expand the group
        const groups = state.groupState?.groups || {};
        for (const [groupKey, group] of Object.entries(groups)) {
            if (group.children.includes(nodeId)) {
                // Import and call expandGroup
                import('./index.js').then(module => {
                    module.expandGroup(groupKey);
                    // Re-layout and then focus
                    setTimeout(() => {
                        reorganizeNodesMatrix();
                        setTimeout(() => focusOnNode(nodeId), 300);
                    }, 100);
                });
                return;
            }
        }
    }

    focusOnNode(nodeId);
};

/**
 * Actually focus the canvas on a node
 */
function focusOnNode(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    const x = nodeData.x || 0;
    const y = nodeData.y || 0;

    // Calculate center position
    const container = elements.canvasContainer;
    if (!container) return;

    const containerRect = container.getBoundingClientRect();
    const centerX = containerRect.width / 2;
    const centerY = containerRect.height / 2;

    // Set canvas position to center on node
    const zoom = state.canvas.zoom || 1;
    state.canvas.x = centerX - x * zoom - 150;  // 150 = approximate half node width
    state.canvas.y = centerY - y * zoom - 80;   // 80 = approximate half node height

    // Apply transform
    const canvas = elements.canvas;
    if (canvas) {
        canvas.style.transform = `translate(${state.canvas.x}px, ${state.canvas.y}px) scale(${zoom})`;
    }

    // Highlight the node briefly
    if (nodeData.element) {
        nodeData.element.classList.add('node-highlight');
        setTimeout(() => {
            nodeData.element.classList.remove('node-highlight');
        }, 2000);
    }

    // Show detail panel
    if (window.showDetailPanel) {
        window.showDetailPanel(nodeId, nodeData);
    }
}
