/**
 * Wizard Suggestion Notifications
 *
 * Displays notification cards for AutoGen agent suggestions that need user review.
 * High-confidence suggestions are auto-applied; this module handles the pending ones.
 *
 * Pattern follows changeRequestNotification.js.
 */

import { state, escapeHtml } from '../state.js';

// ============================================
// State
// ============================================

let suggestions = [];
let containerEl = null;

const TYPE_ICONS = {
    stakeholder: '\u{1F465}',   // 👥
    requirement: '\u{1F4CB}',   // 📋
    constraint: '\u{1F512}',    // 🔒
    context: '\u{1F4A1}',       // 💡
};

const TYPE_LABELS = {
    stakeholder: 'Stakeholder',
    requirement: 'Requirement',
    constraint: 'Constraint',
    context: 'Kontext',
};

// ============================================
// Container
// ============================================

function ensureContainer() {
    if (containerEl && document.body.contains(containerEl)) {
        return containerEl;
    }
    containerEl = document.createElement('div');
    containerEl.className = 'wizard-suggestion-container';
    containerEl.id = 'wizard-suggestion-container';
    document.body.appendChild(containerEl);
    return containerEl;
}

// ============================================
// Show Suggestion Notification
// ============================================

/**
 * Show a pending wizard suggestion as a notification card.
 * @param {Object} data - Suggestion data from WebSocket / REST
 * @param {string} data.id - Suggestion ID
 * @param {string} data.type - stakeholder|requirement|constraint|context
 * @param {number} data.confidence - 0.0-1.0
 * @param {string} data.reasoning - Agent reasoning
 * @param {Object} data.content - Suggestion payload
 * @param {string} data.source_team - Which agent team
 */
export function showWizardSuggestion(data) {
    const container = ensureContainer();

    // Deduplicate
    if (suggestions.find(s => s.id === data.id)) return;

    const entry = { ...data, element: null, created_at: Date.now() };
    const el = document.createElement('div');
    el.className = 'wizard-suggestion-card';
    el.dataset.suggestionId = data.id;

    const confidencePercent = Math.round((data.confidence || 0) * 100);
    const icon = TYPE_ICONS[data.type] || '\u2728'; // ✨
    const label = TYPE_LABELS[data.type] || data.type;
    const contentPreview = _buildContentPreview(data.type, data.content);

    el.innerHTML = `
        <div class="ws-card-header">
            <span class="ws-icon">${icon}</span>
            <span class="ws-label">${escapeHtml(label)}</span>
            <span class="ws-confidence" style="background:${_confidenceColor(data.confidence)}">${confidencePercent}%</span>
        </div>
        <div class="ws-card-body">
            <div class="ws-preview">${contentPreview}</div>
            <p class="ws-reasoning">${escapeHtml(data.reasoning || '')}</p>
        </div>
        <div class="ws-card-actions">
            <button class="ws-btn ws-btn-approve" data-id="${data.id}" title="Annehmen">&#10003;</button>
            <button class="ws-btn ws-btn-reject" data-id="${data.id}" title="Ablehnen">&#10007;</button>
            <button class="ws-btn ws-btn-detail" data-id="${data.id}" title="Details">&#8230;</button>
        </div>
    `;

    // Event delegation for buttons
    el.querySelector('.ws-btn-approve').addEventListener('click', () => approveWizardSuggestion(data.id));
    el.querySelector('.ws-btn-reject').addEventListener('click', () => rejectWizardSuggestion(data.id));
    el.querySelector('.ws-btn-detail').addEventListener('click', () => viewWizardSuggestion(data.id));

    entry.element = el;
    suggestions.push(entry);
    container.appendChild(el);

    console.log('[WizardNotif] Shown:', data.id, data.type);
}

// ============================================
// Actions
// ============================================

export function approveWizardSuggestion(suggestionId) {
    const entry = suggestions.find(s => s.id === suggestionId);
    if (!entry) return;

    // Send via WebSocket
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'approve_wizard_suggestion',
            suggestion_id: suggestionId,
        }));
    }

    removeSuggestion(suggestionId);
    showToast('Vorschlag angenommen', 'success');
}

export function rejectWizardSuggestion(suggestionId) {
    const entry = suggestions.find(s => s.id === suggestionId);
    if (!entry) return;

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'reject_wizard_suggestion',
            suggestion_id: suggestionId,
            reason: 'User rejected',
        }));
    }

    removeSuggestion(suggestionId);
    showToast('Vorschlag abgelehnt', 'info');
}

export function viewWizardSuggestion(suggestionId) {
    const entry = suggestions.find(s => s.id === suggestionId);
    if (!entry) return;

    showDetailModal(entry);
}

/**
 * Handle auto-applied suggestion event (just show toast).
 */
export function handleAutoApplied(data) {
    const label = TYPE_LABELS[data.type] || data.type;
    showToast(`${label} automatisch hinzugefuegt`, 'success');
}

/**
 * Handle enrichment started event.
 */
export function handleEnrichmentStarted(data) {
    showToast(`KI analysiert Step ${data.step}...`, 'info');
}

/**
 * Handle enrichment complete event.
 */
export function handleEnrichmentComplete(data) {
    const autoCount = data.auto_applied || 0;
    const pendingCount = data.pending || 0;
    if (autoCount > 0 || pendingCount > 0) {
        showToast(`${autoCount} automatisch, ${pendingCount} zur Prüfung`, 'success');
    }
}

/**
 * Return list of approved suggestion contents for a given type.
 * Called by wizard.js to merge auto-applied data into wizardState.
 */
export function getApprovedContents(type) {
    // The approved contents come back from the server via the REST response
    // or WebSocket events - this is a convenience getter for the history
    return [];
}

// ============================================
// Helpers
// ============================================

function removeSuggestion(suggestionId) {
    const idx = suggestions.findIndex(s => s.id === suggestionId);
    if (idx === -1) return;

    const entry = suggestions[idx];
    if (entry.element) {
        entry.element.style.animation = 'wsSlideOut 0.3s ease forwards';
        setTimeout(() => entry.element.remove(), 300);
    }
    suggestions.splice(idx, 1);
}

function _buildContentPreview(type, content) {
    if (!content) return '';
    switch (type) {
        case 'stakeholder':
            return `<b>${escapeHtml(content.role || content.name || '')}</b>`;
        case 'requirement':
            return `<b>${escapeHtml(content.title || content.text || '')}</b>`;
        case 'constraint':
            return `<b>${escapeHtml(content.description || content.title || '')}</b>`;
        case 'context':
            return `<b>${escapeHtml(content.summary || '').substring(0, 120)}</b>`;
        default:
            return `<b>${escapeHtml(JSON.stringify(content).substring(0, 100))}</b>`;
    }
}

function _confidenceColor(confidence) {
    if (confidence >= 0.8) return 'rgba(0,186,124,0.3)';
    if (confidence >= 0.6) return 'rgba(255,179,0,0.3)';
    return 'rgba(244,33,46,0.3)';
}

function showDetailModal(entry) {
    const modal = document.createElement('div');
    modal.className = 're-modal visible';
    const icon = TYPE_ICONS[entry.type] || '';
    const label = TYPE_LABELS[entry.type] || entry.type;
    const confidencePercent = Math.round((entry.confidence || 0) * 100);

    modal.innerHTML = `
        <div class="modal-backdrop" onclick="this.parentElement.remove()"></div>
        <div class="modal-container modal-large">
            <div class="modal-header">
                <h2>${icon} ${escapeHtml(label)}-Vorschlag (${confidencePercent}%)</h2>
                <button class="modal-close" onclick="this.closest('.re-modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <div class="diff-section">
                    <h3>Agent-Begruendung</h3>
                    <p>${escapeHtml(entry.reasoning || 'Keine Begruendung')}</p>
                </div>
                <div class="diff-section">
                    <h3>Vorgeschlagener Inhalt</h3>
                    <pre class="diff-content diff-new">${escapeHtml(JSON.stringify(entry.content, null, 2))}</pre>
                </div>
                <div class="diff-section">
                    <h3>Quelle</h3>
                    <p>Team: ${escapeHtml(entry.source_team || 'unknown')} | Step: ${entry.wizard_step || '?'}</p>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="this.closest('.re-modal').remove()">Schliessen</button>
                <button class="btn-danger" id="ws-modal-reject">Ablehnen</button>
                <button class="btn-primary" id="ws-modal-approve">Annehmen</button>
            </div>
        </div>
    `;

    modal.querySelector('#ws-modal-approve').addEventListener('click', () => {
        approveWizardSuggestion(entry.id);
        modal.remove();
    });
    modal.querySelector('#ws-modal-reject').addEventListener('click', () => {
        rejectWizardSuggestion(entry.id);
        modal.remove();
    });

    document.body.appendChild(modal);
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 24px;
        background: ${type === 'success' ? 'var(--accent-green, #00ba7c)' : 'var(--bg-secondary, #1e2030)'};
        color: ${type === 'success' ? 'white' : 'var(--text-primary, #e0e0e0)'};
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 2000;
        animation: wsFadeInUp 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'wsFadeOutDown 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================
// CSS (injected)
// ============================================

const style = document.createElement('style');
style.textContent = `
    .wizard-suggestion-container {
        position: fixed;
        top: 80px;
        right: 20px;
        z-index: 1500;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-height: calc(100vh - 120px);
        overflow-y: auto;
        pointer-events: none;
    }

    .wizard-suggestion-card {
        pointer-events: auto;
        width: 320px;
        background: var(--bg-secondary, #1e2030);
        border: 1px solid var(--border-color, #2d3154);
        border-radius: 12px;
        padding: 14px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        animation: wsSlideIn 0.3s ease;
    }

    .ws-card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
    }

    .ws-icon { font-size: 18px; }

    .ws-label {
        font-weight: 600;
        font-size: 13px;
        color: var(--text-primary, #e0e0e0);
        flex: 1;
    }

    .ws-confidence {
        font-size: 11px;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 10px;
        color: var(--text-primary, #e0e0e0);
    }

    .ws-card-body {
        margin-bottom: 10px;
    }

    .ws-preview {
        font-size: 13px;
        color: var(--text-primary, #e0e0e0);
        margin-bottom: 4px;
    }

    .ws-reasoning {
        font-size: 11px;
        color: var(--text-secondary, #8a8fb5);
        margin: 0;
        line-height: 1.4;
    }

    .ws-card-actions {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
    }

    .ws-btn {
        border: none;
        border-radius: 6px;
        padding: 6px 12px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
        transition: opacity 0.15s;
    }
    .ws-btn:hover { opacity: 0.85; }

    .ws-btn-approve {
        background: var(--accent-green, #00ba7c);
        color: white;
    }
    .ws-btn-reject {
        background: var(--accent-red, #f4212e);
        color: white;
    }
    .ws-btn-detail {
        background: var(--bg-tertiary, #2a2e4a);
        color: var(--text-secondary, #8a8fb5);
    }

    @keyframes wsSlideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes wsSlideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    @keyframes wsFadeInUp {
        from { transform: translate(-50%, 20px); opacity: 0; }
        to { transform: translate(-50%, 0); opacity: 1; }
    }
    @keyframes wsFadeOutDown {
        from { transform: translate(-50%, 0); opacity: 1; }
        to { transform: translate(-50%, 20px); opacity: 0; }
    }
`;
document.head.appendChild(style);

// ============================================
// Window Exports
// ============================================

window.approveWizardSuggestion = approveWizardSuggestion;
window.rejectWizardSuggestion = rejectWizardSuggestion;
window.viewWizardSuggestion = viewWizardSuggestion;
