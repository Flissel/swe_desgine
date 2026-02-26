/**
 * RE System Dashboard - Kilo Agent Bridge
 *
 * Frontend integration for the Kilo Agent change evaluation system.
 * Connects the change tracker to the backend Kilo Agent via WebSocket.
 *
 * When a change is tracked, this module:
 * 1. Sends evaluation requests to the backend for each affected node
 * 2. Receives responses from the Kilo Agent
 * 3. Updates the UI with visual indicators
 */

import { state, log } from '../state.js';
import { on, emit, EVENTS } from '../core/events.js';
import {
    processAgentResponse,
    markAsProcessing,
    markAsFailed,
    getNotification
} from '../core/change_tracker.js';

// ============================================
// State
// ============================================

let wsConnection = null;
let isInitialized = false;

// Queue for messages to send when connection is ready
const pendingMessages = [];

// ============================================
// Initialization
// ============================================

/**
 * Initialize the Kilo Agent bridge.
 * Sets up WebSocket connection and event listeners.
 */
export function initKiloBridge() {
    if (isInitialized) {
        log('warn', '[KiloBridge] Already initialized');
        return;
    }

    // Use the existing WebSocket from state
    wsConnection = state.ws;

    // Listen for change notifications
    on(EVENTS.CHANGE_TRACKED, handleChangeTracked);

    // Setup WebSocket message handler if connection exists
    if (wsConnection) {
        setupWebSocketHandler(wsConnection);
    }

    // Listen for WebSocket connection events to update our reference
    on(EVENTS.WS_CONNECTED, () => {
        wsConnection = state.ws;
        if (wsConnection) {
            setupWebSocketHandler(wsConnection);
            // Send any pending messages
            flushPendingMessages();
        }
    });

    on(EVENTS.WS_DISCONNECTED, () => {
        wsConnection = null;
    });

    isInitialized = true;
    log('info', '[KiloBridge] Initialized');
}

/**
 * Setup WebSocket message handler.
 */
function setupWebSocketHandler(ws) {
    // Add message listener for Kilo Agent responses
    ws.addEventListener('message', handleWebSocketMessage);
}

/**
 * Flush pending messages when connection is ready.
 */
function flushPendingMessages() {
    while (pendingMessages.length > 0 && wsConnection?.readyState === WebSocket.OPEN) {
        const message = pendingMessages.shift();
        wsConnection.send(JSON.stringify(message));
    }
}

// ============================================
// Change Handling
// ============================================

/**
 * Handle a tracked change - send evaluation requests to Kilo Agent.
 *
 * @param {Object} notification - The change notification
 */
function handleChangeTracked(notification) {
    if (!notification.affectedNodes || notification.affectedNodes.length === 0) {
        log('info', `[KiloBridge] No affected nodes for ${notification.nodeId}`);
        return;
    }

    log('info', `[KiloBridge] Sending evaluation requests for ${notification.affectedNodes.length} nodes`);

    // Mark notification as processing
    markAsProcessing(notification.id);

    // For each affected node, request Kilo Agent evaluation
    notification.affectedNodes.forEach(targetNodeId => {
        const targetNode = state.nodes[targetNodeId];
        if (!targetNode) {
            log('warn', `[KiloBridge] Target node not found: ${targetNodeId}`);
            return;
        }

        const request = {
            type: 'kilo_evaluate_request',
            data: {
                notificationId: notification.id,
                changedNodeId: notification.nodeId,
                changedNodeType: notification.nodeType,
                changedNodeTitle: notification.nodeTitle,
                changeType: notification.changeType,
                changeDetails: notification.changeDetails,
                targetNodeId: targetNodeId,
                targetNodeType: targetNode.type,
                targetNodeTitle: targetNode.data?.title || targetNode.data?.name || targetNodeId,
                targetNodeData: {
                    title: targetNode.data?.title,
                    description: targetNode.data?.description,
                    type: targetNode.type
                },
                timestamp: notification.timestamp
            }
        };

        // Send via WebSocket to backend
        sendToBackend(request);

        // Emit local event for UI updates
        emit(EVENTS.KILO_EVALUATE_REQUEST, request.data);

        // Show pending indicator on target node
        showNodePendingIndicator(targetNodeId);
    });
}

/**
 * Send a message to the backend via WebSocket.
 */
function sendToBackend(message) {
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify(message));
    } else {
        // Queue for later
        pendingMessages.push(message);
        log('warn', '[KiloBridge] WebSocket not ready, message queued');
    }
}

// ============================================
// Response Handling
// ============================================

/**
 * Handle WebSocket messages from the backend.
 */
function handleWebSocketMessage(event) {
    try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'kilo_evaluate_response') {
            handleEvaluateResponse(msg.data);
        }
    } catch (e) {
        // Not our message format, ignore
    }
}

/**
 * Handle evaluation response from Kilo Agent.
 */
function handleEvaluateResponse(data) {
    const {
        notificationId,
        nodeId,
        needsChange,
        changeApplied,
        reason,
        suggestedChanges
    } = data;

    log('info', `[KiloBridge] Response for ${nodeId}: needsChange=${needsChange}`);

    // Process the response in change tracker
    processAgentResponse(notificationId, nodeId, {
        needsChange,
        changeApplied,
        reason,
        suggestedChanges
    });

    // Remove pending indicator
    removeNodePendingIndicator(nodeId);

    // Show response indicator on the node
    showNodeResponseIndicator(nodeId, needsChange, reason);

    // Emit local event
    emit(EVENTS.KILO_EVALUATE_RESPONSE, {
        notificationId,
        nodeId,
        needsChange,
        reason
    });
}

// ============================================
// Visual Indicators
// ============================================

/**
 * Show pending evaluation indicator on a node.
 */
function showNodePendingIndicator(nodeId) {
    const node = state.nodes[nodeId];
    if (!node?.element) return;

    // Remove any existing indicators
    removeNodeIndicators(nodeId);

    const indicator = document.createElement('div');
    indicator.className = 'kilo-indicator kilo-pending';
    indicator.id = `kilo-indicator-${nodeId}`;
    indicator.innerHTML = `
        <span class="kilo-icon">⏳</span>
        <span class="kilo-text">Evaluating...</span>
    `;
    indicator.style.cssText = `
        position: absolute;
        top: -30px;
        right: 5px;
        background: rgba(245, 158, 11, 0.9);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        display: flex;
        align-items: center;
        gap: 4px;
        z-index: 100;
        animation: pulse 1.5s infinite;
    `;

    node.element.style.position = 'relative';
    node.element.appendChild(indicator);
}

/**
 * Remove pending indicator from a node.
 */
function removeNodePendingIndicator(nodeId) {
    const indicator = document.getElementById(`kilo-indicator-${nodeId}`);
    if (indicator) {
        indicator.remove();
    }
}

/**
 * Remove all indicators from a node.
 */
function removeNodeIndicators(nodeId) {
    const node = state.nodes[nodeId];
    if (!node?.element) return;

    node.element.querySelectorAll('.kilo-indicator').forEach(el => el.remove());
}

/**
 * Show response indicator on a node.
 */
function showNodeResponseIndicator(nodeId, needsChange, reason) {
    const node = state.nodes[nodeId];
    if (!node?.element) return;

    // Remove any existing indicators
    removeNodeIndicators(nodeId);

    const indicator = document.createElement('div');
    indicator.className = `kilo-indicator ${needsChange ? 'kilo-needs-change' : 'kilo-no-change'}`;
    indicator.id = `kilo-indicator-${nodeId}`;

    const bgColor = needsChange ? 'rgba(239, 68, 68, 0.9)' : 'rgba(34, 197, 94, 0.9)';
    const icon = needsChange ? '⚠️' : '✓';
    const shortReason = reason.length > 40 ? reason.substring(0, 37) + '...' : reason;

    indicator.innerHTML = `
        <span class="kilo-icon">${icon}</span>
        <span class="kilo-text">${shortReason}</span>
    `;
    indicator.style.cssText = `
        position: absolute;
        top: -30px;
        right: 5px;
        background: ${bgColor};
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        display: flex;
        align-items: center;
        gap: 4px;
        z-index: 100;
        max-width: 200px;
        cursor: pointer;
    `;
    indicator.title = reason;

    // Click to dismiss
    indicator.addEventListener('click', () => indicator.remove());

    node.element.style.position = 'relative';
    node.element.appendChild(indicator);

    // Auto-remove after 8 seconds
    setTimeout(() => {
        if (indicator.parentNode) {
            indicator.remove();
        }
    }, 8000);
}

// ============================================
// Manual Trigger
// ============================================

/**
 * Manually trigger evaluation for a specific node.
 * Useful for user-initiated "check for updates" action.
 *
 * @param {string} nodeId - The node to evaluate
 * @param {string} reason - Reason for evaluation
 */
export function triggerEvaluation(nodeId, reason = 'Manual evaluation request') {
    const { trackChange, CHANGE_TYPES } = require('../core/change_tracker.js');

    trackChange(nodeId, CHANGE_TYPES.CONTENT_EDIT, {
        manual: true,
        reason
    });
}

// ============================================
// CSS Styles (injected on init)
// ============================================

function injectStyles() {
    if (document.getElementById('kilo-bridge-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'kilo-bridge-styles';
    styles.textContent = `
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }

        .kilo-indicator {
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            transition: all 0.2s ease;
        }

        .kilo-indicator:hover {
            transform: scale(1.05);
        }

        .kilo-needs-change {
            border-left: 3px solid #dc2626;
        }

        .kilo-no-change {
            border-left: 3px solid #16a34a;
        }
    `;
    document.head.appendChild(styles);
}

// Inject styles on module load
injectStyles();

// ============================================
// Exports
// ============================================

export default {
    initKiloBridge,
    triggerEvaluation
};
