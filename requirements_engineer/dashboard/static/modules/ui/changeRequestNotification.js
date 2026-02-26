/**
 * Change Request Notification - Displays notifications for affected nodes
 *
 * When a change propagates through the dependency graph, affected nodes
 * receive notifications with auto-generated suggestions from Kilo Agent.
 */

import { state, escapeHtml } from '../state.js';

// ============================================
// Notification State
// ============================================

let notifications = [];
let containerEl = null;

// ============================================
// Create Notification Container
// ============================================

function ensureContainer() {
    if (containerEl && document.body.contains(containerEl)) {
        return containerEl;
    }

    containerEl = document.createElement('div');
    containerEl.className = 'change-request-container';
    containerEl.id = 'change-request-container';
    document.body.appendChild(containerEl);

    return containerEl;
}

// ============================================
// Show Notification
// ============================================

/**
 * Show a change request notification
 * @param {Object} data - Notification data
 * @param {string} data.suggestion_id - Unique ID for the suggestion
 * @param {string} data.source_node_id - ID of the node that was changed
 * @param {string} data.target_node_id - ID of the affected node
 * @param {string} data.target_node_type - Type of the affected node
 * @param {string} data.reasoning - German explanation of why the node is affected
 * @param {string} data.suggested_content - Auto-generated suggested content
 * @param {number} data.confidence - Confidence score 0-1
 */
export function showChangeRequestNotification(data) {
    const container = ensureContainer();

    // Check if notification for this suggestion already exists
    if (notifications.find(n => n.suggestion_id === data.suggestion_id)) {
        return;
    }

    const notification = {
        ...data,
        element: null,
        created_at: Date.now(),
    };

    // Create notification element
    const el = document.createElement('div');
    el.className = 'change-request-notification';
    el.dataset.suggestionId = data.suggestion_id;

    const confidencePercent = Math.round((data.confidence || 0.5) * 100);

    el.innerHTML = `
        <div class="crn-header">
            <span class="crn-icon">⚡</span>
            <span class="crn-title">Change Request</span>
            <span class="crn-confidence">${confidencePercent}%</span>
        </div>
        <div class="crn-body">
            <p>Änderung an <b>${escapeHtml(data.source_node_id)}</b> betrifft <b>${escapeHtml(data.target_node_id)}</b></p>
            <p class="crn-reasoning">${escapeHtml(data.reasoning || 'Update empfohlen')}</p>
        </div>
        <div class="crn-actions">
            <button class="btn-view" onclick="window.viewChangeRequest('${data.suggestion_id}')">
                Anzeigen
            </button>
            <button class="btn-approve" onclick="window.approveChangeRequest('${data.suggestion_id}')">
                ✓
            </button>
            <button class="btn-reject" onclick="window.rejectChangeRequest('${data.suggestion_id}')">
                ✗
            </button>
        </div>
    `;

    notification.element = el;
    notifications.push(notification);

    // Add to container with animation
    container.appendChild(el);

    // Auto-dismiss after 30 seconds if not interacted with
    setTimeout(() => {
        if (notifications.find(n => n.suggestion_id === data.suggestion_id)) {
            // Still exists - don't auto-dismiss, but reduce opacity
            el.style.opacity = '0.7';
        }
    }, 30000);

    console.log('[ChangeRequest] Notification shown:', data.suggestion_id);
}

// ============================================
// Notification Actions
// ============================================

/**
 * View the change request details
 */
export function viewChangeRequest(suggestionId) {
    const notification = notifications.find(n => n.suggestion_id === suggestionId);
    if (!notification) return;

    console.log('[ChangeRequest] Viewing:', suggestionId);

    // Focus on the target node in the canvas
    const targetNodeId = notification.target_node_id;
    if (state.nodes[targetNodeId]) {
        window.dispatchEvent(new CustomEvent('focusNode', {
            detail: { nodeId: targetNodeId }
        }));
    }

    // Show diff modal
    showDiffModal(notification);
}

/**
 * Approve the change request
 */
export function approveChangeRequest(suggestionId) {
    const notification = notifications.find(n => n.suggestion_id === suggestionId);
    if (!notification) return;

    console.log('[ChangeRequest] Approving:', suggestionId);

    // Send approval via WebSocket
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'approve_change_request',
            suggestion_id: suggestionId,
        }));
    }

    // Remove notification with animation
    removeNotification(suggestionId);

    // Show success toast
    showToast('Änderung genehmigt', 'success');
}

/**
 * Reject the change request
 */
export function rejectChangeRequest(suggestionId) {
    const notification = notifications.find(n => n.suggestion_id === suggestionId);
    if (!notification) return;

    console.log('[ChangeRequest] Rejecting:', suggestionId);

    // Send rejection via WebSocket
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'reject_change_request',
            suggestion_id: suggestionId,
            reason: 'User rejected',
        }));
    }

    // Remove notification
    removeNotification(suggestionId);

    // Show toast
    showToast('Änderung abgelehnt', 'info');
}

// ============================================
// Helper Functions
// ============================================

function removeNotification(suggestionId) {
    const index = notifications.findIndex(n => n.suggestion_id === suggestionId);
    if (index === -1) return;

    const notification = notifications[index];

    // Animate out
    if (notification.element) {
        notification.element.style.animation = 'slideOutRight 0.3s ease forwards';
        setTimeout(() => {
            notification.element.remove();
        }, 300);
    }

    notifications.splice(index, 1);
}

function showDiffModal(notification) {
    // Create a simple diff view modal
    const modal = document.createElement('div');
    modal.className = 're-modal visible';
    modal.innerHTML = `
        <div class="modal-backdrop" onclick="this.parentElement.remove()"></div>
        <div class="modal-container modal-large">
            <div class="modal-header">
                <h2>Änderungsvorschlag: ${escapeHtml(notification.target_node_id)}</h2>
                <button class="modal-close" onclick="this.closest('.re-modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <div class="diff-section">
                    <h3>Grund</h3>
                    <p>${escapeHtml(notification.reasoning || 'Keine Begründung')}</p>
                </div>
                <div class="diff-section">
                    <h3>Aktueller Inhalt</h3>
                    <pre class="diff-content diff-old">${escapeHtml(notification.current_content || '(leer)')}</pre>
                </div>
                <div class="diff-section">
                    <h3>Vorgeschlagener Inhalt</h3>
                    <pre class="diff-content diff-new">${escapeHtml(notification.suggested_content || '(keine Änderung)')}</pre>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-secondary" onclick="this.closest('.re-modal').remove()">Schließen</button>
                <button class="btn-danger" onclick="window.rejectChangeRequest('${notification.suggestion_id}'); this.closest('.re-modal').remove();">Ablehnen</button>
                <button class="btn-primary" onclick="window.approveChangeRequest('${notification.suggestion_id}'); this.closest('.re-modal').remove();">Anwenden</button>
            </div>
        </div>
    `;

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
        background: ${type === 'success' ? 'var(--accent-green)' : 'var(--bg-secondary)'};
        color: ${type === 'success' ? 'white' : 'var(--text-primary)'};
        border-radius: 8px;
        box-shadow: var(--shadow-lg);
        z-index: 2000;
        animation: fadeInUp 0.3s ease;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOutDown 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================
// CSS Animations (injected)
// ============================================

const style = document.createElement('style');
style.textContent = `
    @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }

    @keyframes fadeInUp {
        from { transform: translate(-50%, 20px); opacity: 0; }
        to { transform: translate(-50%, 0); opacity: 1; }
    }

    @keyframes fadeOutDown {
        from { transform: translate(-50%, 0); opacity: 1; }
        to { transform: translate(-50%, 20px); opacity: 0; }
    }

    .diff-section {
        margin-bottom: 20px;
    }

    .diff-section h3 {
        margin: 0 0 8px 0;
        font-size: 14px;
        color: var(--text-secondary);
    }

    .diff-content {
        padding: 12px;
        border-radius: 8px;
        font-family: 'SF Mono', monospace;
        font-size: 13px;
        line-height: 1.5;
        white-space: pre-wrap;
        overflow-x: auto;
        max-height: 200px;
        overflow-y: auto;
    }

    .diff-old {
        background: rgba(244, 33, 46, 0.1);
        border: 1px solid rgba(244, 33, 46, 0.2);
    }

    .diff-new {
        background: rgba(0, 186, 124, 0.1);
        border: 1px solid rgba(0, 186, 124, 0.2);
    }
`;
document.head.appendChild(style);

// ============================================
// Window Exports
// ============================================

window.showChangeRequestNotification = showChangeRequestNotification;
window.viewChangeRequest = viewChangeRequest;
window.approveChangeRequest = approveChangeRequest;
window.rejectChangeRequest = rejectChangeRequest;

// ============================================
// WebSocket Integration
// ============================================

/**
 * Handle incoming change request from WebSocket
 * Called by the main app when it receives a change_request_created event
 */
export function handleChangeRequestEvent(data) {
    showChangeRequestNotification(data);
}

window.handleChangeRequestEvent = handleChangeRequestEvent;
