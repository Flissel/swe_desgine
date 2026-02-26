/**
 * RE System Dashboard - State Management Module
 *
 * Central state object and helper utilities
 */

// ============================================
// Application State
// ============================================

export const state = {
    canvas: {
        x: 0,
        y: 0,
        zoom: 1.0,
        minZoom: 0.1,
        maxZoom: 3.0
    },
    dragging: {
        active: false,
        node: null,
        startX: 0,
        startY: 0,
        nodeStartX: 0,
        nodeStartY: 0
    },
    panning: {
        active: false,
        startX: 0,
        startY: 0,
        canvasStartX: 0,
        canvasStartY: 0
    },
    nodes: {},
    nodeCounters: {},  // Track count per node type for positioning
    connections: [],
    ws: null,
    connected: false,
    // Group state for collapsed/expanded node groups
    groupState: {
        expanded: new Set(),   // Groups explicitly expanded by user
        collapsed: new Set(),  // Groups explicitly collapsed by user
        groups: {}             // Detected groups cache
    }
};

// ============================================
// DOM References (initialized in app.js)
// ============================================

export const elements = {
    canvas: null,
    canvasContainer: null,
    canvasNodes: null,
    nodesLayer: null,  // Alias for canvasNodes
    connectionsLayer: null,
    minimap: null,
    minimapViewport: null,
    minimapNodes: null,
    sidebar: null,
    sidebarList: null,
    projectList: null,
    logContent: null,
    detailPanel: null,
    qualityGateStatus: null,
    statusText: null,
    statusDot: null
};

// ============================================
// Helper Functions
// ============================================

/**
 * Get tag type for CSS class based on tag name
 */
export function getTagType(tag) {
    const tagLower = tag.toLowerCase();
    if (tagLower === 'smoke') return 'smoke';
    if (tagLower === 'regression') return 'regression';
    if (tagLower.includes('happy') || tagLower.includes('positive')) return 'happy';
    if (tagLower.includes('negative') || tagLower.includes('error')) return 'negative';
    if (tagLower.includes('edge') || tagLower.includes('boundary')) return 'edge';
    return 'default';
}

/**
 * Highlight Gherkin syntax for display in detail panel
 */
export function highlightGherkin(code) {
    // Escape HTML entities
    let html = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Highlight keywords
    const keywords = ['Feature:', 'Background:', 'Scenario:', 'Scenario Outline:',
                      'Given', 'When', 'Then', 'And', 'But', 'Examples:'];
    keywords.forEach(kw => {
        html = html.replace(new RegExp(`^(\\s*)(${kw})`, 'gm'),
            '$1<span class="gherkin-keyword">$2</span>');
    });

    // Highlight tags (@@tag)
    html = html.replace(/(@@[\w-]+)/g, '<span class="gherkin-tag">$1</span>');

    // Highlight comments (# ...)
    html = html.replace(/^(\s*#.*)$/gm, '<span class="gherkin-comment">$1</span>');

    // Highlight placeholders (<placeholder>)
    html = html.replace(/(&lt;[\w_]+&gt;)/g, '<span class="gherkin-placeholder">$1</span>');

    return html;
}

/**
 * Initialize DOM element references
 */
export function initElements() {
    elements.canvas = document.getElementById('canvas');
    elements.canvasContainer = document.getElementById('canvas-container');
    elements.canvasNodes = document.getElementById('canvas-nodes');
    elements.nodesLayer = elements.canvasNodes;  // Alias
    elements.connectionsLayer = document.getElementById('connections-layer');
    elements.projectInfo = document.getElementById('project-info');
    elements.progressFill = document.getElementById('progress-fill');
    elements.progressText = document.getElementById('progress-text');
    elements.zoomLevel = document.getElementById('zoom-level');
    elements.logContent = document.getElementById('log-content');
    elements.minimapContent = document.getElementById('minimap-content');
    elements.minimapViewport = document.getElementById('minimap-viewport');
    elements.connectionStatus = document.getElementById('connection-status');
    elements.requirementsList = document.getElementById('requirements-list');
    elements.userStoriesList = document.getElementById('user-stories-list');
    elements.epicsList = document.getElementById('epics-list');
    elements.testsList = document.getElementById('tests-list');
    elements.diagramsList = document.getElementById('diagrams-list');
    elements.screensList = document.getElementById('screens-list');
    elements.apiList = document.getElementById('api-list');
    elements.personasList = document.getElementById('personas-list');
    elements.componentsList = document.getElementById('components-list');
    elements.tasksList = document.getElementById('tasks-list');
    elements.servicesList = document.getElementById('services-list');
    elements.stateMachinesList = document.getElementById('state-machines-list');
    elements.reqCount = document.getElementById('req-count');
    elements.usCount = document.getElementById('us-count');
    elements.epicCount = document.getElementById('epic-count');
    elements.testCount = document.getElementById('test-count');
    elements.diagramCount = document.getElementById('diagram-count');
    elements.screenCount = document.getElementById('screen-count');
    elements.apiCount = document.getElementById('api-count');
    elements.personaCount = document.getElementById('persona-count');
    elements.componentCount = document.getElementById('component-count');
    elements.taskCount = document.getElementById('task-count');
    elements.serviceCount = document.getElementById('service-count');
    elements.stateMachineCount = document.getElementById('state-machine-count');
    elements.projectList = document.getElementById('project-list');
    elements.detailPanel = document.getElementById('detail-panel');
    elements.sidebar = document.getElementById('sidebar');
}

/**
 * Log message to console and UI log
 */
export function log(level, message) {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
    console.log(logLine);

    if (elements.logContent) {
        const line = document.createElement('div');
        line.className = `log-${level}`;
        line.textContent = logLine;
        elements.logContent.appendChild(line);
        elements.logContent.scrollTop = elements.logContent.scrollHeight;
    }
}

// ============================================
// Safety Helpers
// ============================================

/**
 * Escape HTML to prevent XSS attacks
 */
export function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * Safely query within a parent element
 * @param {HTMLElement} parent - Parent element to search within
 * @param {string} selector - CSS selector
 * @returns {HTMLElement|null} Found element or null
 */
export function safeQuery(parent, selector) {
    if (!parent) {
        console.warn(`[DOM] Parent element is null for selector: ${selector}`);
        return null;
    }
    return parent.querySelector(selector);
}

/**
 * Safely set text content on an element
 * @param {HTMLElement} element - Target element
 * @param {string} text - Text to set
 */
export function safeSetText(element, text) {
    if (element) {
        element.textContent = text;
    }
}

/**
 * Safely get element from elements registry
 * @param {string} key - Element key
 * @returns {HTMLElement|null} Element or null
 */
export function getElement(key) {
    const el = elements[key];
    if (!el) {
        console.warn(`[Elements] ${key} not found`);
    }
    return el;
}

// ============================================
// Event Listener Registry (for cleanup)
// ============================================

const eventListenerRegistry = new Map();

/**
 * Register an event listener for later cleanup
 * @param {HTMLElement} element - Target element
 * @param {string} event - Event name
 * @param {Function} handler - Event handler
 * @param {Object} options - Event options
 */
export function registerEventListener(element, event, handler, options) {
    element.addEventListener(event, handler, options);

    if (!eventListenerRegistry.has(element)) {
        eventListenerRegistry.set(element, []);
    }
    eventListenerRegistry.get(element).push({ event, handler, options });
}

/**
 * Clean up event listeners for a specific element
 * @param {HTMLElement} element - Element to clean up
 */
export function cleanupEventListeners(element) {
    const listeners = eventListenerRegistry.get(element);
    if (listeners) {
        listeners.forEach(({ event, handler, options }) => {
            element.removeEventListener(event, handler, options);
        });
        eventListenerRegistry.delete(element);
    }
}

/**
 * Clean up all registered event listeners
 */
export function cleanupAllEventListeners() {
    eventListenerRegistry.forEach((listeners, element) => {
        listeners.forEach(({ event, handler, options }) => {
            element.removeEventListener(event, handler, options);
        });
    });
    eventListenerRegistry.clear();
}
