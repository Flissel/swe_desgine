/**
 * RE System Dashboard - Event Bus
 *
 * Central event system for module communication.
 * Replaces direct function calls between modules.
 */

// ============================================
// Event Bus Implementation
// ============================================

const listeners = new Map();
let debugMode = false;

/**
 * Subscribe to an event.
 * @param {string} event - Event name
 * @param {Function} callback - Handler function
 * @returns {Function} - Unsubscribe function
 */
export function on(event, callback) {
    if (!listeners.has(event)) {
        listeners.set(event, new Set());
    }
    listeners.get(event).add(callback);

    // Return unsubscribe function
    return () => off(event, callback);
}

/**
 * Subscribe to an event once.
 * @param {string} event - Event name
 * @param {Function} callback - Handler function
 */
export function once(event, callback) {
    const wrapper = (data) => {
        off(event, wrapper);
        callback(data);
    };
    on(event, wrapper);
}

/**
 * Unsubscribe from an event.
 * @param {string} event - Event name
 * @param {Function} callback - Handler function
 */
export function off(event, callback) {
    listeners.get(event)?.delete(callback);
}

/**
 * Emit an event to all subscribers.
 * @param {string} event - Event name
 * @param {*} data - Event data
 */
export function emit(event, data = null) {
    if (debugMode) {
        console.log(`[Events] ${event}`, data);
    }

    listeners.get(event)?.forEach(callback => {
        try {
            callback(data);
        } catch (error) {
            console.error(`[Events] Error in handler for ${event}:`, error);
        }
    });
}

/**
 * Clear all listeners for an event.
 * @param {string} event - Event name (optional, clears all if not provided)
 */
export function clear(event = null) {
    if (event) {
        listeners.delete(event);
    } else {
        listeners.clear();
    }
}

/**
 * Enable/disable debug logging.
 * @param {boolean} enabled
 */
export function setDebug(enabled) {
    debugMode = enabled;
}

// ============================================
// Standard Events
// ============================================

export const EVENTS = {
    // Node events
    NODE_ADDED: 'node:added',
    NODE_REMOVED: 'node:removed',
    NODE_MOVED: 'node:moved',
    NODE_SELECTED: 'node:selected',
    NODE_DESELECTED: 'node:deselected',
    NODES_CLEARED: 'nodes:cleared',

    // Connection events
    CONNECTION_ADDED: 'connection:added',
    CONNECTION_REMOVED: 'connection:removed',
    CONNECTIONS_UPDATED: 'connections:updated',

    // Layout events
    LAYOUT_CHANGED: 'layout:changed',
    LAYOUT_STARTED: 'layout:started',
    LAYOUT_COMPLETED: 'layout:completed',

    // Data events
    DATA_LOADING: 'data:loading',
    DATA_LOADED: 'data:loaded',
    DATA_ERROR: 'data:error',

    // Canvas events
    ZOOM_CHANGED: 'zoom:changed',
    PAN_CHANGED: 'pan:changed',
    FIT_TO_VIEW: 'fit:view',

    // Diagram events
    DIAGRAM_RENDERED: 'diagram:rendered',
    DIAGRAM_ERROR: 'diagram:error',
    DIAGRAM_STACK_TOGGLE: 'diagram:stack-toggle',

    // WebSocket events
    WS_CONNECTED: 'ws:connected',
    WS_DISCONNECTED: 'ws:disconnected',
    WS_MESSAGE: 'ws:message',

    // UI events
    MINIMAP_UPDATE: 'minimap:update',
    TOOLTIP_SHOW: 'tooltip:show',
    TOOLTIP_HIDE: 'tooltip:hide',

    // Change tracking events (for domino effect)
    NODE_EDITED: 'node:edited',
    CHANGE_TRACKED: 'change:tracked',
    CHANGE_PROPAGATION_START: 'change:propagation_start',
    CHANGE_PROPAGATION_COMPLETE: 'change:propagation_complete',
    AGENT_RESPONSE_RECEIVED: 'agent:response_received',

    // Kilo Agent events
    KILO_EVALUATE_REQUEST: 'kilo:evaluate_request',
    KILO_EVALUATE_RESPONSE: 'kilo:evaluate_response'
};

// ============================================
// Initialization
// ============================================

export function initEvents() {
    console.log('[Events] Event bus initialized');

    // Enable debug in development
    if (window.location.hostname === 'localhost') {
        setDebug(false); // Set to true for verbose logging
    }
}

// ============================================
// Export for backwards compatibility
// ============================================

export default {
    on,
    once,
    off,
    emit,
    clear,
    setDebug,
    EVENTS,
    initEvents
};
