/**
 * RE System Dashboard - Kilo Agent Chat Integration
 *
 * Provides chat panel for interacting with Kilo Agent to modify nodes.
 */

import { state, log, escapeHtml } from './state.js';

// ============================================
// Module State
// ============================================

let callbacks = {
    sendMessage: () => {},
    renderMermaid: () => {}
};

export function setChatCallbacks(cbs) {
    callbacks = { ...callbacks, ...cbs };
}

// ============================================
// Chat Button Management
// ============================================

/**
 * Add chat button to a node element.
 * @param {HTMLElement} nodeElement - The node DOM element
 * @param {string} nodeId - The node ID
 */
export function addChatButton(nodeElement, nodeId) {
    // Check if button already exists
    if (nodeElement.querySelector('.kilo-chat-btn')) return;

    const chatBtn = document.createElement('button');
    chatBtn.className = 'kilo-chat-btn';
    chatBtn.innerHTML = '<span class="chat-icon">💬</span>';
    chatBtn.title = 'Mit Kilo Agent bearbeiten';
    chatBtn.onclick = (e) => {
        e.stopPropagation();
        openChatPanel(nodeId);
    };

    // Add to node header or create action container
    const header = nodeElement.querySelector('.node-header');
    if (header) {
        header.appendChild(chatBtn);
    } else {
        nodeElement.appendChild(chatBtn);
    }
}

/**
 * Add edit button to a node element.
 * Opens the edit modal with Kilo Agent integration.
 * @param {HTMLElement} nodeElement - The node DOM element
 * @param {string} nodeId - The node ID
 */
export function addEditButton(nodeElement, nodeId) {
    // Check if button already exists
    if (nodeElement.querySelector('.node-edit-btn')) return;

    const editBtn = document.createElement('button');
    editBtn.className = 'node-edit-btn';
    editBtn.innerHTML = '<span class="edit-icon">✏️</span>';
    editBtn.title = 'Node bearbeiten';
    editBtn.onclick = (e) => {
        e.stopPropagation();
        // Use window.openEditModal which is set by editModal.js
        if (typeof window.openEditModal === 'function') {
            window.openEditModal(nodeId);
        } else {
            console.error('[Chat] openEditModal not available');
        }
    };

    // Add to node header
    const header = nodeElement.querySelector('.node-header');
    if (header) {
        header.appendChild(editBtn);
    } else {
        nodeElement.appendChild(editBtn);
    }
}

// ============================================
// Chat Panel
// ============================================

/**
 * Open chat panel for a specific node.
 * @param {string} nodeId - The node ID
 */
export function openChatPanel(nodeId) {
    // Close existing panel
    closeChatPanel();

    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    const panel = document.createElement('div');
    panel.id = 'kilo-chat-panel';
    panel.className = 'kilo-chat-panel';
    panel.dataset.nodeId = nodeId;

    const title = escapeHtml(nodeData.data?.title || nodeData.data?.diagram_type || nodeId);

    panel.innerHTML = `
        <div class="chat-header">
            <span class="chat-title">Kilo Agent - ${title}</span>
            <button class="chat-close-btn" onclick="closeChatPanel()">×</button>
        </div>
        <div class="chat-messages" id="chat-messages-${nodeId}">
            <div class="chat-message system">Was soll geändert werden?</div>
        </div>
        <div class="chat-input-area">
            <textarea
                id="chat-input"
                placeholder="Beschreibe die gewünschte Änderung..."
                rows="3"
            ></textarea>
            <button class="chat-send-btn" onclick="sendKiloTask('${nodeId}')">
                Senden
            </button>
        </div>
    `;

    document.body.appendChild(panel);

    // Focus input
    const input = document.getElementById('chat-input');
    if (input) {
        input.focus();
        // Allow Enter to send (Shift+Enter for newline)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendKiloTask(nodeId);
            }
        });
    }
}

/**
 * Close the chat panel.
 */
export function closeChatPanel() {
    const panel = document.getElementById('kilo-chat-panel');
    if (panel) {
        panel.remove();
    }
}

// ============================================
// Kilo Agent Communication
// ============================================

/**
 * Send a task to the Kilo Agent.
 * @param {string} nodeId - The node ID
 */
export function sendKiloTask(nodeId) {
    console.log('[KILO] sendKiloTask called for node:', nodeId);
    const input = document.getElementById('chat-input');
    const task = input?.value?.trim();

    if (!task) {
        console.log('[KILO] No task provided');
        return;
    }

    const nodeData = state.nodes[nodeId];
    if (!nodeData) {
        console.log('[KILO] No node data found for:', nodeId);
        return;
    }

    // Determine content and type
    let content = '';
    let contentType = 'generic';
    let filePath = '';

    if (nodeData.type === 'diagram') {
        content = nodeData.data?.mermaid_code || '';
        contentType = 'diagram';
        filePath = nodeData.data?.file_path || '';
    } else if (nodeData.type === 'requirement') {
        content = JSON.stringify(nodeData.data, null, 2);
        contentType = 'requirement';
    } else {
        content = JSON.stringify(nodeData.data, null, 2);
    }

    console.log('[KILO] Sending message:', { nodeId, contentType, taskLength: task.length });
    console.log('[KILO] WebSocket state:', state.ws?.readyState);

    // Send to server via callback
    callbacks.sendMessage({
        type: 'kilo_task',
        node_id: nodeId,
        content: content,
        file_path: filePath,
        task: task,
        content_type: contentType
    });

    // Add user message to chat
    addChatMessage(nodeId, 'user', task);

    // Show processing indicator immediately
    addChatMessage(nodeId, 'system', 'Sende an Kilo Agent...');

    // Clear input
    input.value = '';
}

/**
 * Add a message to the chat panel.
 * @param {string} nodeId - The node ID
 * @param {string} type - Message type (user, agent, system, error)
 * @param {string} message - The message text
 */
export function addChatMessage(nodeId, type, message) {
    const messagesContainer = document.getElementById(`chat-messages-${nodeId}`);
    if (!messagesContainer) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${type}`;
    msgDiv.textContent = message;

    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ============================================
// Processing Indicators
// ============================================

/**
 * Show processing indicator on a node.
 * @param {string} nodeId - The node ID
 */
export function showKiloProcessing(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (nodeData?.element) {
        nodeData.element.classList.add('kilo-processing');
    }
}

/**
 * Hide processing indicator on a node.
 * @param {string} nodeId - The node ID
 */
export function hideKiloProcessing(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (nodeData?.element) {
        nodeData.element.classList.remove('kilo-processing');
    }
}

// ============================================
// Node Content Updates
// ============================================

/**
 * Update a diagram node with new content.
 * @param {Object} data - Update data with node_id and mermaid_code
 */
export function updateDiagramNode(data) {
    const nodeId = data.node_id;
    const nodeData = state.nodes[nodeId];

    if (!nodeData) return;

    // Update state
    nodeData.data.mermaid_code = data.mermaid_code;

    // Re-render Mermaid
    const mermaidContainer = nodeData.element?.querySelector('.node-diagram-content');
    if (mermaidContainer) {
        mermaidContainer.textContent = data.mermaid_code;
        callbacks.renderMermaid(nodeId, data.mermaid_code);
    }

    hideKiloProcessing(nodeId);
}

/**
 * Update node content (generic).
 * @param {Object} data - Update data
 */
export function updateNodeContent(data) {
    const nodeId = data.node_id;
    const nodeData = state.nodes[nodeId];

    if (!nodeData) return;

    // Try to parse and merge the content
    try {
        const newContent = JSON.parse(data.content);
        Object.assign(nodeData.data, newContent);
    } catch {
        // If not JSON, store as raw content
        nodeData.data.content = data.content;
    }

    hideKiloProcessing(nodeId);
}

// ============================================
// Initialization
// ============================================

/**
 * Initialize chat buttons on all existing nodes.
 */
export function initializeChatButtons() {
    Object.entries(state.nodes).forEach(([nodeId, nodeData]) => {
        if (nodeData.element) {
            addChatButton(nodeData.element, nodeId);
        }
    });
}

// ============================================
// Kilo Event Handlers (called from WebSocket message handler)
// ============================================

export function handleKiloTaskProcessing(data) {
    showKiloProcessing(data.node_id);
    addChatMessage(data.node_id, 'system', 'Verarbeite...');
    log('info', `Kilo Agent processing: ${data.task}`);
}

export function handleKiloTaskComplete(data) {
    hideKiloProcessing(data.node_id);
    addChatMessage(data.node_id, 'agent', 'Aufgabe abgeschlossen!');
    log('success', `Kilo Agent task complete for ${data.node_id}`);
}

export function handleKiloTaskError(data) {
    hideKiloProcessing(data.node_id);
    addChatMessage(data.node_id, 'error', data.error);
    log('error', `Kilo Agent error: ${data.error}`);
}

export function handleDiagramUpdate(data) {
    updateDiagramNode(data);
    addChatMessage(data.node_id, 'agent', 'Diagramm aktualisiert!');
}

export function handleContentUpdate(data) {
    updateNodeContent(data);
    addChatMessage(data.node_id, 'agent', 'Inhalt aktualisiert!');
}
