/**
 * Edit Modal - Modal for editing nodes with Kilo Agent integration
 *
 * Supports editing:
 * - Epics
 * - Requirements
 * - User Stories
 * - Tasks
 * - Diagrams (fullscreen)
 */

import { state, escapeHtml } from '../state.js';
import { openModal, closeModal } from './modal.js';

// ============================================
// Edit Modal State
// ============================================

let editModalState = {
    nodeId: null,
    nodeType: null,
    originalData: null,
    isDirty: false,
    kiloProcessing: false,
    affectedNodes: [],
};

// ============================================
// Form Configurations per Node Type
// ============================================

const FORM_CONFIGS = {
    epic: {
        title: 'Epic bearbeiten',
        fields: [
            { name: 'title', label: 'Titel', type: 'text', required: true },
            { name: 'description', label: 'Beschreibung', type: 'textarea', rows: 4 },
            { name: 'priority', label: 'Priorität', type: 'select', options: ['MUST', 'SHOULD', 'COULD', 'WONT'] },
            { name: 'status', label: 'Status', type: 'select', options: ['draft', 'in_progress', 'review', 'done'] },
        ],
    },
    requirement: {
        title: 'Requirement bearbeiten',
        fields: [
            { name: 'title', label: 'Titel', type: 'text', required: true },
            { name: 'description', label: 'Beschreibung', type: 'textarea', rows: 4 },
            { name: 'type', label: 'Typ', type: 'select', options: ['functional', 'non-functional'] },
            { name: 'priority', label: 'Priorität', type: 'select', options: ['must', 'should', 'could'] },
            { name: 'rationale', label: 'Begründung', type: 'textarea', rows: 2 },
        ],
    },
    'user-story': {
        title: 'User Story bearbeiten',
        fields: [
            { name: 'persona', label: 'Als (Persona)', type: 'text', required: true },
            { name: 'action', label: 'möchte ich (Aktion)', type: 'textarea', rows: 2, required: true },
            { name: 'benefit', label: 'damit ich (Nutzen)', type: 'textarea', rows: 2 },
            { name: 'priority', label: 'Priorität', type: 'select', options: ['MUST', 'SHOULD', 'COULD', 'WONT'] },
            { name: 'acceptance_criteria', label: 'Akzeptanzkriterien', type: 'textarea', rows: 4 },
        ],
    },
    task: {
        title: 'Task bearbeiten',
        fields: [
            { name: 'title', label: 'Titel', type: 'text', required: true },
            { name: 'description', label: 'Beschreibung', type: 'textarea', rows: 3 },
            { name: 'task_type', label: 'Typ', type: 'select', options: ['design', 'development', 'testing', 'documentation', 'devops'] },
            { name: 'complexity', label: 'Komplexität', type: 'select', options: ['low', 'medium', 'high'] },
            { name: 'estimated_hours', label: 'Geschätzte Stunden', type: 'number', min: 0, max: 1000 },
            { name: 'story_points', label: 'Story Points', type: 'number', min: 0, max: 100 },
            { name: 'status', label: 'Status', type: 'select', options: ['todo', 'in_progress', 'review', 'done'] },
        ],
    },
    diagram: {
        title: 'Diagramm bearbeiten',
        fields: [
            { name: 'mermaid_code', label: 'Mermaid Code', type: 'code', language: 'mermaid', rows: 20 },
        ],
    },
};

// ============================================
// Open Edit Modal
// ============================================

/**
 * Open edit modal for a node
 * @param {string} nodeId - ID of the node to edit
 */
export function openEditModal(nodeId) {
    const node = state.nodes[nodeId];
    if (!node) {
        console.error(`Node not found: ${nodeId}`);
        return;
    }

    // Determine node type
    const nodeType = node.type || detectNodeType(nodeId);
    const formConfig = FORM_CONFIGS[nodeType];

    if (!formConfig) {
        console.error(`No form config for node type: ${nodeType}`);
        return;
    }

    // Store original data for dirty checking
    editModalState = {
        nodeId,
        nodeType,
        originalData: JSON.parse(JSON.stringify(node.data || {})),
        isDirty: false,
        kiloProcessing: false,
        affectedNodes: [],
    };

    // Open modal with edit type
    openModal({
        type: 'edit-node',
        title: `${formConfig.title}: ${nodeId}`,
        size: nodeType === 'diagram' ? 'xl' : 'large',
        data: {
            nodeId,
            nodeType,
            formConfig,
            nodeData: node.data || {},
        },
    });
}

/**
 * Detect node type from ID
 */
function detectNodeType(nodeId) {
    const id = nodeId.toUpperCase();
    if (id.startsWith('EPIC')) return 'epic';
    if (id.startsWith('REQ')) return 'requirement';
    if (id.startsWith('US')) return 'user-story';
    if (id.startsWith('TASK')) return 'task';
    if (id.includes('FLOWCHART') || id.includes('SEQUENCE') || id.includes('CLASS') || id.includes('ER')) return 'diagram';
    return 'requirement'; // Default
}

// ============================================
// Render Edit Form
// ============================================

/**
 * Render the edit form in the modal body
 * @param {HTMLElement} body - Modal body element
 * @param {Object} config - Modal config with form data
 */
export function renderEditForm(body, config) {
    const { nodeId, nodeType, formConfig, nodeData } = config.data;

    const fieldsHtml = formConfig.fields.map(field => renderFormField(field, nodeData)).join('');

    body.innerHTML = `
        <form class="edit-form" id="edit-form" data-node-id="${escapeHtml(nodeId)}">
            <div class="edit-form-fields">
                ${fieldsHtml}
            </div>

            <!-- Kilo Agent Input Section -->
            <div class="kilo-agent-section" id="kilo-section">
                <div class="kilo-header">
                    <span class="kilo-icon">🤖</span>
                    <span class="kilo-title">Kilo Agent</span>
                    <span class="kilo-status" id="kilo-status"></span>
                </div>
                <div class="kilo-input-wrapper">
                    <textarea
                        id="kilo-prompt"
                        class="kilo-prompt-input"
                        placeholder="Beschreibe die gewünschte Änderung..."
                        rows="2"
                    ></textarea>
                    <button type="button" class="btn-kilo-submit" id="btn-kilo-submit">
                        Senden
                    </button>
                </div>
                <div class="kilo-response" id="kilo-response" style="display: none;"></div>
            </div>

            <!-- Affected Nodes Preview -->
            <div class="affected-nodes-section" id="affected-nodes-section" style="display: none;">
                <div class="affected-header">
                    <span>⚡ Betroffene Nodes</span>
                    <span class="affected-count" id="affected-count">0</span>
                </div>
                <div class="affected-list" id="affected-list"></div>
            </div>

            <!-- Form Actions -->
            <div class="edit-form-actions">
                <button type="button" class="btn-secondary" onclick="window.closeEditModal()">
                    Abbrechen
                </button>
                <button type="submit" class="btn-primary" id="btn-save">
                    Speichern
                </button>
            </div>
        </form>
    `;

    // Setup event listeners
    setupEditFormListeners(body);
}

/**
 * Render a single form field
 */
function renderFormField(field, data) {
    const value = data[field.name] || '';
    const required = field.required ? 'required' : '';
    const label = `${field.label}${field.required ? ' *' : ''}`;

    switch (field.type) {
        case 'text':
            return `
                <div class="form-group">
                    <label for="field-${field.name}">${label}</label>
                    <input
                        type="text"
                        id="field-${field.name}"
                        name="${field.name}"
                        value="${escapeHtml(value)}"
                        ${required}
                    />
                </div>
            `;

        case 'textarea':
            return `
                <div class="form-group">
                    <label for="field-${field.name}">${label}</label>
                    <textarea
                        id="field-${field.name}"
                        name="${field.name}"
                        rows="${field.rows || 3}"
                        ${required}
                    >${escapeHtml(value)}</textarea>
                </div>
            `;

        case 'code':
            return `
                <div class="form-group form-group-code">
                    <label for="field-${field.name}">${label}</label>
                    <textarea
                        id="field-${field.name}"
                        name="${field.name}"
                        class="code-editor"
                        rows="${field.rows || 10}"
                        spellcheck="false"
                        ${required}
                    >${escapeHtml(value)}</textarea>
                </div>
            `;

        case 'select':
            const options = (field.options || []).map(opt => {
                const selected = value === opt ? 'selected' : '';
                return `<option value="${opt}" ${selected}>${opt}</option>`;
            }).join('');
            return `
                <div class="form-group">
                    <label for="field-${field.name}">${label}</label>
                    <select id="field-${field.name}" name="${field.name}" ${required}>
                        <option value="">-- Auswählen --</option>
                        ${options}
                    </select>
                </div>
            `;

        case 'number':
            return `
                <div class="form-group">
                    <label for="field-${field.name}">${label}</label>
                    <input
                        type="number"
                        id="field-${field.name}"
                        name="${field.name}"
                        value="${value}"
                        min="${field.min || 0}"
                        max="${field.max || 9999}"
                        ${required}
                    />
                </div>
            `;

        default:
            return '';
    }
}

// ============================================
// Event Listeners
// ============================================

function setupEditFormListeners(body) {
    const form = body.querySelector('#edit-form');
    const kiloSubmitBtn = body.querySelector('#btn-kilo-submit');
    const kiloPrompt = body.querySelector('#kilo-prompt');

    // Form submission
    if (form) {
        form.addEventListener('submit', handleFormSubmit);

        // Track dirty state
        form.addEventListener('input', () => {
            editModalState.isDirty = true;
        });
    }

    // Kilo submit button
    if (kiloSubmitBtn) {
        kiloSubmitBtn.addEventListener('click', handleKiloSubmit);
    }

    // Kilo prompt enter key
    if (kiloPrompt) {
        kiloPrompt.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleKiloSubmit();
            }
        });
    }
}

// ============================================
// Form Handlers
// ============================================

async function handleFormSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const formData = new FormData(form);
    const nodeId = form.dataset.nodeId;

    // Collect form values
    const updates = {};
    for (const [key, value] of formData.entries()) {
        updates[key] = value;
    }

    console.log('[EditModal] Saving:', nodeId, updates);

    // Update state
    if (state.nodes[nodeId]) {
        state.nodes[nodeId].data = {
            ...state.nodes[nodeId].data,
            ...updates,
        };
    }

    // Send via WebSocket if connected
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'edit_node',
            node_id: nodeId,
            updates: updates,
        }));
    }

    // Dispatch event for other listeners
    window.dispatchEvent(new CustomEvent('node:edited', {
        detail: { nodeId, updates }
    }));

    // Close modal
    closeModal();
}

async function handleKiloSubmit() {
    const promptInput = document.getElementById('kilo-prompt');
    const statusEl = document.getElementById('kilo-status');
    const responseEl = document.getElementById('kilo-response');
    const submitBtn = document.getElementById('btn-kilo-submit');

    const prompt = promptInput?.value?.trim();
    if (!prompt) return;

    // Show processing state
    editModalState.kiloProcessing = true;
    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) statusEl.textContent = 'Verarbeite...';
    if (statusEl) statusEl.className = 'kilo-status processing';

    console.log('[EditModal] Kilo submit:', prompt, 'for', editModalState.nodeId);

    // Get current form data
    const form = document.getElementById('edit-form');
    const formData = new FormData(form);
    const currentContent = Object.fromEntries(formData.entries());

    // Send to backend via WebSocket
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'kilo_edit_request',
            node_id: editModalState.nodeId,
            node_type: editModalState.nodeType,
            kilo_prompt: prompt,
            current_content: currentContent,
            original_content: editModalState.originalData,
        }));
    }

    // Show response area
    if (responseEl) {
        responseEl.style.display = 'block';
        responseEl.innerHTML = '<div class="kilo-loading">🤖 Kilo Agent analysiert...</div>';
    }
}

/**
 * Handle Kilo response from WebSocket
 */
export function handleKiloResponse(data) {
    const statusEl = document.getElementById('kilo-status');
    const responseEl = document.getElementById('kilo-response');
    const submitBtn = document.getElementById('btn-kilo-submit');
    const affectedSection = document.getElementById('affected-nodes-section');
    const affectedCount = document.getElementById('affected-count');
    const affectedList = document.getElementById('affected-list');

    editModalState.kiloProcessing = false;
    if (submitBtn) submitBtn.disabled = false;

    if (data.success) {
        if (statusEl) {
            statusEl.textContent = 'Fertig';
            statusEl.className = 'kilo-status success';
        }

        // Show Kilo response
        if (responseEl && data.kilo_response) {
            responseEl.innerHTML = `<div class="kilo-result">${escapeHtml(data.kilo_response)}</div>`;
        }

        // Show affected nodes
        if (data.affected_node_ids && data.affected_node_ids.length > 0) {
            editModalState.affectedNodes = data.affected_node_ids;

            if (affectedSection) affectedSection.style.display = 'block';
            if (affectedCount) affectedCount.textContent = data.affected_node_ids.length;
            if (affectedList) {
                affectedList.innerHTML = data.affected_node_ids.map(id => `
                    <div class="affected-node-item" data-id="${escapeHtml(id)}">
                        <span class="affected-node-id">${escapeHtml(id)}</span>
                        <span class="affected-node-badge">Wird benachrichtigt</span>
                    </div>
                `).join('');
            }
        }
    } else {
        if (statusEl) {
            statusEl.textContent = 'Fehler';
            statusEl.className = 'kilo-status error';
        }

        if (responseEl) {
            responseEl.innerHTML = `<div class="kilo-error">${escapeHtml(data.error || 'Unbekannter Fehler')}</div>`;
        }
    }
}

// ============================================
// Close Edit Modal
// ============================================

export function closeEditModal() {
    if (editModalState.isDirty) {
        if (!confirm('Ungespeicherte Änderungen verwerfen?')) {
            return;
        }
    }
    closeModal();
}

// ============================================
// Window Exports
// ============================================

window.openEditModal = openEditModal;
window.closeEditModal = closeEditModal;
window.handleKiloResponse = handleKiloResponse;
