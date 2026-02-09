/**
 * RE System Dashboard - Change Tracker Module
 *
 * Monitors node changes and builds a notification queue for the domino effect.
 * When a node changes, all connected nodes are notified and can be evaluated
 * by the Kilo Agent to determine if they need updates.
 */

import { state, log } from '../state.js';
import { emit, on, EVENTS } from './events.js';

// ============================================
// Notification Queue
// ============================================

const notificationQueue = [];
let queueIdCounter = 0;

// ============================================
// Change Types
// ============================================

export const CHANGE_TYPES = {
    CONTENT_EDIT: 'content_edit',       // Title, description, etc.
    STRUCTURE_CHANGE: 'structure_change', // Added/removed connections
    DIAGRAM_UPDATE: 'diagram_update',   // Mermaid code changed
    CONNECTION_CHANGE: 'connection_change', // Link added/removed
    STATUS_CHANGE: 'status_change'      // Priority, status, etc.
};

// ============================================
// Core Functions
// ============================================

/**
 * Track a change to a node.
 * Creates a notification and adds it to the queue.
 *
 * @param {string} nodeId - The ID of the changed node
 * @param {string} changeType - Type of change (from CHANGE_TYPES)
 * @param {Object} changeDetails - Details about the change
 * @returns {Object} The created notification
 */
export function trackChange(nodeId, changeType, changeDetails = {}) {
    const node = state.nodes[nodeId];
    if (!node) {
        log('warn', `[ChangeTracker] Node not found: ${nodeId}`);
        return null;
    }

    // Find all connected nodes (domino effect targets)
    const affectedNodes = findConnectedNodes(nodeId);

    const notification = {
        id: `change-${++queueIdCounter}-${Date.now()}`,
        nodeId,
        nodeType: node.type,
        nodeTitle: node.data?.title || node.data?.name || nodeId,
        changeType,
        changeDetails,
        affectedNodes,
        timestamp: new Date().toISOString(),
        status: 'pending',  // pending, processing, completed, failed
        responses: {},      // nodeId -> { acknowledged, needsChange, changeApplied, reason }
        createdAt: Date.now()
    };

    notificationQueue.push(notification);

    // Log the change
    log('info', `[ChangeTracker] Change tracked: ${changeType} on ${nodeId} (affects ${affectedNodes.length} nodes)`);

    // Emit event for UI and Kilo Agent bridge
    emit(EVENTS.CHANGE_TRACKED, notification);

    return notification;
}

/**
 * Find all nodes directly connected to the given node.
 *
 * @param {string} nodeId - The node to find connections for
 * @returns {Array<string>} Array of connected node IDs
 */
function findConnectedNodes(nodeId) {
    const connected = new Set();

    state.connections.forEach(conn => {
        if (conn.from === nodeId && state.nodes[conn.to]) {
            connected.add(conn.to);
        }
        if (conn.to === nodeId && state.nodes[conn.from]) {
            connected.add(conn.from);
        }
    });

    return Array.from(connected);
}

/**
 * Process a response from the Kilo Agent for a notification.
 *
 * @param {string} notificationId - The notification ID
 * @param {string} respondingNodeId - The node that was evaluated
 * @param {Object} response - The agent's response
 */
export function processAgentResponse(notificationId, respondingNodeId, response) {
    const notification = notificationQueue.find(n => n.id === notificationId);
    if (!notification) {
        log('warn', `[ChangeTracker] Notification not found: ${notificationId}`);
        return;
    }

    notification.responses[respondingNodeId] = {
        acknowledged: true,
        needsChange: response.needsChange || false,
        changeApplied: response.changeApplied || false,
        reason: response.reason || 'No reason provided',
        timestamp: new Date().toISOString()
    };

    // Check if all affected nodes have responded
    const allResponded = notification.affectedNodes.every(
        nodeId => notification.responses[nodeId]?.acknowledged
    );

    if (allResponded) {
        notification.status = 'completed';
        notification.completedAt = Date.now();

        log('info', `[ChangeTracker] Propagation complete for ${notificationId}`);
        emit(EVENTS.CHANGE_PROPAGATION_COMPLETE, notification);
    }

    // Emit individual response event
    emit(EVENTS.AGENT_RESPONSE_RECEIVED, {
        notificationId,
        respondingNodeId,
        response: notification.responses[respondingNodeId]
    });
}

/**
 * Mark a notification as processing (being evaluated by agent).
 *
 * @param {string} notificationId - The notification ID
 */
export function markAsProcessing(notificationId) {
    const notification = notificationQueue.find(n => n.id === notificationId);
    if (notification) {
        notification.status = 'processing';
        emit(EVENTS.CHANGE_PROPAGATION_START, notification);
    }
}

/**
 * Mark a notification as failed.
 *
 * @param {string} notificationId - The notification ID
 * @param {string} reason - Failure reason
 */
export function markAsFailed(notificationId, reason) {
    const notification = notificationQueue.find(n => n.id === notificationId);
    if (notification) {
        notification.status = 'failed';
        notification.failureReason = reason;
        notification.failedAt = Date.now();
    }
}

// ============================================
// Queue Management
// ============================================

/**
 * Get current queue status.
 *
 * @returns {Object} Queue status info
 */
export function getQueueStatus() {
    return {
        total: notificationQueue.length,
        pending: notificationQueue.filter(n => n.status === 'pending').length,
        processing: notificationQueue.filter(n => n.status === 'processing').length,
        completed: notificationQueue.filter(n => n.status === 'completed').length,
        failed: notificationQueue.filter(n => n.status === 'failed').length
    };
}

/**
 * Get all notifications (optionally filtered by status).
 *
 * @param {string} status - Optional status filter
 * @returns {Array} Notifications
 */
export function getNotifications(status = null) {
    if (status) {
        return notificationQueue.filter(n => n.status === status);
    }
    return [...notificationQueue];
}

/**
 * Get a specific notification by ID.
 *
 * @param {string} notificationId - The notification ID
 * @returns {Object|null} The notification or null
 */
export function getNotification(notificationId) {
    return notificationQueue.find(n => n.id === notificationId) || null;
}

/**
 * Get pending notifications (for processing).
 *
 * @returns {Array} Pending notifications
 */
export function getPendingNotifications() {
    return notificationQueue.filter(n => n.status === 'pending');
}

/**
 * Clear completed notifications older than given age.
 *
 * @param {number} maxAgeMs - Maximum age in milliseconds (default: 1 hour)
 */
export function clearOldNotifications(maxAgeMs = 3600000) {
    const now = Date.now();
    const before = notificationQueue.length;

    for (let i = notificationQueue.length - 1; i >= 0; i--) {
        const notification = notificationQueue[i];
        if (notification.status === 'completed' &&
            notification.completedAt &&
            (now - notification.completedAt) > maxAgeMs) {
            notificationQueue.splice(i, 1);
        }
    }

    const removed = before - notificationQueue.length;
    if (removed > 0) {
        log('info', `[ChangeTracker] Cleared ${removed} old notifications`);
    }
}

/**
 * Clear all notifications.
 */
export function clearAllNotifications() {
    notificationQueue.length = 0;
    log('info', '[ChangeTracker] Cleared all notifications');
}

// ============================================
// Initialization
// ============================================

/**
 * Initialize change tracking listeners.
 * Sets up event listeners for node edits, diagram updates, etc.
 */
export function initChangeTracker() {
    // Listen for node edits
    on(EVENTS.NODE_EDITED, ({ nodeId, changes }) => {
        trackChange(nodeId, CHANGE_TYPES.CONTENT_EDIT, changes);
    });

    // Listen for diagram updates
    on(EVENTS.DIAGRAM_RENDERED, ({ nodeId }) => {
        // Only track if it was a user-initiated update, not initial load
        // We can check this by looking at the notification queue
        // For now, we'll skip auto-tracking diagram renders
    });

    // Listen for connection changes
    on(EVENTS.CONNECTION_ADDED, ({ from, to }) => {
        // Track change for both nodes
        trackChange(from, CHANGE_TYPES.CONNECTION_CHANGE, { action: 'added', linkedTo: to });
    });

    on(EVENTS.CONNECTION_REMOVED, ({ from, to }) => {
        trackChange(from, CHANGE_TYPES.CONNECTION_CHANGE, { action: 'removed', linkedTo: to });
    });

    log('info', '[ChangeTracker] Initialized');
}

// ============================================
// Exports
// ============================================

export default {
    CHANGE_TYPES,
    trackChange,
    processAgentResponse,
    markAsProcessing,
    markAsFailed,
    getQueueStatus,
    getNotifications,
    getNotification,
    getPendingNotifications,
    clearOldNotifications,
    clearAllNotifications,
    initChangeTracker
};
