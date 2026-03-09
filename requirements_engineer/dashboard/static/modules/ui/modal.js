/**
 * RE System Dashboard - Modal Module
 *
 * Provides reusable modal system for:
 * - Diagram gallery view (all diagrams for a requirement)
 * - Test case details
 * - User story list (for epics)
 * - Group expansion view
 */

import { state, escapeHtml, highlightGherkin, getTagType } from '../state.js';
import { DIAGRAM_TYPES, getDiagramTypeFromId, getDiagramTypeFromCode } from '../layouts/grouping.js';
import { pauseResizeObserver, resumeResizeObserver } from '../connections.js';
import { openDiagramKiloPanel } from './diagramKiloPanel.js';

// ============================================
// Modal State
// ============================================

let activeModal = null;
let mermaidRenderQueue = [];
let queuedIds = new Set();  // CRASH FIX: Prevent duplicate renders
let modalEventListeners = [];  // CRASH FIX: Track listeners for cleanup

// ============================================
// Size Limits (CRASH PREVENTION)
// ============================================
const MAX_MERMAID_CODE_LENGTH = 15000;  // 15KB - larger codes crash browser
const MAX_SVG_LENGTH = 100000;  // 100KB - larger SVGs freeze during innerHTML

// ============================================
// Debug Logging
// ============================================

const DEBUG_MODAL = true;  // Set to false to disable verbose logging

function debugLog(...args) {
    if (DEBUG_MODAL) {
        console.log('[Modal Debug]', new Date().toISOString().substr(11, 12), ...args);
    }
}

function debugError(...args) {
    console.error('[Modal ERROR]', new Date().toISOString().substr(11, 12), ...args);
}

function debugWarn(...args) {
    console.warn('[Modal WARN]', new Date().toISOString().substr(11, 12), ...args);
}

// ============================================
// Event Listener Management (CRASH FIX)
// ============================================

/**
 * Add event listener and track for cleanup
 * CRASH FIX: Prevents memory leaks from accumulated listeners
 */
function addModalEventListener(element, event, handler) {
    if (!element) return;
    element.addEventListener(event, handler);
    modalEventListeners.push({ element, event, handler });
}

/**
 * Clean up all tracked event listeners
 */
function cleanupModalEventListeners() {
    debugLog('Cleaning up', modalEventListeners.length, 'event listeners');
    modalEventListeners.forEach(({ element, event, handler }) => {
        try {
            element.removeEventListener(event, handler);
        } catch (e) {
            // Element may no longer exist
        }
    });
    modalEventListeners = [];
}

// ============================================
// Core Modal Functions
// ============================================

/**
 * Open a modal with given configuration
 * @param {Object} config - Modal configuration
 * @param {string} config.type - Modal type: 'diagram-gallery', 'test-cases', 'user-stories', 'single-diagram'
 * @param {string} config.title - Modal title
 * @param {string} config.size - Modal size: 'small', 'medium', 'large', 'xl'
 * @param {*} config.data - Data for the modal content
 */
export function openModal(config) {
    debugLog('openModal called', { type: config.type, title: config.title, size: config.size });

    // CRASH FIX #4: Pause ResizeObserver to prevent cascading updates
    try {
        pauseResizeObserver();
    } catch (e) {
        debugWarn('pauseResizeObserver failed:', e);
    }

    try {
        closeModal();
    } catch (e) {
        debugError('closeModal failed:', e);
    }

    const modal = document.createElement('div');
    modal.className = 're-modal';
    modal.id = 'active-modal';

    modal.innerHTML = `
        <div class="modal-backdrop"></div>
        <div class="modal-container modal-${config.size || 'medium'}">
            <div class="modal-header">
                <h2 class="modal-title">${escapeHtml(config.title)}</h2>
                <div class="modal-tabs" id="modal-tabs"></div>
                <button class="modal-close" aria-label="Close">×</button>
            </div>
            <div class="modal-body" id="modal-body">
                <div class="modal-loading">Loading...</div>
            </div>
            <div class="modal-footer" id="modal-footer"></div>
        </div>
    `;

    document.body.appendChild(modal);
    activeModal = modal;

    // Event listeners
    modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
    modal.querySelector('.modal-close').addEventListener('click', closeModal);
    document.addEventListener('keydown', handleModalKeydown);

    // PERFORMANCE: Show modal first, then render content asynchronously
    // This allows the modal to appear immediately (good INP)
    // BUGFIX: Capture modal reference to check if still active when callback fires
    const modalRef = modal;

    requestAnimationFrame(() => {
        modal.classList.add('visible');

        // Use requestIdleCallback if available, otherwise setTimeout
        const deferredRender = typeof requestIdleCallback === 'function'
            ? (cb) => requestIdleCallback(cb, { timeout: 100 })
            : (cb) => setTimeout(cb, 16);

        deferredRender(() => {
            // BUGFIX: Check if this modal is still the active one
            // When user rapidly switches between diagrams, old deferredRender callbacks
            // might fire after a new modal was opened
            if (modalRef !== activeModal) {
                debugWarn('deferredRender fired but modal is no longer active - skipping render');
                return;
            }

            debugLog('deferredRender executing, calling renderModalContent');
            try {
                // BUGFIX: Pass modal reference to scope element lookups
                renderModalContent(config, modalRef);
                debugLog('renderModalContent completed successfully');
            } catch (e) {
                debugError('renderModalContent CRASHED:', e);
                debugError('Stack:', e.stack);
                // Show error in modal body - use scoped lookup
                const body = modalRef.querySelector('#modal-body');
                if (body) {
                    body.innerHTML = `<div class="modal-error">
                        <h3>❌ Render Error</h3>
                        <pre>${e.message}\n${e.stack}</pre>
                    </div>`;
                }
            }
        });
    });

    debugLog('openModal setup complete');

    // Dispatch event
    window.dispatchEvent(new CustomEvent('modal:opened', {
        detail: { type: config.type, title: config.title }
    }));
}

/**
 * Close the active modal
 */
export function closeModal() {
    if (!activeModal) return;

    debugLog('closeModal called');

    // FIX: Speichere Referenz auf das ZU SCHLIESSENDE Modal
    // Dies verhindert Race Condition wenn openModal() sofort aufgerufen wird
    const modalToClose = activeModal;

    modalToClose.classList.remove('visible');

    // CRASH FIX: Clean up all tracked event listeners
    cleanupModalEventListeners();

    // CRASH FIX: Clear render queue and dedup set
    mermaidRenderQueue = [];
    queuedIds.clear();

    // CRASH FIX: Clean up global mermaid code reference
    if (window._currentDiagramCode) {
        window._currentDiagramCode = null;
    }

    // FIX: activeModal sofort auf null setzen damit openModal() funktioniert
    activeModal = null;

    // Das ALTE Modal nach Animation entfernen (mit gespeicherter Referenz)
    setTimeout(() => {
        modalToClose.remove();
    }, 200);

    document.removeEventListener('keydown', handleModalKeydown);

    // CRASH FIX #4: Resume ResizeObserver
    try {
        resumeResizeObserver();
    } catch (e) {
        debugWarn('resumeResizeObserver failed:', e);
    }

    // Dispatch event
    window.dispatchEvent(new CustomEvent('modal:closed', {}));

    debugLog('closeModal complete');
}

/**
 * Handle keyboard events for modal
 */
function handleModalKeydown(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
}

// ============================================
// Content Renderers
// ============================================

/**
 * Render modal content based on type
 * @param {Object} config - Modal configuration
 * @param {HTMLElement} modalRef - Reference to the modal element (for scoped lookups)
 */
function renderModalContent(config, modalRef) {
    debugLog('renderModalContent called with type:', config.type);

    // BUGFIX: Use scoped element lookups to avoid affecting wrong modal
    // when multiple modals exist during rapid switching
    const body = modalRef ? modalRef.querySelector('#modal-body') : document.getElementById('modal-body');
    const tabs = modalRef ? modalRef.querySelector('#modal-tabs') : document.getElementById('modal-tabs');
    const footer = modalRef ? modalRef.querySelector('#modal-footer') : document.getElementById('modal-footer');

    if (!body) {
        debugError('modal-body element not found!');
        return;
    }

    debugLog('Switching on type:', config.type);

    switch (config.type) {
        case 'diagram-gallery':
            debugLog('Rendering diagram-gallery...');
            renderDiagramGallery(body, tabs, config);
            break;
        case 'test-cases':
            debugLog('Rendering test-cases...');
            renderTestCases(body, config);
            break;
        case 'user-stories':
            debugLog('Rendering user-stories...');
            renderUserStories(body, config);
            break;
        case 'tasks':
            debugLog('Rendering tasks...');
            renderTasks(body, config);
            break;
        case 'api-package':
            debugLog('Rendering api-package...');
            renderApiPackage(body, tabs, config);
            break;
        case 'task-group':
            debugLog('Rendering task-group...');
            renderTaskGroup(body, config);
            break;
        case 'state-machine':
            debugLog('Rendering state-machine...');
            renderStateMachine(body, config);
            break;
        case 'single-diagram':
            debugLog('Rendering single-diagram...', { diagramId: config.diagramId });
            renderSingleDiagram(body, config);
            break;
        case 'edit-node':
            debugLog('Rendering edit-node...', { nodeId: config.data?.nodeId });
            // Dynamic import to avoid circular dependency
            import('./editModal.js').then(module => {
                module.renderEditForm(body, config);
            }).catch(e => {
                debugError('Failed to load editModal:', e);
                body.innerHTML = `<div class="modal-error">Failed to load edit form</div>`;
            });
            break;
        default:
            debugLog('Rendering default content...');
            body.innerHTML = `<div class="modal-content-text">${config.content || ''}</div>`;
    }

    debugLog('renderModalContent switch completed');

    if (config.footer) {
        footer.innerHTML = config.footer;
        footer.style.display = 'flex';
    } else {
        footer.style.display = 'none';
    }
}

/**
 * Render diagram gallery modal with PROGRESSIVE loading
 * PERFORMANCE: Builds DOM incrementally to avoid blocking
 */
function renderDiagramGallery(body, tabs, config) {
    const { diagrams, parentId } = config;

    if (!diagrams || diagrams.length === 0) {
        body.innerHTML = '<div class="modal-empty">Keine Diagramme gefunden</div>';
        return;
    }

    // Group diagrams by type (fast operation)
    const byType = {};
    diagrams.forEach(d => {
        const type = getDiagramTypeFromId(d.id) || getDiagramTypeFromCode(d.mermaid_code);
        if (!byType[type]) byType[type] = [];
        byType[type].push(d);
    });

    const sortedTypes = Object.keys(byType).sort((a, b) =>
        (DIAGRAM_TYPES[a]?.order || 99) - (DIAGRAM_TYPES[b]?.order || 99)
    );

    // PERFORMANCE: Render minimal structure first
    tabs.innerHTML = sortedTypes.map((type, i) => `
        <button class="modal-tab ${i === 0 ? 'active' : ''}"
                data-type="${type}"
                onclick="window.modalSwitchTab('${type}')">
            ${DIAGRAM_TYPES[type]?.icon || '📊'} ${DIAGRAM_TYPES[type]?.name || type}
            <span class="tab-count">${byType[type].length}</span>
        </button>
    `).join('');

    // Create container with loading state
    body.innerHTML = `
        <div class="diagram-gallery" id="diagram-gallery-container">
            <div class="modal-loading">Loading diagrams...</div>
        </div>
    `;

    const container = document.getElementById('diagram-gallery-container');
    if (!container) return;

    // PERFORMANCE: Progressive section rendering
    let typeIndex = 0;

    function renderNextSection() {
        if (!activeModal || typeIndex >= sortedTypes.length) {
            // Remove loading indicator
            const loading = container.querySelector('.modal-loading');
            if (loading) loading.remove();
            return;
        }

        const type = sortedTypes[typeIndex];
        const typeDiagrams = byType[type];
        typeIndex++;

        // Create section element
        const section = document.createElement('div');
        section.className = `diagram-gallery-section ${typeIndex === 1 ? 'active' : ''}`;
        section.dataset.type = type;

        const grid = document.createElement('div');
        grid.className = 'diagram-grid';
        section.appendChild(grid);

        // Remove loading on first section
        if (typeIndex === 1) {
            const loading = container.querySelector('.modal-loading');
            if (loading) loading.remove();
        }

        container.appendChild(section);

        // PERFORMANCE: Add diagram cards in batches
        const BATCH_SIZE = 3;
        let diagramIndex = 0;

        function addDiagramBatch() {
            if (!activeModal || diagramIndex >= typeDiagrams.length) {
                // Move to next section
                requestAnimationFrame(renderNextSection);
                return;
            }

            const batch = typeDiagrams.slice(diagramIndex, diagramIndex + BATCH_SIZE);
            diagramIndex += BATCH_SIZE;

            batch.forEach(d => {
                const card = document.createElement('div');
                card.className = 'diagram-card';
                card.dataset.id = d.id;
                // Store mermaid code for deferred rendering on tab switch
                card.dataset.mermaidCode = d.mermaid_code || '';
                card.innerHTML = `
                    <div class="diagram-card-preview" id="preview-${escapeHtml(d.id)}">
                        <div class="diagram-loading">
                            <div class="loading-spinner"></div>
                        </div>
                    </div>
                    <div class="diagram-card-footer">
                        <span class="diagram-card-title">${escapeHtml(d.id)}</span>
                        <button class="btn-fullscreen" title="Vollbild">⛶</button>
                    </div>
                `;

                // Add click handler with tracking (CRASH FIX: tracked for cleanup)
                const fullscreenBtn = card.querySelector('.btn-fullscreen');
                if (fullscreenBtn) {
                    const handler = (e) => {
                        e.stopPropagation();
                        window.modalOpenFullDiagram(d.id);
                    };
                    addModalEventListener(fullscreenBtn, 'click', handler);
                }

                grid.appendChild(card);

                // Queue for render if first section (visible)
                if (typeIndex === 1) {
                    queueDiagramRender(d.id, d.mermaid_code);
                }
            });

            requestAnimationFrame(addDiagramBatch);
        }

        requestAnimationFrame(addDiagramBatch);
    }

    // Start progressive rendering
    requestAnimationFrame(renderNextSection);

    // Start mermaid rendering after initial structure is built
    setTimeout(() => processDiagramRenderQueue(), 300);
}

/**
 * Render test cases modal with PROGRESSIVE loading
 * PERFORMANCE: Defer gherkin highlighting which is expensive
 */
function renderTestCases(body, config) {
    const { tests, parentId } = config;

    if (!tests || tests.length === 0) {
        body.innerHTML = '<div class="modal-empty">Keine Test Cases gefunden</div>';
        return;
    }

    // Calculate total scenarios (fast)
    const totalScenarios = tests.reduce((sum, t) => sum + (t.scenario_count || 0), 0);

    // PERFORMANCE: Render summary and container first
    body.innerHTML = `
        <div class="test-summary">
            <span class="test-summary-item">
                <strong>${tests.length}</strong> Test Files
            </span>
            <span class="test-summary-item">
                <strong>${totalScenarios}</strong> Scenarios
            </span>
        </div>
        <div class="test-list" id="test-list-container">
            <div class="tasks-loading">Loading tests...</div>
        </div>
    `;

    const container = document.getElementById('test-list-container');
    if (!container) return;

    // PERFORMANCE: Progressive rendering
    const BATCH_SIZE = 3;
    let testIndex = 0;

    function addTestBatch() {
        if (!activeModal || testIndex >= tests.length) {
            const loading = container.querySelector('.tasks-loading');
            if (loading) loading.remove();
            return;
        }

        // Remove loading on first batch
        if (testIndex === 0) {
            const loading = container.querySelector('.tasks-loading');
            if (loading) loading.remove();
        }

        const batch = tests.slice(testIndex, testIndex + BATCH_SIZE);
        testIndex += BATCH_SIZE;

        batch.forEach((test, batchIdx) => {
            const globalIdx = testIndex - BATCH_SIZE + batchIdx;
            const item = document.createElement('div');
            item.className = `test-item ${globalIdx === 0 ? 'expanded' : ''}`;
            item.dataset.index = globalIdx;

            // PERFORMANCE: Build tags without expensive operations
            const tagsHtml = test.tags && test.tags.length > 0
                ? `<div class="test-tags">${test.tags.map(t =>
                    `<span class="tag-badge tag-${getTagType(t)}">${escapeHtml(t)}</span>`
                  ).join('')}</div>`
                : '';

            // PERFORMANCE: Defer gherkin highlighting - show plain text first
            const contentHtml = test.content
                ? `<pre class="gherkin-code" data-needs-highlight="true">${escapeHtml(test.content)}</pre>`
                : '<p class="test-no-content">Kein Gherkin-Code verfügbar</p>';

            item.innerHTML = `
                <div class="test-item-header">
                    <span class="test-icon">🧪</span>
                    <span class="test-title">${escapeHtml(test.title || test.id)}</span>
                    <span class="test-scenario-count">${test.scenario_count || 0} Scenarios</span>
                    <span class="test-expand-icon">▼</span>
                </div>
                <div class="test-item-body">
                    ${tagsHtml}
                    ${contentHtml}
                </div>
            `;

            // Add click handler
            const header = item.querySelector('.test-item-header');
            header?.addEventListener('click', () => {
                item.classList.toggle('expanded');

                // LAZY HIGHLIGHT: Only highlight when expanded for the first time
                const pre = item.querySelector('.gherkin-code[data-needs-highlight="true"]');
                if (pre && item.classList.contains('expanded')) {
                    pre.removeAttribute('data-needs-highlight');
                    // Defer highlighting to avoid blocking
                    requestIdleCallback(() => {
                        if (test.content) {
                            pre.innerHTML = highlightGherkin(test.content);
                        }
                    }, { timeout: 200 });
                }
            });

            container.appendChild(item);
        });

        requestAnimationFrame(addTestBatch);
    }

    // Start progressive rendering
    requestAnimationFrame(addTestBatch);
}

/**
 * Render user stories modal with PROGRESSIVE loading
 */
function renderUserStories(body, config) {
    const { stories, parentId, epicTitle } = config;

    if (!stories || stories.length === 0) {
        body.innerHTML = '<div class="modal-empty">Keine User Stories gefunden</div>';
        return;
    }

    // Group by priority (fast)
    const byPriority = { 'MUST': [], 'SHOULD': [], 'COULD': [], 'other': [] };
    stories.forEach(s => {
        const priority = (s.priority || '').toUpperCase();
        if (byPriority[priority]) {
            byPriority[priority].push(s);
        } else {
            byPriority.other.push(s);
        }
    });

    // PERFORMANCE: Render summary and container first
    body.innerHTML = `
        <div class="stories-summary">
            <span class="stories-summary-item priority-must">
                <strong>${byPriority.MUST.length}</strong> MUST
            </span>
            <span class="stories-summary-item priority-should">
                <strong>${byPriority.SHOULD.length}</strong> SHOULD
            </span>
            <span class="stories-summary-item priority-could">
                <strong>${byPriority.COULD.length}</strong> COULD
            </span>
        </div>
        <div class="stories-list" id="stories-list-container">
            <div class="tasks-loading">Loading stories...</div>
        </div>
    `;

    const container = document.getElementById('stories-list-container');
    if (!container) return;

    // PERFORMANCE: Progressive rendering
    const BATCH_SIZE = 4;
    let storyIndex = 0;

    function addStoryBatch() {
        if (!activeModal || storyIndex >= stories.length) {
            const loading = container.querySelector('.tasks-loading');
            if (loading) loading.remove();
            return;
        }

        // Remove loading on first batch
        if (storyIndex === 0) {
            const loading = container.querySelector('.tasks-loading');
            if (loading) loading.remove();
        }

        const batch = stories.slice(storyIndex, storyIndex + BATCH_SIZE);
        storyIndex += BATCH_SIZE;

        batch.forEach(story => {
            const card = document.createElement('div');
            card.className = 'story-card';
            card.dataset.id = story.id;

            const criteriaHtml = story.acceptance_criteria && story.acceptance_criteria.length > 0
                ? `<div class="story-criteria">
                    <strong>Acceptance Criteria:</strong>
                    <ul>
                        ${story.acceptance_criteria.slice(0, 3).map(c =>
                            `<li>${escapeHtml(c)}</li>`
                        ).join('')}
                        ${story.acceptance_criteria.length > 3
                            ? `<li class="more">+${story.acceptance_criteria.length - 3} more...</li>`
                            : ''}
                    </ul>
                </div>`
                : '';

            card.innerHTML = `
                <div class="story-header">
                    <span class="story-id">${escapeHtml(story.id)}</span>
                    <span class="story-priority priority-${(story.priority || '').toLowerCase()}">
                        ${escapeHtml(story.priority || 'N/A')}
                    </span>
                </div>
                <div class="story-title">${escapeHtml(story.title || '')}</div>
                <div class="story-content">
                    <p><strong>As a</strong> ${escapeHtml(story.persona || 'user')}</p>
                    <p><strong>I want to</strong> ${escapeHtml(story.action || '...')}</p>
                    <p><strong>So that</strong> ${escapeHtml(story.benefit || '...')}</p>
                </div>
                ${criteriaHtml}
                <div class="story-footer">
                    <button class="btn-secondary btn-tests">🧪 Tests anzeigen</button>
                    <button class="btn-focus btn-canvas">→ Im Canvas</button>
                </div>
            `;

            // Add click handlers (avoid inline onclick)
            card.querySelector('.btn-tests')?.addEventListener('click', () => {
                window.openTestCasesModal(story.id);
            });
            card.querySelector('.btn-canvas')?.addEventListener('click', () => {
                window.modalFocusNode(story.id);
            });

            container.appendChild(card);
        });

        requestAnimationFrame(addStoryBatch);
    }

    // Start progressive rendering
    requestAnimationFrame(addStoryBatch);
}

/**
 * Render tasks modal with progressive loading for large datasets
 */
function renderTasks(body, config) {
    const { tasks, totalHours, totalPoints } = config;

    if (!tasks || tasks.length === 0) {
        body.innerHTML = '<div class="modal-empty">Keine Tasks gefunden</div>';
        return;
    }

    // Group by task type
    const byType = {};
    tasks.forEach(t => {
        const type = t.task_type || 'other';
        if (!byType[type]) byType[type] = [];
        byType[type].push(t);
    });

    const typeLabels = {
        'design': '🎨 Design',
        'development': '💻 Development',
        'testing': '🧪 Testing',
        'documentation': '📝 Documentation',
        'devops': '⚙️ DevOps',
        'other': '📋 Other'
    };

    // PERFORMANCE: Render summary immediately, defer task cards
    body.innerHTML = `
        <div class="tasks-summary">
            <span class="tasks-summary-item">
                <strong>${tasks.length}</strong> Tasks
            </span>
            <span class="tasks-summary-item">
                <strong>${totalHours || 0}</strong> Stunden
            </span>
            <span class="tasks-summary-item">
                <strong>${totalPoints || 0}</strong> Story Points
            </span>
        </div>
        <div class="tasks-list" id="tasks-list-container">
            <div class="tasks-loading">Loading tasks...</div>
        </div>
    `;

    // PERFORMANCE: Progressive rendering for task cards
    const container = document.getElementById('tasks-list-container');
    const sortedTypes = Object.keys(byType);
    let typeIndex = 0;

    function renderNextGroup() {
        if (!activeModal || typeIndex >= sortedTypes.length) {
            // Remove loading indicator if done
            const loading = container?.querySelector('.tasks-loading');
            if (loading) loading.remove();
            return;
        }

        const type = sortedTypes[typeIndex];
        const typeTasks = byType[type];
        typeIndex++;

        // Create group element
        const groupEl = document.createElement('div');
        groupEl.className = 'tasks-group';
        groupEl.innerHTML = `
            <div class="tasks-group-header">${typeLabels[type] || type} (${typeTasks.length})</div>
        `;

        // Add task cards in batches
        const BATCH_SIZE = 5;
        let taskIndex = 0;

        function addTaskBatch() {
            if (!activeModal || taskIndex >= typeTasks.length) {
                // Move to next group
                requestAnimationFrame(renderNextGroup);
                return;
            }

            const batch = typeTasks.slice(taskIndex, taskIndex + BATCH_SIZE);
            taskIndex += BATCH_SIZE;

            batch.forEach(task => {
                const card = document.createElement('div');
                card.className = 'task-card';
                card.dataset.id = task.id;
                card.innerHTML = `
                    <div class="task-header">
                        <span class="task-id">${escapeHtml(task.id)}</span>
                        <span class="task-complexity complexity-${(task.complexity || 'medium').toLowerCase()}">
                            ${escapeHtml(task.complexity || 'medium')}
                        </span>
                    </div>
                    <div class="task-title">${escapeHtml(task.title || '')}</div>
                    ${task.description ? `
                        <div class="task-description">${escapeHtml(task.description.substring(0, 150))}${task.description.length > 150 ? '...' : ''}</div>
                    ` : ''}
                    <div class="task-meta">
                        ${task.estimated_hours ? `<span>⏱️ ${task.estimated_hours}h</span>` : ''}
                        ${task.story_points ? `<span>📊 ${task.story_points} SP</span>` : ''}
                        ${task.status ? `<span class="task-status status-${task.status}">${task.status}</span>` : ''}
                    </div>
                    ${task.required_skills && task.required_skills.length > 0 ? `
                        <div class="task-skills">
                            ${task.required_skills.slice(0, 3).map(s =>
                                `<span class="skill-tag">${escapeHtml(s)}</span>`
                            ).join('')}
                            ${task.required_skills.length > 3 ? `<span class="skill-more">+${task.required_skills.length - 3}</span>` : ''}
                        </div>
                    ` : ''}
                    <div class="task-footer">
                        <button class="btn-focus" onclick="window.modalFocusNode('${escapeHtml(task.id)}')">
                            → Im Canvas
                        </button>
                    </div>
                `;
                groupEl.appendChild(card);
            });

            // Schedule next batch
            requestAnimationFrame(addTaskBatch);
        }

        // Remove loading indicator before first group
        if (typeIndex === 1) {
            const loading = container?.querySelector('.tasks-loading');
            if (loading) loading.remove();
        }

        container?.appendChild(groupEl);
        requestAnimationFrame(addTaskBatch);
    }

    // Start progressive rendering
    requestAnimationFrame(renderNextGroup);
}

/**
 * Estimate diagram complexity to prevent browser crashes
 * Returns: { score: number, tooComplex: boolean, reason: string }
 */
function estimateDiagramComplexity(code) {
    if (!code) return { score: 0, tooComplex: false, reason: '' };

    const lines = code.split('\n').length;
    const chars = code.length;

    // Count entities/nodes (lines with { or class or state definitions)
    const entities = (code.match(/\{[^}]*\}/g) || []).length;

    // Count relationships (lines with arrows or connections)
    const relationships = (code.match(/(\|\||\|o|o\||\}\||\|\{|-->|--\>|--|\.\.)/g) || []).length;

    // Detect diagram type
    const firstLine = code.trim().split('\n')[0].toLowerCase();
    const isER = firstLine.includes('erdiagram');
    const isClass = firstLine.includes('classdiagram');
    const isSequence = firstLine.includes('sequencediagram');

    // ER and Class diagrams are particularly expensive with many entities
    let score = lines + (entities * 3) + (relationships * 2);
    if (isER || isClass) {
        score = score * 1.5; // These are more expensive
    }

    // Thresholds based on testing
    const MAX_SAFE_SCORE = 150; // Diagrams above this may crash
    const MAX_SAFE_ENTITIES = 30;
    const MAX_SAFE_RELATIONSHIPS = 40;

    let tooComplex = false;
    let reason = '';

    if (score > MAX_SAFE_SCORE) {
        tooComplex = true;
        reason = `Komplexitätsscore: ${Math.round(score)} (max: ${MAX_SAFE_SCORE})`;
    } else if (entities > MAX_SAFE_ENTITIES) {
        tooComplex = true;
        reason = `Zu viele Entitäten: ${entities} (max: ${MAX_SAFE_ENTITIES})`;
    } else if (relationships > MAX_SAFE_RELATIONSHIPS) {
        tooComplex = true;
        reason = `Zu viele Beziehungen: ${relationships} (max: ${MAX_SAFE_RELATIONSHIPS})`;
    }

    return {
        score: Math.round(score),
        entities,
        relationships,
        lines,
        tooComplex,
        reason,
        diagramType: isER ? 'ER' : isClass ? 'Class' : isSequence ? 'Sequence' : 'Other'
    };
}

/**
 * Render single diagram in full view with complexity check
 * PERFORMANCE: Prevents browser crashes by checking complexity first
 */
function renderSingleDiagram(body, config) {
    debugLog('=== renderSingleDiagram START ===');
    debugLog('Config keys:', Object.keys(config));
    debugLog('Config:', JSON.stringify(config, (key, value) => {
        if (key === 'mermaidCode' && value) return `[${value.length} chars]`;
        return value;
    }, 2));

    const { diagramId, mermaidCode, title } = config;

    debugLog('Extracted values:', {
        diagramId,
        mermaidCodeLength: mermaidCode?.length || 0,
        mermaidCodePreview: mermaidCode?.substring(0, 100) || 'NULL/UNDEFINED',
        title
    });

    if (!mermaidCode) {
        debugError('mermaidCode is NULL or UNDEFINED!');
        body.innerHTML = `<div class="diagram-error">
            <h3>❌ Kein Mermaid-Code</h3>
            <p>diagramId: ${escapeHtml(diagramId || 'undefined')}</p>
            <p>config keys: ${Object.keys(config).join(', ')}</p>
        </div>`;
        return;
    }

    // Store mermaid code and diagram ID globally for buttons
    window._currentDiagramCode = mermaidCode;
    window._currentDiagramId = diagramId;
    debugLog('Stored mermaidCode and diagramId in window globals');

    // Check complexity BEFORE rendering
    debugLog('Calling estimateDiagramComplexity...');
    const complexity = estimateDiagramComplexity(mermaidCode);
    debugLog('Complexity result:', complexity);

    // If too complex, show warning instead of crashing
    if (complexity.tooComplex) {
        body.innerHTML = `
            <div class="single-diagram-view">
                <div class="diagram-toolbar">
                    <span class="diagram-warning">⚠️ Komplexes Diagramm</span>
                    <button class="btn-kilo-diagram" id="btn-kilo-diagram">🤖 KiloAgent</button>
                    <span class="diagram-info">${complexity.lines} Zeilen, ${complexity.entities} Entitäten, ${complexity.relationships} Beziehungen</span>
                </div>
                <div class="diagram-container" id="single-diagram-container">
                    <div class="diagram-complexity-warning">
                        <h3>⚠️ Diagramm zu komplex für Live-Rendering</h3>
                        <p>${escapeHtml(complexity.reason)}</p>
                        <p>Typ: ${complexity.diagramType} | Score: ${complexity.score}</p>
                        <div class="complexity-actions">
                            <button class="btn-primary" id="btn-show-code-complex">
                                📝 Mermaid-Code anzeigen
                            </button>
                            <button class="btn-secondary btn-danger" id="btn-try-render">
                                ⚡ Trotzdem rendern (Risiko: Browser-Freeze)
                            </button>
                        </div>
                    </div>
                </div>
                <div id="kilo-diagram-panel" style="display: none;"></div>
            </div>
        `;

        // Setup buttons with tracked listeners
        const showCodeBtn = document.getElementById('btn-show-code-complex');
        const tryRenderBtn = document.getElementById('btn-try-render');

        if (showCodeBtn) {
            addModalEventListener(showCodeBtn, 'click', () => {
                const container = document.getElementById('single-diagram-container');
                if (container) {
                    container.innerHTML = `<pre class="diagram-code-view">${escapeHtml(mermaidCode)}</pre>`;
                }
            });
        }

        if (tryRenderBtn) {
            addModalEventListener(tryRenderBtn, 'click', () => {
                const container = document.getElementById('single-diagram-container');
                if (container) {
                    container.innerHTML = `
                        <div class="diagram-loading">
                            <div class="loading-spinner"></div>
                            <span>Rendering (kann mehrere Sekunden dauern)...</span>
                        </div>
                    `;
                    // Force render with delay to show loading state
                    setTimeout(() => forceRenderDiagram(container, mermaidCode), 100);
                }
            });
        }

        // KiloAgent button for complex diagrams
        const kiloBtnComplex = body.querySelector('#btn-kilo-diagram');
        if (kiloBtnComplex) {
            addModalEventListener(kiloBtnComplex, 'click', () => {
                openDiagramKiloPanel(diagramId, mermaidCode);
            });
        }

        return;
    }

    // Normal rendering for simple diagrams
    // Toolbar UNTER dem Diagramm für bessere UX (Inhalt zuerst)
    body.innerHTML = `
        <div class="single-diagram-view">
            <div class="diagram-container" id="single-diagram-container">
                <div class="diagram-loading">
                    <div class="loading-spinner"></div>
                    <span>Rendering...</span>
                </div>
            </div>
            <div class="diagram-toolbar">
                <button class="btn-secondary btn-show-code" id="btn-show-code">
                    📝 Code anzeigen
                </button>
                <button class="btn-kilo-diagram" id="btn-kilo-diagram">🤖 KiloAgent</button>
                <span class="diagram-info">${complexity.lines} Zeilen, Score: ${complexity.score}</span>
            </div>
            <div id="kilo-diagram-panel" style="display: none;"></div>
        </div>
    `;

    // Setup show code button with tracked listener
    const showCodeBtn = document.getElementById('btn-show-code');
    if (showCodeBtn) {
        addModalEventListener(showCodeBtn, 'click', () => {
            const container = document.getElementById('single-diagram-container');
            if (container && window._currentDiagramCode) {
                container.innerHTML = `<pre class="diagram-code-view">${escapeHtml(window._currentDiagramCode)}</pre>`;
            }
        });
    }

    // KiloAgent button for normal diagrams
    const kiloBtn = body.querySelector('#btn-kilo-diagram');
    if (kiloBtn) {
        addModalEventListener(kiloBtn, 'click', () => {
            openDiagramKiloPanel(diagramId, mermaidCode);
        });
    }

    // Start rendering - BUGFIX: Capture container BEFORE setTimeout to avoid race condition
    // When user clicks different diagrams quickly, there may be multiple elements with same ID
    // BUGFIX #2: Use body.querySelector instead of document.getElementById to scope to current modal
    // This prevents finding old modal's container when multiple modals exist during rapid switching
    const containerRef = body.querySelector('#single-diagram-container');
    debugLog('Container reference captured:', !!containerRef, 'in body:', body?.id);

    setTimeout(() => {
        // BUGFIX: Verify container is still in current modal (not the old one being removed)
        if (!containerRef) {
            debugWarn('Container reference is null - aborting render');
            return;
        }
        if (!document.body.contains(containerRef)) {
            debugWarn('Container was removed from DOM (old modal?) - aborting render');
            return;
        }
        if (!activeModal || !activeModal.contains(containerRef)) {
            debugWarn('Container is not in active modal - aborting render');
            return;
        }
        if (mermaidCode) {
            debugLog('Starting render with verified container');
            attemptDiagramRender(containerRef, mermaidCode);
        }
    }, 100);
}

/**
 * Attempt to render a mermaid diagram with error handling
 */
async function attemptDiagramRender(container, mermaidCode) {
    debugLog('=== attemptDiagramRender START ===');
    debugLog('container exists:', !!container);
    debugLog('mermaidCode length:', mermaidCode?.length || 0);
    debugLog('activeModal exists:', !!activeModal);
    debugLog('window.mermaid exists:', !!window.mermaid);
    debugLog('window.mermaid.render exists:', typeof window.mermaid?.render);

    if (!container) {
        debugError('Container is NULL - aborting render');
        return;
    }
    if (!mermaidCode) {
        debugError('mermaidCode is NULL - aborting render');
        return;
    }
    if (!activeModal) {
        debugWarn('activeModal is NULL - modal was closed, aborting render');
        return;
    }

    // CRASH FIX #1: Check code length BEFORE attempting render
    if (mermaidCode.length > MAX_MERMAID_CODE_LENGTH) {
        debugWarn(`Mermaid code too large: ${mermaidCode.length} chars (max: ${MAX_MERMAID_CODE_LENGTH})`);
        container.innerHTML = `
            <div class="diagram-fallback">
                <h3>📊 Diagramm zu groß für Live-Rendering</h3>
                <p>Code-Größe: ${Math.round(mermaidCode.length / 1000)}KB (max: ${MAX_MERMAID_CODE_LENGTH / 1000}KB)</p>
                <div class="fallback-actions">
                    <button class="btn-primary" id="btn-show-code-fallback">📝 Code anzeigen</button>
                    <button class="btn-secondary btn-danger" id="btn-force-render-fallback">⚡ Trotzdem rendern</button>
                </div>
            </div>
        `;
        // Setup buttons
        addModalEventListener(document.getElementById('btn-show-code-fallback'), 'click', () => {
            container.innerHTML = `<pre class="diagram-code-view">${escapeHtml(mermaidCode)}</pre>`;
        });
        addModalEventListener(document.getElementById('btn-force-render-fallback'), 'click', () => {
            container.innerHTML = `<div class="diagram-loading"><div class="loading-spinner"></div><span>Rendering...</span></div>`;
            setTimeout(() => forceRenderDiagram(container, mermaidCode), 100);
        });
        return;
    }

    if (!window.mermaid) {
        debugError('window.mermaid is not loaded!');
        container.innerHTML = `<div class="diagram-error">
            <p>❌ Mermaid library nicht geladen</p>
        </div>`;
        return;
    }

    // CRASH FIX: Validate mermaid code has valid syntax start
    const firstLine = mermaidCode.trim().split('\n')[0].toLowerCase();
    const validStarts = ['graph', 'flowchart', 'sequencediagram', 'classDiagram', 'statediagram', 'erdiagram', 'gantt', 'pie', 'journey', 'gitgraph', 'c4context', 'mindmap', 'timeline', 'sankey', 'xychart', 'block'];
    const hasValidStart = validStarts.some(s => firstLine.includes(s.toLowerCase()));

    if (!hasValidStart) {
        debugWarn('Mermaid code may have invalid syntax - first line:', firstLine);
        // Still try to render, but log warning
    }

    const RENDER_TIMEOUT_MS = 10000; // CRASH FIX: Reduced from 30s to 10s
    debugLog('RENDER_TIMEOUT_MS:', RENDER_TIMEOUT_MS);

    try {
        let timedOut = false;
        debugLog('Setting up timeout...');
        const timeoutId = setTimeout(() => {
            debugWarn('TIMEOUT REACHED - mermaid.render took too long');
            timedOut = true;
            container.innerHTML = `
                <div class="diagram-error">
                    <p>⏱️ Timeout beim Rendern</p>
                    <p>Das Diagramm ist zu komplex.</p>
                    <button class="btn-secondary" onclick="document.getElementById('single-diagram-container').innerHTML='<pre class=\\'diagram-code-view\\'>' + window._currentDiagramCode.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>'">
                        Code anzeigen
                    </button>
                </div>
            `;
        }, RENDER_TIMEOUT_MS);

        const svgId = `modal-full-${Date.now()}`;
        debugLog('Generated svgId:', svgId);
        debugLog('>>> CALLING mermaid.render() - this may block the browser <<<');
        debugLog('mermaidCode first 200 chars:', mermaidCode.substring(0, 200));

        const renderStartTime = performance.now();
        const result = await window.mermaid.render(svgId, mermaidCode);
        const renderEndTime = performance.now();

        debugLog('>>> mermaid.render() COMPLETED <<<');
        debugLog('Render time:', (renderEndTime - renderStartTime).toFixed(2), 'ms');
        debugLog('Result exists:', !!result);
        debugLog('Result.svg length:', result?.svg?.length || 0);

        clearTimeout(timeoutId);
        debugLog('Timeout cleared');

        if (timedOut) {
            debugWarn('Render completed but timeout already fired - ignoring result');
            return;
        }
        if (!activeModal) {
            debugWarn('Modal closed during render - ignoring result');
            return;
        }

        if (!result?.svg) {
            throw new Error('Kein SVG generiert');
        }

        // CRASH FIX #2: Check SVG size BEFORE innerHTML assignment
        if (result.svg.length > MAX_SVG_LENGTH) {
            debugWarn(`SVG too large: ${result.svg.length} chars (max: ${MAX_SVG_LENGTH})`);
            container.innerHTML = `
                <div class="diagram-warning">
                    <h3>⚠️ SVG sehr groß</h3>
                    <p>Größe: ${Math.round(result.svg.length / 1000)}KB (max: ${MAX_SVG_LENGTH / 1000}KB)</p>
                    <p>Das Anzeigen kann den Browser verlangsamen.</p>
                    <div class="fallback-actions">
                        <button class="btn-primary" id="btn-force-svg">Trotzdem anzeigen</button>
                        <button class="btn-secondary" id="btn-show-code-svg">Code anzeigen</button>
                    </div>
                </div>
            `;
            const forceSvgBtn = document.getElementById('btn-force-svg');
            const showCodeBtn = document.getElementById('btn-show-code-svg');
            if (forceSvgBtn) {
                addModalEventListener(forceSvgBtn, 'click', () => {
                    container.innerHTML = result.svg;
                    const svg = container.querySelector('svg');
                    if (svg) {
                        svg.style.maxWidth = '100%';
                        svg.style.height = 'auto';
                    }
                });
            }
            if (showCodeBtn) {
                addModalEventListener(showCodeBtn, 'click', () => {
                    container.innerHTML = `<pre class="diagram-code-view">${escapeHtml(window._currentDiagramCode || '')}</pre>`;
                });
            }
            return;
        }

        // BUGFIX: Final verification before DOM manipulation
        if (!document.body.contains(container)) {
            debugWarn('Container no longer in DOM before SVG insertion - aborting');
            return;
        }
        if (!activeModal || !activeModal.contains(container)) {
            debugWarn('Container not in active modal before SVG insertion - aborting');
            return;
        }

        debugLog('Inserting SVG into container...');
        debugLog('Container parent:', container.parentElement?.className);
        debugLog('Container in activeModal:', activeModal?.contains(container));
        container.innerHTML = result.svg;
        debugLog('SVG inserted successfully, checking result...');

        // Make SVG responsive
        const svg = container.querySelector('svg');
        if (svg) {
            debugLog('Making SVG responsive...');

            // CRASH FIX #10: Remove ALL script elements and style elements with animations
            svg.querySelectorAll('script').forEach(el => el.remove());
            svg.querySelectorAll('style').forEach(styleEl => {
                const styleText = styleEl.textContent || '';
                if (styleText.includes('animation') || styleText.includes('@keyframes')) {
                    debugWarn('Removing style element with animations');
                    styleEl.remove();
                }
            });

            // NOTE: foreignObject elements are REQUIRED for text labels in Mermaid diagrams
            // DO NOT remove them - they are safe since htmlLabels: false in app.js config
            // prevents executable content inside foreignObject elements

            // Set explicit dimensions to prevent layout thrashing
            svg.style.maxWidth = '100%';
            svg.style.height = 'auto';
            svg.style.display = 'block';
            svg.style.margin = '0 auto';

            // CRASH FIX #8: Stop event propagation to prevent canvas interactions
            svg.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true });
            svg.addEventListener('mousedown', (e) => e.stopPropagation());
            svg.addEventListener('mousemove', (e) => e.stopPropagation());

            // CRASH FIX #8: Remove any inline event handlers that mermaid might have added
            svg.querySelectorAll('[onclick], [onmouseover], [onmouseout], [onload]').forEach(el => {
                el.removeAttribute('onclick');
                el.removeAttribute('onmouseover');
                el.removeAttribute('onmouseout');
                el.removeAttribute('onload');
            });

            // CRASH FIX #8: Disable pointer events on ALL interactive elements
            svg.querySelectorAll('.clickable, .node, .edge, .label, .edgeLabel, .nodeLabel, .cluster').forEach(el => {
                el.style.pointerEvents = 'none';
            });

            debugLog('SVG sanitization complete');
        }

        debugLog('=== attemptDiagramRender SUCCESS ===');
        debugLog('Final container check:');
        debugLog('  - container still in DOM:', document.body.contains(container));
        debugLog('  - container has SVG child:', !!container.querySelector('svg'));
        debugLog('  - container innerHTML length:', container.innerHTML.length);
        debugLog('Waiting 100ms to check for post-render issues...');

        // CRASH FIX #10: Yield to browser to detect any post-render issues
        await new Promise(resolve => setTimeout(resolve, 100));
        debugLog('Post-render check passed - no immediate freeze detected');
    } catch (e) {
        debugError('=== attemptDiagramRender FAILED ===');
        debugError('Error:', e.message);
        debugError('Stack:', e.stack);
        container.innerHTML = `
            <div class="diagram-error">
                <p>❌ Fehler beim Rendern</p>
                <p class="error-message">${escapeHtml(e.message || 'Unbekannter Fehler')}</p>
                <pre style="font-size: 10px; max-height: 200px; overflow: auto;">${escapeHtml(e.stack || '')}</pre>
            </div>
        `;
    }
}

/**
 * Force render without size checks (user explicitly requested)
 * WARNING: May crash browser for very large diagrams
 */
async function forceRenderDiagram(container, mermaidCode) {
    debugLog('=== forceRenderDiagram (bypassing size checks) ===');

    if (!container || !mermaidCode || !window.mermaid) {
        debugError('Missing requirements for force render');
        return;
    }

    try {
        const svgId = `modal-force-${Date.now()}`;
        const result = await window.mermaid.render(svgId, mermaidCode);

        if (result?.svg) {
            container.innerHTML = result.svg;
            const svg = container.querySelector('svg');
            if (svg) {
                svg.style.maxWidth = '100%';
                svg.style.height = 'auto';

                // CRASH FIX #8: Apply same event isolation as attemptDiagramRender
                svg.addEventListener('wheel', (e) => e.stopPropagation(), { passive: true });
                svg.addEventListener('mousedown', (e) => e.stopPropagation());
                svg.querySelectorAll('[onclick], [onmouseover], [onmouseout]').forEach(el => {
                    el.removeAttribute('onclick');
                    el.removeAttribute('onmouseover');
                    el.removeAttribute('onmouseout');
                });
                svg.querySelectorAll('.clickable, .node, .edge').forEach(el => {
                    el.style.pointerEvents = 'none';
                });
            }
            debugLog('Force render completed successfully');
        }
    } catch (e) {
        debugError('Force render failed:', e);
        container.innerHTML = `<div class="diagram-error">
            <p>❌ Render fehlgeschlagen</p>
            <p>${escapeHtml(e.message)}</p>
        </div>`;
    }
}

// ============================================
// Diagram Render Queue
// ============================================

/**
 * Queue a diagram for rendering
 * CRASH FIX #5: Uses Set to prevent duplicate renders
 */
function queueDiagramRender(diagramId, code) {
    if (!code) return;

    // CRASH FIX: Prevent duplicate queue entries
    if (queuedIds.has(diagramId)) {
        debugLog('Skipping duplicate queue entry:', diagramId);
        return;
    }

    queuedIds.add(diagramId);
    mermaidRenderQueue.push({ id: diagramId, code });
}

/**
 * Process the diagram render queue with complexity check
 * CRITICAL: Check complexity BEFORE calling mermaid.render() to prevent browser freeze
 */
async function processDiagramRenderQueue() {
    const batchSize = 1;  // Process one at a time for safety
    const delay = 200;    // Longer delay between renders

    while (mermaidRenderQueue.length > 0 && activeModal) {
        const { id, code } = mermaidRenderQueue.shift();

        // CRASH FIX: Remove from dedup Set
        queuedIds.delete(id);

        if (!activeModal) break;

        const container = document.getElementById(`preview-${id}`);
        if (!container) continue;

        // CRASH FIX: Skip if code is null/undefined
        if (!code) {
            debugWarn(`Skipping render for ${id} - code is null/undefined`);
            container.innerHTML = `<div class="diagram-error-small">Kein Code verfügbar</div>`;
            continue;
        }

        // CRITICAL: Check complexity BEFORE rendering to prevent freeze
        const complexity = estimateDiagramComplexity(code);

        if (complexity.tooComplex) {
            console.log(`[Modal] Preview skipped - too complex: ${id}`, complexity);
            container.innerHTML = `<div class="diagram-error-small" title="${complexity.reason}">Zu komplex<br><small>${complexity.entities} Entitäten</small></div>`;
            continue;
        }

        // Also skip if code is too long (simpler check)
        if (code?.length > 5000) {
            container.innerHTML = `<div class="diagram-error-small">Zu groß für Vorschau<br><small>${Math.round(code.length/1000)}KB Code</small></div>`;
            continue;
        }

        try {
            const svgId = `modal-preview-${id}-${Date.now()}`;
            const result = await window.mermaid.render(svgId, code);

            if (!activeModal) break;

            // CRASH FIX: Null check on result before accessing svg
            if (!result || !result.svg) {
                console.warn(`[Modal] No SVG result for ${id}`);
                container.innerHTML = `<div class="diagram-error-small">Kein Ergebnis</div>`;
                continue;
            }

            // Scale SVG to fit preview - use innerHTML instead of DOMParser for performance
            container.innerHTML = result.svg;
            const svgEl = container.querySelector('svg');

            if (svgEl) {
                svgEl.style.maxWidth = '100%';
                svgEl.style.maxHeight = '100%';
                svgEl.style.width = 'auto';
                svgEl.style.height = 'auto';
            }
        } catch (e) {
            console.warn(`[Modal] Preview render error for ${id}:`, e.message);
            container.innerHTML = `<div class="diagram-error-small">Render-Fehler<br><small>${escapeHtml(e.message?.substring(0, 50) || '')}</small></div>`;
        }

        // Delay between renders to keep UI responsive
        await new Promise(r => setTimeout(r, delay));
    }
}

// ============================================
// Tab Switching
// ============================================

/**
 * Switch diagram gallery tab
 * BUGFIX: Queue diagrams for rendering when switching to a new tab
 */
export function switchDiagramTab(type) {
    // Update tab buttons
    document.querySelectorAll('.modal-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.type === type)
    );

    // Update sections
    document.querySelectorAll('.diagram-gallery-section').forEach(s =>
        s.classList.toggle('active', s.dataset.type === type)
    );

    // BUGFIX: Queue diagrams in newly active section that haven't been rendered yet
    const activeSection = document.querySelector(`.diagram-gallery-section[data-type="${type}"]`);
    if (activeSection) {
        const cards = activeSection.querySelectorAll('.diagram-card');
        let queuedCount = 0;

        cards.forEach(card => {
            const preview = card.querySelector('.diagram-card-preview');
            // Check if still has loading spinner (not yet rendered)
            if (preview && preview.querySelector('.diagram-loading')) {
                const diagramId = card.dataset.id;
                const code = card.dataset.mermaidCode;
                if (diagramId && code) {
                    queueDiagramRender(diagramId, code);
                    queuedCount++;
                }
            }
        });

        // Start processing the queue if we added anything
        if (queuedCount > 0) {
            debugLog(`Tab switch: queued ${queuedCount} diagrams for rendering`);
            processDiagramRenderQueue();
        }
    }
}

/**
 * Toggle test item expansion
 */
export function toggleTestItem(index) {
    const item = document.querySelector(`.test-item[data-index="${index}"]`);
    if (item) {
        item.classList.toggle('expanded');
    }
}

// ============================================
// Helper Functions for Opening Specific Modals
// ============================================

/**
 * Open diagram gallery for a parent node
 * Finds ALL diagrams connected to the parent via:
 * 1. Direct connections (in both directions)
 * 2. ID pattern (parentId_type or parentId-type)
 * 3. Partial ID match
 * @param {string} parentId - Parent node ID (e.g., requirement ID)
 */
export function openDiagramGallery(parentId) {
    // Use Set to avoid duplicates
    const diagramIds = new Set();
    const diagrams = [];
    const diagramTypes = ['flowchart', 'sequence', 'class', 'er', 'state', 'c4'];

    // 1. Find by ID pattern (supports both underscore and hyphen separators)
    // e.g., REQ-001_flowchart or REQ-001-flowchart
    Object.entries(state.nodes).forEach(([nodeId, node]) => {
        if (node.type !== 'diagram') return;

        // Check if diagram ID starts with parent ID + underscore or hyphen
        if (nodeId.startsWith(parentId + '_') || nodeId.startsWith(parentId + '-')) {
            // Verify it's a diagram type suffix
            const suffix = nodeId.slice(parentId.length + 1).toLowerCase();
            if (diagramTypes.includes(suffix)) {
                diagramIds.add(nodeId);
            }
        }
    });

    // 2. Find by direct connections (both directions)
    state.connections.forEach(conn => {
        // Check from → to direction
        if (conn.from === parentId) {
            const targetNode = state.nodes[conn.to];
            if (targetNode?.type === 'diagram') {
                diagramIds.add(conn.to);
            }
        }
        // Check to → from direction
        if (conn.to === parentId) {
            const sourceNode = state.nodes[conn.from];
            if (sourceNode?.type === 'diagram') {
                diagramIds.add(conn.from);
            }
        }
    });

    // 3. Find diagrams whose ID contains the parent ID (for complex naming patterns)
    Object.entries(state.nodes).forEach(([nodeId, node]) => {
        if (node.type !== 'diagram') return;
        if (diagramIds.has(nodeId)) return; // Already found

        // Check if nodeId contains parentId followed by underscore/hyphen or at end
        if (nodeId.includes(parentId + '_') || nodeId.includes('_' + parentId + '_') ||
            nodeId.includes(parentId + '-') || nodeId.includes('-' + parentId + '-')) {
            diagramIds.add(nodeId);
        }
    });

    // 4. Check group state for pre-detected diagrams
    const groupKey = `${parentId}-diagram`;
    const groupData = state.groupState?.groups?.[groupKey];
    if (groupData?.children) {
        groupData.children.forEach(id => diagramIds.add(id));
    }

    // Build diagram objects
    diagramIds.forEach(nodeId => {
        const node = state.nodes[nodeId];
        if (node) {
            diagrams.push({
                id: nodeId,
                mermaid_code: node.data?.mermaid_code || node.data?.content,
                title: node.data?.title || nodeId
            });
        }
    });

    // Sort diagrams by type order
    diagrams.sort((a, b) => {
        const typeA = getDiagramTypeFromId(a.id);
        const typeB = getDiagramTypeFromId(b.id);
        return (DIAGRAM_TYPES[typeA]?.order || 99) - (DIAGRAM_TYPES[typeB]?.order || 99);
    });

    console.log(`[Modal] Found ${diagrams.length} diagrams for ${parentId}:`, diagrams.map(d => d.id));

    openModal({
        type: 'diagram-gallery',
        title: `Diagrams: ${parentId} (${diagrams.length})`,
        size: 'xl',
        diagrams,
        parentId
    });
}

/**
 * Open test cases modal for a parent node (User Story or Requirement)
 * Finds tests via:
 * 1. Direct connections
 * 2. linked_user_story field in test data
 * 3. ID pattern matching
 * @param {string} parentId - Parent node ID (User Story or Requirement)
 */
export function openTestCasesModal(parentId) {
    const tests = [];
    const addedIds = new Set();

    // Helper to add test if not already added
    const addTest = (testId, testNode) => {
        if (addedIds.has(testId)) return;
        addedIds.add(testId);
        tests.push({
            id: testId,
            title: testNode.data?.title || testId,
            content: testNode.data?.content || testNode.data?.gherkin_content,
            tags: testNode.data?.tags || [],
            scenario_count: testNode.data?.scenario_count || 0
        });
    };

    // 1. Find all test nodes connected to parent via connections
    state.connections.forEach(conn => {
        const testNode = state.nodes[conn.to]?.type === 'test' ? state.nodes[conn.to] :
                         state.nodes[conn.from]?.type === 'test' ? state.nodes[conn.from] : null;
        const testId = state.nodes[conn.to]?.type === 'test' ? conn.to :
                       state.nodes[conn.from]?.type === 'test' ? conn.from : null;

        if (!testNode || !testId) return;

        const isConnectedToParent = conn.from === parentId || conn.to === parentId;
        if (isConnectedToParent) {
            addTest(testId, testNode);
        }
    });

    // 2. Find tests by linked_user_story field in test data
    Object.entries(state.nodes).forEach(([testId, testNode]) => {
        if (testNode.type !== 'test') return;

        // Check if test has linked_user_story matching parentId
        const linkedStory = testNode.data?.linked_user_story;
        if (linkedStory === parentId) {
            addTest(testId, testNode);
        }

        // Also check for partial match (e.g., US-001 in "US-001-TC1")
        if (testId.startsWith(parentId + '-') || testId.startsWith(parentId + '_')) {
            addTest(testId, testNode);
        }
    });

    // 3. Find tests whose ID pattern matches parent (for patterns like US-001-TC-001)
    Object.entries(state.nodes).forEach(([testId, testNode]) => {
        if (testNode.type !== 'test') return;
        if (addedIds.has(testId)) return;

        // Check if test ID contains parent ID
        if (testId.includes(parentId)) {
            addTest(testId, testNode);
        }
    });

    // Sort tests by ID
    tests.sort((a, b) => (a.id || '').localeCompare(b.id || ''));

    console.log(`[Modal] Found ${tests.length} tests for ${parentId}:`, tests.map(t => t.id));

    openModal({
        type: 'test-cases',
        title: `Test Cases: ${parentId} (${tests.length})`,
        size: 'large',
        tests,
        parentId
    });
}

/**
 * Open user stories modal for an epic
 * @param {string} epicId - Epic node ID
 */
export function openUserStoriesModal(epicId) {
    const stories = [];
    const epicNode = state.nodes[epicId];

    // Find all user stories connected to epic
    state.connections.forEach(conn => {
        const storyNode = state.nodes[conn.to]?.type === 'user-story' ? state.nodes[conn.to] :
                          state.nodes[conn.from]?.type === 'user-story' ? state.nodes[conn.from] : null;
        const storyId = state.nodes[conn.to]?.type === 'user-story' ? conn.to :
                        state.nodes[conn.from]?.type === 'user-story' ? conn.from : null;

        if (!storyNode || !storyId) return;

        const isConnectedToEpic = conn.from === epicId || conn.to === epicId;
        if (isConnectedToEpic && !stories.find(s => s.id === storyId)) {
            stories.push({
                id: storyId,
                title: storyNode.data?.title || storyId,
                persona: storyNode.data?.persona,
                action: storyNode.data?.action,
                benefit: storyNode.data?.benefit,
                priority: storyNode.data?.priority,
                acceptance_criteria: storyNode.data?.acceptance_criteria || []
            });
        }
    });

    // Sort by priority (MUST first)
    const priorityOrder = { 'MUST': 0, 'SHOULD': 1, 'COULD': 2 };
    stories.sort((a, b) =>
        (priorityOrder[a.priority?.toUpperCase()] || 99) -
        (priorityOrder[b.priority?.toUpperCase()] || 99)
    );

    openModal({
        type: 'user-stories',
        title: `User Stories: ${epicNode?.data?.title || epicId}`,
        size: 'large',
        stories,
        parentId: epicId,
        epicTitle: epicNode?.data?.title
    });
}

/**
 * Open tasks modal for an epic
 * @param {string} epicId - Epic node ID
 */
export function openTasksModal(epicId) {
    const tasks = [];
    const epicNode = state.nodes[epicId];

    // Find all tasks connected to epic (direct or through features/requirements)
    state.connections.forEach(conn => {
        const taskNode = state.nodes[conn.to]?.type === 'task' ? state.nodes[conn.to] :
                         state.nodes[conn.from]?.type === 'task' ? state.nodes[conn.from] : null;
        const taskId = state.nodes[conn.to]?.type === 'task' ? conn.to :
                       state.nodes[conn.from]?.type === 'task' ? conn.from : null;

        if (!taskNode || !taskId) return;

        const isConnectedToEpic = conn.from === epicId || conn.to === epicId;
        if (isConnectedToEpic && !tasks.find(t => t.id === taskId)) {
            tasks.push({
                id: taskId,
                title: taskNode.data?.title || taskId,
                task_type: taskNode.data?.task_type,
                estimated_hours: taskNode.data?.estimated_hours,
                complexity: taskNode.data?.complexity,
                story_points: taskNode.data?.story_points,
                status: taskNode.data?.status || 'todo',
                required_skills: taskNode.data?.required_skills || [],
                description: taskNode.data?.description
            });
        }
    });

    // Also search by ID pattern (TASK-001 might be connected to EPIC-001)
    Object.entries(state.nodes).forEach(([nodeId, node]) => {
        if (node.type !== 'task') return;
        if (tasks.find(t => t.id === nodeId)) return;

        // Check if task data references the epic
        const parentEpic = node.data?.parent_epic_id || node.data?.epic_id;
        if (parentEpic === epicId) {
            tasks.push({
                id: nodeId,
                title: node.data?.title || nodeId,
                task_type: node.data?.task_type,
                estimated_hours: node.data?.estimated_hours,
                complexity: node.data?.complexity,
                story_points: node.data?.story_points,
                status: node.data?.status || 'todo',
                required_skills: node.data?.required_skills || [],
                description: node.data?.description
            });
        }
    });

    // Sort by task type then by ID
    const typeOrder = { 'design': 0, 'development': 1, 'testing': 2, 'documentation': 3, 'devops': 4 };
    tasks.sort((a, b) => {
        const orderA = typeOrder[a.task_type] ?? 99;
        const orderB = typeOrder[b.task_type] ?? 99;
        if (orderA !== orderB) return orderA - orderB;
        return (a.id || '').localeCompare(b.id || '');
    });

    // Calculate totals
    const totalHours = tasks.reduce((sum, t) => sum + (t.estimated_hours || 0), 0);
    const totalPoints = tasks.reduce((sum, t) => sum + (t.story_points || 0), 0);

    openModal({
        type: 'tasks',
        title: `Tasks: ${epicNode?.data?.title || epicId} (${tasks.length})`,
        size: 'large',
        tasks,
        parentId: epicId,
        epicTitle: epicNode?.data?.title,
        totalHours,
        totalPoints
    });
}

/**
 * Open single diagram in full view
 * @param {string} diagramId - Diagram node ID
 */
export function openFullDiagram(diagramId) {
    debugLog('=== openFullDiagram called ===');
    debugLog('diagramId:', diagramId);
    debugLog('state.nodes count:', Object.keys(state.nodes).length);

    const node = state.nodes[diagramId];

    debugLog('node found:', !!node);

    if (!node) {
        debugError('Node not found in state.nodes!');
        debugLog('Available node IDs:', Object.keys(state.nodes).slice(0, 20));
        return;
    }

    debugLog('node.type:', node.type);
    debugLog('node.data exists:', !!node.data);
    debugLog('node.data keys:', node.data ? Object.keys(node.data) : 'N/A');
    debugLog('node.data.mermaid_code exists:', !!node.data?.mermaid_code);
    debugLog('node.data.mermaid_code length:', node.data?.mermaid_code?.length || 0);
    debugLog('node.data.content exists:', !!node.data?.content);
    debugLog('node.data.content length:', node.data?.content?.length || 0);

    const mermaidCode = node.data?.mermaid_code || node.data?.content;

    debugLog('Final mermaidCode length:', mermaidCode?.length || 0);

    // CRASH FIX: Don't call openModal with undefined mermaidCode
    if (!mermaidCode) {
        debugError('NO MERMAID CODE FOUND in node!');
        debugLog('Full node.data:', JSON.stringify(node.data, null, 2).substring(0, 500));

        // Show error modal instead of crashing
        openModal({
            type: 'single-diagram',
            title: `Error: ${diagramId}`,
            size: 'medium',
            diagramId,
            mermaidCode: null  // Will be handled by renderSingleDiagram
        });
        return;
    }

    debugLog('Calling openModal with single-diagram...');

    openModal({
        type: 'single-diagram',
        title: diagramId,
        size: 'xl',
        diagramId,
        mermaidCode
    });

    debugLog('openModal called, returning from openFullDiagram');
}

// ============================================
// Screen Wireframe Modal
// ============================================

/**
 * Open screen wireframe in full view with ASCII art and component layout
 * @param {string} screenId - Screen node ID
 */
export function openScreenWireframeModal(screenId) {
    const node = state.nodes[screenId];
    if (!node || !node.data) return;

    const data = node.data;
    const wireframe = data.wireframe_ascii || '';
    const components = data.components || [];
    const componentLayout = data.component_layout || [];

    // Build component layout table
    let layoutTable = '';
    if (componentLayout.length > 0) {
        layoutTable = `
            <div class="wireframe-layout-table">
                <h3>Component Layout</h3>
                <table>
                    <thead>
                        <tr><th>ID</th><th>Name</th><th>X</th><th>Y</th><th>W</th><th>H</th></tr>
                    </thead>
                    <tbody>
                        ${componentLayout.map(c => `
                            <tr>
                                <td>${escapeHtml(c.id || '')}</td>
                                <td>${escapeHtml(c.name || '')}</td>
                                <td>${c.x ?? ''}</td>
                                <td>${c.y ?? ''}</td>
                                <td>${c.w ?? ''}</td>
                                <td>${c.h ?? ''}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // Build component list
    let componentList = '';
    if (components.length > 0) {
        componentList = `
            <div class="wireframe-components">
                <h3>Components (${components.length})</h3>
                <div class="wireframe-comp-list">
                    ${components.map(c => `<span class="wireframe-comp-badge">${escapeHtml(c)}</span>`).join('')}
                </div>
            </div>
        `;
    }

    openModal({
        type: 'custom',
        title: `${data.name || screenId} - Wireframe`,
        size: 'xl',
    });

    // Render content after modal opens
    setTimeout(() => {
        const body = activeModal?.querySelector('#modal-body');
        if (!body) return;

        body.innerHTML = `
            <div class="screen-wireframe-modal">
                <div class="wireframe-meta">
                    <span class="wireframe-route">${escapeHtml(data.route || '')}</span>
                    <span class="wireframe-layout-badge">${escapeHtml(data.layout || 'default')}</span>
                    ${data.parent_user_story ? `<span class="wireframe-story-link">${escapeHtml(data.parent_user_story)}</span>` : ''}
                </div>
                ${data.description ? `<p class="wireframe-description">${escapeHtml(data.description)}</p>` : ''}
                ${wireframe ? `
                    <div class="wireframe-ascii-container">
                        <h3>ASCII Wireframe</h3>
                        <pre class="wireframe-ascii-full">${escapeHtml(wireframe)}</pre>
                    </div>
                ` : '<div class="wireframe-empty">Kein Wireframe verfuegbar. Bitte Pipeline erneut ausfuehren.</div>'}
                ${layoutTable}
                ${componentList}
                ${data.data_requirements?.length ? `
                    <div class="wireframe-data-reqs">
                        <h3>Data Requirements</h3>
                        <ul>${data.data_requirements.map(d => `<li><code>${escapeHtml(d)}</code></li>`).join('')}</ul>
                    </div>
                ` : ''}
            </div>
        `;
    }, 50);
}

// ============================================
// Window Exports for onclick handlers
// ============================================

if (typeof window !== 'undefined') {
    window.closeModal = closeModal;
    window.modalSwitchTab = switchDiagramTab;
    window.modalToggleTest = toggleTestItem;
    window.modalOpenFullDiagram = openFullDiagram;
    window.openScreenWireframeModal = openScreenWireframeModal;

    // Focus node in canvas and close modal
    window.modalFocusNode = (nodeId) => {
        closeModal();
        // Dispatch event for canvas to handle
        window.dispatchEvent(new CustomEvent('focusNode', {
            detail: { nodeId }
        }));
    };

    // Global modal openers
    window.openDiagramGallery = openDiagramGallery;
    window.openTestCasesModal = openTestCasesModal;
    window.openUserStoriesModal = openUserStoriesModal;
    window.openTasksModal = openTasksModal;
    window.openScreenWireframeModal = openScreenWireframeModal;
    window.openApiPackageModal = openApiPackageModal;
    window.openTaskGroupModal = openTaskGroupModal;
    window.openStateMachineModal = openStateMachineModal;
}

// ============================================
// API Package Modal
// ============================================

export function openApiPackageModal(nodeId) {
    const node = state.nodes[nodeId];
    if (!node || !node.data) return;
    const d = node.data;
    openModal({
        type: 'api-package',
        title: `API: ${d.tag} (${d.endpoint_count} endpoints)`,
        size: 'xl',
        data: d
    });
}

function renderApiPackage(body, tabs, config) {
    const d = config.data || {};
    const endpoints = d.endpoints || [];
    const mc = d.method_counts || {};

    // Method filter tabs
    const methods = Object.keys(mc);
    if (tabs && methods.length > 1) {
        let tabHtml = `<button class="modal-tab active" data-filter="all">All (${endpoints.length})</button>`;
        methods.forEach(m => {
            tabHtml += `<button class="modal-tab" data-filter="${m}">${m} (${mc[m]})</button>`;
        });
        tabs.innerHTML = tabHtml;
    }

    // Summary bar
    const summaryHtml = `<div class="api-pkg-summary">
        ${methods.map(m => `<span class="method-chip method-${m.toLowerCase()}">${m}: ${mc[m]}</span>`).join(' ')}
    </div>`;

    // Search
    const searchHtml = `<div class="api-pkg-search">
        <input type="text" id="api-pkg-filter" placeholder="Filter by path or description..." class="modal-search-input" />
    </div>`;

    // Table
    let tableHtml = `<div class="api-pkg-table-wrap"><table class="api-pkg-table" id="api-pkg-table">
        <thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>
        <tbody>`;
    endpoints.forEach(ep => {
        const m = (ep.method || 'GET').toUpperCase();
        tableHtml += `<tr data-method="${m}">
            <td><span class="method-chip method-${m.toLowerCase()}">${escapeHtml(m)}</span></td>
            <td class="api-path"><code>${escapeHtml(ep.path || '')}</code></td>
            <td>${escapeHtml(ep.description || ep.summary || '')}</td>
        </tr>`;
    });
    tableHtml += `</tbody></table></div>`;

    body.innerHTML = summaryHtml + searchHtml + tableHtml;

    // Filter functionality
    const filterInput = body.querySelector('#api-pkg-filter');
    const table = body.querySelector('#api-pkg-table');
    if (filterInput && table) {
        addModalEventListener(filterInput, 'input', () => {
            const q = filterInput.value.toLowerCase();
            table.querySelectorAll('tbody tr').forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(q) ? '' : 'none';
            });
        });
    }

    // Tab filtering
    if (tabs) {
        tabs.querySelectorAll('.modal-tab').forEach(tab => {
            addModalEventListener(tab, 'click', () => {
                tabs.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const filter = tab.dataset.filter;
                if (table) {
                    table.querySelectorAll('tbody tr').forEach(row => {
                        if (filter === 'all') {
                            row.style.display = '';
                        } else {
                            row.style.display = row.dataset.method === filter ? '' : 'none';
                        }
                    });
                }
            });
        });
    }
}

// ============================================
// Task Group Modal
// ============================================

export function openTaskGroupModal(nodeId) {
    const node = state.nodes[nodeId];
    if (!node || !node.data) return;
    const d = node.data;
    openModal({
        type: 'task-group',
        title: `Tasks: ${d.title} (${d.task_count} tasks, ${d.total_hours}h)`,
        size: 'large',
        data: d
    });
}

function renderTaskGroup(body, config) {
    const d = config.data || {};
    const tasks = d.tasks || [];

    let tableHtml = `<table class="api-pkg-table">
        <thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Hours</th><th>Complexity</th></tr></thead>
        <tbody>`;
    tasks.forEach(t => {
        const typeClass = (t.task_type || '').toLowerCase();
        tableHtml += `<tr>
            <td><code>${escapeHtml(t.id || '')}</code></td>
            <td>${escapeHtml(t.title || '')}</td>
            <td><span class="task-type-chip task-${typeClass}">${escapeHtml(t.task_type || 'N/A')}</span></td>
            <td>${t.estimated_hours || '-'}</td>
            <td>${escapeHtml(t.complexity || '-')}</td>
        </tr>`;
    });
    tableHtml += `</tbody></table>`;

    body.innerHTML = tableHtml;
}

// ============================================
// State Machine Modal
// ============================================

export function openStateMachineModal(nodeId) {
    const node = state.nodes[nodeId];
    if (!node || !node.data) return;
    const d = node.data;
    openModal({
        type: 'state-machine',
        title: `State Machine: ${d.name || d.entity}`,
        size: 'xl',
        data: d
    });
}

function renderStateMachine(body, config) {
    const d = config.data || {};
    const transitions = d.transitions || [];

    // Mermaid diagram
    let mermaidHtml = '';
    if (d.mermaid_code) {
        mermaidHtml = `<div class="sm-diagram" id="sm-mermaid-container">
            <pre class="mermaid">${escapeHtml(d.mermaid_code)}</pre>
        </div>`;
    }

    // Transition table
    let tableHtml = `<div class="sm-transitions"><h3>Transitions (${transitions.length})</h3>
        <table class="api-pkg-table">
        <thead><tr><th>From</th><th>To</th><th>Trigger</th><th>Guard</th><th>Action</th></tr></thead>
        <tbody>`;
    transitions.forEach(tr => {
        tableHtml += `<tr>
            <td><code>${escapeHtml(tr.from_state || tr.from || '')}</code></td>
            <td><code>${escapeHtml(tr.to_state || tr.to || '')}</code></td>
            <td>${escapeHtml(tr.trigger || tr.event || '')}</td>
            <td>${escapeHtml(tr.guard || '')}</td>
            <td>${escapeHtml(tr.action || '')}</td>
        </tr>`;
    });
    tableHtml += `</tbody></table></div>`;

    body.innerHTML = mermaidHtml + tableHtml;

    // Render mermaid if present
    if (d.mermaid_code && typeof mermaid !== 'undefined') {
        try {
            const container = body.querySelector('#sm-mermaid-container');
            if (container) {
                mermaid.run({ nodes: container.querySelectorAll('.mermaid') });
            }
        } catch (e) {
            debugWarn('Mermaid render failed for state machine:', e);
        }
    }
}
