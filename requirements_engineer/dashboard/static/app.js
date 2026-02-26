/**
 * RE System - Endless Canvas Dashboard (Refactored)
 *
 * Main application entry point - imports from modular architecture.
 *
 * Module Structure:
 * - modules/state.js         - State management, DOM refs, helpers
 * - modules/canvas.js        - Pan, zoom, edge navigation
 * - modules/connections.js   - Connection rendering and routing
 * - modules/mermaidRenderer.js - Mermaid diagram queue and rendering
 * - modules/nodeFactory.js   - Node creation functions
 * - modules/autoLinker.js    - Auto-linking based on metadata
 * - modules/layouts/         - Layout algorithms
 * - modules/ui/              - UI components
 */

// ============================================
// Module Imports
// ============================================

import { state, elements, initElements, log, getTagType, highlightGherkin, escapeHtml } from './modules/state.js';
import { initEdgeNavigation } from './modules/canvas.js';
import { addConnection, updateConnections, scheduleConnectionUpdate, setLayoutConfig, setDragNode, clearDragNode } from './modules/connections.js';
import {
    queueMermaidRender,
    startMermaidRendering,
    reRenderAllDiagrams,
    renderMermaid,
    sanitizeMermaidCode,
    sanitizeIdForHtml,
    clearMermaidQueue
} from './modules/mermaidRenderer.js';
import {
    createNodeFromJournal,
    createRequirementFromArray,
    createEpicFromFolder,
    createUserStoryFromFolder,
    createDiagramFromFolder,
    createTestFromFolder,
    createEntityFromDictionary,
    createFeatureFromBreakdown,
    createApiEndpointNode,
    createApiPackageNode,
    createTechStackNode,
    createPersonaNode,
    createUserFlowNode,
    createUIComponentNode,
    createScreenNode,
    createTaskNode,
    createTaskGroupNode,
    createServiceNode,
    createStateMachineNode,
    createInfrastructureNode,
    createDesignTokensNode,
    findNodeByPartialId,
    setSidebarCallback,
    setCreateNodeFunction
} from './modules/nodeFactory.js';
import {
    applyTraceabilityLinks,
    applyEpicStoryLinks,
    applyUserStoryLinks,
    applyPersonaStoryLinks,
    applyFlowScreenLinks,
    applyScreenStoryLinks,
    applyScreenComponentLinks,
    applyFeatureTaskLinks,
    applyMetadataLinks,
    applyTestStoryLinks,
    applyApiRequirementLinks,
    applyApiScreenLinks,
    applyEntityApiLinks,
    applyScreenEntityLinks,
    applyTestApiLinks,
    applyPersonaScreenLinks,
    applyComponentApiLinks,
    applyApiEntityLinks,
    applyDiagramEntityLinks,
    applyRequirementFeatureLinks,
    applyFeatureStoryLinks,
    applyTechComponentLinks
} from './modules/autoLinker.js';
import { addSidebarItem, focusNode, updateCounts, setSidebarCallbacks } from './modules/ui/sidebar.js';
import { updateMinimap, clearMinimap } from './modules/ui/minimap.js';
import { showDetailPanel, hideDetailPanel, addNodeClickHandler, setDetailPanelCallbacks } from './modules/ui/detailPanel.js';
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

// Layout imports
import {
    LAYOUT_MODES,
    WORKPACKAGE_COLUMNS,
    setLayout,
    currentLayout,
    detectWorkPackages,
    setLayoutCallbacks
} from './modules/layouts/index.js';
import { reorganizeNodesMatrix, setMatrixCallbacks } from './modules/layouts/matrix.js';
import { renderPackageMatrix, refreshPackageMatrix, togglePackageMatrix } from './modules/package_matrix.js';

// Change tracking and Kilo Agent integration
import { initChangeTracker, trackChange, CHANGE_TYPES } from './modules/core/change_tracker.js';

// Wizard module
import { initWizard, setOnAnalysisComplete } from './modules/ui/wizard.js';
import { initKiloBridge } from './modules/agents/kilo_bridge.js';

// Pipeline View module
import { initPipelineView, onStageEvent, onPipelineComplete, refreshPipelineView } from './modules/ui/pipeline_view.js';

// Link Discovery module (orphan node auto-linking)
import {
    discoverLinks, approveLink, rejectLink,
    updateOrphanCount, getOrphanCount,
    handleLinkSuggestion, handleLinkCreated, handleLinkRejected
} from './modules/ui/linkDiscovery.js';

// ============================================
// Performance: RAF Throttling for Mouse Events
// ============================================

let rafPending = false;
let lastMouseEvent = null;

// ============================================
// Node Templates
// ============================================

const NODE_TEMPLATES = {
    requirement: `
        <div class="node-header">
            <span class="node-type">REQ</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-meta-row">
                <div class="node-priority"></div>
                <div class="node-quality-bar" title="Quality Score"></div>
            </div>
            <div class="node-status-flags"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    epic: `
        <div class="node-header">
            <span class="node-type-badge ap-badge">AP</span>
            <span class="node-type">Epic</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-meta-row">
                <span class="node-badge node-badge-count" title="Requirements"></span>
                <span class="node-badge node-badge-stories" title="User Stories"></span>
            </div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    'user-story': `
        <div class="node-header">
            <span class="node-type">User Story</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-persona"></div>
            <div class="node-linked-tests"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    diagram: `
        <div class="node-header">
            <span class="node-type">Diagram</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content node-diagram-content"></div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    test: `
        <div class="node-header">
            <span class="node-type">Test</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-meta-row">
                <span class="node-test-type"></span>
                <span class="node-scenario-count"></span>
            </div>
            <div class="node-tags"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    api: `
        <div class="node-header">
            <span class="node-type">API</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-meta-row">
                <span class="node-method"></span>
                <span class="node-path"></span>
            </div>
            <div class="node-description"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    persona: `
        <div class="node-header">
            <span class="node-type">Persona</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-role"></div>
            <div class="node-meta-row">
                <span class="node-badge node-badge-goals" title="Goals"></span>
                <span class="node-badge node-badge-pains" title="Pain Points"></span>
            </div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-out"></div>
        </div>
    `,
    'user-flow': `
        <div class="node-header">
            <span class="node-type">User Flow</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content node-diagram-content"></div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    screen: `
        <div class="node-header">
            <span class="node-type">Screen</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-route"></div>
            <pre class="node-wireframe-preview"></pre>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    component: `
        <div class="node-header">
            <span class="node-type">Component</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-meta-row">
                <span class="node-component-type"></span>
                <span class="node-badge node-badge-variants" title="Variants"></span>
            </div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    task: `
        <div class="node-header">
            <span class="node-type">Task</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-meta-row">
                <span class="node-task-type"></span>
                <span class="node-task-estimate"></span>
            </div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    'tech-stack': `
        <div class="node-header">
            <span class="node-type">Tech Stack</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-tech-grid"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    entity: `
        <div class="node-header">
            <span class="node-type">Entity</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-attributes"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    'api-package': `
        <div class="node-header">
            <span class="node-type">API Package</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-method-chips"></div>
            <div class="node-endpoint-count"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    'task-group': `
        <div class="node-header">
            <span class="node-type">Task Group</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-task-summary"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    service: `
        <div class="node-header">
            <span class="node-type">Service</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-service-tech"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    'state-machine': `
        <div class="node-header">
            <span class="node-type">State Machine</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-sm-summary"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
            <div class="connector connector-out"></div>
        </div>
    `,
    infrastructure: `
        <div class="node-header">
            <span class="node-type">Infrastructure</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-infra-summary"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `,
    'design-tokens': `
        <div class="node-header">
            <span class="node-type">Design Tokens</span>
            <span class="node-id"></span>
        </div>
        <div class="node-content">
            <div class="node-title"></div>
            <div class="node-token-preview"></div>
        </div>
        <div class="node-connectors">
            <div class="connector connector-in"></div>
        </div>
    `
};

// ============================================
// Node Creation (Core Function)
// ============================================

function createNode(type, id, data) {
    // Prevent duplicate nodes
    if (state.nodes[id]) {
        console.log(`[Node] Skipping duplicate: ${id}`);
        return state.nodes[id].element;
    }

    const template = NODE_TEMPLATES[type] || NODE_TEMPLATES.requirement;
    const position = calculateNodePosition(type, id);

    const node = document.createElement('div');
    node.className = `canvas-node node-${type}`;
    node.dataset.nodeId = id;
    node.dataset.nodeType = type;
    node.innerHTML = template;

    // Position node
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;

    // Populate content based on type
    populateNodeContent(node, type, id, data);

    // Add event listeners
    node.addEventListener('mousedown', onNodeMouseDown);
    addNodeClickHandler(node, id);

    // Add to DOM
    elements.canvasNodes.appendChild(node);

    // Store in state
    state.nodes[id] = {
        element: node,
        type,
        data,
        x: position.x,
        y: position.y
    };

    // Add Kilo chat button and edit button
    setTimeout(() => {
        addChatButton(node, id);
        addEditButton(node, id);
    }, 100);

    // Queue mermaid render if diagram
    if (type === 'diagram' || type === 'user-flow') {
        console.log(`[Node] Created ${type}: ${id}, has mermaid_code:`, !!data.mermaid_code, 'length:', data.mermaid_code?.length);
        if (data.mermaid_code && data.mermaid_code.trim()) {
            const sanitizedId = sanitizeIdForHtml(id);
            queueMermaidRender(sanitizedId, data.mermaid_code);
        } else {
            console.warn(`[Mermaid] No code for diagram: ${id}`);
        }
    }

    return node;
}

function populateNodeContent(node, type, id, data) {
    const idEl = node.querySelector('.node-id');
    if (idEl) idEl.textContent = id;

    switch (type) {
        case 'requirement': {
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            const prioEl = node.querySelector('.node-priority');
            if (prioEl) {
                prioEl.textContent = data.priority || '';
                prioEl.className = `node-priority ${data.priority || ''}`;
            }
            // Quality score mini-bar
            const qualBar = node.querySelector('.node-quality-bar');
            if (qualBar) {
                const scores = [
                    data.completeness_score, data.consistency_score,
                    data.testability_score, data.clarity_score,
                    data.feasibility_score, data.traceability_score
                ].filter(s => s !== undefined && s !== null && s > 0);
                if (scores.length > 0) {
                    const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
                    const pct = Math.round(avg * 100);
                    const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
                    qualBar.innerHTML = `<div class="quality-fill" style="width:${pct}%;background:${color}"></div>`;
                    qualBar.title = `Quality: ${pct}%`;
                    qualBar.style.display = 'block';
                }
            }
            // Status flags (buggy, complete)
            const flagsEl = node.querySelector('.node-status-flags');
            if (flagsEl) {
                let flags = '';
                if (data.is_buggy) flags += '<span class="flag-buggy" title="Has Issues">!</span>';
                if (data.is_complete) flags += '<span class="flag-complete" title="Complete">OK</span>';
                if (flags) flagsEl.innerHTML = flags;
            }
            break;
        }

        case 'epic': {
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const reqCount = node.querySelector('.node-badge-count');
            const storyCount = node.querySelector('.node-badge-stories');
            const reqs = data.linked_requirements || [];
            const stories = data.linked_user_stories || [];
            if (reqCount && reqs.length) reqCount.textContent = `${reqs.length} REQ`;
            if (storyCount && stories.length) storyCount.textContent = `${stories.length} US`;
            break;
        }

        case 'persona': {
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const roleEl = node.querySelector('.node-role');
            if (roleEl) roleEl.textContent = data.role || '';
            const goalsEl = node.querySelector('.node-badge-goals');
            const painsEl = node.querySelector('.node-badge-pains');
            const goals = data.goals || [];
            const pains = data.pain_points || [];
            if (goalsEl && goals.length) goalsEl.textContent = `${goals.length} Goals`;
            if (painsEl && pains.length) painsEl.textContent = `${pains.length} Pains`;
            break;
        }

        case 'component': {
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const compTypeEl = node.querySelector('.node-component-type');
            if (compTypeEl) compTypeEl.textContent = data.component_type || '';
            const variantEl = node.querySelector('.node-badge-variants');
            const variants = data.variants || [];
            if (variantEl && variants.length) variantEl.textContent = `${variants.length} Var`;
            break;
        }

        case 'task': {
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const taskTypeEl = node.querySelector('.node-task-type');
            if (taskTypeEl) taskTypeEl.textContent = data.task_type || '';
            const estEl = node.querySelector('.node-task-estimate');
            if (estEl) {
                const parts = [];
                if (data.estimated_hours) parts.push(`${data.estimated_hours}h`);
                if (data.complexity) parts.push(data.complexity);
                if (parts.length) estEl.textContent = parts.join(' | ');
            }
            break;
        }

        case 'tech-stack': {
            node.querySelector('.node-title').textContent = data.title || data.name || data.project_name || 'Tech Stack';
            const gridEl = node.querySelector('.node-tech-grid');
            if (gridEl) {
                const items = [];
                if (data.frontend_framework) items.push(`<span class="tech-item tech-fe">${data.frontend_framework}</span>`);
                if (data.backend_framework) items.push(`<span class="tech-item tech-be">${data.backend_framework}</span>`);
                if (data.primary_database) items.push(`<span class="tech-item tech-db">${data.primary_database}</span>`);
                if (data.cloud_provider) items.push(`<span class="tech-item tech-cloud">${data.cloud_provider}</span>`);
                if (items.length) gridEl.innerHTML = items.join('');
            }
            break;
        }

        case 'screen': {
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const routeEl = node.querySelector('.node-route');
            if (routeEl && data.route) routeEl.textContent = data.route;
            const wireframePreview = node.querySelector('.node-wireframe-preview');
            if (wireframePreview && data.wireframe_ascii) {
                const lines = data.wireframe_ascii.split('\n').slice(0, 8);
                wireframePreview.textContent = lines.join('\n') + (data.wireframe_ascii.split('\n').length > 8 ? '\n...' : '');
                wireframePreview.style.display = 'block';
            } else if (wireframePreview) {
                wireframePreview.style.display = 'none';
            }
            break;
        }

        case 'user-story':
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            const personaEl = node.querySelector('.node-persona');
            if (personaEl) personaEl.textContent = `As a ${data.persona || 'user'}`;
            const linkedTestsEl = node.querySelector('.node-linked-tests');
            if (linkedTestsEl) {
                linkedTestsEl.dataset.userStoryId = id;
                linkedTestsEl.innerHTML = '';
            }
            break;

        case 'diagram':
        case 'user-flow': {
            const diagramTypeEl = node.querySelector('.node-type');
            const diagramType = data.diagram_type || 'Diagram';
            if (diagramTypeEl) diagramTypeEl.textContent = diagramType;
            const mermaidContent = node.querySelector('.node-diagram-content');
            if (mermaidContent) {
                const sanitizedId = sanitizeIdForHtml(id);
                mermaidContent.id = `mermaid-${sanitizedId}`;
                mermaidContent.dataset.originalId = id;
                console.log(`[Node] Set mermaid container ID: mermaid-${sanitizedId} (original: ${id})`);
                if (data.mermaid_code && data.mermaid_code.trim()) {
                    mermaidContent.innerHTML = `<div class="diagram-loading">Loading ${diagramType}...</div>`;
                } else {
                    mermaidContent.innerHTML = `<div class="diagram-error">No diagram code available</div>`;
                }
            }
            break;
        }

        case 'test': {
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            const testTypeEl = node.querySelector('.node-test-type');
            if (testTypeEl) testTypeEl.textContent = data.test_type || 'BDD';
            // Scenario count badge
            const scenarioEl = node.querySelector('.node-scenario-count');
            if (scenarioEl && data.scenario_count) {
                scenarioEl.textContent = `${data.scenario_count} Sc`;
                scenarioEl.title = `${data.scenario_count} Scenarios`;
            }
            // Tags as colored badges
            const tagsEl = node.querySelector('.node-tags');
            if (tagsEl && data.tags && data.tags.length) {
                tagsEl.innerHTML = data.tags.slice(0, 3).map(t =>
                    `<span class="tag-mini">${t}</span>`
                ).join('') + (data.tags.length > 3 ? `<span class="tag-mini tag-more">+${data.tags.length - 3}</span>` : '');
            }
            break;
        }

        case 'api': {
            const methodEl = node.querySelector('.node-method');
            const pathEl = node.querySelector('.node-path');
            if (methodEl) {
                methodEl.textContent = data.method || 'GET';
                methodEl.className = `node-method method-${(data.method || 'GET').toLowerCase()}`;
            }
            if (pathEl) pathEl.textContent = data.path || '/';
            const descEl = node.querySelector('.node-description');
            if (descEl && data.description) {
                descEl.textContent = data.description.length > 60
                    ? data.description.substring(0, 57) + '...'
                    : data.description;
            }
            break;
        }

        case 'entity':
            node.querySelector('.node-title').textContent = data.title || data.name || 'Untitled';
            const attrsEl = node.querySelector('.node-attributes');
            if (attrsEl) {
                const attrCount = (data.attributes || []).length;
                attrsEl.textContent = `${attrCount} Attribute${attrCount !== 1 ? 's' : ''}`;
            }
            break;

        case 'api-package': {
            node.querySelector('.node-title').textContent = data.tag || 'Package';
            const mcEl = node.querySelector('.node-method-chips');
            if (mcEl) {
                const mc = data.method_counts || {};
                mcEl.innerHTML = Object.entries(mc)
                    .map(([m, c]) => `<span class="method-chip method-${m.toLowerCase()}">${m}:${c}</span>`)
                    .join(' ');
            }
            const countEl = node.querySelector('.node-endpoint-count');
            if (countEl) countEl.textContent = `${data.endpoint_count || 0} endpoints`;
            break;
        }

        case 'task-group': {
            node.querySelector('.node-title').textContent = data.title || 'Tasks';
            const summEl = node.querySelector('.node-task-summary');
            if (summEl) {
                summEl.textContent = `${data.task_count || 0} tasks | ${data.total_hours || 0}h`;
            }
            break;
        }

        case 'service': {
            node.querySelector('.node-title').textContent = data.name || 'Service';
            const techEl = node.querySelector('.node-service-tech');
            if (techEl && data.technology) {
                techEl.innerHTML = `<span class="tech-item tech-be">${data.technology}</span>`;
            }
            break;
        }

        case 'state-machine': {
            node.querySelector('.node-title').textContent = data.name || data.entity || 'State Machine';
            const smSumm = node.querySelector('.node-sm-summary');
            if (smSumm) {
                smSumm.textContent = `${data.state_count || 0} states | ${data.transition_count || 0} transitions`;
            }
            break;
        }

        case 'infrastructure': {
            node.querySelector('.node-title').textContent = 'Infrastructure';
            const infraSumm = node.querySelector('.node-infra-summary');
            if (infraSumm) {
                const parts = [];
                if (data.architecture_style) parts.push(data.architecture_style);
                if (data.service_count) parts.push(`${data.service_count} services`);
                const flags = [];
                if (data.has_dockerfile) flags.push('Docker');
                if (data.has_k8s) flags.push('K8s');
                if (data.has_ci) flags.push('CI/CD');
                if (flags.length) parts.push(flags.join('+'));
                infraSumm.textContent = parts.join(' | ') || 'N/A';
            }
            break;
        }

        case 'design-tokens': {
            node.querySelector('.node-title').textContent = 'Design Tokens';
            const tokenPrev = node.querySelector('.node-token-preview');
            if (tokenPrev) {
                const colorCount = Object.keys(data.colors || {}).length;
                const typoCount = Object.keys(data.typography || {}).length;
                tokenPrev.textContent = `${colorCount} colors | ${typoCount} typography`;
            }
            break;
        }
    }
}

/**
 * Update all user story nodes to show their linked tests as metadata
 * Called after all nodes are loaded
 */
function updateLinkedTestsDisplay() {
    // Find all user story nodes with linked-tests container
    document.querySelectorAll('.node-linked-tests[data-user-story-id]').forEach(container => {
        const userStoryId = container.dataset.userStoryId;
        const linkedTests = findLinkedTests(userStoryId);

        if (linkedTests.length > 0) {
            container.innerHTML = `<span class="tests-badge" title="${linkedTests.map(t => t.title).join('\n')}">🧪 ${linkedTests.length} Test${linkedTests.length > 1 ? 's' : ''}</span>`;
        } else {
            container.innerHTML = '';
        }
    });
}

/**
 * Find all tests linked to a user story
 * @param {string} userStoryId - The user story ID
 * @returns {Array} Array of linked test objects
 */
function findLinkedTests(userStoryId) {
    const tests = [];
    const addedIds = new Set();

    // 1. Find by direct connection
    state.connections.forEach(conn => {
        // Check both directions
        if (conn.from === userStoryId) {
            const targetNode = state.nodes[conn.to];
            if (targetNode?.type === 'test' && !addedIds.has(conn.to)) {
                addedIds.add(conn.to);
                tests.push({ id: conn.to, title: targetNode.data?.title || conn.to });
            }
        }
        if (conn.to === userStoryId) {
            const sourceNode = state.nodes[conn.from];
            if (sourceNode?.type === 'test' && !addedIds.has(conn.from)) {
                addedIds.add(conn.from);
                tests.push({ id: conn.from, title: sourceNode.data?.title || conn.from });
            }
        }
    });

    // 2. Find by linked_user_story field in test data
    Object.entries(state.nodes).forEach(([testId, testNode]) => {
        if (testNode.type !== 'test' || addedIds.has(testId)) return;
        if (testNode.data?.linked_user_story === userStoryId) {
            addedIds.add(testId);
            tests.push({ id: testId, title: testNode.data?.title || testId });
        }
    });

    // 3. Find by ID pattern (TC-US-001 belongs to US-001)
    const userStoryMatch = userStoryId.match(/US-(\d+)/i);
    if (userStoryMatch) {
        const usNumber = userStoryMatch[1];
        Object.entries(state.nodes).forEach(([testId, testNode]) => {
            if (testNode.type !== 'test' || addedIds.has(testId)) return;
            // Match TC-US-001, TC-US-001-xxx patterns
            if (testId.includes(`TC-US-${usNumber}`) || testId.includes(`TC-US${usNumber}`)) {
                addedIds.add(testId);
                tests.push({ id: testId, title: testNode.data?.title || testId });
            }
        });
    }

    return tests;
}

function calculateNodePosition(type, id) {
    const baseX = 3000;
    const baseY = 3000;
    const isDiagram = type === 'diagram';
    const columnWidth = isDiagram ? 450 : 500;
    const rowHeight = isDiagram ? 400 : 180;
    const nodesPerRow = isDiagram ? 3 : 5;

    const typeColumns = {
        'requirement': 0, 'epic': 1, 'user-story': 2, 'persona': 3,
        'user-flow': 4, 'screen': 5, 'component': 6, 'diagram': 7,
        'test': 8, 'api': 9, 'entity': 10, 'feature': 11,
        'task': 12, 'tech-stack': 13
    };

    const column = typeColumns[type] || 0;

    if (state.nodeCounters[type] === undefined) {
        state.nodeCounters[type] = 0;
    }
    const nodesOfType = state.nodeCounters[type]++;

    const gridRow = Math.floor(nodesOfType / nodesPerRow);
    const gridCol = nodesOfType % nodesPerRow;

    const typeRow = column < 3 ? 0 : 1;
    const typeColInRow = column < 3 ? column : column - 3;

    const sectionWidth = isDiagram ? 2500 : 2000;
    const sectionHeight = isDiagram ? 2500 : 1500;

    return {
        x: baseX + (typeColInRow * sectionWidth) + (gridCol * columnWidth),
        y: baseY + (typeRow * sectionHeight) + (gridRow * rowHeight)
    };
}

// ============================================
// Node Dragging
// ============================================

function onNodeMouseDown(e) {
    if (e.target.classList.contains('connector')) return;

    const node = e.currentTarget;
    node.classList.add('dragging');

    // PERFORMANCE: Add global drag state to disable expensive effects
    document.body.classList.add('is-dragging');

    state.dragging.active = true;
    state.dragging.node = node;
    state.dragging.startX = e.clientX;
    state.dragging.startY = e.clientY;
    state.dragging.nodeStartX = parseFloat(node.style.left) || 0;
    state.dragging.nodeStartY = parseFloat(node.style.top) || 0;

    // PERFORMANCE: Set drag node for partial connection updates
    const nodeId = node.dataset.nodeId;
    if (nodeId) {
        setDragNode(nodeId);
    }

    e.stopPropagation();
}

function onMouseMove(e) {
    // RAF throttling: batch mouse events to max 60fps
    lastMouseEvent = e;
    if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(processMouseMove);
    }
}

function processMouseMove() {
    rafPending = false;
    const e = lastMouseEvent;
    if (!e) return;

    if (state.dragging.active && state.dragging.node) {
        const dx = (e.clientX - state.dragging.startX) / state.canvas.zoom;
        const dy = (e.clientY - state.dragging.startY) / state.canvas.zoom;

        const newX = state.dragging.nodeStartX + dx;
        const newY = state.dragging.nodeStartY + dy;

        state.dragging.node.style.left = `${newX}px`;
        state.dragging.node.style.top = `${newY}px`;

        const nodeId = state.dragging.node.dataset.nodeId;
        if (state.nodes[nodeId]) {
            state.nodes[nodeId].x = newX;
            state.nodes[nodeId].y = newY;
        }

        // Use RAF-scheduled connection update instead of immediate update
        scheduleConnectionUpdate();
    } else if (state.panning.active) {
        const dx = e.clientX - state.panning.startX;
        const dy = e.clientY - state.panning.startY;

        state.canvas.x = state.panning.canvasStartX + dx;
        state.canvas.y = state.panning.canvasStartY + dy;

        updateCanvasTransform();
    }
}

function onMouseUp() {
    if (state.dragging.active && state.dragging.node) {
        state.dragging.node.classList.remove('dragging');

        // PERFORMANCE: Remove global drag state
        document.body.classList.remove('is-dragging');

        // PERFORMANCE: Clear drag node before full update
        clearDragNode();

        // PERFORMANCE: Use requestIdleCallback for non-urgent updates
        // This prevents blocking the main thread after drag ends
        if (typeof requestIdleCallback === 'function') {
            requestIdleCallback(() => {
                updateConnections(true);
                updateMinimap();
            }, { timeout: 100 });
        } else {
            // Fallback: Use setTimeout for browsers without requestIdleCallback
            setTimeout(() => {
                updateConnections(true);
                updateMinimap();
            }, 0);
        }
    }

    if (state.panning.active) {
        elements.canvas.style.cursor = 'grab';
    }

    state.dragging.active = false;
    state.dragging.node = null;
    state.panning.active = false;
}

// ============================================
// Canvas Controls
// ============================================

function updateCanvasTransform() {
    elements.canvas.style.transform =
        `translate(${state.canvas.x}px, ${state.canvas.y}px) scale(${state.canvas.zoom})`;
    elements.zoomLevel.textContent = `${Math.round(state.canvas.zoom * 100)}%`;
    updateMinimap();
}

function zoom(delta, targetX = null, targetY = null) {
    const oldZoom = state.canvas.zoom;
    const newZoom = Math.max(state.canvas.minZoom, Math.min(state.canvas.maxZoom, oldZoom + delta));

    if (newZoom !== oldZoom) {
        if (targetX !== null && targetY !== null) {
            // Zoom towards target point (mouse position)
            const worldX = (targetX - state.canvas.x) / oldZoom;
            const worldY = (targetY - state.canvas.y) / oldZoom;
            state.canvas.zoom = newZoom;
            state.canvas.x = targetX - worldX * newZoom;
            state.canvas.y = targetY - worldY * newZoom;
        } else {
            // Zoom to center
            state.canvas.zoom = newZoom;
        }
        updateCanvasTransform();
    }
}

function fitToView() {
    if (Object.keys(state.nodes).length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    Object.values(state.nodes).forEach(node => {
        minX = Math.min(minX, node.x);
        minY = Math.min(minY, node.y);
        maxX = Math.max(maxX, node.x + 300);
        maxY = Math.max(maxY, node.y + 150);
    });

    const contentWidth = maxX - minX;
    const contentHeight = maxY - minY;
    const containerRect = elements.canvasContainer.getBoundingClientRect();

    const scaleX = containerRect.width / (contentWidth + 200);
    const scaleY = containerRect.height / (contentHeight + 200);
    // Minimum zoom 0.35 to prevent too much zooming out, max 1.0
    state.canvas.zoom = Math.max(0.35, Math.min(1.0, Math.min(scaleX, scaleY)));

    state.canvas.x = -minX * state.canvas.zoom + (containerRect.width - contentWidth * state.canvas.zoom) / 2;
    state.canvas.y = -minY * state.canvas.zoom + (containerRect.height - contentHeight * state.canvas.zoom) / 2;

    updateCanvasTransform();
}

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
    elements.projectList.innerHTML = projects.map(p => {
        const counts = [];
        if (p.node_count > 0) counts.push(`${p.node_count} reqs`);
        if (p.epic_count > 0) counts.push(`${p.epic_count} epics`);
        if (p.us_count > 0) counts.push(`${p.us_count} stories`);
        if (p.diagram_count > 0) counts.push(`${p.diagram_count} diagrams`);
        if (p.test_count > 0) counts.push(`${p.test_count} tests`);

        const countStr = counts.length > 0 ? counts.join(' | ') : 'Empty';
        const formatBadge = p.format === 'journal' ? '📋' : '📁';

        return `
            <div class="project-item" data-project-id="${p.id}">
                <div class="project-name">${formatBadge} ${escapeHtml(p.name)}</div>
                <div class="project-meta">
                    <span class="item-counts">${countStr}</span>
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
        clearCanvas();

        // Update project info
        const projectName = data.project_name || projectId;
        if (elements.projectInfo) {
            const nameEl = elements.projectInfo.querySelector('.project-name');
            if (nameEl) nameEl.textContent = projectName;
        }

        let totalItems = 0;

        // Check if separate diagrams array exists - if so, skip embedded diagram creation
        const hasSeparateDiagrams = data.diagrams?.length > 0;

        // Load all node types using the factory functions
        // NOTE: data.nodes and data.requirements often contain the same data (backend extracts requirements from nodes)
        // So we only process one of them to avoid duplicates
        if (data.nodes && Object.keys(data.nodes).length > 0) {
            Object.entries(data.nodes).forEach(([nodeId, nodeData]) => {
                // Skip embedded mermaid_diagrams if separate diagrams array exists
                if (hasSeparateDiagrams) {
                    delete nodeData.mermaid_diagrams;
                }
                createNodeFromJournal(nodeId, nodeData);
                totalItems++;
            });
            // Skip data.requirements since it's extracted from the same nodes
        } else if (data.requirements?.length) {
            // Only use requirements if nodes doesn't exist
            data.requirements.forEach(req => {
                // Skip embedded mermaid_diagrams if separate diagrams array exists
                if (hasSeparateDiagrams) {
                    delete req.mermaid_diagrams;
                }
                createRequirementFromArray(req);
                totalItems++;
            });
        }

        if (data.epics?.length) {
            data.epics.forEach(epic => { createEpicFromFolder(epic); totalItems++; });
        }

        if (data.user_stories?.length) {
            data.user_stories.forEach(story => { createUserStoryFromFolder(story); totalItems++; });
        }

        // Use diagrams array as canonical source (avoids duplicates from embedded mermaid_diagrams)
        console.log('[Project] Diagrams data:', {
            hasDiagrams: !!data.diagrams,
            diagramCount: data.diagrams?.length || 0,
            sampleDiagram: data.diagrams?.[0] ? {
                id: data.diagrams[0].id,
                hasCode: !!data.diagrams[0].mermaid_code,
                codeLength: data.diagrams[0].mermaid_code?.length || 0
            } : null
        });
        if (data.diagrams?.length) {
            console.log(`[Project] Creating ${data.diagrams.length} diagram nodes...`);
            data.diagrams.forEach((diagram, i) => {
                console.log(`[Project] Diagram ${i}: ${diagram.id} (code length: ${diagram.mermaid_code?.length || 0})`);
                createDiagramFromFolder(diagram);
                totalItems++;
            });
            console.log(`[Project] Finished creating diagram nodes`);
        }

        if (data.tests?.length) {
            data.tests.forEach(test => { createTestFromFolder(test); totalItems++; });
        }

        if (data.data_dictionary?.entities?.length) {
            data.data_dictionary.entities.forEach(entity => { createEntityFromDictionary(entity); totalItems++; });
        }

        if (data.features?.length) {
            data.features.forEach(feature => { createFeatureFromBreakdown(feature); totalItems++; });
        }

        // API: use packages (stacked) if available, fallback to individual endpoints
        if (data.api_packages && Object.keys(data.api_packages).length) {
            Object.values(data.api_packages).forEach(pkg => {
                createApiPackageNode(pkg);
                totalItems++;
            });
        } else if (data.api_endpoints?.length) {
            data.api_endpoints.forEach(endpoint => { createApiEndpointNode(endpoint); totalItems++; });
        }

        if (data.tech_stack) {
            createTechStackNode(data.tech_stack);
            totalItems++;
        }

        if (data.personas?.length) {
            data.personas.forEach(persona => { createPersonaNode(persona); totalItems++; });
        }

        if (data.user_flows?.length) {
            data.user_flows.forEach(flow => { createUserFlowNode(flow); totalItems++; });
        }

        if (data.ui_components?.length) {
            data.ui_components.forEach(component => { createUIComponentNode(component); totalItems++; });
        }

        if (data.screens?.length) {
            data.screens.forEach(screen => { createScreenNode(screen); totalItems++; });
        }

        // Tasks: use groups (stacked by feature) if structured, fallback to individual
        if (data.tasks && typeof data.tasks === 'object' && !Array.isArray(data.tasks)) {
            Object.entries(data.tasks).forEach(([featureId, tasks]) => {
                if (Array.isArray(tasks) && tasks.length) {
                    // Find feature name from features array
                    const feature = (data.features || []).find(f => f.id === featureId);
                    const featureName = feature ? feature.title : featureId;
                    createTaskGroupNode(featureId, featureName, tasks);
                    totalItems++;
                }
            });
        }

        // Architecture services
        if (data.architecture && data.architecture.services?.length) {
            data.architecture.services.forEach(svc => {
                createServiceNode(svc);
                totalItems++;
            });
        }

        // State machines
        if (data.state_machines?.length) {
            data.state_machines.forEach(sm => {
                createStateMachineNode(sm);
                totalItems++;
            });
        }

        // Infrastructure (single node)
        if (data.infrastructure) {
            createInfrastructureNode(data.infrastructure);
            totalItems++;
        }

        // Design tokens (single node)
        if (data.design_tokens) {
            createDesignTokensNode(data.design_tokens);
            totalItems++;
        }

        // Project stats bar (LLM usage + pipeline info)
        if (data.project_stats) {
            const statsEl = document.getElementById('project-info');
            if (statsEl) {
                const s = data.project_stats;
                let statsHtml = `<span class="project-name">${data.project_name || 'Project'}</span>`;
                const badges = [];
                if (s.llm_total_calls) badges.push(`${s.llm_total_calls} LLM calls`);
                if (s.llm_total_cost) badges.push(`$${s.llm_total_cost.toFixed(2)}`);
                if (s.pipeline_duration_ms) {
                    const secs = Math.round(s.pipeline_duration_ms / 1000);
                    const mins = Math.floor(secs / 60);
                    const remSecs = secs % 60;
                    badges.push(`${mins}m ${remSecs}s`);
                }
                if (badges.length) {
                    statsHtml += `<span class="project-stats-badges">${badges.map(b => `<span class="stats-badge">${b}</span>`).join('')}</span>`;
                }
                statsEl.innerHTML = statsHtml;
            }
        }

        updateCounts();

        // Apply auto-linking
        setTimeout(() => {
            if (data.traceability?.length) applyTraceabilityLinks(data.traceability);
            if (data.epics?.length) applyEpicStoryLinks(data.epics, data.user_stories);
            if (data.user_stories?.length) applyUserStoryLinks(data.user_stories);
            if (data.tests?.length && data.user_stories?.length) applyTestStoryLinks(data.tests, data.user_stories);
            if (data.personas && data.user_stories) applyPersonaStoryLinks(data.personas, data.user_stories);
            if (data.user_flows && data.screens) applyFlowScreenLinks(data.user_flows, data.screens);
            if (data.screens && data.user_stories) applyScreenStoryLinks(data.screens);
            if (data.screens && data.ui_components) applyScreenComponentLinks(data.screens, data.ui_components);
            if (data.tasks) applyFeatureTaskLinks(data.tasks);
            // Cross-artifact links (API, Entity, Screen)
            if (data.api_endpoints?.length) {
                applyApiRequirementLinks(data.api_endpoints);
                if (data.screens?.length) applyApiScreenLinks(data.api_endpoints, data.screens);
                if (data.data_dictionary?.entities?.length) applyEntityApiLinks(data.data_dictionary.entities, data.api_endpoints);
                if (data.tests?.length) applyTestApiLinks(data.tests, data.api_endpoints);
            }
            if (data.screens?.length && data.data_dictionary?.entities?.length) {
                applyScreenEntityLinks(data.screens, data.data_dictionary.entities);
            }
            // Phase 3: Complete all 24 link types
            if (data.personas?.length && data.user_stories?.length && data.screens?.length) {
                applyPersonaScreenLinks(data.personas, data.user_stories, data.screens);
            }
            if (data.ui_components?.length && data.screens?.length && data.api_endpoints?.length) {
                applyComponentApiLinks(data.ui_components, data.screens, data.api_endpoints);
            }
            if (data.api_endpoints?.length && data.data_dictionary?.entities?.length) {
                applyApiEntityLinks(data.api_endpoints, data.data_dictionary.entities);
            }
            if (data.diagrams?.length && data.data_dictionary?.entities?.length) {
                applyDiagramEntityLinks(data.diagrams, data.data_dictionary.entities);
            }
            if (data.features?.length) {
                applyRequirementFeatureLinks(data.features);
                if (data.user_stories?.length) {
                    applyFeatureStoryLinks(data.features, data.user_stories);
                }
            }
            if (data.tech_stack && data.ui_components?.length) {
                applyTechComponentLinks(data.tech_stack, data.ui_components);
            }
            applyMetadataLinks();
            updateConnections();
            // Update user stories to show linked tests as metadata
            updateLinkedTestsDisplay();
            // Build legend from active connections
            buildLegend();
            // Update orphan count badge after all auto-linkers finish
            updateOrphanCount(getOrphanCount());
        }, 200);

        log('success', `Loaded "${projectName}" with ${totalItems} items`);

        // Apply layout
        setTimeout(() => setLayoutMode('by_matrix'), 300);

        // Render package matrix
        setTimeout(() => renderPackageMatrix(), 500);

        // Start mermaid rendering
        console.log('[Project] Scheduling mermaid rendering in 1500ms...');
        setTimeout(() => {
            console.log('[Project] Triggering startMermaidRendering now');
            startMermaidRendering();
        }, 1500);

        // Fallback: Force re-render after 3 seconds if diagrams still show loading
        setTimeout(() => {
            const loadingDiagrams = document.querySelectorAll('.diagram-loading');
            if (loadingDiagrams.length > 0) {
                console.warn(`[Project] ${loadingDiagrams.length} diagrams still loading after 3s, forcing re-render`);
                reRenderAllDiagrams();
            }
        }, 3000);

        // Initialize chat buttons on all nodes
        setTimeout(() => initializeChatButtons(), 600);

        // Mark project as selected
        document.querySelectorAll('.project-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.projectId === projectId);
        });

    } catch (error) {
        console.error('Failed to load project:', error);
        log('error', `Failed to load project: ${error.message}`);
    }
}

// ============================================
// Dynamic Legend Builder
// ============================================

const LEGEND_LABELS = {
    'epic-story': 'Epic \u2192 User Story',
    'epic-req': 'Epic \u2192 Requirement',
    'req-story': 'Requirement \u2192 Story',
    'story-test': 'Story \u2192 Test',
    'req-diagram': 'Requirement \u2192 Diagram',
    'persona-story': 'Persona \u2192 Story',
    'persona-screen': 'Persona \u2192 Screen',
    'flow-screen': 'Flow \u2192 Screen',
    'screen-component': 'Screen \u2192 Component',
    'story-screen': 'Story \u2192 Screen',
    'feature-task': 'Feature \u2192 Task',
    'feature-story': 'Feature \u2192 Story',
    'req-api': 'Requirement \u2192 API',
    'api-screen': 'API \u2192 Screen',
    'comp-api': 'Component \u2192 API',
    'test-api': 'Test \u2192 API',
    'api-entity': 'API \u2192 Entity',
    'entity-api': 'Entity \u2192 API',
    'req-entity': 'Requirement \u2192 Entity',
    'screen-entity': 'Screen \u2192 Entity',
    'diagram-entity': 'Diagram \u2192 Entity',
    'tech-comp': 'Tech Stack \u2192 Component',
    'default': 'Andere Verbindung'
};

function buildLegend() {
    const container = document.getElementById('legend-items');
    if (!container) return;
    container.innerHTML = '';

    // Collect active connection types from rendered SVG paths
    const activePaths = document.querySelectorAll('.connection-path');
    const activeTypes = new Set();
    activePaths.forEach(path => {
        const marker = path.getAttribute('marker-end') || '';
        const match = marker.match(/arrow-([a-z-]+)/);
        if (match) activeTypes.add(match[1]);
    });

    // Build legend items for active types (excluding default)
    const sortedTypes = [...activeTypes].filter(t => t !== 'default').sort((a, b) => {
        const labelA = LEGEND_LABELS[a] || a;
        const labelB = LEGEND_LABELS[b] || b;
        return labelA.localeCompare(labelB);
    });

    sortedTypes.forEach(type => {
        const label = LEGEND_LABELS[type] || type;
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<span class="legend-line ${type}"></span><span>${label}</span>`;
        container.appendChild(item);
    });

    // Always add "Andere Verbindung" at end if default connections exist
    if (activeTypes.has('default')) {
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<span class="legend-line default"></span><span>Andere Verbindung</span>`;
        container.appendChild(item);
    }

    console.log(`[Legend] Built legend with ${sortedTypes.length} active link types`);
}

function clearCanvas() {
    // Clear mermaid queue first to prevent rendering orphaned diagrams
    clearMermaidQueue();

    elements.canvasNodes.innerHTML = '';
    state.nodes = {};
    state.connections = [];
    state.nodeCounters = {};
    elements.requirementsList.innerHTML = '';
    elements.userStoriesList.innerHTML = '';
    elements.epicsList.innerHTML = '';
    elements.testsList.innerHTML = '';
    elements.connectionsLayer.innerHTML = '';
    clearMinimap();
    updateCounts();
}

// ============================================
// Layout Management
// ============================================

function setLayoutMode(mode) {
    log('info', `Using Matrix layout`);

    // Only Matrix layout supported
    reorganizeNodesMatrix();

    // Update button states
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.layout === 'by_matrix');
    });

    // NOTE: renderPackageMatrix is called separately after data load (line 849)
    // Removed duplicate refreshPackageMatrix() call that caused double rendering

    setTimeout(() => fitToView(), 150);
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

        case 'node_created':
            if (data.type && data.id) {
                createNode(data.type, data.id, data);
                updateConnections();
                updateMinimap();
            }
            break;

        case 'connection_created':
            if (data.from && data.to) {
                addConnection(data.from, data.to, data.type);
                updateConnections();
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
            showNotification('Änderung angewendet', 'success');
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

        // Auto-Link Discovery Events
        case 'orphans_detected':
            updateOrphanCount(data.count);
            break;
        case 'link_suggestion':
            handleLinkSuggestion(data);
            break;
        case 'link_created':
            handleLinkCreated(data);
            break;
        case 'link_rejected':
            handleLinkRejected(data);
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
                // Better contrast for dark backgrounds
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
            securityLevel: 'strict',  // CRASH FIX #6: Disable JS callbacks in SVG to prevent post-render freeze
            suppressErrorRendering: false,  // Show errors instead of silent fail
            maxTextSize: 50000,  // Limit text size to prevent crashes
            maxEdges: 500,  // Limit edges to prevent complexity issues
            flowchart: { useMaxWidth: true, htmlLabels: false },  // CRASH FIX #7: Disable htmlLabels to prevent foreignObject issues
            sequence: { useMaxWidth: true, showSequenceNumbers: false },
            er: { useMaxWidth: true },
            c4: { useMaxWidth: true },  // Enable C4 diagram support
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
    // Verify critical elements exist
    if (!elements.canvasContainer) {
        console.error('[Init] canvasContainer is null - cannot setup panning');
        log('error', 'Canvas container not found - panning disabled');
        return;
    }
    if (!elements.canvas) {
        console.error('[Init] canvas is null - transform will fail');
        log('error', 'Canvas element not found');
    }
    console.log('[Init] Setting up event listeners on canvasContainer:', elements.canvasContainer);

    // Canvas panning - allow panning on any part of canvas area except nodes
    elements.canvasContainer.addEventListener('mousedown', (e) => {
        // Debug: Log all mousedown events
        console.log('[Pan] mousedown on:', e.target.tagName, e.target.id || e.target.className, 'button:', e.button);

        // Don't pan if clicking on a node or its children
        if (e.target.closest('.canvas-node')) {
            console.log('[Pan] Skipping - clicked on node');
            return;
        }
        // Don't pan if clicking on buttons or controls
        if (e.target.closest('button') || e.target.closest('.layout-btn')) {
            console.log('[Pan] Skipping - clicked on button');
            return;
        }
        // Allow panning on left mouse button for canvas area
        if (e.button === 0) {
            console.log('[Pan] Starting pan at:', e.clientX, e.clientY);
            state.panning.active = true;
            state.panning.startX = e.clientX;
            state.panning.startY = e.clientY;
            state.panning.canvasStartX = state.canvas.x;
            state.panning.canvasStartY = state.canvas.y;
            elements.canvas.style.cursor = 'grabbing';
        }
    });

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);

    // Zoom with wheel - zoom towards mouse position
    elements.canvasContainer.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        const rect = elements.canvasContainer.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        zoom(delta, mouseX, mouseY);
    }, { passive: false });

    // Layout buttons
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const layout = btn.dataset.layout;
            if (layout) setLayoutMode(layout);
        });
    });

    // Zoom buttons (HTML IDs: btn-zoom-in, btn-zoom-out, btn-fit)
    document.getElementById('btn-zoom-in')?.addEventListener('click', () => zoom(0.2));
    document.getElementById('btn-zoom-out')?.addEventListener('click', () => zoom(-0.2));
    document.getElementById('btn-fit')?.addEventListener('click', fitToView);

    // Project list clicks
    if (elements.projectList) {
        elements.projectList.addEventListener('click', (e) => {
            const projectItem = e.target.closest('.project-item');
            if (projectItem) loadProject(projectItem.dataset.projectId);
        });
    }
}

function initCanvas() {
    updateCanvasTransform();
}

// ============================================
// Module Setup
// ============================================

function setupModuleCallbacks() {
    // Setup nodeFactory callbacks
    setCreateNodeFunction(createNode);
    setSidebarCallback(addSidebarItem);

    // Setup sidebar callbacks
    setSidebarCallbacks({
        updateCanvasTransform,
        updateMinimap
    });

    // Setup detail panel callbacks
    setDetailPanelCallbacks({
        focusNode
    });

    // Setup layout callbacks
    const layoutCallbacks = {
        updateMinimap,
        reRenderAllDiagrams,
        fitToView,
        calculateNodePosition
    };

    setLayoutCallbacks(layoutCallbacks);
    setMatrixCallbacks(layoutCallbacks);

    // Setup connections layout config
    setLayoutConfig({
        currentLayout: currentLayout,
        LAYOUT_MODES
    });

    // Setup chat callbacks
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
    console.log('[Init] mermaid global available:', typeof mermaid !== 'undefined');

    initElements();
    console.log('[Init] Elements initialized:', {
        canvas: !!elements.canvas,
        canvasContainer: !!elements.canvasContainer,
        canvasNodes: !!elements.canvasNodes
    });

    setupModuleCallbacks();
    initCanvas();
    initMermaid();
    initWebSocket();
    initEventListeners();
    initEdgeNavigation(updateMinimap);  // Enable auto-pan when mouse reaches canvas edges
    loadProjectList();

    // Initialize change tracking and Kilo Agent integration
    initChangeTracker();
    initKiloBridge();

    // Initialize wizard tab
    initWizardTab();

    log('info', 'Dashboard initialized (modular architecture with change tracking)');
});

// ============================================
// Tab Switching (Canvas / Wizard / Pipeline)
// ============================================

function switchTab(tabName) {
    // Toggle tab buttons
    document.querySelectorAll('.header-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.tab === tabName)
    );

    // Canvas elements to toggle
    const canvasElements = [
        'canvas-container', 'log-panel', 'minimap',
        'connection-legend', 'layout-switcher', 'package-matrix-panel'
    ];
    const isCanvas = tabName === 'canvas';

    canvasElements.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = isCanvas ? '' : 'none';
    });

    const wizardContainer = document.getElementById('wizard-container');
    if (wizardContainer) wizardContainer.style.display = tabName === 'wizard' ? '' : 'none';

    const pipelineContainer = document.getElementById('pipeline-container');
    if (pipelineContainer) pipelineContainer.style.display = tabName === 'pipeline' ? '' : 'none';

    // Refresh pipeline data when switching to it
    if (tabName === 'pipeline') {
        refreshPipelineView();
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

    // Initialize wizard content
    const wizardContainer = document.getElementById('wizard-container');
    if (wizardContainer) {
        initWizard(wizardContainer);

        // Callback: when wizard completes, create nodes on canvas + start pipeline
        setOnAnalysisComplete(({ requirements, project, pipelineStarted }) => {
            let created = 0;
            requirements.forEach(req => {
                createRequirementFromArray(req);
                created++;
            });

            // Switch back to canvas
            switchTab('canvas');

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
    bar.innerHTML = `
        <span id="pipeline-project-label" style="color: #4fc3f7;">Pipeline</span>
        <div style="flex:1; height:6px; background:#333; border-radius:3px; overflow:hidden;">
            <div id="pipeline-fill" style="height:100%; width:0%; background:linear-gradient(90deg,#4fc3f7,#29b6f6);
                 border-radius:3px; transition:width 0.5s ease;"></div>
        </div>
        <span id="pipeline-step-text" style="min-width:140px;">Starting...</span>
        <span id="pipeline-cost-text" style="color: #aaa; min-width:80px;"></span>
        <button id="pipeline-stop-btn" style="background:#c62828; color:#fff; border:none;
                padding:4px 10px; border-radius:3px; cursor:pointer; font-size:12px;"
                onclick="window.stopPipeline()">Stop</button>
    `;
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

    log('info', `[Pipeline] Complete: ${total} project(s)${costStr}`);

    // Notify pipeline view tab to refresh manifest
    onPipelineComplete();

    // Auto-hide after 8s (longer for batch)
    setTimeout(() => {
        const bar = document.getElementById('pipeline-progress-bar');
        if (bar) bar.remove();
    }, total > 1 ? 10000 : 5000);

    // Reload project data if output_dir is available
    const outputDir = summary?.output_dir;
    if (outputDir) {
        log('info', `[Pipeline] Output: ${outputDir}`);
    }
}

function handlePipelineError(data) {
    const fill = document.getElementById('pipeline-fill');
    const text = document.getElementById('pipeline-step-text');
    const stopBtn = document.getElementById('pipeline-stop-btn');

    // If batch continues, just show warning — don't kill the progress bar
    if (data.continues) {
        showNotification(`Projekt-Fehler: ${data.error} — weiter mit nächstem`, 'warning');
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

window.setLayout = setLayoutMode;
window.setLayoutMode = setLayoutMode;
window.focusNode = focusNode;
window.hideDetailPanel = hideDetailPanel;
window.zoom = zoom;
window.fitToView = fitToView;

// Kilo Agent chat exports
window.openChatPanel = openChatPanel;
window.closeChatPanel = closeChatPanel;
window.sendKiloTask = sendKiloTask;

// Change tracking exports (for domino effect)
window.trackChange = trackChange;
window.CHANGE_TYPES = CHANGE_TYPES;

// Package Matrix toggle
window.togglePackageMatrix = togglePackageMatrix;

// Tab switching
window.switchTab = switchTab;

// Auto-Link Discovery exports
window.discoverLinks = discoverLinks;
window.approveLink = approveLink;
window.rejectLink = rejectLink;

// Modal system exports
window.openModal = openModal;
window.closeModal = closeModal;
window.openDiagramGallery = openDiagramGallery;
window.openTestCasesModal = openTestCasesModal;
window.openUserStoriesModal = openUserStoriesModal;
window.openTasksModal = openTasksModal;
window.openFullDiagram = openFullDiagram;

// Listen for focusNode events from modals
window.addEventListener('focusNode', (e) => {
    const { nodeId } = e.detail || {};
    if (nodeId) {
        focusNode(nodeId);
    }
});
