/**
 * RE System Dashboard - Diagram KiloAgent Cascade Panel
 *
 * Provides KiloAgent cascade editing for Mermaid diagrams.
 * When a diagram is edited, changes cascade down the hierarchy:
 * - Epic: edit all linked Requirements + User Stories (many LLM calls)
 * - Requirement: edit linked User Stories (fewer LLM calls)
 * - User Story: edit just this node (1 LLM call)
 */

import { state, escapeHtml } from '../state.js';

// ============================================
// Panel State
// ============================================

let panelState = {
    diagramId: null,
    mermaidCode: null,
    parentNodeId: null,
    parentNodeType: null,
    cascadeNodes: [],       // [{id, type, depth, hasDiagram}]
    isProcessing: false,
    changeId: null,
    results: {},            // nodeId -> {success, suggested_mermaid, error, reasoning}
};

// ============================================
// Hierarchy Definitions
// ============================================

const DIAGRAM_SUFFIXES = [
    '_flowchart', '_sequence', '_class', '_er', '_state', '_c4',
    '-flowchart', '-sequence', '-class', '-er', '-state', '-c4',
];

const DOWNWARD_EDGE_TYPES = {
    'epic': ['epic-req', 'epic-story'],
    'requirement': ['req-story', 'req-diagram'],
    'user-story': ['story-test'],
};

// ============================================
// Parent Node Resolution
// ============================================

/**
 * Extract parent node ID from a diagram ID.
 * E.g., "REQ-001_flowchart" -> "REQ-001"
 */
function resolveParentNode(diagramId) {
    // Try suffix-based extraction
    for (const suffix of DIAGRAM_SUFFIXES) {
        if (diagramId.endsWith(suffix)) {
            const parentId = diagramId.slice(0, -suffix.length);
            const node = state.nodes[parentId];
            if (node) {
                return { nodeId: parentId, nodeType: node.type };
            }
        }
    }

    // Fallback: check connections for incoming edges to this diagram
    for (const conn of state.connections) {
        if (conn.to === diagramId) {
            const sourceNode = state.nodes[conn.from];
            if (sourceNode && sourceNode.type !== 'diagram') {
                return { nodeId: conn.from, nodeType: sourceNode.type };
            }
        }
    }

    // Last resort: the diagram itself is the target
    const node = state.nodes[diagramId];
    return {
        nodeId: diagramId,
        nodeType: node?.type || 'diagram',
    };
}

// ============================================
// Cascade Node Discovery (BFS)
// ============================================

/**
 * Find a diagram node belonging to a given node ID.
 */
function findNodeDiagram(nodeId) {
    for (const suffix of DIAGRAM_SUFFIXES) {
        const diagramId = nodeId + suffix;
        if (state.nodes[diagramId]) return diagramId;
    }
    // Check connections for outgoing diagram edges
    for (const conn of state.connections) {
        if (conn.from === nodeId) {
            const target = state.nodes[conn.to];
            if (target && target.type === 'diagram') return conn.to;
        }
    }
    return null;
}

/**
 * BFS traversal to find all downstream nodes that have diagrams.
 * Returns ordered list: Root -> Requirements -> User Stories
 */
function findCascadeNodes(parentNodeId, parentNodeType) {
    const result = [];
    const visited = new Set();
    const queue = [{ id: parentNodeId, depth: 0 }];

    while (queue.length > 0) {
        const { id, depth } = queue.shift();
        if (visited.has(id)) continue;
        visited.add(id);

        const node = state.nodes[id];
        if (!node) continue;

        // Skip root node (depth 0) - it's handled separately
        if (depth > 0) {
            const diagramId = findNodeDiagram(id);
            result.push({
                id,
                type: node.type,
                depth,
                hasDiagram: !!diagramId,
                diagramId: diagramId,
            });
        }

        // Find downstream connections
        const allowedTypes = DOWNWARD_EDGE_TYPES[node.type] || [];
        for (const conn of state.connections) {
            if (conn.from === id && !visited.has(conn.to)) {
                const targetNode = state.nodes[conn.to];
                if (targetNode && targetNode.type !== 'diagram') {
                    // If no allowed types defined, allow all non-diagram connections
                    if (allowedTypes.length === 0 || !conn.type || allowedTypes.includes(conn.type)) {
                        queue.push({ id: conn.to, depth: depth + 1 });
                    }
                }
            }
        }
    }

    return result;
}

// ============================================
// Panel Rendering
// ============================================

function getTypeLabel(type) {
    const labels = {
        'epic': 'Epic',
        'requirement': 'Requirement',
        'user-story': 'User Story',
        'test': 'Test',
        'task': 'Task',
        'diagram': 'Diagramm',
    };
    return labels[type] || type;
}

function renderCascadeTree(cascadeNodes, parentNodeId, parentNodeType) {
    if (cascadeNodes.length === 0) {
        return `<div class="cascade-empty">Keine verlinkten Nodes gefunden. Nur dieses Diagramm wird bearbeitet.</div>`;
    }

    const items = cascadeNodes.map(node => {
        const indent = '&nbsp;'.repeat(node.depth * 4);
        const diagramIcon = node.hasDiagram ? '📊' : '📄';
        const typeLabel = getTypeLabel(node.type);
        return `
            <div class="cascade-node-item" data-node-id="${escapeHtml(node.id)}">
                <span class="status-indicator pending"></span>
                <span class="cascade-node-indent">${indent}</span>
                <span class="cascade-node-icon">${diagramIcon}</span>
                <span class="cascade-node-label">${escapeHtml(node.id)}</span>
                <span class="cascade-node-type">${typeLabel}</span>
            </div>
        `;
    }).join('');

    const totalCalls = 1 + cascadeNodes.filter(n => n.hasDiagram).length;

    return `
        <div class="cascade-header">
            <span>Betroffene Artefakte</span>
            <span class="cascade-count">${cascadeNodes.length} Nodes, ~${totalCalls} LLM Calls</span>
        </div>
        <div class="cascade-root-item">
            <span class="status-indicator pending"></span>
            <span class="cascade-node-icon">📊</span>
            <span class="cascade-node-label">${escapeHtml(parentNodeId)}</span>
            <span class="cascade-node-type">${getTypeLabel(parentNodeType)} (Root)</span>
        </div>
        ${items}
    `;
}

/**
 * Open the KiloAgent cascade panel in the diagram modal.
 */
export function openDiagramKiloPanel(diagramId, mermaidCode) {
    const panel = document.getElementById('kilo-diagram-panel');
    if (!panel) return;

    // Toggle: if panel is visible and same diagram, close it
    if (panel.style.display !== 'none' && panelState.diagramId === diagramId) {
        panel.style.display = 'none';
        return;
    }

    // Resolve parent node
    const { nodeId, nodeType } = resolveParentNode(diagramId);

    // Find cascade nodes
    const cascadeNodes = findCascadeNodes(nodeId, nodeType);

    // Update state
    panelState = {
        diagramId,
        mermaidCode,
        parentNodeId: nodeId,
        parentNodeType: nodeType,
        cascadeNodes,
        isProcessing: false,
        changeId: null,
        results: {},
    };

    // Render panel
    const cascadeTreeHtml = renderCascadeTree(cascadeNodes, nodeId, nodeType);

    panel.innerHTML = `
        <div class="kilo-diagram-cascade-panel">
            <div class="kilo-header">
                <span class="kilo-icon">🤖</span>
                <span class="kilo-title">KiloAgent Cascade Edit</span>
                <span class="kilo-status" id="kilo-diagram-status"></span>
            </div>
            <div class="kilo-input-wrapper">
                <textarea
                    id="kilo-diagram-prompt"
                    class="kilo-prompt-input"
                    placeholder="Beschreibe die gewuenschte Aenderung am Diagramm..."
                    rows="2"
                ></textarea>
                <button type="button" class="btn-kilo-submit" id="btn-kilo-diagram-submit">
                    Senden
                </button>
            </div>
            <div class="cascade-preview" id="cascade-preview">
                ${cascadeTreeHtml}
            </div>
            <div class="cascade-progress" id="cascade-progress" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="cascade-progress-fill" style="width: 0%"></div>
                </div>
                <span class="progress-text" id="cascade-progress-text">0 / 0</span>
            </div>
            <div class="cascade-results" id="cascade-results"></div>
        </div>
    `;

    panel.style.display = 'block';

    // Setup submit handler
    const submitBtn = document.getElementById('btn-kilo-diagram-submit');
    if (submitBtn) {
        submitBtn.addEventListener('click', submitCascadeEdit);
    }

    // Allow Enter+Ctrl to submit
    const promptInput = document.getElementById('kilo-diagram-prompt');
    if (promptInput) {
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                submitCascadeEdit();
            }
        });
        promptInput.focus();
    }
}

// ============================================
// Submit & WebSocket Communication
// ============================================

function submitCascadeEdit() {
    if (panelState.isProcessing) return;

    const promptEl = document.getElementById('kilo-diagram-prompt');
    const prompt = promptEl?.value?.trim();
    if (!prompt) return;

    const submitBtn = document.getElementById('btn-kilo-diagram-submit');
    const statusEl = document.getElementById('kilo-diagram-status');

    panelState.isProcessing = true;
    panelState.results = {};

    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) {
        statusEl.textContent = 'Verarbeite...';
        statusEl.className = 'kilo-status processing';
    }

    // Show progress bar
    const progressEl = document.getElementById('cascade-progress');
    if (progressEl) progressEl.style.display = 'block';

    // Build cascade node IDs (only those with diagrams, plus root)
    const cascadeNodeIds = panelState.cascadeNodes
        .filter(n => n.hasDiagram)
        .map(n => n.id);

    // Send via WebSocket
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'kilo_diagram_cascade_request',
            diagram_id: panelState.diagramId,
            parent_node_id: panelState.parentNodeId,
            parent_node_type: panelState.parentNodeType,
            cascade_node_ids: cascadeNodeIds,
            kilo_prompt: prompt,
            current_mermaid_code: panelState.mermaidCode,
        }));
    }

    // Reset all status indicators to pending
    document.querySelectorAll('.cascade-node-item .status-indicator, .cascade-root-item .status-indicator').forEach(el => {
        el.className = 'status-indicator pending';
    });
}

// ============================================
// WebSocket Event Handlers (called from app.js)
// ============================================

/**
 * Handle cascade progress update from server.
 */
export function handleCascadeProgress(data) {
    panelState.changeId = data.change_id;

    const { current_node_id, current_index, total } = data;

    // Update progress bar
    const fillEl = document.getElementById('cascade-progress-fill');
    const textEl = document.getElementById('cascade-progress-text');
    if (fillEl) {
        const percent = total > 0 ? ((current_index) / total) * 100 : 0;
        fillEl.style.width = `${percent}%`;
    }
    if (textEl) {
        textEl.textContent = `${current_index + 1} / ${total}`;
    }

    // Update status indicator for current node
    const nodeItem = document.querySelector(`.cascade-node-item[data-node-id="${current_node_id}"]`);
    if (nodeItem) {
        const indicator = nodeItem.querySelector('.status-indicator');
        if (indicator) indicator.className = 'status-indicator processing';
    }

    // If index 0, update root indicator
    if (current_index === 0) {
        const rootIndicator = document.querySelector('.cascade-root-item .status-indicator');
        if (rootIndicator) rootIndicator.className = 'status-indicator processing';
    }
}

/**
 * Handle individual node result from server.
 */
export function handleCascadeNodeResult(data) {
    const { node_id, success, suggested_mermaid, error, reasoning } = data;

    // Store result
    panelState.results[node_id] = { success, suggested_mermaid, error, reasoning };

    // Update status indicator
    const nodeItem = document.querySelector(`.cascade-node-item[data-node-id="${node_id}"]`);
    if (nodeItem) {
        const indicator = nodeItem.querySelector('.status-indicator');
        if (indicator) indicator.className = `status-indicator ${success ? 'done' : 'error'}`;
    }

    // Check if this is the root node (parent)
    if (node_id === panelState.parentNodeId) {
        const rootIndicator = document.querySelector('.cascade-root-item .status-indicator');
        if (rootIndicator) rootIndicator.className = `status-indicator ${success ? 'done' : 'error'}`;
    }

    // Add result card
    const resultsEl = document.getElementById('cascade-results');
    if (resultsEl && success && suggested_mermaid) {
        const card = document.createElement('div');
        card.className = 'cascade-result-card';
        card.dataset.nodeId = node_id;
        card.innerHTML = `
            <div class="result-card-header">
                <span class="result-node-id">${escapeHtml(node_id)}</span>
                <span class="result-status success">Vorschlag</span>
            </div>
            <div class="result-mermaid-preview">
                <pre>${escapeHtml(suggested_mermaid.substring(0, 500))}${suggested_mermaid.length > 500 ? '\n...' : ''}</pre>
            </div>
            ${reasoning ? `<div class="result-reasoning">${escapeHtml(reasoning.substring(0, 200))}</div>` : ''}
            <div class="result-actions">
                <button class="btn-approve" onclick="window._approveCascadeNode('${escapeHtml(node_id)}')">
                    Anwenden
                </button>
                <button class="btn-reject" onclick="window._rejectCascadeNode('${escapeHtml(node_id)}')">
                    Ablehnen
                </button>
            </div>
        `;
        resultsEl.appendChild(card);
    } else if (resultsEl && !success) {
        const card = document.createElement('div');
        card.className = 'cascade-result-card error';
        card.innerHTML = `
            <div class="result-card-header">
                <span class="result-node-id">${escapeHtml(node_id)}</span>
                <span class="result-status error">Fehler</span>
            </div>
            <div class="result-error">${escapeHtml(error || 'Unbekannter Fehler')}</div>
        `;
        resultsEl.appendChild(card);
    }
}

/**
 * Handle cascade complete from server.
 */
export function handleCascadeComplete(data) {
    panelState.isProcessing = false;

    const statusEl = document.getElementById('kilo-diagram-status');
    const submitBtn = document.getElementById('btn-kilo-diagram-submit');
    const fillEl = document.getElementById('cascade-progress-fill');

    if (fillEl) fillEl.style.width = '100%';
    if (submitBtn) submitBtn.disabled = false;

    if (statusEl) {
        statusEl.textContent = `Fertig (${data.success_count}/${data.total_processed})`;
        statusEl.className = 'kilo-status success';
    }
}

// ============================================
// Approve / Reject Handlers
// ============================================

window._approveCascadeNode = function(nodeId) {
    if (!panelState.changeId) return;

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'approve_cascade_node',
            change_id: panelState.changeId,
            node_id: nodeId,
        }));
    }

    // Update card UI
    const card = document.querySelector(`.cascade-result-card[data-node-id="${nodeId}"]`);
    if (card) {
        const actions = card.querySelector('.result-actions');
        if (actions) {
            actions.innerHTML = '<span class="result-applied">Angewendet</span>';
        }
    }
};

window._rejectCascadeNode = function(nodeId) {
    if (!panelState.changeId) return;

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'reject_cascade_node',
            change_id: panelState.changeId,
            node_id: nodeId,
        }));
    }

    // Update card UI
    const card = document.querySelector(`.cascade-result-card[data-node-id="${nodeId}"]`);
    if (card) {
        const actions = card.querySelector('.result-actions');
        if (actions) {
            actions.innerHTML = '<span class="result-rejected">Abgelehnt</span>';
        }
    }
};
