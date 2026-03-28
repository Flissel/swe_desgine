/**
 * RE System Dashboard - State Management Module
 *
 * Central state object and helper utilities
 */

// ============================================
// Application State
// ============================================

export const state = {
    ws: null,
    connected: false
};

// ============================================
// DOM References (initialized in app.js)
// ============================================

export const elements = {
    sidebar: null,
    projectList: null,
    projectInfo: null,
    progressFill: null,
    progressText: null,
    logContent: null,
    connectionStatus: null
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
    elements.projectInfo = document.getElementById('project-info');
    elements.progressFill = document.getElementById('progress-fill');
    elements.progressText = document.getElementById('progress-text');
    elements.logContent = document.getElementById('log-content');
    elements.connectionStatus = document.getElementById('connection-status');
    elements.projectList = document.getElementById('project-list');
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
