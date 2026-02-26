/**
 * RE System Dashboard - Node Grouping Module
 *
 * Provides grouping logic for collapsing related nodes:
 * - Requirement → Diagrams (6 per requirement)
 * - Epic → User Stories
 * - Requirement → Test Cases
 * - Persona → User Flows
 */

import { state } from '../state.js';

// ============================================
// Grouping Rules Configuration
// ============================================

export const GROUPING_RULES = {
    // Requirement → Diagrams (always collapsed, 6 diagrams per requirement)
    'requirement-diagrams': {
        parentType: 'requirement',
        childType: 'diagram',
        collapseThreshold: 1,  // Always collapse
        alwaysCollapse: true,
        badgeText: (count) => `${count} Diagrams`,
        badgeIcon: '📊',
        groupNodeWidth: 200,
        groupNodeHeight: 160
    },

    // Epic → User Stories (collapse when > 4)
    'epic-stories': {
        parentType: 'epic',
        childType: 'user-story',
        collapseThreshold: 4,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Stories`,
        badgeIcon: '📖',
        groupNodeWidth: 220,
        groupNodeHeight: 140
    },

    // Requirement → Test Cases (collapse when > 3)
    'requirement-tests': {
        parentType: 'requirement',
        childType: 'test',
        collapseThreshold: 3,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Tests`,
        badgeIcon: '🧪',
        groupNodeWidth: 180,
        groupNodeHeight: 120
    },

    // User Story → Test Cases (collapse when > 2)
    'user-story-tests': {
        parentType: 'user-story',
        childType: 'test',
        collapseThreshold: 2,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Tests`,
        badgeIcon: '🧪',
        groupNodeWidth: 180,
        groupNodeHeight: 120
    },

    // Persona → User Flows (for edge positioning)
    'persona-flows': {
        parentType: 'persona',
        childType: 'user-flow',
        collapseThreshold: 2,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Flows`,
        badgeIcon: '🔀',
        groupNodeWidth: 180,
        groupNodeHeight: 120,
        positioning: 'edge-left'  // Special positioning flag
    },

    // Epic → Tasks (collapse when > 3)
    'epic-tasks': {
        parentType: 'epic',
        childType: 'task',
        collapseThreshold: 3,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Tasks`,
        badgeIcon: '📋',
        groupNodeWidth: 200,
        groupNodeHeight: 130
    },

    // Epic → Requirements (collapse when > 3)
    'epic-requirements': {
        parentType: 'epic',
        childType: 'requirement',
        collapseThreshold: 3,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Requirements`,
        badgeIcon: '📝',
        groupNodeWidth: 250,
        groupNodeHeight: 150
    },

    // Epic → Data Requirements (requirements with type="data")
    'epic-data-requirements': {
        parentType: 'epic',
        childType: 'requirement',
        childFilter: (node) => node.data?.type === 'data',
        collapseThreshold: 2,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Data Reqs`,
        badgeIcon: '💾',
        groupNodeWidth: 220,
        groupNodeHeight: 140
    },

    // Feature → Data Requirements
    'feature-data-requirements': {
        parentType: 'feature',
        childType: 'requirement',
        childFilter: (node) => node.data?.type === 'data',
        collapseThreshold: 2,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Data Reqs`,
        badgeIcon: '💾',
        groupNodeWidth: 220,
        groupNodeHeight: 140
    },

    // Requirement → Entities (Data Model)
    'requirement-entities': {
        parentType: 'requirement',
        childType: 'entity',
        collapseThreshold: 2,
        alwaysCollapse: false,
        badgeText: (count) => `${count} Entities`,
        badgeIcon: '💾',
        groupNodeWidth: 220,
        groupNodeHeight: 140
    }
};

// ============================================
// Diagram Type Utilities
// ============================================

export const DIAGRAM_TYPES = {
    'flowchart': { icon: '📈', name: 'Flowchart', order: 0 },
    'sequence': { icon: '↔️', name: 'Sequence', order: 1 },
    'class': { icon: '🏛️', name: 'Class', order: 2 },
    'er': { icon: '🔗', name: 'ER', order: 3 },
    'state': { icon: '🔄', name: 'State', order: 4 },
    'c4': { icon: '🏢', name: 'C4', order: 5 }
};

/**
 * Detect diagram type from mermaid code
 */
export function getDiagramTypeFromCode(code) {
    if (!code) return 'flowchart';
    const codeLower = code.toLowerCase().trim();
    if (codeLower.startsWith('classdiagram')) return 'class';
    if (codeLower.startsWith('sequencediagram')) return 'sequence';
    if (codeLower.startsWith('erdiagram')) return 'er';
    if (codeLower.startsWith('c4')) return 'c4';
    if (codeLower.startsWith('statediagram')) return 'state';
    return 'flowchart';
}

/**
 * Get diagram type from node ID
 * Supports multiple formats:
 * - "REQ-001_flowchart" → "flowchart" (underscore separator)
 * - "REQ-001-flowchart" → "flowchart" (hyphen separator - from nodeFactory)
 */
export function getDiagramTypeFromId(nodeId) {
    if (!nodeId) return 'flowchart';

    // First try underscore separator
    const underscoreParts = nodeId.split('_');
    if (underscoreParts.length > 1) {
        const lastPart = underscoreParts[underscoreParts.length - 1].toLowerCase();
        if (DIAGRAM_TYPES[lastPart]) return lastPart;
    }

    // Then try hyphen separator (from nodeFactory.js)
    const hyphenParts = nodeId.split('-');
    if (hyphenParts.length > 1) {
        const lastPart = hyphenParts[hyphenParts.length - 1].toLowerCase();
        if (DIAGRAM_TYPES[lastPart]) return lastPart;
    }

    return 'flowchart';
}

/**
 * Get parent requirement ID from diagram node ID
 * Supports multiple formats:
 * - "REQ-001_flowchart" → "REQ-001" (underscore separator)
 * - "REQ-001-flowchart" → "REQ-001" (hyphen separator - from nodeFactory)
 * - "REQ-f359e5-000-flowchart" → "REQ-f359e5-000" (complex IDs)
 */
export function getParentIdFromDiagramId(diagramId) {
    if (!diagramId) return null;

    // Define known diagram types
    const diagramTypes = ['flowchart', 'sequence', 'class', 'er', 'state', 'c4'];

    // First try underscore separator (new format)
    const underscoreParts = diagramId.split('_');
    if (underscoreParts.length > 1) {
        const lastPart = underscoreParts[underscoreParts.length - 1].toLowerCase();
        if (diagramTypes.includes(lastPart)) {
            return underscoreParts.slice(0, -1).join('_');
        }
    }

    // Then try hyphen separator (from nodeFactory.js)
    // Look for diagram type at the end after last hyphen
    const hyphenParts = diagramId.split('-');
    if (hyphenParts.length > 1) {
        const lastPart = hyphenParts[hyphenParts.length - 1].toLowerCase();
        if (diagramTypes.includes(lastPart)) {
            return hyphenParts.slice(0, -1).join('-');
        }
    }

    return null;
}

// ============================================
// Group Detection
// ============================================

/**
 * Find all diagrams connected to a specific node (in any direction)
 * @param {string} nodeId - The parent node ID
 * @param {Object} nodes - All nodes
 * @param {Array} connections - All connections
 * @returns {Array} Array of connected diagram node IDs
 */
function findConnectedDiagrams(nodeId, nodes, connections) {
    const diagrams = new Set();

    // 1. Find by direct connections (both directions)
    connections.forEach(conn => {
        // Check if connection involves the parent node
        if (conn.from === nodeId) {
            const targetNode = nodes[conn.to];
            if (targetNode?.type === 'diagram') {
                diagrams.add(conn.to);
            }
        }
        if (conn.to === nodeId) {
            const sourceNode = nodes[conn.from];
            if (sourceNode?.type === 'diagram') {
                diagrams.add(conn.from);
            }
        }
    });

    // 2. Find by ID pattern (e.g., REQ-001_flowchart belongs to REQ-001)
    Object.keys(nodes).forEach(diagramId => {
        const node = nodes[diagramId];
        if (node?.type === 'diagram') {
            const parentFromId = getParentIdFromDiagramId(diagramId);
            if (parentFromId === nodeId) {
                diagrams.add(diagramId);
            }
        }
    });

    // 3. Also check if diagram ID contains the parent ID anywhere
    // This catches patterns like "AUTO-001_c4" or "REQ-001-flowchart" for parent "REQ-001"
    Object.keys(nodes).forEach(diagramId => {
        const node = nodes[diagramId];
        if (node?.type === 'diagram' && !diagrams.has(diagramId)) {
            // Check if diagram ID starts with parent ID followed by underscore or hyphen
            if (diagramId.startsWith(nodeId + '_') || diagramId.startsWith(nodeId + '-')) {
                // Verify this is actually a diagram type suffix (not just another ID segment)
                const diagramTypes = ['flowchart', 'sequence', 'class', 'er', 'state', 'c4'];
                const suffix = diagramId.slice(nodeId.length + 1).toLowerCase();
                if (diagramTypes.includes(suffix)) {
                    diagrams.add(diagramId);
                }
            }
        }
    });

    return Array.from(diagrams);
}

/**
 * Detect node groups based on GROUPING_RULES and connections
 * @returns {Object} Map of parentId → { children: [nodeIds], type: string, collapsed: boolean, rule: object }
 */
export function detectNodeGroups() {
    const groups = {};
    const connections = state.connections || [];
    const nodes = state.nodes || {};

    // Track which diagrams have been assigned to a group
    const assignedDiagrams = new Set();

    // 1. First, find all diagram groups for requirements/epics
    // Check all potential parent types that can have diagrams
    const parentTypes = ['requirement', 'epic', 'user-story'];

    Object.entries(nodes).forEach(([nodeId, node]) => {
        if (!parentTypes.includes(node.type)) return;

        // Find all diagrams connected to this node
        const connectedDiagrams = findConnectedDiagrams(nodeId, nodes, connections);

        if (connectedDiagrams.length > 0) {
            console.log(`[Grouping] Found ${connectedDiagrams.length} diagrams for ${nodeId}:`, connectedDiagrams);

            const groupKey = `${nodeId}-diagram`;
            const rule = GROUPING_RULES['requirement-diagrams'];

            groups[groupKey] = {
                parentId: nodeId,
                children: connectedDiagrams,
                childType: 'diagram',
                ruleKey: 'requirement-diagrams',
                rule: rule,
                collapsed: rule.alwaysCollapse || connectedDiagrams.length > rule.collapseThreshold
            };

            connectedDiagrams.forEach(id => assignedDiagrams.add(id));
        }
    });

    // 2. Build parent-child relationships for other types (tests, user-stories, etc.)
    // Track which child nodes match which rules (a node can match multiple rules)
    const childMatches = {}; // childId -> [{ parent, ruleKey }]

    connections.forEach(conn => {
        const fromNode = nodes[conn.from];
        const toNode = nodes[conn.to];

        if (!fromNode || !toNode) return;

        // Skip diagrams - they're already handled above
        if (fromNode.type === 'diagram' || toNode.type === 'diagram') return;

        // Check each grouping rule (except diagram rule)
        Object.entries(GROUPING_RULES).forEach(([ruleKey, rule]) => {
            if (ruleKey === 'requirement-diagrams') return; // Skip diagram rule

            // Check if this connection matches the rule (parent → child)
            if (fromNode.type === rule.parentType && toNode.type === rule.childType) {
                // Apply childFilter if defined
                if (rule.childFilter && !rule.childFilter(toNode)) return;

                if (!childMatches[conn.to]) childMatches[conn.to] = [];
                // Avoid duplicates
                if (!childMatches[conn.to].some(m => m.parent === conn.from && m.ruleKey === ruleKey)) {
                    childMatches[conn.to].push({ parent: conn.from, ruleKey });
                }
            }
            // Also check reverse direction (child → parent)
            if (toNode.type === rule.parentType && fromNode.type === rule.childType) {
                // Apply childFilter if defined
                if (rule.childFilter && !rule.childFilter(fromNode)) return;

                if (!childMatches[conn.from]) childMatches[conn.from] = [];
                if (!childMatches[conn.from].some(m => m.parent === conn.to && m.ruleKey === ruleKey)) {
                    childMatches[conn.from].push({ parent: conn.to, ruleKey });
                }
            }
        });
    });

    // 3. Group children by parent for non-diagram types
    Object.entries(childMatches).forEach(([childId, matches]) => {
        matches.forEach(({ parent: parentId, ruleKey }) => {
            const rule = GROUPING_RULES[ruleKey];
            if (!rule) return;

            // Use ruleKey suffix for filtered groups to distinguish them
            const groupSuffix = rule.childFilter ? ruleKey.split('-').slice(1).join('-') : rule.childType;
            const groupKey = `${parentId}-${groupSuffix}`;

            if (!groups[groupKey]) {
                groups[groupKey] = {
                    parentId,
                    children: [],
                    childType: rule.childType,
                    ruleKey,
                    rule,
                    collapsed: false
                };
            }

            if (!groups[groupKey].children.includes(childId)) {
                groups[groupKey].children.push(childId);
            }
        });
    });

    // Determine collapse state based on thresholds
    Object.values(groups).forEach(group => {
        const rule = group.rule;
        if (rule.alwaysCollapse) {
            group.collapsed = true;
        } else if (group.children.length > rule.collapseThreshold) {
            group.collapsed = true;
        }
    });

    return groups;
}

/**
 * Find which group a node belongs to (if any)
 * @param {string} nodeId - Node ID to check
 * @param {Object} groups - Groups from detectNodeGroups()
 * @returns {string|null} Group key or null
 */
export function findNodeGroup(nodeId, groups) {
    for (const [groupKey, group] of Object.entries(groups)) {
        if (group.children.includes(nodeId)) {
            return groupKey;
        }
    }
    return null;
}

/**
 * Check if a node should be hidden (because it's in a collapsed group)
 * @param {string} nodeId - Node ID to check
 * @param {Object} groups - Groups from detectNodeGroups()
 * @returns {boolean}
 */
export function isNodeHiddenInGroup(nodeId, groups) {
    const groupKey = findNodeGroup(nodeId, groups);
    if (!groupKey) return false;
    return groups[groupKey].collapsed;
}

/**
 * Get all diagram types present in a group
 * @param {Array} childIds - Array of diagram node IDs
 * @returns {Object} Map of type → count
 */
export function getDiagramTypeCounts(childIds) {
    const counts = {};
    childIds.forEach(id => {
        const type = getDiagramTypeFromId(id);
        counts[type] = (counts[type] || 0) + 1;
    });
    return counts;
}

/**
 * Get group statistics for display
 * @param {Object} group - Group object
 * @returns {Object} Statistics
 */
export function getGroupStats(group) {
    const stats = {
        count: group.children.length,
        icon: group.rule.badgeIcon,
        text: group.rule.badgeText(group.children.length)
    };

    // Add diagram type breakdown for diagram groups
    if (group.childType === 'diagram') {
        stats.typeCounts = getDiagramTypeCounts(group.children);
        stats.types = Object.entries(stats.typeCounts)
            .sort((a, b) => (DIAGRAM_TYPES[a[0]]?.order || 99) - (DIAGRAM_TYPES[b[0]]?.order || 99))
            .map(([type, count]) => ({
                type,
                count,
                icon: DIAGRAM_TYPES[type]?.icon || '📊',
                name: DIAGRAM_TYPES[type]?.name || type
            }));
    }

    // Add scenario count for test groups
    if (group.childType === 'test') {
        stats.scenarioCount = group.children.reduce((sum, id) => {
            const node = state.nodes[id];
            return sum + (node?.data?.scenario_count || 0);
        }, 0);
    }

    return stats;
}

// ============================================
// Group State Management
// ============================================

// Store for user-toggled group states (persists during session)
const groupStateOverrides = {
    expanded: new Set(),   // Groups user explicitly expanded
    collapsed: new Set()   // Groups user explicitly collapsed
};

/**
 * Toggle group collapse state
 * @param {string} groupKey - Group key to toggle
 */
export function toggleGroupCollapse(groupKey) {
    if (groupStateOverrides.expanded.has(groupKey)) {
        groupStateOverrides.expanded.delete(groupKey);
        groupStateOverrides.collapsed.add(groupKey);
    } else if (groupStateOverrides.collapsed.has(groupKey)) {
        groupStateOverrides.collapsed.delete(groupKey);
        groupStateOverrides.expanded.add(groupKey);
    } else {
        // First toggle - expand if currently collapsed by default, collapse if expanded
        groupStateOverrides.expanded.add(groupKey);
    }

    // Dispatch event for layout update
    window.dispatchEvent(new CustomEvent('group:toggle', {
        detail: { groupKey }
    }));
}

/**
 * Check if a group is collapsed (considering user overrides)
 * @param {string} groupKey - Group key
 * @param {Object} groups - Groups from detectNodeGroups()
 * @returns {boolean}
 */
export function isGroupCollapsed(groupKey, groups) {
    // User overrides take precedence
    if (groupStateOverrides.expanded.has(groupKey)) return false;
    if (groupStateOverrides.collapsed.has(groupKey)) return true;

    // Otherwise use default state from detection
    return groups[groupKey]?.collapsed || false;
}

/**
 * Force expand a group
 * @param {string} groupKey - Group key
 */
export function expandGroup(groupKey) {
    groupStateOverrides.collapsed.delete(groupKey);
    groupStateOverrides.expanded.add(groupKey);

    window.dispatchEvent(new CustomEvent('group:expanded', {
        detail: { groupKey }
    }));
}

/**
 * Force collapse a group
 * @param {string} groupKey - Group key
 */
export function collapseGroup(groupKey) {
    groupStateOverrides.expanded.delete(groupKey);
    groupStateOverrides.collapsed.add(groupKey);

    window.dispatchEvent(new CustomEvent('group:collapsed', {
        detail: { groupKey }
    }));
}

/**
 * Reset all group state overrides
 */
export function resetGroupStates() {
    groupStateOverrides.expanded.clear();
    groupStateOverrides.collapsed.clear();
}

// Export group state for external access
export function getGroupStateOverrides() {
    return {
        expanded: new Set(groupStateOverrides.expanded),
        collapsed: new Set(groupStateOverrides.collapsed)
    };
}
