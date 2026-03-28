/**
 * RE System Dashboard (Canvas-Free)
 *
 * Main application entry point.
 * Views: Wizard | Pipeline | Trace Explorer
 * Each view fetches its own data via dedicated APIs.
 */

// ============================================
// Module Imports
// ============================================

import { state, elements, initElements, log, escapeHtml } from './modules/state.js';
import {
    queueMermaidRender,
    startMermaidRendering,
    reRenderAllDiagrams,
    renderMermaid,
    sanitizeMermaidCode,
    sanitizeIdForHtml,
    clearMermaidQueue
} from './modules/mermaidRenderer.js';
import { showNotification } from './modules/ui/notifications.js';
import { openEditModal, handleKiloResponse } from './modules/ui/editModal.js';
import { handleCascadeProgress, handleCascadeNodeResult, handleCascadeComplete } from './modules/ui/diagramKiloPanel.js';
import { showChangeRequestNotification, handleChangeRequestEvent } from './modules/ui/changeRequestNotification.js';
import {
    showWizardSuggestion,
    handleAutoApplied,
    handleEnrichmentStarted,
    handleEnrichmentComplete,
} from './modules/ui/wizardNotifications.js';
import {
    openModal,
    closeModal,
    openDiagramGallery,
    openTestCasesModal,
    openUserStoriesModal,
    openTasksModal,
    openFullDiagram
} from './modules/ui/modal.js';
import {
    addChatButton,
    addEditButton,
    openChatPanel,
    closeChatPanel,
    sendKiloTask,
    initializeChatButtons,
    setChatCallbacks,
    handleKiloTaskProcessing,
    handleKiloTaskComplete,
    handleKiloTaskError,
    handleDiagramUpdate,
    handleContentUpdate
} from './modules/chat.js';

// Change tracking and Kilo Agent integration
import { initChangeTracker, trackChange, CHANGE_TYPES } from './modules/core/change_tracker.js';

// Wizard module
import { initWizard, setOnAnalysisComplete } from './modules/ui/wizard.js';
import { initKiloBridge } from './modules/agents/kilo_bridge.js';

// Pipeline View module
import { initPipelineView, onStageEvent, onPipelineComplete, refreshPipelineView } from './modules/ui/pipeline_view.js';
import { initTraceExplorer, onTraceEvent, refreshTraceView } from './modules/ui/traceExplorer.js';

// ============================================
// Project Loading
// ============================================

async function loadProjectList() {
    if (!elements.projectList) return;

    try {
        elements.projectList.innerHTML = '<div class="loading">Loading projects...</div>';
        const response = await fetch('/api/projects');
        const data = await response.json();

        if (data.projects && data.projects.length > 0) {
            renderProjectList(data.projects);
            log('info', `Found ${data.projects.length} saved project(s)`);
        } else {
            elements.projectList.innerHTML = '<div class="no-projects">No projects found</div>';
        }
    } catch (error) {
        console.error('Failed to load projects:', error);
        elements.projectList.innerHTML = '<div class="error">Failed to load projects</div>';
    }
}

function renderProjectList(projects) {
    // NOTE: escapeHtml is used for project names to prevent XSS
    elements.projectList.innerHTML = projects.map(p => {
        const counts = [];
        if (p.node_count > 0) counts.push(`${p.node_count} reqs`);
        if (p.epic_count > 0) counts.push(`${p.epic_count} epics`);
        if (p.us_count > 0) counts.push(`${p.us_count} stories`);
        if (p.diagram_count > 0) counts.push(`${p.diagram_count} diagrams`);
        if (p.test_count > 0) counts.push(`${p.test_count} tests`);

        const countStr = counts.length > 0 ? counts.join(' | ') : 'Empty';
        const formatBadge = p.format === 'journal' ? '\u{1F4CB}' : '\u{1F4C1}';

        return `
            <div class="project-item" data-project-id="${escapeHtml(p.id)}">
                <div class="project-name">${formatBadge} ${escapeHtml(p.name)}</div>
                <div class="project-meta">
                    <span class="item-counts">${escapeHtml(countStr)}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function loadProject(projectId) {
    try {
        log('info', `Loading project: ${projectId}...`);
        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        // Update project name in header
        const projectName = data.project_name || projectId;
        if (elements.projectInfo) {
            const nameEl = elements.projectInfo.querySelector('.project-name');
            if (nameEl) nameEl.textContent = projectName;
        }

        // Project stats bar (LLM usage + pipeline info)
        if (data.project_stats) {
            const statsEl = document.getElementById('project-info');
            if (statsEl) {
                const s = data.project_stats;
                const badges = [];
                if (s.llm_total_calls) badges.push(`${s.llm_total_calls} LLM calls`);
                if (s.llm_total_cost) badges.push(`$${s.llm_total_cost.toFixed(2)}`);
                if (s.pipeline_duration_ms) {
                    const secs = Math.round(s.pipeline_duration_ms / 1000);
                    const mins = Math.floor(secs / 60);
                    const remSecs = secs % 60;
                    badges.push(`${mins}m ${remSecs}s`);
                }

                // Build stats display using DOM methods
                statsEl.textContent = '';
                const nameSpan = document.createElement('span');
                nameSpan.className = 'project-name';
                nameSpan.textContent = projectName;
                statsEl.appendChild(nameSpan);

                if (badges.length) {
                    const badgesSpan = document.createElement('span');
                    badgesSpan.className = 'project-stats-badges';
                    badges.forEach(b => {
                        const badge = document.createElement('span');
                        badge.className = 'stats-badge';
                        badge.textContent = b;
                        badgesSpan.appendChild(badge);
                    });
                    statsEl.appendChild(badgesSpan);
                }
            }
        }

        // Mark project as selected in sidebar
        document.querySelectorAll('.project-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.projectId === projectId);
        });

        log('success', `Loaded "${projectName}"`);

        // Refresh active views so they pick up the new project
        refreshTraceView();
        refreshPipelineView();

    } catch (error) {
        console.error('Failed to load project:', error);
        log('error', `Failed to load project: ${error.message}`);
    }
}

// ============================================
// WebSocket
// ============================================

function initWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        state.connected = true;
        elements.connectionStatus.textContent = 'Connected';
        elements.connectionStatus.classList.add('connected');
        log('info', 'WebSocket connected');
    };

    state.ws.onclose = () => {
        state.connected = false;
        elements.connectionStatus.textContent = 'Disconnected';
        elements.connectionStatus.classList.remove('connected');
        log('warn', 'WebSocket disconnected');
        setTimeout(initWebSocket, 3000);
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        log('error', 'WebSocket error');
    };

    state.ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleMessage(message);
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };
}

function sendMessage(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    } else {
        console.warn('[WS] Cannot send message - not connected');
    }
}

function handleMessage(message) {
    const { type, data } = message;
    console.log(`[WS] Received: ${type}`);

    switch (type) {
        case 'progress':
            if (data.step && data.total) {
                const percent = Math.round((data.step / data.total) * 100);
                elements.progressFill.style.width = `${percent}%`;
                elements.progressText.textContent = data.message || `Step ${data.step}/${data.total}`;
            }
            break;

        case 'error':
            log('error', data.message || 'Unknown error');
            break;

        // Kilo Agent Events
        case 'kilo_task_processing':
            handleKiloTaskProcessing(data);
            break;

        case 'kilo_task_complete':
            handleKiloTaskComplete(data);
            break;

        case 'kilo_task_error':
            handleKiloTaskError(data);
            break;

        case 'diagram_update':
        case 'diagram_updated':
            handleDiagramUpdate(data);
            break;

        case 'content_update':
        case 'content_updated':
            handleContentUpdate(data);
            break;

        // Edit Modal + Kilo Agent Events
        case 'kilo_edit_response':
            handleKiloResponse(data);
            break;

        case 'edit_saved':
            console.log('[WS] Edit saved:', data.node_id);
            showNotification(`${data.node_id} gespeichert`, 'success');
            break;

        // Change Request Notification Events
        case 'change_request_created':
            handleChangeRequestEvent(data);
            break;

        case 'change_request_approved':
            console.log('[WS] Change request approved:', data.suggestion_id);
            showNotification('\u00c4nderung angewendet', 'success');
            break;

        case 'change_request_rejected':
            console.log('[WS] Change request rejected:', data.suggestion_id);
            break;

        // KiloAgent Diagram Cascade Events
        case 'kilo_diagram_cascade_progress':
            handleCascadeProgress(data);
            break;

        case 'kilo_diagram_cascade_node_result':
            handleCascadeNodeResult(data);
            break;

        case 'kilo_diagram_cascade_complete':
            handleCascadeComplete(data);
            break;

        case 'cascade_node_approved':
            showNotification(`${data.node_id} aktualisiert`, 'success');
            break;

        case 'cascade_node_rejected':
            break;

        // Pipeline Execution Events
        case 'pipeline_progress':
            handlePipelineProgress(data);
            break;

        case 'pipeline_complete':
            handlePipelineComplete(data);
            break;

        case 'pipeline_error':
            handlePipelineError(data);
            break;

        // Wizard AutoGen Agent Events
        case 'wizard_suggestion_pending':
            showWizardSuggestion(data);
            break;

        case 'wizard_suggestion_auto_applied':
            handleAutoApplied(data);
            break;

        case 'wizard_suggestion_approved':
            console.log('[WS] Wizard suggestion approved:', data.id);
            showNotification('Vorschlag angenommen', 'success');
            break;

        case 'wizard_suggestion_rejected':
            console.log('[WS] Wizard suggestion rejected:', data.id);
            break;

        case 'wizard_enrichment_started':
            handleEnrichmentStarted(data);
            break;

        case 'wizard_enrichment_complete':
            handleEnrichmentComplete(data);
            break;

        // Pipeline Stage I/O Events
        case 'stage_started':
        case 'stage_completed':
        case 'stage_failed':
        case 'stage_skipped':
            onStageEvent({ ...data, type });
            break;

        // Trace Explorer Events
        case 'trace_edit':
        case 'trace_impact':
        case 'trace_kilo_complete':
            onTraceEvent({ ...data, type });
            break;

        default:
            console.log(`[WS] Unhandled message type: ${type}`);
    }
}

// ============================================
// Mermaid Initialization
// ============================================

function initMermaid() {
    if (typeof mermaid === 'undefined') {
        console.error('[Mermaid] Library not loaded - check CDN/network');
        log('error', 'Mermaid library failed to load from CDN');
        return;
    }

    try {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
            themeVariables: {
                background: '#1a1f26',
                primaryColor: '#2d5a8e',
                primaryTextColor: '#e7e9ea',
                primaryBorderColor: '#4a6a8a',
                secondaryColor: '#1e4d3a',
                secondaryTextColor: '#e7e9ea',
                tertiaryColor: '#3a3a1e',
                lineColor: '#8b98a5',
                textColor: '#e7e9ea',
                mainBkg: '#242b33',
                nodeBorder: '#4a6a8a',
                clusterBkg: '#1a1f26',
                clusterBorder: '#3d4349',
                titleColor: '#e7e9ea',
                actorTextColor: '#e7e9ea',
                actorBkg: '#2d5a8e',
                actorBorder: '#4a6a8a',
                actorLineColor: '#536471',
                signalColor: '#8b98a5',
                signalTextColor: '#e7e9ea',
                labelBoxBkgColor: '#242b33',
                labelBoxBorderColor: '#3d4349',
                labelTextColor: '#e7e9ea',
                loopTextColor: '#8b98a5',
                noteBkgColor: '#3a3a1e',
                noteTextColor: '#e7e9ea',
                noteBorderColor: '#536471',
            },
            securityLevel: 'strict',
            suppressErrorRendering: false,
            maxTextSize: 50000,
            maxEdges: 500,
            flowchart: { useMaxWidth: true, htmlLabels: false },
            sequence: { useMaxWidth: true, showSequenceNumbers: false },
            er: { useMaxWidth: true },
            c4: { useMaxWidth: true },
            class: { useMaxWidth: true },
            state: { useMaxWidth: true }
        });
        console.log('[Mermaid] Library initialized successfully');
        log('info', 'Mermaid initialized');
    } catch (e) {
        console.error('[Mermaid] Initialization failed:', e);
        log('error', `Mermaid initialization failed: ${e.message}`);
    }
}

// ============================================
// Event Listeners
// ============================================

function initEventListeners() {
    // Project list clicks
    if (elements.projectList) {
        elements.projectList.addEventListener('click', (e) => {
            const projectItem = e.target.closest('.project-item');
            if (projectItem) loadProject(projectItem.dataset.projectId);
        });
    }
}

// ============================================
// Module Setup
// ============================================

function setupModuleCallbacks() {
    // Setup chat callbacks (for Kilo Agent WS integration)
    setChatCallbacks({
        sendMessage,
        renderMermaid
    });
}

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('[Init] DOMContentLoaded fired');

    initElements();
    console.log('[Init] Elements initialized');

    setupModuleCallbacks();
    initMermaid();
    initWebSocket();
    initEventListeners();
    loadProjectList();

    // Initialize change tracking and Kilo Agent integration
    initChangeTracker();
    initKiloBridge();

    // Initialize wizard tab and set as default view
    initWizardTab();
    switchTab('wizard');

    log('info', 'Dashboard initialized');
});

// ============================================
// Tab Switching (Wizard / Pipeline / Trace Explorer)
// ============================================

function switchTab(tabName) {
    // Toggle tab buttons
    document.querySelectorAll('.header-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tabName)
    );

    const wizardContainer = document.getElementById('wizard-container');
    if (wizardContainer) wizardContainer.style.display = tabName === 'wizard' ? '' : 'none';

    const pipelineContainer = document.getElementById('pipeline-container');
    if (pipelineContainer) pipelineContainer.style.display = tabName === 'pipeline' ? '' : 'none';

    const traceContainer = document.getElementById('trace-container');
    if (traceContainer) traceContainer.style.display = tabName === 'trace' ? '' : 'none';

    // Refresh pipeline data when switching to it
    if (tabName === 'pipeline') {
        refreshPipelineView();
    }

    // Refresh trace explorer when switching to it
    if (tabName === 'trace') {
        refreshTraceView();
    }
}

function initWizardTab() {
    // Tab click handlers
    document.querySelectorAll('.header-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Initialize pipeline view
    const pipelineContainer = document.getElementById('pipeline-container');
    if (pipelineContainer) {
        initPipelineView(pipelineContainer);
    }

    // Initialize trace explorer
    const traceContainer = document.getElementById('trace-container');
    if (traceContainer) {
        initTraceExplorer(traceContainer);
    }

    // Initialize wizard content
    const wizardContainer = document.getElementById('wizard-container');
    if (wizardContainer) {
        initWizard(wizardContainer);

        // Callback: when wizard completes, switch to trace explorer
        setOnAnalysisComplete(({ requirements, project, pipelineStarted }) => {
            const created = requirements ? requirements.length : 0;

            // Switch to trace explorer to view results
            switchTab('trace');

            if (pipelineStarted) {
                showPipelineProgressBar();
                showNotification(`Pipeline gestartet mit ${created} Requirements`, 'success');
                log('info', `[Pipeline] Gestartet fuer "${project.name}" (${created} Requirements)`);
            } else {
                showNotification(`${created} Requirements aus Wizard geladen`, 'success');
                log('info', `[Wizard] ${created} Requirements aus Projekt "${project.name}" erstellt`);
            }
        });
    }
}

// ============================================
// Pipeline Progress UI
// ============================================

function showPipelineProgressBar() {
    // Remove existing bar if any
    let bar = document.getElementById('pipeline-progress-bar');
    if (bar) bar.remove();

    bar = document.createElement('div');
    bar.id = 'pipeline-progress-bar';
    bar.style.cssText = `
        position: fixed; top: 48px; left: 0; right: 0; z-index: 9999;
        background: #1a1a2e; border-bottom: 1px solid #333;
        padding: 8px 20px; display: flex; align-items: center; gap: 12px;
        font-family: monospace; font-size: 13px; color: #e0e0e0;
    `;

    const label = document.createElement('span');
    label.id = 'pipeline-project-label';
    label.style.color = '#4fc3f7';
    label.textContent = 'Pipeline';
    bar.appendChild(label);

    const trackDiv = document.createElement('div');
    trackDiv.style.cssText = 'flex:1; height:6px; background:#333; border-radius:3px; overflow:hidden;';
    const fillDiv = document.createElement('div');
    fillDiv.id = 'pipeline-fill';
    fillDiv.style.cssText = 'height:100%; width:0%; background:linear-gradient(90deg,#4fc3f7,#29b6f6); border-radius:3px; transition:width 0.5s ease;';
    trackDiv.appendChild(fillDiv);
    bar.appendChild(trackDiv);

    const stepText = document.createElement('span');
    stepText.id = 'pipeline-step-text';
    stepText.style.minWidth = '140px';
    stepText.textContent = 'Starting...';
    bar.appendChild(stepText);

    const costText = document.createElement('span');
    costText.id = 'pipeline-cost-text';
    costText.style.cssText = 'color:#888; min-width:60px;';
    bar.appendChild(costText);

    const stopBtn = document.createElement('button');
    stopBtn.id = 'pipeline-stop-btn';
    stopBtn.textContent = 'Stop';
    stopBtn.style.cssText = 'background:#c62828; color:white; border:none; border-radius:4px; padding:2px 10px; cursor:pointer; font-size:12px;';
    stopBtn.addEventListener('click', () => window.stopPipeline());
    bar.appendChild(stopBtn);

    document.body.appendChild(bar);
}

function handlePipelineProgress(data) {
    // Auto-show progress bar if not visible
    if (!document.getElementById('pipeline-progress-bar')) {
        showPipelineProgressBar();
    }

    const fill = document.getElementById('pipeline-fill');
    const text = document.getElementById('pipeline-step-text');
    const costText = document.getElementById('pipeline-cost-text');
    const label = document.getElementById('pipeline-project-label');

    // Show project N/M for batch runs
    const projTotal = data.project_total || 1;
    const projIndex = data.project_index || 1;
    const projName = data.project_name || '';
    if (label) {
        label.textContent = projTotal > 1
            ? `[${projIndex}/${projTotal}] ${projName}`
            : projName || 'Pipeline';
    }

    if (fill) fill.style.width = `${data.percent || 0}%`;
    if (text) text.textContent = `Step ${data.step}/${data.total}: ${data.description || ''}`;
    if (costText && data.cost_usd > 0) {
        costText.textContent = `$${data.cost_usd.toFixed(4)}`;
    }
}

function handlePipelineComplete(data) {
    const fill = document.getElementById('pipeline-fill');
    const text = document.getElementById('pipeline-step-text');
    const costText = document.getElementById('pipeline-cost-text');
    const stopBtn = document.getElementById('pipeline-stop-btn');
    if (fill) fill.style.width = '100%';
    const summary = data?.summary || {};
    const costStr = summary.cost_usd ? ` | $${summary.cost_usd.toFixed(4)}` : '';

    // Show batch results if multiple projects
    const total = summary.projects_total || 1;
    const completed = summary.projects_completed || total;
    const failed = summary.projects_failed || 0;
    if (total > 1) {
        const batchInfo = `${completed}/${total} done` + (failed ? `, ${failed} failed` : '');
        if (text) text.textContent = `Batch complete (${batchInfo})${costStr}`;
        showNotification(`Batch abgeschlossen: ${batchInfo}${costStr}`, failed ? 'warning' : 'success');
    } else {
        if (text) text.textContent = `Pipeline complete!${costStr}`;
        const costMsg = summary.cost_usd ? ` ($${summary.cost_usd.toFixed(4)})` : '';
        showNotification(`Pipeline abgeschlossen!${costMsg}`, 'success');
    }

    if (costText && summary.cost_usd) costText.textContent = `$${summary.cost_usd.toFixed(4)}`;
    if (stopBtn) stopBtn.style.display = 'none';

    // Refresh views to show completed results
    refreshTraceView();
    refreshPipelineView();
    loadProjectList();
}

function handlePipelineError(data) {
    const fill = document.getElementById('pipeline-fill');
    const text = document.getElementById('pipeline-step-text');
    const stopBtn = document.getElementById('pipeline-stop-btn');

    // If batch continues, just show warning
    if (data.continues) {
        showNotification(`Projekt-Fehler: ${data.error} \u2014 weiter mit n\u00e4chstem`, 'warning');
        log('error', `[Pipeline] Error (continuing): ${data.error}`);
        return;
    }

    if (fill) { fill.style.width = '100%'; fill.style.background = '#c62828'; }
    if (text) text.textContent = `Error: ${data.error || 'Unknown'}`;
    if (stopBtn) stopBtn.style.display = 'none';

    showNotification(`Pipeline-Fehler: ${data.error}`, 'error');
    log('error', `[Pipeline] Error: ${data.error}`);
}

window.stopPipeline = async function() {
    try {
        const resp = await fetch('/api/pipeline/stop', { method: 'POST' });
        const result = await resp.json();
        if (result.status === 'cancelled') {
            showNotification('Pipeline gestoppt', 'info');
        }
    } catch (e) {
        console.error('Failed to stop pipeline:', e);
    }
};

// ============================================
// Global Exports (for HTML onclick handlers)
// ============================================

// Kilo Agent chat exports
window.openChatPanel = openChatPanel;
window.closeChatPanel = closeChatPanel;
window.sendKiloTask = sendKiloTask;

// Change tracking exports (for domino effect)
window.trackChange = trackChange;
window.CHANGE_TYPES = CHANGE_TYPES;

// Tab switching
window.switchTab = switchTab;

// Modal system exports
window.openModal = openModal;
window.closeModal = closeModal;
window.openDiagramGallery = openDiagramGallery;
window.openTestCasesModal = openTestCasesModal;
window.openUserStoriesModal = openUserStoriesModal;
window.openTasksModal = openTasksModal;
window.openFullDiagram = openFullDiagram;
