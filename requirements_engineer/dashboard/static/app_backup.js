/**
 * RE System - Endless Canvas Dashboard
 *
 * Features:
 * - Infinite canvas with pan and zoom
 * - Draggable nodes
 * - WebSocket real-time updates
 * - Mermaid diagram rendering
 * - Mini-map navigation
 *
 * Module Structure (ES6):
 * - modules/state.js      - State management, DOM refs, helpers
 * - modules/canvas.js     - Pan, zoom, edge navigation
 * - modules/connections.js - Connection rendering and routing
 * - modules/layouts/      - Layout algorithms (Phase 2)
 * - modules/ui/           - UI components (Phase 4)
 */

// ============================================
// State Management
// ============================================

const state = {
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
    connections: [],
    ws: null,
    connected: false,
    // Counter for each node type to prevent race conditions during rapid node creation
    nodeCounters: {}
};

// ============================================
// Helper Functions
// ============================================

/**
 * Get tag type for CSS class based on tag name
 */
function getTagType(tag) {
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
function highlightGherkin(code) {
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

// ============================================
// DOM References
// ============================================

const elements = {
    canvas: null,
    canvasContainer: null,
    canvasNodes: null,
    connectionsLayer: null,
    projectInfo: null,
    progressFill: null,
    progressText: null,
    zoomLevel: null,
    logContent: null,
    minimapContent: null,
    minimapViewport: null,
    connectionStatus: null,
    requirementsList: null,
    userStoriesList: null,
    epicsList: null,
    testsList: null,
    reqCount: null,
    usCount: null,
    epicCount: null,
    testCount: null,
    projectList: null
};

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initCanvas();
    initMermaid();
    initWebSocket();
    initEventListeners();
    loadProjectList();  // Load saved projects on startup

    // Event delegation for project list clicks (works with ES6 modules)
    if (elements.projectList) {
        elements.projectList.addEventListener('click', (e) => {
            const projectItem = e.target.closest('.project-item');
            if (projectItem) {
                const projectId = projectItem.dataset.projectId;
                loadProject(projectId);
            }
        });
    }

    log('info', 'Dashboard initialized. Waiting for connection...');
});

function initElements() {
    elements.canvas = document.getElementById('canvas');
    elements.canvasContainer = document.getElementById('canvas-container');
    elements.canvasNodes = document.getElementById('canvas-nodes');
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
    elements.reqCount = document.getElementById('req-count');
    elements.usCount = document.getElementById('us-count');
    elements.epicCount = document.getElementById('epic-count');
    elements.testCount = document.getElementById('test-count');
    elements.projectList = document.getElementById('project-list');
}

function initCanvas() {
    // Center canvas initially - start at the node area (baseX=3000, baseY=3000)
    const containerRect = elements.canvasContainer.getBoundingClientRect();
    state.canvas.x = -3000 + containerRect.width / 2;
    state.canvas.y = -3000 + containerRect.height / 2;
    updateCanvasTransform();
}

function initMermaid() {
    mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',  // Allow more diagram features
        themeVariables: {
            primaryColor: '#1e3a5f',
            primaryTextColor: '#e7e9ea',
            primaryBorderColor: '#3d4349',
            lineColor: '#536471',
            secondaryColor: '#242b33',
            tertiaryColor: '#1a1f26',
            background: 'transparent'
        },
        flowchart: {
            curve: 'basis',
            htmlLabels: true
        },
        sequence: {
            diagramMarginX: 10,
            diagramMarginY: 10,
            actorMargin: 50,
            width: 150,
            height: 65,
            boxMargin: 10,
            boxTextMargin: 5,
            noteMargin: 10,
            messageMargin: 35,
            mirrorActors: true,
            useMaxWidth: true
        },
        er: {
            useMaxWidth: true
        },
        class: {
            useMaxWidth: true
        },
        c4: {
            useMaxWidth: true
        }
    });
}

// WebSocket reconnection state
let wsReconnectTimeout = null;
let wsReconnectAttempts = 0;
const WS_MAX_RECONNECT_ATTEMPTS = 10;

function initWebSocket() {
    // Clear any pending reconnect
    if (wsReconnectTimeout) {
        clearTimeout(wsReconnectTimeout);
        wsReconnectTimeout = null;
    }

    // Check for max attempts
    if (wsReconnectAttempts >= WS_MAX_RECONNECT_ATTEMPTS) {
        log('error', 'Max reconnection attempts reached. Please refresh the page.');
        return;
    }

    // Close existing connection if any
    if (state.ws && state.ws.readyState !== WebSocket.CLOSED) {
        state.ws.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
        state.ws = new WebSocket(wsUrl);

        state.ws.onopen = () => {
            state.connected = true;
            wsReconnectAttempts = 0; // Reset on successful connection
            updateConnectionStatus(true);
            log('success', 'Connected to RE System');
        };

        state.ws.onclose = () => {
            state.connected = false;
            updateConnectionStatus(false);
            wsReconnectAttempts++;
            // Exponential backoff: 3s, 4.5s, 6.75s, ... up to 30s max
            const delay = Math.min(3000 * Math.pow(1.5, wsReconnectAttempts - 1), 30000);
            log('warn', `Disconnected. Reconnecting in ${Math.round(delay/1000)}s (attempt ${wsReconnectAttempts}/${WS_MAX_RECONNECT_ATTEMPTS})...`);
            wsReconnectTimeout = setTimeout(initWebSocket, delay);
        };

        state.ws.onerror = (error) => {
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
    } catch (e) {
        log('warn', 'Could not connect to WebSocket. Running in offline mode.');
    }
}

function initEventListeners() {
    // Canvas panning
    elements.canvasContainer.addEventListener('mousedown', onCanvasMouseDown);
    document.addEventListener('mousemove', onCanvasMouseMove);
    document.addEventListener('mouseup', onCanvasMouseUp);

    // Canvas zooming
    elements.canvasContainer.addEventListener('wheel', onCanvasWheel);

    // Zoom buttons
    document.getElementById('btn-zoom-in').addEventListener('click', () => zoom(0.2));
    document.getElementById('btn-zoom-out').addEventListener('click', () => zoom(-0.2));
    document.getElementById('btn-reset').addEventListener('click', resetView);
    document.getElementById('btn-fit').addEventListener('click', fitToView);

    // Log toggle
    document.getElementById('btn-toggle-log').addEventListener('click', toggleLog);

    // Project browser refresh
    const refreshBtn = document.getElementById('btn-refresh-projects');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadProjectList);
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', onKeyDown);

    // Edge-based navigation (auto-pan when mouse is at screen edges)
    initEdgeNavigation();
}

// ============================================
// Edge-Based Navigation
// ============================================

let edgeNavState = {
    active: false,
    direction: { x: 0, y: 0 },
    animationId: null
};

function initEdgeNavigation() {
    const edgeThreshold = 60;  // Pixels from edge to trigger panning
    const panSpeed = 15;       // Pixels per frame

    document.addEventListener('mousemove', (e) => {
        // Only active when not dragging a node
        if (state.dragging.active) {
            stopEdgePan();
            return;
        }

        const rect = elements.canvasContainer.getBoundingClientRect();
        const x = e.clientX;
        const y = e.clientY;

        // Check if mouse is within canvas container bounds
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            stopEdgePan();
            return;
        }

        // Calculate direction based on edge proximity
        let dirX = 0, dirY = 0;

        // Left edge
        if (x - rect.left < edgeThreshold) {
            dirX = panSpeed * (1 - (x - rect.left) / edgeThreshold);
        }
        // Right edge
        else if (rect.right - x < edgeThreshold) {
            dirX = -panSpeed * (1 - (rect.right - x) / edgeThreshold);
        }

        // Top edge
        if (y - rect.top < edgeThreshold) {
            dirY = panSpeed * (1 - (y - rect.top) / edgeThreshold);
        }
        // Bottom edge
        else if (rect.bottom - y < edgeThreshold) {
            dirY = -panSpeed * (1 - (rect.bottom - y) / edgeThreshold);
        }

        if (dirX !== 0 || dirY !== 0) {
            edgeNavState.direction = { x: dirX, y: dirY };
            if (!edgeNavState.active) {
                startEdgePan();
            }
        } else {
            stopEdgePan();
        }
    });

    // Stop panning when mouse leaves window
    document.addEventListener('mouseleave', stopEdgePan);
}

function startEdgePan() {
    if (edgeNavState.active) return;
    edgeNavState.active = true;

    function panFrame() {
        if (!edgeNavState.active) return;

        state.canvas.x += edgeNavState.direction.x;
        state.canvas.y += edgeNavState.direction.y;
        updateCanvasTransform();
        updateMinimap();

        edgeNavState.animationId = requestAnimationFrame(panFrame);
    }

    edgeNavState.animationId = requestAnimationFrame(panFrame);
}

function stopEdgePan() {
    edgeNavState.active = false;
    edgeNavState.direction = { x: 0, y: 0 };
    if (edgeNavState.animationId) {
        cancelAnimationFrame(edgeNavState.animationId);
        edgeNavState.animationId = null;
    }
}

// ============================================
// Canvas Pan & Zoom
// ============================================

function onCanvasMouseDown(e) {
    if (e.target === elements.canvasContainer || e.target.id === 'canvas-grid') {
        state.panning.active = true;
        state.panning.startX = e.clientX;
        state.panning.startY = e.clientY;
        state.panning.canvasStartX = state.canvas.x;
        state.panning.canvasStartY = state.canvas.y;
        elements.canvas.style.cursor = 'grabbing';
    }
}

function onCanvasMouseMove(e) {
    if (state.panning.active) {
        const dx = e.clientX - state.panning.startX;
        const dy = e.clientY - state.panning.startY;
        state.canvas.x = state.panning.canvasStartX + dx;
        state.canvas.y = state.panning.canvasStartY + dy;
        updateCanvasTransform();
        updateMinimap();
    }

    if (state.dragging.active && state.dragging.node) {
        const dx = (e.clientX - state.dragging.startX) / state.canvas.zoom;
        const dy = (e.clientY - state.dragging.startY) / state.canvas.zoom;
        const newX = state.dragging.nodeStartX + dx;
        const newY = state.dragging.nodeStartY + dy;

        state.dragging.node.style.left = `${newX}px`;
        state.dragging.node.style.top = `${newY}px`;

        updateConnections();
    }
}

function onCanvasMouseUp(e) {
    if (state.panning.active) {
        state.panning.active = false;
        elements.canvas.style.cursor = 'grab';
    }

    if (state.dragging.active && state.dragging.node) {
        state.dragging.node.classList.remove('dragging');

        // Update node position in state
        const nodeId = state.dragging.node.dataset.nodeId;
        const x = parseFloat(state.dragging.node.style.left);
        const y = parseFloat(state.dragging.node.style.top);

        if (state.nodes[nodeId]) {
            state.nodes[nodeId].x = x;
            state.nodes[nodeId].y = y;
        }

        // Send position update to server
        sendMessage({
            type: 'update_node_position',
            node_id: nodeId,
            x: x,
            y: y
        });

        state.dragging.active = false;
        state.dragging.node = null;
    }
}

function onCanvasWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;

    // Zoom towards cursor
    const rect = elements.canvasContainer.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    zoomTowards(delta, mouseX, mouseY);
}

function zoom(delta) {
    const rect = elements.canvasContainer.getBoundingClientRect();
    zoomTowards(delta, rect.width / 2, rect.height / 2);
}

function zoomTowards(delta, targetX, targetY) {
    const oldZoom = state.canvas.zoom;
    const newZoom = Math.min(state.canvas.maxZoom, Math.max(state.canvas.minZoom, oldZoom + delta));

    if (newZoom !== oldZoom) {
        // Adjust position to zoom towards target point
        const worldX = (targetX - state.canvas.x) / oldZoom;
        const worldY = (targetY - state.canvas.y) / oldZoom;

        state.canvas.zoom = newZoom;
        state.canvas.x = targetX - worldX * newZoom;
        state.canvas.y = targetY - worldY * newZoom;

        updateCanvasTransform();
        updateMinimap();
    }
}

function updateCanvasTransform() {
    elements.canvas.style.transform = `translate(${state.canvas.x}px, ${state.canvas.y}px) scale(${state.canvas.zoom})`;
    elements.zoomLevel.textContent = `${Math.round(state.canvas.zoom * 100)}%`;
}

function resetView() {
    state.canvas.zoom = 0.8;  // Start slightly zoomed out to see more
    const containerRect = elements.canvasContainer.getBoundingClientRect();
    state.canvas.x = -3000 + containerRect.width / 2;
    state.canvas.y = -3000 + containerRect.height / 2;
    updateCanvasTransform();
    updateMinimap();
}

function fitToView() {
    const nodeElements = elements.canvasNodes.querySelectorAll('.canvas-node');
    if (nodeElements.length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    nodeElements.forEach(node => {
        const x = parseFloat(node.style.left) || 0;
        const y = parseFloat(node.style.top) || 0;
        const w = node.offsetWidth;
        const h = node.offsetHeight;

        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x + w);
        maxY = Math.max(maxY, y + h);
    });

    const padding = 100;
    const contentWidth = maxX - minX + padding * 2;
    const contentHeight = maxY - minY + padding * 2;

    const containerRect = elements.canvasContainer.getBoundingClientRect();
    const zoomX = containerRect.width / contentWidth;
    const zoomY = containerRect.height / contentHeight;

    state.canvas.zoom = Math.min(1.5, Math.max(0.2, Math.min(zoomX, zoomY)));
    state.canvas.x = -minX * state.canvas.zoom + padding * state.canvas.zoom + (containerRect.width - contentWidth * state.canvas.zoom) / 2;
    state.canvas.y = -minY * state.canvas.zoom + padding * state.canvas.zoom + (containerRect.height - contentHeight * state.canvas.zoom) / 2;

    updateCanvasTransform();
    updateMinimap();
}

// ============================================
// Node Management
// ============================================

function createNode(type, id, data) {
    const template = document.getElementById(`template-${type}`);
    if (!template) {
        console.error(`No template found for type: ${type}`);
        return null;
    }

    const node = template.content.cloneNode(true).firstElementChild;
    node.dataset.nodeId = id;
    node.dataset.nodeType = type;

    // Position node
    const position = calculateNodePosition(type, id);
    node.style.left = `${position.x}px`;
    node.style.top = `${position.y}px`;

    // Fill content based on type
    switch (type) {
        case 'requirement':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            node.querySelector('.node-type').textContent = data.type || 'functional';
            const priorityEl = node.querySelector('.node-priority');
            priorityEl.textContent = data.priority || 'should';
            priorityEl.classList.add(data.priority || 'should');
            break;

        case 'user-story':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            node.querySelector('.node-persona').textContent = `As a ${data.persona || 'user'}`;
            break;

        case 'epic':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.title || 'Untitled';
            node.querySelector('.node-count').textContent = `${(data.requirements || []).length} requirements`;
            break;

        case 'diagram':
            const diagramTypeEl = node.querySelector('.node-type');
            const diagramType = data.diagram_type || 'Diagram';
            diagramTypeEl.textContent = diagramType;
            const mermaidContent = node.querySelector('.node-diagram-content');
            mermaidContent.id = `mermaid-${id}`;
            // Show loading indicator with diagram type
            mermaidContent.innerHTML = `<div class="diagram-loading">⏳ Loading ${diagramType}...</div>`;
            break;

        case 'test':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.title || 'Untitled';

            // Scenario Count
            const scenarioCount = data.scenario_count || 0;
            const scenarioEl = node.querySelector('.node-scenario-count');
            if (scenarioEl) {
                scenarioEl.textContent = `${scenarioCount} ${scenarioCount === 1 ? 'Scenario' : 'Scenarios'}`;
            }

            // Tags als Badges
            const tagsContainer = node.querySelector('.node-tags');
            if (tagsContainer && data.tags && data.tags.length > 0) {
                data.tags.slice(0, 3).forEach(tag => {  // Max 3 Tags im Node
                    const badge = document.createElement('span');
                    badge.className = `tag-badge tag-${getTagType(tag)}`;
                    badge.textContent = tag;
                    tagsContainer.appendChild(badge);
                });
            }
            break;

        case 'api':
            const methodEl = node.querySelector('.node-method');
            methodEl.textContent = data.method || 'GET';
            methodEl.classList.add((data.method || 'get').toLowerCase());
            node.querySelector('.node-path').textContent = data.path || '/api';
            break;

        // ========== NEW NODE TYPES ==========

        case 'tech-stack':
            node.querySelector('.node-title').textContent = data.project_name || 'Tech Stack';
            node.querySelector('.tech-frontend').textContent = `Frontend: ${data.frontend_framework || 'N/A'}`;
            node.querySelector('.tech-backend').textContent = `Backend: ${data.backend_framework || 'N/A'}`;
            node.querySelector('.tech-db').textContent = `DB: ${data.primary_database || 'N/A'}`;

            // Deploy info: cloud + orchestration + deployment_strategy
            const deployEl = node.querySelector('.tech-deploy');
            if (deployEl) {
                const deployParts = [
                    data.cloud_provider,
                    data.orchestration,
                    data.deployment_strategy || data.deployment_model
                ].filter(Boolean);
                deployEl.textContent = deployParts.length > 0
                    ? `Deploy: ${deployParts.join(' / ')}`
                    : '';
            }

            // Monitor info: monitoring + logging + ci_cd
            const monitorEl = node.querySelector('.tech-monitor');
            if (monitorEl) {
                const monitorParts = [
                    data.monitoring_solution,
                    data.logging_solution,
                    data.ci_cd
                ].filter(Boolean);
                monitorEl.textContent = monitorParts.length > 0
                    ? `Ops: ${monitorParts.join(' / ')}`
                    : (data.ci_cd ? `CI/CD: ${data.ci_cd}` : '');
            }
            break;

        case 'persona':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.name || 'Persona';
            node.querySelector('.node-role').textContent = data.role || '';
            break;

        case 'user-flow':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.name || 'Flow';
            node.querySelector('.node-steps').textContent = `${(data.steps || []).length} steps`;
            // Add mermaid diagram if available
            const flowDiagram = node.querySelector('.node-flow-diagram');
            if (flowDiagram && data.mermaid_code) {
                flowDiagram.id = `mermaid-${id}`;  // Use standard ID pattern for rendering
                flowDiagram.innerHTML = '<div class="diagram-loading">⏳ Rendering...</div>';
            }
            break;

        case 'component':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.name || 'Component';
            node.querySelector('.node-comp-type').textContent = data.component_type || '';
            break;

        case 'screen':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.name || 'Screen';
            node.querySelector('.node-route').textContent = data.route || '';
            break;

        case 'task':
            node.querySelector('.node-id').textContent = id;
            node.querySelector('.node-title').textContent = data.title || 'Task';
            node.querySelector('.node-estimate').textContent = `${data.estimated_hours || 0}h / ${data.story_points || 0}pts`;
            break;
    }

    // Add drag handlers
    node.addEventListener('mousedown', onNodeMouseDown);

    // Add click handler for detail panel
    node.addEventListener('click', (e) => {
        // Don't show panel if dragging was active
        if (!state.dragging.active) {
            setTimeout(() => {
                const nodeData = state.nodes[id];
                if (nodeData) {
                    showDetailPanel(id, nodeData);
                }
            }, 50);
        }
    });

    // Add to canvas
    elements.canvasNodes.appendChild(node);

    // Store in state
    state.nodes[id] = {
        type,
        x: position.x,
        y: position.y,
        data,
        element: node
    };

    // Queue mermaid for lazy rendering (don't render immediately)
    // Include diagram nodes and user-flow nodes (which also have mermaid diagrams)
    if ((type === 'diagram' || type === 'user-flow') && data.mermaid_code) {
        queueMermaidRender(id, data.mermaid_code);
    }

    updateMinimap();
    return node;
}

// ============================================
// Lazy Mermaid Rendering with Batch Loading
// ============================================

const mermaidRenderQueue = [];
let mermaidRenderInProgress = false;
let mermaidRenderEnabled = false;  // Disabled by default until layout is complete

// Batch loading configuration
const MERMAID_BATCH_SIZE = 5;        // Render 5 diagrams per batch
const MERMAID_BATCH_DELAY_MS = 150;  // 150ms pause between batches
let mermaidBatchCount = 0;
let mermaidTotalCount = 0;

/**
 * Queue a diagram for rendering
 */
function queueMermaidRender(id, code) {
    mermaidRenderQueue.push({ id, code });

    // If rendering is enabled, start processing
    if (mermaidRenderEnabled && !mermaidRenderInProgress) {
        processMermaidBatch();
    }
}

/**
 * Start rendering all queued diagrams
 * Call this after layout is complete
 */
function startMermaidRendering() {
    mermaidTotalCount = mermaidRenderQueue.length;
    mermaidBatchCount = 0;
    console.log(`[Mermaid] Starting batch rendering of ${mermaidTotalCount} diagrams (batch size: ${MERMAID_BATCH_SIZE})...`);
    mermaidRenderEnabled = true;

    if (!mermaidRenderInProgress && mermaidRenderQueue.length > 0) {
        processMermaidBatch();
    }
}

/**
 * Re-queue and re-render all diagrams
 * Call this when switching layouts to ensure diagrams are rendered
 * (The queue may be empty from initial load if diagrams were already processed)
 */
let reRenderPending = false;
let reRenderTimeout = null;

function reRenderAllDiagrams() {
    // Debounce: If multiple calls come in rapid succession, only execute once
    if (reRenderTimeout) {
        clearTimeout(reRenderTimeout);
    }

    reRenderTimeout = setTimeout(() => {
        reRenderTimeout = null;

        // Clear the existing queue to avoid duplicates
        mermaidRenderQueue.length = 0;
        mermaidRenderEnabled = false;
        mermaidRenderInProgress = false;

        // Re-queue all diagrams that have mermaid_code (including user-flow nodes)
        let requeued = 0;
        Object.entries(state.nodes).forEach(([id, node]) => {
            if ((node.type === 'diagram' || node.type === 'user-flow') && node.data?.mermaid_code) {
                queueMermaidRender(id, node.data.mermaid_code);
                requeued++;
            }
        });

        console.log(`[Mermaid] Re-queued ${requeued} diagrams for layout rendering`);
        startMermaidRendering();
    }, 100);  // 100ms debounce
}

/**
 * Process the next diagram in the queue (legacy single-item processing)
 */
async function processNextMermaid() {
    if (!mermaidRenderEnabled || mermaidRenderQueue.length === 0) {
        mermaidRenderInProgress = false;
        console.log('[Mermaid] Rendering complete');
        return;
    }

    mermaidRenderInProgress = true;
    const { id, code } = mermaidRenderQueue.shift();

    try {
        await renderMermaid(id, code);
    } catch (e) {
        console.warn(`[Mermaid] Error rendering ${id}:`, e);
    }

    // Process next with a small delay to keep UI responsive
    setTimeout(processNextMermaid, 50);
}

/**
 * Process a batch of diagrams from the queue
 * Renders MERMAID_BATCH_SIZE diagrams in parallel, then pauses before next batch
 */
async function processMermaidBatch() {
    if (!mermaidRenderEnabled || mermaidRenderQueue.length === 0) {
        mermaidRenderInProgress = false;
        const batchesProcessed = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE);
        console.log(`[Mermaid] Batch rendering complete: ${mermaidBatchCount}/${mermaidTotalCount} diagrams in ${batchesProcessed} batches`);
        return;
    }

    mermaidRenderInProgress = true;

    // Take up to MERMAID_BATCH_SIZE items from the queue
    const batch = [];
    while (batch.length < MERMAID_BATCH_SIZE && mermaidRenderQueue.length > 0) {
        batch.push(mermaidRenderQueue.shift());
    }

    const batchNum = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE) + 1;
    const remaining = mermaidRenderQueue.length;
    console.log(`[Mermaid] Processing batch ${batchNum}: ${batch.length} diagrams (${remaining} remaining)`);

    // Render all items in this batch in parallel
    const renderPromises = batch.map(async ({ id, code }) => {
        try {
            await renderMermaid(id, code);
            mermaidBatchCount++;
        } catch (e) {
            console.warn(`[Mermaid] Error rendering ${id}:`, e);
            mermaidBatchCount++;  // Count failed renders too
        }
    });

    // Wait for all renders in this batch to complete
    await Promise.all(renderPromises);

    // If more diagrams remain, schedule next batch with delay
    if (mermaidRenderQueue.length > 0) {
        // Pause between batches to let UI breathe
        setTimeout(processMermaidBatch, MERMAID_BATCH_DELAY_MS);
    } else {
        // All done
        mermaidRenderInProgress = false;
        const batchesProcessed = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE);
        console.log(`[Mermaid] Batch rendering complete: ${mermaidBatchCount}/${mermaidTotalCount} diagrams in ${batchesProcessed} batches`);
    }
}

function calculateNodePosition(type, id) {
    // Auto-layout: organize by type in columns with grid wrapping
    const baseX = 3000;  // Start further left
    const baseY = 3000;  // Start further up

    // Use larger spacing for diagram nodes (they contain Mermaid SVGs)
    const isDiagram = type === 'diagram';
    const columnWidth = isDiagram ? 450 : 500;  // Diagrams need more horizontal space
    const rowHeight = isDiagram ? 400 : 180;    // Diagrams need much more vertical space
    const nodesPerRow = isDiagram ? 3 : 5;      // Fewer diagrams per row

    const typeColumns = {
        'requirement': 0,
        'epic': 1,
        'user-story': 2,
        'persona': 3,        // NEW
        'user-flow': 4,      // NEW
        'screen': 5,         // NEW
        'component': 6,      // NEW
        'diagram': 7,
        'test': 8,
        'api': 9,
        'entity': 10,
        'feature': 11,
        'task': 12,          // NEW
        'tech-stack': 13     // NEW
    };

    const column = typeColumns[type] || 0;

    // FIX: Use counter instead of counting state.nodes to prevent race condition
    // Initialize counter for this type if not exists
    if (state.nodeCounters[type] === undefined) {
        state.nodeCounters[type] = 0;
    }
    // Get current count and increment IMMEDIATELY to prevent duplicates
    const nodesOfType = state.nodeCounters[type]++;

    // Calculate grid position within the type's area
    const gridRow = Math.floor(nodesOfType / nodesPerRow);
    const gridCol = nodesOfType % nodesPerRow;

    // Each type gets its own horizontal section
    // Types are arranged in 2 rows: [req, epic, story] and [diagram, test, api, entity, feature]
    const typeRow = column < 3 ? 0 : 1;
    const typeColInRow = column < 3 ? column : column - 3;

    // Calculate position with wider spacing - diagrams get more space
    const sectionWidth = isDiagram ? 2500 : 2000;  // Diagrams section is wider
    const sectionHeight = isDiagram ? 2500 : 1500; // Diagrams section is taller

    return {
        x: baseX + (typeColInRow * sectionWidth) + (gridCol * columnWidth),
        y: baseY + (typeRow * sectionHeight) + (gridRow * rowHeight)
    };
}

function onNodeMouseDown(e) {
    if (e.target.classList.contains('connector')) return;

    const node = e.currentTarget;
    node.classList.add('dragging');

    state.dragging.active = true;
    state.dragging.node = node;
    state.dragging.startX = e.clientX;
    state.dragging.startY = e.clientY;
    state.dragging.nodeStartX = parseFloat(node.style.left) || 0;
    state.dragging.nodeStartY = parseFloat(node.style.top) || 0;

    e.stopPropagation();
}

/**
 * Sanitize Mermaid code to fix common syntax errors.
 * Fixes missing closing braces in classDiagram and erDiagram.
 * Fixes state diagram 'as' keyword issues.
 * Fixes sequence diagram multi-line messages.
 */
function sanitizeMermaidCode(code) {
    if (!code) return code;

    const trimmed = code.trim();
    if (!trimmed) return code;

    // Detect diagram type (case-insensitive for robustness)
    const firstLine = trimmed.split('\n')[0];
    const firstLineLower = firstLine.toLowerCase();

    // Class diagrams - add missing closing braces
    if (firstLineLower.startsWith('classdiagram')) {
        return fixClassDiagram(code);
    }

    // ER diagrams - add missing closing braces
    if (firstLineLower.startsWith('erdiagram')) {
        return fixERDiagram(code);
    }

    // State diagrams - remove problematic "state X as Y" lines (keep other lines)
    if (firstLineLower.startsWith('statediagram')) {
        const lines = code.split('\n');
        const filtered = lines.filter(line => !line.match(/^\s*state\s+\w+\s+as\s+/));
        // Only return filtered if we didn't remove everything
        if (filtered.length > 1) {
            return filtered.join('\n');
        }
        return code;  // Return original if filtering would empty it
    }

    // Flowchart diagrams - escape parentheses inside node labels
    if (firstLineLower.startsWith('flowchart')) {
        return fixFlowchartDiagram(code);
    }

    // All other diagram types (sequence, C4, etc.) - pass through as-is
    return code;
}

/**
 * Fix class diagrams by adding missing closing braces before new class definitions
 * or relationship lines.
 */
function fixClassDiagram(code) {
    const lines = code.split('\n');
    const result = [];
    let inClassBlock = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();

        // Check if this line starts a new class definition
        const isClassStart = /^class\s+\w+/.test(trimmedLine);

        // Check if this line is a relationship (outside class block)
        // Relationships have arrows like -->, --|>, ..|>, etc.
        const isRelationship = /^\w+\s*(--|\.\.|\*--|o--|<\||>\|)/.test(trimmedLine) ||
                               /^\w+\s*:\s*/.test(trimmedLine);

        // If we're in a class block and encounter a new class or relationship
        if (inClassBlock && (isClassStart || isRelationship)) {
            result.push('    }');
            inClassBlock = false;
        }

        result.push(line);

        // If this line starts a class block (has { but no })
        if (isClassStart) {
            const hasOpenBrace = line.includes('{');
            const hasCloseBrace = line.includes('}');
            if (hasOpenBrace && !hasCloseBrace) {
                inClassBlock = true;
            }
        }
    }

    // Close any remaining open block
    if (inClassBlock) {
        result.push('    }');
    }

    return result.join('\n');
}

/**
 * Fix ER diagrams by adding missing closing braces before new entity definitions
 * or relationship lines.
 */
function fixERDiagram(code) {
    const lines = code.split('\n');
    const result = [];
    let inEntityBlock = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();

        // Check if this line starts a new entity definition
        // Pattern: ENTITY_NAME { (entity names are typically UPPERCASE)
        const isEntityStart = /^[A-Z][A-Z0-9_]*\s*\{/.test(trimmedLine);

        // Check if this line is a relationship
        // Pattern: ENTITY ||--o{ OTHER_ENTITY : label
        // Contains cardinality symbols: ||, |o, o|, }|, |{, etc.
        const isRelationship = /^[A-Z][A-Z0-9_]*\s*(\|\||\|o|o\||\}\||\|\{|\{o|o\{|\}\{)/.test(trimmedLine);

        // If we're in an entity block and encounter a new entity or relationship
        if (inEntityBlock && (isEntityStart || isRelationship)) {
            result.push('    }');
            inEntityBlock = false;
        }

        result.push(line);

        // If this line starts an entity block (has { but no })
        if (isEntityStart) {
            const hasOpenBrace = line.includes('{');
            const hasCloseBrace = line.includes('}');
            // Only mark as in block if we see { without corresponding }
            // Also check it's not a cardinality brace like }|
            if (hasOpenBrace && !hasCloseBrace && !isRelationship) {
                inEntityBlock = true;
            }
        }
    }

    // Close any remaining open block
    if (inEntityBlock) {
        result.push('    }');
    }

    return result.join('\n');
}

/**
 * Fix flowchart diagrams by escaping parentheses inside node labels.
 * Mermaid uses () for stadium-shaped nodes, so parentheses in text
 * like [Mahnstufe bestimmen(DunningLevelCalculator)] cause parse errors.
 * We replace them with fullwidth parentheses which render similarly but don't break parsing.
 */
function fixFlowchartDiagram(code) {
    const lines = code.split('\n');
    const result = [];

    for (const line of lines) {
        let fixedLine = line;

        // Match node definitions with square brackets: ID[text] or after arrow like --> B[text]
        // The key is to find [...] content and escape parentheses inside
        fixedLine = fixedLine.replace(/(\w+)\[([^\]]+)\]/g, (match, nodeId, content) => {
            // Only fix if content has parentheses
            if (!content.includes('(') && !content.includes(')')) {
                return match;
            }
            // Replace parentheses with fullwidth versions inside the label
            const fixedContent = content
                .replace(/\(/g, '（')  // Fullwidth left parenthesis U+FF08
                .replace(/\)/g, '）'); // Fullwidth right parenthesis U+FF09
            return `${nodeId}[${fixedContent}]`;
        });

        // Also handle curly brace nodes: ID{text}
        fixedLine = fixedLine.replace(/(\w+)\{([^}]+)\}/g, (match, nodeId, content) => {
            if (!content.includes('(') && !content.includes(')')) {
                return match;
            }
            const fixedContent = content
                .replace(/\(/g, '（')
                .replace(/\)/g, '）');
            return `${nodeId}{${fixedContent}}`;
        });

        // Note: Stadium nodes ID(text) are left as-is to avoid breaking shape syntax
        // If nested parens cause issues, they need manual fixing in the source data

        result.push(fixedLine);
    }

    return result.join('\n');
}

async function renderMermaid(id, code) {
    const element = document.getElementById(`mermaid-${id}`);
    if (!element) {
        console.warn(`[Mermaid] Element not found for: mermaid-${id}`);
        return;
    }

    // Check for empty code
    if (!code || !code.trim()) {
        console.warn(`[Mermaid] Empty code for: ${id}`);
        element.innerHTML = '<div class="diagram-loading">No diagram code</div>';
        return;
    }

    // Detect diagram type for logging
    const diagramType = code.trim().split('\n')[0].split(/\s/)[0];
    console.log(`[Mermaid] Rendering ${diagramType} diagram: ${id}`);

    // Sanitize the code to fix common syntax errors
    const sanitizedCode = sanitizeMermaidCode(code);

    // Generate unique SVG ID to avoid conflicts
    const svgId = `mermaid-svg-${id}-${Date.now()}`;

    try {
        // Clean up any existing temporary Mermaid elements with similar IDs
        const existingTempElement = document.getElementById(svgId);
        if (existingTempElement) {
            existingTempElement.remove();
        }

        const { svg } = await mermaid.render(svgId, sanitizedCode);
        element.innerHTML = svg;
        console.log(`[Mermaid] Successfully rendered: ${id}`);

        // Clean up the temporary element Mermaid creates
        const tempElement = document.getElementById(svgId);
        if (tempElement && tempElement !== element) {
            tempElement.remove();
        }
    } catch (error) {
        // Show original code in error for debugging
        console.warn(`[Mermaid] Error rendering ${id}:`, error.message);
        console.warn(`[Mermaid] Sanitized code:\n${sanitizedCode.substring(0, 500)}...`);

        // Show a user-friendly error with CSS class for proper styling
        const shortError = error.message.length > 80 ? error.message.substring(0, 80) + '...' : error.message;
        element.innerHTML = `
            <div class="diagram-error">
                <span>⚠️ ${shortError}</span>
            </div>
        `;
    }
}

// ============================================
// Connections
// ============================================

function addConnection(fromId, toId, relationType = 'default') {
    // Prevent duplicate connections
    const exists = state.connections.some(c => c.from === fromId && c.to === toId);
    if (exists) {
        console.log(`[Link] Duplicate skipped: ${fromId} -> ${toId}`);
        return;
    }

    // Debug: Log connection creation with node types
    const fromNode = state.nodes[fromId];
    const toNode = state.nodes[toId];
    const fromType = fromNode?.type || 'MISSING';
    const toType = toNode?.type || 'MISSING';
    console.log(`[Link] Created: ${fromId}(${fromType}) -> ${toId}(${toType}) [${relationType}]`);

    if (!fromNode) console.warn(`[Link] WARNING: Source node not found: ${fromId}`);
    if (!toNode) console.warn(`[Link] WARNING: Target node not found: ${toId}`);

    state.connections.push({ from: fromId, to: toId, type: relationType });
    // Don't update immediately - batch updates
}

// Batched connection update system for performance
let connectionUpdateScheduled = false;
let connectionUpdateTimeout = null;

/**
 * Schedule a batched connection update using requestAnimationFrame.
 * Multiple calls within the same frame will be coalesced into one update.
 */
function scheduleConnectionUpdate() {
    if (connectionUpdateScheduled) return;
    connectionUpdateScheduled = true;

    requestAnimationFrame(() => {
        updateConnectionsInternal();
        connectionUpdateScheduled = false;
    });
}

/**
 * Debounced version for rapid updates (e.g., during drag).
 * Waits 16ms (~60fps) before updating.
 */
function scheduleConnectionUpdateDebounced() {
    if (connectionUpdateTimeout) {
        clearTimeout(connectionUpdateTimeout);
    }
    connectionUpdateTimeout = setTimeout(() => {
        updateConnectionsInternal();
        connectionUpdateTimeout = null;
    }, 16);
}

function updateConnections() {
    // For immediate updates (e.g., after layout change), call internal directly
    updateConnectionsInternal();
}

/**
 * Route an orthogonal path from start to end.
 * For tree layouts: simple L-shaped paths (horizontal then vertical)
 * For other layouts: Z-paths through channels
 */
function routeOrthogonalPath(startX, startY, endX, endY, fromBounds, toBounds, nodeBounds, fromId, toId, offset) {
    const margin = 20; // Padding around nodes
    const channelOffset = offset || 0;

    // Determine direction
    const goingRight = endX > startX;
    const goingDown = endY > startY;

    // Check if direct path is clear
    const isNearlyHorizontal = Math.abs(endY - startY) < 30;
    const isNearlyVertical = Math.abs(endX - startX) < 30;

    if (isNearlyHorizontal) {
        // Nearly horizontal - straight line
        return `M ${startX} ${startY} L ${endX} ${endY}`;
    }

    if (isNearlyVertical) {
        // Nearly vertical - straight line
        return `M ${startX} ${startY} L ${endX} ${endY}`;
    }

    // For tree layout (hierarchical): use simple L-path
    // Parent -> Child: horizontal from parent, then vertical to child level, then horizontal to child
    if (currentLayout === LAYOUT_MODES.BY_HIERARCHY) {
        // Simple L-path: go horizontal first, then vertical
        // Use a small horizontal segment from parent, then drop/rise to child Y, then go to child
        const bendX = startX + 40 + channelOffset;  // Small horizontal segment from parent
        return `M ${startX} ${startY} L ${bendX} ${startY} L ${bendX} ${endY} L ${endX} ${endY}`;
    }

    // For other layouts: Z-path through channels
    const midX = (startX + endX) / 2 + channelOffset;

    // Clamp to stay between source and target
    let channelX;
    if (goingRight) {
        channelX = Math.max(fromBounds.right + margin, Math.min(midX, toBounds.left - margin));
    } else {
        channelX = Math.min(fromBounds.left - margin, Math.max(midX, toBounds.right + margin));
    }

    // Z-path: horizontal to channel, vertical through channel, horizontal to target
    return `M ${startX} ${startY} L ${channelX} ${startY} L ${channelX} ${endY} L ${endX} ${endY}`;
}

function updateConnectionsInternal() {
    elements.connectionsLayer.innerHTML = '';

    // DISABLED: Cluster backgrounds cause performance issues with 300+ nodes
    // renderClusterBackgrounds();

    // Connection colors by type
    const connectionColors = {
        'epic-story': '#7856ff',      // Purple for Epic -> Story
        'req-story': '#1d9bf0',       // Blue for Req -> Story
        'story-test': '#00ba7c',      // Green for Story -> Test
        'req-diagram': '#ffd400',     // Yellow for Req -> Diagram
        'persona-story': '#f97316',   // Orange for Persona -> Story
        'flow-screen': '#ec4899',     // Pink for Flow -> Screen
        'screen-component': '#84cc16', // Lime for Screen -> Component
        'story-screen': '#8b5cf6',    // Violet for Story -> Screen
        'feature-task': '#f59e0b',    // Amber for Feature -> Task
        'default': '#536471'          // Gray for others
    };

    // Collect all node bounding boxes for collision detection
    const nodeBounds = [];
    Object.values(state.nodes).forEach(node => {
        if (node.element) {
            const el = node.element;
            nodeBounds.push({
                left: parseFloat(el.style.left) || 0,
                top: parseFloat(el.style.top) || 0,
                right: (parseFloat(el.style.left) || 0) + el.offsetWidth,
                bottom: (parseFloat(el.style.top) || 0) + el.offsetHeight,
                id: el.dataset.nodeId
            });
        }
    });

    // Group connections by their endpoints to detect overlaps
    const connectionGroups = groupConnectionsByPath();

    let pathsCreated = 0;
    let pathsFailed = 0;

    state.connections.forEach((conn, index) => {
        const fromNode = state.nodes[conn.from];
        const toNode = state.nodes[conn.to];

        if (fromNode && toNode && fromNode.element && toNode.element) {
            const fromEl = fromNode.element;
            const toEl = toNode.element;

            // Calculate offset for overlapping connections
            const groupKey = getConnectionGroupKey(conn.from, conn.to);
            const groupConnections = connectionGroups[groupKey] || [];
            const groupIndex = groupConnections.indexOf(index);
            const groupSize = groupConnections.length;
            const offsetStep = 8;
            const offset = groupIndex * offsetStep - ((groupSize - 1) * offsetStep) / 2;

            // Get node bounds
            const fromBounds = {
                left: parseFloat(fromEl.style.left),
                top: parseFloat(fromEl.style.top),
                right: parseFloat(fromEl.style.left) + fromEl.offsetWidth,
                bottom: parseFloat(fromEl.style.top) + fromEl.offsetHeight,
                centerX: parseFloat(fromEl.style.left) + fromEl.offsetWidth / 2,
                centerY: parseFloat(fromEl.style.top) + fromEl.offsetHeight / 2
            };

            const toBounds = {
                left: parseFloat(toEl.style.left),
                top: parseFloat(toEl.style.top),
                right: parseFloat(toEl.style.left) + toEl.offsetWidth,
                bottom: parseFloat(toEl.style.top) + toEl.offsetHeight,
                centerX: parseFloat(toEl.style.left) + toEl.offsetWidth / 2,
                centerY: parseFloat(toEl.style.top) + toEl.offsetHeight / 2
            };

            // Determine connection direction
            const goingRight = toBounds.centerX > fromBounds.centerX;
            const goingDown = toBounds.centerY > fromBounds.centerY;

            // Determine exit and entry points based on relative positions
            // Exit from the side closest to target, enter from side closest to source
            let startX, startY, endX, endY;

            if (Math.abs(toBounds.centerX - fromBounds.centerX) > Math.abs(toBounds.centerY - fromBounds.centerY)) {
                // Horizontal dominant - exit from left/right side
                if (goingRight) {
                    startX = fromBounds.right;
                    startY = fromBounds.centerY + offset;
                    endX = toBounds.left;
                    endY = toBounds.centerY + offset;
                } else {
                    startX = fromBounds.left;
                    startY = fromBounds.centerY + offset;
                    endX = toBounds.right;
                    endY = toBounds.centerY + offset;
                }
            } else {
                // Vertical dominant - exit from top/bottom
                if (goingDown) {
                    startX = fromBounds.centerX + offset;
                    startY = fromBounds.bottom;
                    endX = toBounds.centerX + offset;
                    endY = toBounds.top;
                } else {
                    startX = fromBounds.centerX + offset;
                    startY = fromBounds.top;
                    endX = toBounds.centerX + offset;
                    endY = toBounds.bottom;
                }
            }

            // Determine connection color
            let colorKey = 'default';
            if (fromNode.type === 'epic' && toNode.type === 'user-story') colorKey = 'epic-story';
            else if (fromNode.type === 'requirement' && toNode.type === 'user-story') colorKey = 'req-story';
            else if (fromNode.type === 'user-story' && toNode.type === 'test') colorKey = 'story-test';
            else if (fromNode.type === 'requirement' && toNode.type === 'diagram') colorKey = 'req-diagram';
            else if (fromNode.type === 'persona' && toNode.type === 'user-story') colorKey = 'persona-story';
            else if (fromNode.type === 'user-flow' && toNode.type === 'screen') colorKey = 'flow-screen';
            else if (fromNode.type === 'screen' && toNode.type === 'component') colorKey = 'screen-component';
            else if (fromNode.type === 'user-story' && toNode.type === 'screen') colorKey = 'story-screen';
            else if ((fromNode.type === 'feature' || fromNode.type === 'epic') && toNode.type === 'task') colorKey = 'feature-task';

            const color = connectionColors[colorKey];

            // Create orthogonal path that routes around nodes
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

            // Route path avoiding all other nodes
            const d = routeOrthogonalPath(
                startX, startY, endX, endY,
                fromBounds, toBounds,
                nodeBounds, conn.from, conn.to,
                offset
            );

            // Skip if coordinates are invalid
            if (isNaN(startX) || isNaN(startY) || isNaN(endX) || isNaN(endY)) {
                pathsFailed++;
                return;
            }

            path.setAttribute('d', d);
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', color);
            path.setAttribute('stroke-width', '2');
            path.setAttribute('stroke-opacity', '0.7');

            // Add arrow marker
            path.setAttribute('marker-end', `url(#arrow-${colorKey})`);

            // Add hover effect data
            path.dataset.from = conn.from;
            path.dataset.to = conn.to;
            path.classList.add('connection-path');

            elements.connectionsLayer.appendChild(path);
            pathsCreated++;
        } else {
            pathsFailed++;
        }
    });

    console.log(`[Connections] Created ${pathsCreated} paths, failed ${pathsFailed} (missing element or invalid coords)`);

    // Debug: Log first connection's coordinates
    if (state.connections.length > 0 && pathsCreated > 0) {
        const firstConn = state.connections[0];
        const from = state.nodes[firstConn.from];
        const to = state.nodes[firstConn.to];
        if (from && to && from.element && to.element) {
            console.log(`[Connections] Sample path: from ${firstConn.from} (${from.element.style.left}, ${from.element.style.top}) to ${firstConn.to} (${to.element.style.left}, ${to.element.style.top})`);
        }
    }

    // Ensure SVG covers the full canvas area
    elements.connectionsLayer.setAttribute('width', '20000');
    elements.connectionsLayer.setAttribute('height', '15000');
    elements.connectionsLayer.setAttribute('viewBox', '0 0 20000 15000');
    elements.connectionsLayer.style.overflow = 'visible';

    // Add arrow markers definitions
    addArrowMarkers();
}

/**
 * Group connections by their source-target pair to detect overlaps.
 * Returns an object mapping group keys to arrays of connection indices.
 */
function groupConnectionsByPath() {
    const groups = {};

    state.connections.forEach((conn, index) => {
        // Create a key for the source-target region
        // Group connections that share endpoints (bidirectional)
        const key = getConnectionGroupKey(conn.from, conn.to);
        if (!groups[key]) groups[key] = [];
        groups[key].push(index);
    });

    return groups;
}

/**
 * Get a unique key for a connection based on its endpoints.
 * Connections with same endpoints get the same key.
 */
function getConnectionGroupKey(from, to) {
    // Sort to make bidirectional connections share the same key
    return [from, to].sort().join('|');
}

function addArrowMarkers() {
    // Check if defs already exists
    let defs = elements.connectionsLayer.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        elements.connectionsLayer.prepend(defs);
    }
    defs.innerHTML = '';

    const colors = {
        'epic-story': '#7856ff',
        'req-story': '#1d9bf0',
        'story-test': '#00ba7c',
        'req-diagram': '#ffd400',
        'default': '#536471'
    };

    Object.entries(colors).forEach(([key, color]) => {
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
        marker.setAttribute('id', `arrow-${key}`);
        marker.setAttribute('viewBox', '0 0 10 10');
        marker.setAttribute('refX', '9');
        marker.setAttribute('refY', '5');
        marker.setAttribute('markerWidth', '6');
        marker.setAttribute('markerHeight', '6');
        marker.setAttribute('orient', 'auto-start-reverse');

        const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arrowPath.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
        arrowPath.setAttribute('fill', color);

        marker.appendChild(arrowPath);
        defs.appendChild(marker);
    });
}

// ============================================
// Sidebar
// ============================================

function addSidebarItem(listId, id, title, priority) {
    const list = document.getElementById(listId);
    if (!list) return;

    const item = document.createElement('div');
    item.className = 'sidebar-item';
    item.dataset.nodeId = id;

    item.innerHTML = `
        <span class="item-id">${id}</span>
        <span class="item-title">${title}</span>
        ${priority ? `<span class="item-priority ${priority}"></span>` : ''}
    `;

    item.addEventListener('click', () => focusNode(id));

    list.appendChild(item);
    updateCounts();
}

function focusNode(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    const containerRect = elements.canvasContainer.getBoundingClientRect();
    state.canvas.x = -nodeData.x * state.canvas.zoom + containerRect.width / 2 - 100;
    state.canvas.y = -nodeData.y * state.canvas.zoom + containerRect.height / 2 - 50;

    updateCanvasTransform();
    updateMinimap();

    // Highlight node
    document.querySelectorAll('.canvas-node').forEach(n => n.classList.remove('selected'));
    nodeData.element.classList.add('selected');
}

function updateCounts() {
    elements.reqCount.textContent = elements.requirementsList.children.length;
    elements.usCount.textContent = elements.userStoriesList.children.length;
    elements.epicCount.textContent = elements.epicsList.children.length;
    elements.testCount.textContent = elements.testsList.children.length;
}

// ============================================
// Minimap
// ============================================

// Cache for minimap dot elements - reuse instead of recreate
const minimapDots = new Map();

function updateMinimap() {
    const scale = 0.01;  // Smaller scale for larger canvas
    const offsetX = 2500; // Offset to center minimap content
    const offsetY = 2500;

    const currentNodeIds = new Set(Object.keys(state.nodes));

    // Update or create dots for existing nodes
    currentNodeIds.forEach(nodeId => {
        const node = state.nodes[nodeId];
        let dot = minimapDots.get(nodeId);

        if (!dot) {
            // Create new dot only if it doesn't exist
            dot = document.createElement('div');
            dot.className = 'minimap-node';
            dot.style.width = '3px';
            dot.style.height = '3px';
            elements.minimapContent.appendChild(dot);
            minimapDots.set(nodeId, dot);
        }

        // Update position (cheap operation)
        dot.style.left = `${(node.x - offsetX) * scale}px`;
        dot.style.top = `${(node.y - offsetY) * scale}px`;
    });

    // Remove dots for deleted nodes
    minimapDots.forEach((dot, nodeId) => {
        if (!currentNodeIds.has(nodeId)) {
            dot.remove();
            minimapDots.delete(nodeId);
        }
    });

    // Update viewport indicator
    const containerRect = elements.canvasContainer.getBoundingClientRect();
    const viewportWidth = containerRect.width / state.canvas.zoom * scale;
    const viewportHeight = containerRect.height / state.canvas.zoom * scale;
    const viewportX = (-state.canvas.x / state.canvas.zoom - offsetX) * scale;
    const viewportY = (-state.canvas.y / state.canvas.zoom - offsetY) * scale;

    elements.minimapViewport.style.left = `${viewportX}px`;
    elements.minimapViewport.style.top = `${viewportY}px`;
    elements.minimapViewport.style.width = `${viewportWidth}px`;
    elements.minimapViewport.style.height = `${viewportHeight}px`;
}

// ============================================
// WebSocket Messages
// ============================================

function sendMessage(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        console.log('[WS] Sending:', data.type);
        state.ws.send(JSON.stringify(data));
    } else {
        console.error('[WS] Cannot send - WebSocket not connected. State:', state.ws?.readyState);
        log('error', 'WebSocket nicht verbunden. Bitte Seite neu laden.');
    }
}

function handleMessage(message) {
    const { type, data, timestamp } = message;

    switch (type) {
        case 'init':
            handleInit(data);
            break;

        case 'pipeline_started':
            elements.projectInfo.querySelector('.project-name').textContent = data.project_name;
            log('info', `Pipeline started: ${data.project_name} (${data.mode} mode)`);
            break;

        case 'pipeline_complete':
            elements.progressFill.style.width = '100%';
            elements.progressText.textContent = 'Complete!';
            log('success', 'Pipeline completed successfully!');
            break;

        case 'pass_started':
            updateQualityGate(data.pass_name, 'active');
            elements.progressText.textContent = `${data.pass_name}...`;
            log('info', `Starting pass ${data.pass_number}: ${data.pass_name}`);
            break;

        case 'pass_complete':
            updateQualityGate(data.pass_name, 'passed');
            const progress = (data.pass_number / 5) * 100;
            elements.progressFill.style.width = `${progress}%`;
            log('success', `Pass ${data.pass_number} complete: ${data.pass_name}`);
            break;

        case 'requirement_added':
            createNode('requirement', data.req_id, data);
            addSidebarItem('requirements-list', data.req_id, data.title, data.priority);
            log('info', `Requirement added: ${data.req_id}`);
            break;

        case 'user_story_generated':
            createNode('user-story', data.us_id, data);
            addSidebarItem('user-stories-list', data.us_id, data.title);
            if (data.parent_req) {
                addConnection(data.parent_req, data.us_id);
            }
            log('info', `User Story generated: ${data.us_id}`);
            break;

        case 'epic_generated':
            createNode('epic', data.epic_id, data);
            addSidebarItem('epics-list', data.epic_id, data.title);
            log('info', `Epic generated: ${data.epic_id}`);
            break;

        case 'diagram_generated':
            const diagramId = `${data.req_id}-${data.diagram_type}`;
            createNode('diagram', diagramId, data);
            if (data.req_id) {
                addConnection(data.req_id, diagramId);
            }
            log('info', `Diagram generated: ${data.diagram_type} for ${data.req_id}`);
            break;

        case 'api_spec_generated':
            const apiId = `API-${data.method}-${data.path.replace(/\//g, '-')}`;
            createNode('api', apiId, data);
            log('info', `API endpoint: ${data.method} ${data.path}`);
            break;

        case 'test_generated':
            createNode('test', data.test_id, data);
            addSidebarItem('tests-list', data.test_id, data.title);
            if (data.parent_req) {
                addConnection(data.parent_req, data.test_id);
            }
            log('info', `Test generated: ${data.test_id}`);
            break;

        case 'quality_gate':
            updateQualityGate(data.gate_name, data.status);
            log(data.status === 'passed' ? 'success' : 'warn',
                `Quality Gate ${data.gate_name}: ${data.status}`);
            break;

        case 'log_info':
        case 'log_warn':
        case 'log_error':
            const level = type.replace('log_', '');
            log(level, data.message);
            break;

        case 'node_position':
            if (state.nodes[data.node_id] && state.nodes[data.node_id].element) {
                state.nodes[data.node_id].x = data.x;
                state.nodes[data.node_id].y = data.y;
                state.nodes[data.node_id].element.style.left = `${data.x}px`;
                state.nodes[data.node_id].element.style.top = `${data.y}px`;
            }
            break;

        // ========== Kilo Agent Events ==========
        case 'kilo_task_processing':
            showKiloProcessing(data.node_id);
            addChatMessage(data.node_id, 'system', 'Verarbeite...');
            log('info', `Kilo Agent processing: ${data.task}`);
            break;

        case 'kilo_task_complete':
            hideKiloProcessing(data.node_id);
            addChatMessage(data.node_id, 'agent', 'Aufgabe abgeschlossen!');
            log('success', `Kilo Agent task complete for ${data.node_id}`);
            break;

        case 'kilo_task_error':
            hideKiloProcessing(data.node_id);
            addChatMessage(data.node_id, 'error', data.error);
            log('error', `Kilo Agent error: ${data.error}`);
            break;

        case 'diagram_updated':
            updateDiagramNode(data);
            addChatMessage(data.node_id, 'agent', 'Diagramm aktualisiert!');
            log('success', `Diagram updated: ${data.node_id}`);
            break;

        case 'content_updated':
            updateNodeContent(data);
            addChatMessage(data.node_id, 'agent', 'Inhalt aktualisiert!');
            log('success', `Content updated: ${data.node_id}`);
            break;

        // ========== Change Propagation Events ==========
        case 'file_changed':
            log('info', `Datei geändert: ${data.file_path}`);
            showNotification(`Änderung erkannt: ${data.affected_nodes.length} Node(s) betroffen`, 'info');
            break;

        case 'propagation_suggestion':
            addPropagationSuggestion(data);
            showNotification(`Änderungsvorschlag für ${data.target_node_id}`, 'info');
            log('info', `Propagation suggestion: ${data.source_node_id} → ${data.target_node_id}`);
            break;

        case 'propagation_applied':
            removePropagationSuggestion(data.id);
            showNotification(`Änderung angewendet: ${data.target_node_id}`, 'success');
            log('success', `Propagation applied: ${data.target_node_id}`);
            break;

        case 'propagation_rejected':
            removePropagationSuggestion(data.id);
            log('info', `Propagation rejected: ${data.target_node_id}`);
            break;

        case 'file_watching_started':
            updateWatchingStatus(true);
            log('info', 'File watching gestartet');
            break;

        case 'file_watching_stopped':
            updateWatchingStatus(false);
            log('info', 'File watching gestoppt');
            break;

        // ========== Auto-Link Events ==========
        case 'orphans_detected':
            updateOrphanCount(data.count);
            if (data.count > 0) {
                showNotification(`${data.count} verwaiste Node(s) gefunden`, 'warn');
            }
            log('info', `Orphans detected: ${data.count}`);
            break;

        case 'link_suggestion':
            addLinkSuggestion(data);
            log('info', `Link suggestion: ${data.orphan_node_id} → ${data.target_node_id}`);
            break;

        case 'link_created':
            removeLinkSuggestion(data.id);
            addConnection(data.orphan_node_id, data.target_node_id);
            showNotification(`Link erstellt: ${data.link_type}`, 'success');
            log('success', `Link created: ${data.orphan_node_id} → ${data.target_node_id}`);
            break;

        case 'link_rejected':
            removeLinkSuggestion(data.id);
            log('info', `Link rejected: ${data.orphan_node_id}`);
            break;

        // ========== Matrix Event Types (Steps 6-15) ==========
        case 'matrix_node_added':
            // Dispatch custom event for matrix.js to handle
            if (data.matrix_node) {
                window.dispatchEvent(new CustomEvent('matrix:node-added', { detail: data.matrix_node }));
                log('info', `Matrix node: ${data.matrix_node.id} (${data.matrix_node.type})`);
            }
            break;

        case 'matrix_step_complete':
            window.dispatchEvent(new CustomEvent('matrix:step-complete', { detail: data }));
            log('info', `Matrix step ${data.step_number}/15: ${data.step_name} (${data.node_count} nodes)`);
            break;

        case 'data_dictionary_generated':
            log('success', `Data Dictionary: ${data.entity_count} entities, ${data.relationship_count || 0} relationships`);
            break;

        case 'tech_stack_generated':
            log('success', `Tech Stack: ${data.backend} / ${data.frontend} / ${data.database}`);
            break;

        case 'ux_design_generated':
            log('success', `UX Design: ${data.persona_count} personas, ${data.user_flow_count} user flows`);
            break;

        case 'ui_design_generated':
            log('success', `UI Design: ${data.component_count} components, ${data.screen_count} screens`);
            break;

        case 'work_breakdown_generated':
            log('success', `Work Breakdown: ${data.package_count} work packages`);
            break;

        case 'task_list_generated':
            log('success', `Task List: ${data.task_count} tasks (${data.total_hours}h total)`);
            break;

        case 'reports_generated':
            log('success', `Reports: ${data.report_paths.length} reports generated`);
            break;

        case 'critique_complete':
            const scoreClass = data.quality_score >= 7 ? 'success' : data.quality_score >= 4 ? 'warn' : 'error';
            log(scoreClass, `Self-Critique: ${data.quality_score}/10 (${data.issue_count} issues, ${data.critical_count} critical)`);
            break;

        // ========== Layout Generation Events (Interactive Selection) ==========
        case 'layout_analysis_started':
            log('info', 'Layout analysis started - analyzing project structure...');
            showNotification('Layout-Analyse gestartet', 'info');
            break;

        case 'layout_analysis_complete':
            log('success', `Layout analysis complete: ${data.domain_count || 0} domains, ${data.cluster_count || 0} clusters identified`);
            break;

        case 'layout_variants_ready':
            log('info', `${data.variants.length} layout variants ready for selection (Stage ${data.stage})`);
            showLayoutSelectionModal(data.variants, data.stage);
            break;

        case 'layout_selected':
            log('success', `Layout variant "${data.variant_id}" selected for stage ${data.stage}`);
            hideLayoutSelectionModal();
            showNotification(`Layout "${data.variant_id}" ausgewählt`, 'success');
            break;

        case 'layout_refinement_ready':
            log('info', `${data.variants.length} refined layout variants ready (Stage ${data.stage})`);
            showLayoutSelectionModal(data.variants, data.stage);
            break;

        case 'layout_finalized':
            log('success', `Final layout: ${data.layout_type} with ${data.aggregations?.length || 0} aggregations`);
            hideLayoutSelectionModal();
            applyFinalLayout(data);
            showNotification('Layout finalisiert!', 'success');
            break;
    }
}

function handleInit(data) {
    log('info', 'Received initial state');

    // Replay history
    if (data.history) {
        data.history.forEach(event => {
            handleMessage(event);
        });
    }

    // Restore node positions
    if (data.canvas_state && data.canvas_state.nodes) {
        Object.entries(data.canvas_state.nodes).forEach(([nodeId, pos]) => {
            if (state.nodes[nodeId]) {
                state.nodes[nodeId].x = pos.x;
                state.nodes[nodeId].y = pos.y;
                state.nodes[nodeId].element.style.left = `${pos.x}px`;
                state.nodes[nodeId].element.style.top = `${pos.y}px`;
            }
        });
    }

    updateConnections();
    updateMinimap();
    fitToView();
}

// ============================================
// Layout Selection Modal (Interactive Layout Generation)
// ============================================

let currentLayoutStage = 1;
let layoutSelectionCallback = null;

/**
 * Shows the layout selection modal with variant previews.
 * Users can select their preferred layout variant in each stage.
 * @param {Array} variants - Layout variants to display
 * @param {number} stage - Current selection stage (1, 2, or 3)
 */
function showLayoutSelectionModal(variants, stage) {
    currentLayoutStage = stage;

    // Remove existing modal if present
    hideLayoutSelectionModal();

    const modal = document.createElement('div');
    modal.id = 'layout-selection-modal';
    modal.className = 'layout-selection-modal';

    const stageDescriptions = {
        1: 'Wähle die grundlegende Layout-Struktur',
        2: 'Verfeinere das Layout',
        3: 'Finale Layout-Auswahl'
    };

    modal.innerHTML = `
        <div class="layout-modal-overlay"></div>
        <div class="layout-modal-content">
            <div class="layout-modal-header">
                <h2>Stage ${stage}: Layout-Auswahl</h2>
                <p class="layout-modal-subtitle">${stageDescriptions[stage] || 'Wähle dein bevorzugtes Layout'}</p>
                <div class="layout-stage-indicator">
                    <span class="stage-dot ${stage >= 1 ? 'active' : ''}"></span>
                    <span class="stage-dot ${stage >= 2 ? 'active' : ''}"></span>
                    <span class="stage-dot ${stage >= 3 ? 'active' : ''}"></span>
                </div>
            </div>
            <div class="layout-variant-grid">
                ${variants.map((variant, index) => `
                    <div class="layout-variant-card" data-variant-id="${variant.id}" data-variant-index="${index}">
                        <div class="variant-preview">
                            <canvas id="variant-preview-${index}" width="280" height="180"></canvas>
                        </div>
                        <div class="variant-info">
                            <h3>${variant.name || variant.layout_type || 'Variante ' + (index + 1)}</h3>
                            <p class="variant-description">${variant.description || getLayoutTypeDescription(variant.layout_type)}</p>
                            <div class="variant-stats">
                                ${variant.aggregations ? `<span class="stat">📦 ${variant.aggregations.length} Gruppen</span>` : ''}
                                ${variant.columns ? `<span class="stat">📊 ${variant.columns.length} Spalten</span>` : ''}
                                ${variant.score ? `<span class="stat score">⭐ ${(variant.score * 100).toFixed(0)}%</span>` : ''}
                            </div>
                        </div>
                        <button class="btn-select-variant" onclick="selectLayoutVariant('${variant.id}')">
                            Auswählen
                        </button>
                    </div>
                `).join('')}
            </div>
            <div class="layout-modal-footer">
                <button class="btn-secondary" onclick="hideLayoutSelectionModal()">Abbrechen</button>
                <span class="footer-hint">Klicke auf eine Variante, um sie auszuwählen</span>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Render mini-previews for each variant
    setTimeout(() => {
        variants.forEach((variant, index) => {
            renderVariantPreview(variant, `variant-preview-${index}`);
        });
    }, 100);

    // Add click handlers for variant cards
    modal.querySelectorAll('.layout-variant-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (!e.target.classList.contains('btn-select-variant')) {
                // Toggle selection highlight
                modal.querySelectorAll('.layout-variant-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
            }
        });
    });

    log('info', `Layout selection modal opened for stage ${stage}`);
}

/**
 * Hides and removes the layout selection modal.
 */
function hideLayoutSelectionModal() {
    const modal = document.getElementById('layout-selection-modal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => modal.remove(), 200);
    }
}

/**
 * Handles user selection of a layout variant.
 * Sends the selection back to the server via WebSocket.
 * @param {string} variantId - ID of the selected variant
 */
function selectLayoutVariant(variantId) {
    log('info', `User selected layout variant: ${variantId} (stage ${currentLayoutStage})`);

    // Send selection to server
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'layout_selection',
            data: {
                variant_id: variantId,
                stage: currentLayoutStage
            }
        }));
    }

    // Visual feedback
    const modal = document.getElementById('layout-selection-modal');
    if (modal) {
        const selectedCard = modal.querySelector(`[data-variant-id="${variantId}"]`);
        if (selectedCard) {
            selectedCard.classList.add('confirming');
        }
    }

    showNotification(`Layout-Variante ausgewählt`, 'success');
}

/**
 * Returns a description for a layout type.
 * @param {string} layoutType - Type of layout
 * @returns {string} Description text
 */
function getLayoutTypeDescription(layoutType) {
    const descriptions = {
        'hierarchical': 'Baumstruktur mit Eltern-Kind-Beziehungen',
        'matrix': 'Tabellarische Anordnung nach Kategorien',
        'cluster': 'Gruppierung nach Ähnlichkeit',
        'domain-based': 'Spalten pro Fachdomäne',
        'swimlane': 'Horizontale Bahnen pro Akteur/Rolle',
        'timeline': 'Chronologische Anordnung',
        'radial': 'Kreisförmige Anordnung um Zentrum'
    };
    return descriptions[layoutType] || 'Optimierte Anordnung für dieses Projekt';
}

/**
 * Renders a mini-preview of a layout variant on a canvas.
 * @param {Object} variant - Layout variant data
 * @param {string} canvasId - ID of the canvas element
 */
function renderVariantPreview(variant, canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas
    ctx.fillStyle = '#1a1f26';
    ctx.fillRect(0, 0, width, height);

    // Draw layout preview based on type
    const layoutType = variant.layout_type || 'cluster';

    switch (layoutType) {
        case 'hierarchical':
            drawHierarchicalPreview(ctx, width, height, variant);
            break;
        case 'matrix':
            drawMatrixPreview(ctx, width, height, variant);
            break;
        case 'cluster':
            drawClusterPreview(ctx, width, height, variant);
            break;
        case 'domain-based':
            drawDomainPreview(ctx, width, height, variant);
            break;
        case 'swimlane':
            drawSwimlanePreview(ctx, width, height, variant);
            break;
        default:
            drawDefaultPreview(ctx, width, height, variant);
    }
}

function drawHierarchicalPreview(ctx, width, height, variant) {
    // Root node
    ctx.fillStyle = '#7856ff';
    ctx.fillRect(width/2 - 30, 20, 60, 25);

    // Level 1
    ctx.fillStyle = '#1d9bf0';
    ctx.fillRect(width/4 - 25, 70, 50, 20);
    ctx.fillRect(width*3/4 - 25, 70, 50, 20);

    // Level 2
    ctx.fillStyle = '#00ba7c';
    const positions = [width/6, width/3, width*2/3, width*5/6];
    positions.forEach(x => {
        ctx.fillRect(x - 20, 115, 40, 18);
    });

    // Connections
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(width/2, 45);
    ctx.lineTo(width/4, 70);
    ctx.moveTo(width/2, 45);
    ctx.lineTo(width*3/4, 70);
    ctx.stroke();

    // Level 3 (leaf nodes)
    ctx.fillStyle = '#ffd400';
    for (let i = 0; i < 6; i++) {
        ctx.fillRect(25 + i * 42, 150, 35, 15);
    }
}

function drawMatrixPreview(ctx, width, height, variant) {
    // Column headers
    ctx.fillStyle = '#ffd400';
    for (let i = 0; i < 4; i++) {
        ctx.fillRect(60 + i * 55, 15, 50, 20);
    }

    // Row headers
    ctx.fillStyle = '#1d9bf0';
    for (let i = 0; i < 4; i++) {
        ctx.fillRect(5, 45 + i * 35, 50, 25);
    }

    // Grid cells
    ctx.fillStyle = '#2d353f';
    for (let row = 0; row < 4; row++) {
        for (let col = 0; col < 4; col++) {
            ctx.fillRect(60 + col * 55, 45 + row * 35, 50, 25);
        }
    }

    // Some filled cells (random data)
    ctx.fillStyle = '#00ba7c';
    [[0,0], [0,2], [1,1], [1,3], [2,0], [2,2], [3,1]].forEach(([row, col]) => {
        ctx.fillRect(62 + col * 55, 47 + row * 35, 46, 21);
    });
}

function drawClusterPreview(ctx, width, height, variant) {
    // Draw clusters as circles with nodes
    const clusters = [
        { x: 70, y: 70, r: 45, color: '#1d9bf0', nodes: 5 },
        { x: 200, y: 60, r: 40, color: '#7856ff', nodes: 4 },
        { x: 140, y: 130, r: 50, color: '#00ba7c', nodes: 6 }
    ];

    clusters.forEach(cluster => {
        // Cluster background
        ctx.fillStyle = cluster.color + '30';
        ctx.beginPath();
        ctx.arc(cluster.x, cluster.y, cluster.r, 0, Math.PI * 2);
        ctx.fill();

        // Cluster border
        ctx.strokeStyle = cluster.color;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Nodes inside
        ctx.fillStyle = cluster.color;
        for (let i = 0; i < cluster.nodes; i++) {
            const angle = (i / cluster.nodes) * Math.PI * 2;
            const r = cluster.r * 0.6;
            const nx = cluster.x + Math.cos(angle) * r;
            const ny = cluster.y + Math.sin(angle) * r;
            ctx.fillRect(nx - 8, ny - 6, 16, 12);
        }
    });
}

function drawDomainPreview(ctx, width, height, variant) {
    // Domain columns
    const domains = ['#1d9bf0', '#00ba7c', '#7856ff', '#ff7a00'];
    const colWidth = (width - 20) / 4;

    domains.forEach((color, i) => {
        // Column header
        ctx.fillStyle = color;
        ctx.fillRect(10 + i * colWidth, 10, colWidth - 5, 25);

        // Column background
        ctx.fillStyle = color + '15';
        ctx.fillRect(10 + i * colWidth, 40, colWidth - 5, height - 50);

        // Nodes in column
        const nodeCount = 3 + Math.floor(Math.random() * 2);
        ctx.fillStyle = color + '90';
        for (let j = 0; j < nodeCount; j++) {
            ctx.fillRect(15 + i * colWidth, 50 + j * 40, colWidth - 15, 30);
        }
    });
}

function drawSwimlanePreview(ctx, width, height, variant) {
    // Swimlane rows
    const lanes = ['#f97316', '#ec4899', '#8b5cf6'];
    const laneHeight = (height - 20) / 3;

    lanes.forEach((color, i) => {
        // Lane background
        ctx.fillStyle = color + '15';
        ctx.fillRect(50, 10 + i * laneHeight, width - 60, laneHeight - 5);

        // Lane label
        ctx.fillStyle = color;
        ctx.fillRect(5, 10 + i * laneHeight, 40, laneHeight - 5);

        // Nodes in lane (flow from left to right)
        const nodeCount = 3 + Math.floor(Math.random() * 2);
        ctx.fillStyle = color + '90';
        for (let j = 0; j < nodeCount; j++) {
            ctx.fillRect(60 + j * 50, 20 + i * laneHeight, 40, laneHeight - 25);
        }

        // Arrows between nodes
        ctx.strokeStyle = 'rgba(255,255,255,0.4)';
        ctx.lineWidth = 1;
        for (let j = 0; j < nodeCount - 1; j++) {
            ctx.beginPath();
            ctx.moveTo(100 + j * 50, 20 + i * laneHeight + (laneHeight - 25) / 2);
            ctx.lineTo(105 + j * 50, 20 + i * laneHeight + (laneHeight - 25) / 2);
            ctx.stroke();
        }
    });
}

function drawDefaultPreview(ctx, width, height, variant) {
    // Simple scattered nodes
    ctx.fillStyle = '#1d9bf0';
    const nodePositions = [
        [30, 30], [120, 50], [200, 40], [70, 100],
        [150, 90], [230, 110], [50, 150], [130, 140], [210, 155]
    ];

    nodePositions.forEach(([x, y]) => {
        ctx.fillRect(x, y, 40, 25);
    });

    // Some connections
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(70, 42);
    ctx.lineTo(120, 62);
    ctx.moveTo(160, 62);
    ctx.lineTo(200, 52);
    ctx.moveTo(90, 112);
    ctx.lineTo(150, 102);
    ctx.stroke();
}

/**
 * Applies the finalized layout to the canvas.
 * @param {Object} layoutData - Final layout configuration
 */
function applyFinalLayout(layoutData) {
    log('info', `Applying final layout: ${layoutData.layout_type}`);

    // Store the layout configuration
    state.currentLayout = layoutData;

    // Apply aggregations if present
    if (layoutData.aggregations && layoutData.aggregations.length > 0) {
        applyAggregations(layoutData.aggregations);
    }

    // Apply column-based positioning if present
    if (layoutData.columns && layoutData.columns.length > 0) {
        applyColumnLayout(layoutData.columns);
    }

    // Update connections
    updateConnections();
    updateMinimap();

    // Dispatch custom event for other components
    window.dispatchEvent(new CustomEvent('layout:applied', { detail: layoutData }));
}

/**
 * Applies requirement aggregations (grouping).
 * @param {Array} aggregations - Aggregation configurations
 */
function applyAggregations(aggregations) {
    aggregations.forEach(agg => {
        // Create a group container if it doesn't exist
        let groupNode = state.nodes[agg.id];

        if (!groupNode) {
            // Create aggregation node
            const groupData = {
                id: agg.id,
                name: agg.name,
                type: 'aggregation',
                contains: agg.contains,
                collapsed: agg.collapsed !== false
            };

            createAggregationNode(groupData);
        }

        // Move contained nodes inside or hide them if collapsed
        if (agg.contains) {
            agg.contains.forEach(nodeId => {
                const node = state.nodes[nodeId];
                if (node && node.element) {
                    if (agg.collapsed) {
                        node.element.style.display = 'none';
                    } else {
                        node.element.dataset.aggregation = agg.id;
                    }
                }
            });
        }
    });

    log('info', `Applied ${aggregations.length} aggregations`);
}

/**
 * Creates an aggregation (group) node on the canvas.
 * @param {Object} data - Aggregation data
 */
function createAggregationNode(data) {
    const element = document.createElement('div');
    element.className = 'canvas-node node-aggregation';
    element.id = `node-${data.id}`;
    element.dataset.nodeId = data.id;
    element.dataset.nodeType = 'aggregation';

    element.innerHTML = `
        <div class="node-header">
            <span class="node-icon">📦</span>
            <span class="node-id">${data.id}</span>
            <span class="node-count">${data.contains?.length || 0} items</span>
        </div>
        <div class="node-title">${data.name}</div>
        <button class="expand-aggregation-btn" onclick="toggleAggregation('${data.id}')">
            ${data.collapsed ? '▼ Expand' : '▲ Collapse'}
        </button>
    `;

    // Position (will be updated by layout)
    element.style.left = '100px';
    element.style.top = '100px';

    document.getElementById('canvas-nodes').appendChild(element);

    state.nodes[data.id] = {
        id: data.id,
        type: 'aggregation',
        data: data,
        element: element,
        x: 100,
        y: 100
    };

    // Make draggable
    makeDraggable(element);
}

/**
 * Toggles the collapsed state of an aggregation.
 * @param {string} aggId - Aggregation ID
 */
function toggleAggregation(aggId) {
    const aggNode = state.nodes[aggId];
    if (!aggNode || !aggNode.data) return;

    const isCollapsed = aggNode.data.collapsed;
    aggNode.data.collapsed = !isCollapsed;

    // Update button text
    const btn = aggNode.element.querySelector('.expand-aggregation-btn');
    if (btn) {
        btn.textContent = aggNode.data.collapsed ? '▼ Expand' : '▲ Collapse';
    }

    // Show/hide contained nodes
    if (aggNode.data.contains) {
        aggNode.data.contains.forEach(nodeId => {
            const node = state.nodes[nodeId];
            if (node && node.element) {
                node.element.style.display = aggNode.data.collapsed ? 'none' : 'block';
            }
        });
    }

    updateConnections();
    updateMinimap();
}

/**
 * Applies column-based layout to nodes.
 * @param {Array} columns - Column configurations
 */
function applyColumnLayout(columns) {
    const startX = 100;
    const startY = 150;
    const colWidth = 350;
    const rowHeight = 200;

    columns.forEach((col, colIndex) => {
        const x = startX + colIndex * colWidth;

        if (col.nodes) {
            col.nodes.forEach((nodeId, rowIndex) => {
                const node = state.nodes[nodeId];
                if (node && node.element) {
                    const y = startY + rowIndex * rowHeight;
                    node.x = x;
                    node.y = y;
                    node.element.style.left = `${x}px`;
                    node.element.style.top = `${y}px`;
                }
            });
        }
    });

    log('info', `Applied ${columns.length} column layout`);
}

// ============================================
// UI Helpers
// ============================================

function updateConnectionStatus(connected) {
    elements.connectionStatus.className = 'connection-status ' + (connected ? 'connected' : 'disconnected');
    elements.connectionStatus.querySelector('.status-text').textContent = connected ? 'Connected' : 'Disconnected';
}

function updateQualityGate(gateName, status) {
    const gate = document.querySelector(`.gate[data-gate="${gateName}"]`);
    if (gate) {
        gate.classList.remove('passed', 'active', 'failed');
        if (status === 'passed' || status === 'PASS') {
            gate.classList.add('passed');
        } else if (status === 'active') {
            gate.classList.add('active');
        } else if (status === 'failed' || status === 'FAIL') {
            gate.classList.add('failed');
        }
    }
}

function log(level, message) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';

    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-level ${level}">${level.toUpperCase()}</span>
        <span class="log-message">${message}</span>
    `;

    elements.logContent.appendChild(entry);
    elements.logContent.scrollTop = elements.logContent.scrollHeight;
}

function toggleLog() {
    document.getElementById('log-panel').classList.toggle('collapsed');
    const btn = document.getElementById('btn-toggle-log');
    btn.textContent = document.getElementById('log-panel').classList.contains('collapsed') ? '▲' : '▼';
}

function onKeyDown(e) {
    // Keyboard shortcuts
    if (e.key === '0' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        resetView();
    } else if (e.key === '=' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        zoom(0.2);
    } else if (e.key === '-' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        zoom(-0.2);
    } else if (e.key === '1' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        fitToView();
    }
}

// ============================================
// Project Browser
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
        // Build item counts string
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
                <div class="project-meta">
                    <span class="project-date">${formatDate(p.created)}</span>
                </div>
            </div>
        `;
    }).join('');
}

function formatDate(dateStr) {
    // Format: "20260201_154145" -> "01.02.2026 15:41"
    if (!dateStr || dateStr.length < 15) return dateStr;
    const year = dateStr.substring(0, 4);
    const month = dateStr.substring(4, 6);
    const day = dateStr.substring(6, 8);
    const hour = dateStr.substring(9, 11);
    const min = dateStr.substring(11, 13);
    return `${day}.${month}.${year} ${hour}:${min}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadProject(projectId) {
    try {
        log('info', `Loading project: ${projectId}...`);

        const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Clear current canvas and state
        clearCanvas();

        // Update project info in header
        const projectName = data.project_name || projectId;
        elements.projectInfo.querySelector('.project-name').textContent = projectName;

        let totalItems = 0;

        // Format 1: journal.json format (nodes contain mermaid_diagrams)
        if (data.nodes && Object.keys(data.nodes).length > 0) {
            Object.entries(data.nodes).forEach(([nodeId, nodeData]) => {
                createNodeFromJournal(nodeId, nodeData);
                totalItems++;
            });
        }

        // NEW: Load requirements from data.requirements array (extracted from journal.json)
        if (data.requirements && data.requirements.length > 0) {
            data.requirements.forEach(req => {
                createRequirementFromArray(req);
                totalItems++;
            });
            log('info', `Loaded ${data.requirements.length} requirements`);
        }

        // Format 2: Folder-based format (separate arrays)
        if (data.epics && data.epics.length > 0) {
            data.epics.forEach(epic => {
                createEpicFromFolder(epic);
                totalItems++;
            });
        }

        if (data.user_stories && data.user_stories.length > 0) {
            data.user_stories.forEach(story => {
                createUserStoryFromFolder(story);
                totalItems++;
            });
        }

        if (data.diagrams && data.diagrams.length > 0) {
            data.diagrams.forEach(diagram => {
                createDiagramFromFolder(diagram);
                totalItems++;
            });
        }

        if (data.tests && data.tests.length > 0) {
            data.tests.forEach(test => {
                createTestFromFolder(test);
                totalItems++;
            });
        }

        // NEW: Load data dictionary entities
        if (data.data_dictionary && data.data_dictionary.entities && data.data_dictionary.entities.length > 0) {
            data.data_dictionary.entities.forEach(entity => {
                createEntityFromDictionary(entity);
                totalItems++;
            });
            log('info', `Loaded ${data.data_dictionary.entities.length} data entities`);
        }

        // NEW: Load work breakdown features
        if (data.features && data.features.length > 0) {
            data.features.forEach(feature => {
                createFeatureFromBreakdown(feature);
                totalItems++;
            });
            log('info', `Loaded ${data.features.length} features`);
        }

        // NEW: Load API endpoints
        if (data.api_endpoints && data.api_endpoints.length > 0) {
            data.api_endpoints.forEach(endpoint => {
                createApiEndpointNode(endpoint);
                totalItems++;
            });
            log('info', `Loaded ${data.api_endpoints.length} API endpoints`);
        }

        // ========== NEW ARTIFACT TYPES (4 New Generators) ==========

        // Load Tech Stack
        if (data.tech_stack) {
            createTechStackNode(data.tech_stack);
            totalItems++;
            log('info', 'Loaded tech stack');
        }

        // Load Personas
        if (data.personas && data.personas.length > 0) {
            data.personas.forEach(persona => {
                createPersonaNode(persona);
                totalItems++;
            });
            log('info', `Loaded ${data.personas.length} personas`);
        }

        // Load User Flows
        if (data.user_flows && data.user_flows.length > 0) {
            data.user_flows.forEach(flow => {
                createUserFlowNode(flow);
                totalItems++;
            });
            log('info', `Loaded ${data.user_flows.length} user flows`);
        }

        // Load UI Components
        if (data.ui_components && data.ui_components.length > 0) {
            data.ui_components.forEach(component => {
                createUIComponentNode(component);
                totalItems++;
            });
            log('info', `Loaded ${data.ui_components.length} UI components`);
        }

        // Load Screens
        if (data.screens && data.screens.length > 0) {
            data.screens.forEach(screen => {
                createScreenNode(screen);
                totalItems++;
            });
            log('info', `Loaded ${data.screens.length} screens`);
        }
        // FALLBACK: Create screens from Information Architecture if screens array is empty
        else if (data.information_architecture && data.information_architecture.length > 0) {
            const iaScreens = data.information_architecture
                .filter(ia => ia.path && ia.path !== '/')  // Exclude root
                .map(ia => ({
                    id: ia.id,  // Use original IA ID for consistency with backend
                    name: ia.name,
                    route: ia.path,
                    ia_id: ia.id,
                    content_types: ia.content_types || [],
                    parent_id: ia.parent_id,
                    children: ia.children || []
                }));

            iaScreens.forEach(screen => {
                createScreenNode(screen);
                totalItems++;
            });

            // Store for linking functions
            data.screens = iaScreens;
            log('info', `Created ${iaScreens.length} screens from Information Architecture`);
        }

        // Load Tasks
        if (data.tasks) {
            // tasks is an object { feature_id: [tasks] }
            Object.entries(data.tasks).forEach(([featureId, tasks]) => {
                if (Array.isArray(tasks)) {
                    tasks.forEach(task => {
                        task.parent_feature_id = featureId;
                        createTaskNode(task);
                        totalItems++;
                    });
                }
            });
            const totalTasks = data.task_summary?.total_tasks || 0;
            log('info', `Loaded ${totalTasks} tasks`);
        }

        // Update sidebar lists
        updateCounts();

        // NEW: Apply auto-linking from traceability matrix
        setTimeout(() => {
            console.log('[Auto-Link] Starting auto-linking...');
            console.log('[Auto-Link] state.nodes:', Object.keys(state.nodes).length, 'nodes');
            console.log('[Auto-Link] state.connections before:', state.connections.length, 'connections');

            if (data.traceability && data.traceability.length > 0) {
                console.log('[Auto-Link] Traceability data:', data.traceability.length, 'entries');
                applyTraceabilityLinks(data.traceability);
            } else {
                console.log('[Auto-Link] No traceability data');
            }

            // Apply epic -> story links
            if (data.epics && data.epics.length > 0) {
                console.log('[Auto-Link] Epics:', data.epics.length);
                applyEpicStoryLinks(data.epics, data.user_stories);
            } else {
                console.log('[Auto-Link] No epics data');
            }

            // Apply user story -> requirement links
            if (data.user_stories && data.user_stories.length > 0) {
                console.log('[Auto-Link] User Stories:', data.user_stories.length);
                applyUserStoryLinks(data.user_stories);
            } else {
                console.log('[Auto-Link] No user_stories data');
            }

            // ========== NEW AUTO-LINKING (4 New Generators) ==========

            // Link Personas → User Stories (based on persona role matching)
            if (data.personas && data.user_stories) {
                applyPersonaStoryLinks(data.personas, data.user_stories);
            }

            // Link User Flows → Screens (based on flow steps)
            if (data.user_flows && data.screens) {
                applyFlowScreenLinks(data.user_flows, data.screens);
            }

            // Link Screens → User Stories (based on parent_user_story)
            if (data.screens && data.user_stories) {
                applyScreenStoryLinks(data.screens);
            }

            // Link Screens → UI Components (based on screen.components)
            if (data.screens && data.ui_components) {
                applyScreenComponentLinks(data.screens, data.ui_components);
            }

            // Link Features → Tasks (based on parent_feature_id)
            if (data.tasks) {
                applyFeatureTaskLinks(data.tasks);
            }

            // Comprehensive metadata-based auto-linking (catches remaining unlinked nodes)
            applyMetadataLinks();

            console.log('[Auto-Link] state.connections after:', state.connections.length, 'connections');
            console.log('[Auto-Link] Connections:', state.connections.slice(0, 10)); // Show first 10

            updateConnections();
            console.log('[Auto-Link] updateConnections() called');
        }, 200);

        log('success', `Loaded "${projectName}" with ${totalItems} items`);

        // Apply hierarchical layout (left-to-right) by default and fit to view
        setTimeout(() => {
            setLayout('by_hierarchy');
        }, 300);

        // Fallback: Ensure mermaid rendering starts even if layout timing is off
        setTimeout(() => {
            if (mermaidRenderQueue.length > 0 && !mermaidRenderEnabled) {
                console.log('[Mermaid] Fallback: Starting rendering that was not triggered by layout');
                startMermaidRendering();
            }
        }, 1500);

        // Mark project as selected in list
        document.querySelectorAll('.project-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.projectId === projectId);
        });

    } catch (error) {
        console.error('Failed to load project:', error);
        log('error', `Failed to load project: ${error.message}`);
    }
}

function clearCanvas() {
    // Clear all nodes from canvas
    elements.canvasNodes.innerHTML = '';

    // Clear state
    state.nodes = {};
    state.connections = [];
    state.nodeCounters = {};  // Reset counters to prevent position conflicts

    // Clear sidebar lists
    elements.requirementsList.innerHTML = '';
    elements.userStoriesList.innerHTML = '';
    elements.epicsList.innerHTML = '';
    elements.testsList.innerHTML = '';

    // Clear connections layer
    elements.connectionsLayer.innerHTML = '';

    // Reset counts
    updateCounts();
}

function createNodeFromJournal(nodeId, nodeData) {
    // Determine node type from the data
    let type = 'requirement';
    let displayId = nodeId;

    if (nodeId.startsWith('node-')) {
        displayId = nodeData.requirement_id || nodeId.replace('node-', '');
    }

    // Create the requirement node using existing createNode function
    const data = {
        title: nodeData.title || nodeData.description || 'Untitled',
        type: nodeData.type || 'functional',
        priority: nodeData.priority || 'should',
        description: nodeData.description || ''
    };

    createNode(type, displayId, data);
    addSidebarItem('requirements-list', displayId, data.title, data.priority);

    // Create diagram nodes if mermaid_diagrams exist
    if (nodeData.mermaid_diagrams && typeof nodeData.mermaid_diagrams === 'object') {
        const diagramTypes = Object.keys(nodeData.mermaid_diagrams);
        diagramTypes.forEach((diagramType, index) => {
            const mermaidCode = nodeData.mermaid_diagrams[diagramType];
            if (mermaidCode && mermaidCode.trim()) {
                const diagramId = `${displayId}-${diagramType}`;
                const diagramData = {
                    diagram_type: diagramType.charAt(0).toUpperCase() + diagramType.slice(1),
                    mermaid_code: mermaidCode,
                    parent_requirement: displayId
                };
                createNode('diagram', diagramId, diagramData);

                // Create connection from requirement to diagram
                addConnection(displayId, diagramId);
            }
        });
    }

    // Create user stories if they exist
    if (nodeData.user_stories && Array.isArray(nodeData.user_stories)) {
        nodeData.user_stories.forEach((story, index) => {
            const storyId = `${displayId}-US${index + 1}`;
            const storyData = {
                title: story.title || story.story || 'User Story',
                persona: story.persona || story.role || 'user'
            };
            createNode('user-story', storyId, storyData);
            addSidebarItem('user-stories-list', storyId, storyData.title, '');
            addConnection(displayId, storyId);
        });
    }

    // Create test nodes if test cases exist
    if (nodeData.acceptance_criteria && Array.isArray(nodeData.acceptance_criteria)) {
        nodeData.acceptance_criteria.forEach((criterion, index) => {
            const testId = `${displayId}-TC${index + 1}`;
            const testData = {
                title: criterion.description || criterion,
                test_type: 'acceptance'
            };
            createNode('test', testId, testData);
            addSidebarItem('tests-list', testId, testData.title, '');
        });
    }
}

function updateSidebarFromJournal(journal) {
    // Update counts after loading
    updateCounts();
}

/**
 * Create a requirement node from the requirements array (simpler format from journal.json).
 * This handles the data.requirements array which contains extracted requirements.
 */
function createRequirementFromArray(req) {
    const reqId = req.id || `REQ-${Date.now()}`;
    const data = {
        title: req.title || 'Untitled Requirement',
        type: req.type || 'functional',
        priority: req.priority || 'should',
        description: req.description || '',
        source: req.source || ''
    };

    createNode('requirement', reqId, data);
    addSidebarItem('requirements-list', reqId, data.title, data.priority);

    // Create diagram nodes if mermaid_diagrams exist
    if (req.mermaid_diagrams && typeof req.mermaid_diagrams === 'object') {
        Object.entries(req.mermaid_diagrams).forEach(([diagramType, mermaidCode]) => {
            if (mermaidCode && mermaidCode.trim()) {
                const diagramId = `${reqId}-${diagramType}`;
                const diagramData = {
                    diagram_type: diagramType.charAt(0).toUpperCase() + diagramType.slice(1),
                    mermaid_code: mermaidCode,
                    parent_requirement: reqId
                };
                createNode('diagram', diagramId, diagramData);
                addConnection(reqId, diagramId);
            }
        });
    }
}

// ============================================
// Folder-Format Node Creators
// ============================================

function createEpicFromFolder(epic) {
    const epicId = epic.id || `EPIC-${Date.now()}`;
    const data = {
        title: epic.title || 'Untitled Epic',
        requirements: epic.linked_requirements || [],
        stories: epic.linked_user_stories || []
    };

    createNode('epic', epicId, data);
    addSidebarItem('epics-list', epicId, data.title, '');

    // Create connections to linked user stories (delayed to ensure stories exist)
    setTimeout(() => {
        if (epic.linked_user_stories && Array.isArray(epic.linked_user_stories)) {
            epic.linked_user_stories.forEach(storyId => {
                addConnection(epicId, storyId);
            });
        }
    }, 50);
}

function createUserStoryFromFolder(story) {
    const storyId = story.id || `US-${Date.now()}`;
    const data = {
        title: story.title || 'Untitled Story',
        persona: story.persona || 'user',
        action: story.action || '',
        benefit: story.benefit || ''
    };

    createNode('user-story', storyId, data);
    addSidebarItem('user-stories-list', storyId, data.title, story.priority || '');

    // Create connection to linked requirement if exists
    if (story.linked_requirement) {
        addConnection(story.linked_requirement, storyId);
    }
}

function createDiagramFromFolder(diagram) {
    const diagramId = diagram.id || `DIAG-${Date.now()}`;

    // Extract requirement ID from diagram ID (e.g., "REQ-001_flowchart" -> "REQ-001")
    let parentReqId = diagram.requirement_id;
    if (!parentReqId && diagramId.includes('_')) {
        // Try to extract from filename pattern like "REQ-001_flowchart" or "FR-IMP-001_sequence"
        const parts = diagramId.split('_');
        if (parts.length >= 2) {
            parentReqId = parts.slice(0, -1).join('_'); // Handle IDs with underscores like "FR-IMP-001"
        }
    }
    // Also try matching patterns like "REQ001-flowchart"
    if (!parentReqId && diagramId.includes('-')) {
        const match = diagramId.match(/^(REQ-?\d+|FR-[A-Z]+-\d+|NFR-[A-Z]+-\d+)/i);
        if (match) {
            parentReqId = match[1];
        }
    }

    const data = {
        diagram_type: diagram.type || 'Flowchart',
        mermaid_code: diagram.mermaid_code || '',
        parent_requirement: parentReqId || ''
    };

    createNode('diagram', diagramId, data);

    // Create connection to parent requirement if exists
    if (parentReqId) {
        // Delay to ensure requirement node exists first
        setTimeout(() => {
            // Try exact match first
            let reqNode = state.nodes[parentReqId];

            // If not found, try partial match
            if (!reqNode) {
                reqNode = findNodeByPartialId('requirement', parentReqId);
            }

            if (reqNode) {
                const reqNodeId = reqNode.element ? reqNode.element.dataset.nodeId : parentReqId;
                addConnection(reqNodeId, diagramId);
                // NOTE: Don't call updateConnections() here - it will be called after all links are created
                console.log(`[Diagram Link] Connected ${diagramId} to ${reqNodeId}`);
            } else {
                console.log(`[Diagram Link] No requirement found for ${diagramId} (tried: ${parentReqId})`);
            }
        }, 100);
    }
}

function createTestFromFolder(test) {
    const testId = test.id || `TEST-${Date.now()}`;
    const data = {
        title: test.title || 'Untitled Test',
        test_type: test.type || 'acceptance',
        content: test.content || '',
        // NEW: Extended test properties from .feature files
        scenario_count: test.scenario_count || 0,
        tags: test.tags || [],
        gherkin_content: test.gherkin_content || '',
        feature_file: test.feature_file || '',
        linked_user_story: test.linked_user_story || ''
    };

    createNode('test', testId, data);
    addSidebarItem('tests-list', testId, data.title, '');

    // Link to user story if linked_user_story is provided (e.g., "US-001")
    if (test.linked_user_story) {
        setTimeout(() => {
            const storyNode = state.nodes[test.linked_user_story];
            if (storyNode) {
                addConnection(test.linked_user_story, testId);
            }
        }, 100);
    }
}

// ============================================
// Entity & Feature Node Creators (New)
// ============================================

function createEntityFromDictionary(entity) {
    const entityId = `ENTITY-${entity.name}`;
    const data = {
        title: entity.name,
        description: entity.description,
        attributes: entity.attributes || [],
        source_requirements: entity.source_requirements || []
    };

    // Create entity node (reuse requirement template style)
    createNode('requirement', entityId, {
        title: data.title,
        type: 'entity',
        priority: 'data'
    });
    addSidebarItem('requirements-list', entityId, data.title, 'data');

    // Link to source requirements
    (data.source_requirements || []).forEach(reqId => {
        setTimeout(() => {
            const reqNode = findNodeByPartialId('requirement', reqId);
            if (reqNode) {
                addConnection(reqNode.element.dataset.nodeId, entityId);
            }
        }, 150);
    });
}

function createFeatureFromBreakdown(feature) {
    const featureId = feature.id || `FEAT-${Date.now()}`;
    const data = {
        title: feature.title,
        priority: feature.priority,
        complexity: feature.complexity,
        requirements: feature.requirements || []
    };

    // Create feature node (reuse epic template style)
    createNode('epic', featureId, {
        title: data.title,
        requirements: data.requirements,
        stories: []
    });
    addSidebarItem('epics-list', featureId, data.title, data.priority);

    // Link to requirements
    (data.requirements || []).forEach(reqId => {
        setTimeout(() => {
            const reqNode = findNodeByPartialId('requirement', reqId);
            if (reqNode) {
                addConnection(featureId, reqNode.element.dataset.nodeId);
            }
        }, 150);
    });
}

function createApiEndpointNode(endpoint) {
    const apiId = `API-${endpoint.method}-${endpoint.path.replace(/\//g, '-').replace(/\{|\}/g, '')}`;
    const data = {
        method: endpoint.method,
        path: endpoint.path,
        description: endpoint.description
    };

    createNode('api', apiId, data);
}

// ============================================
// NEW: Node Creation for 4 New Generators
// ============================================

function createTechStackNode(techStack) {
    const nodeId = 'TECH-STACK';
    const data = {
        project_name: techStack.project_name || 'Tech Stack',
        frontend_framework: techStack.frontend_framework,
        backend_framework: techStack.backend_framework,
        primary_database: techStack.primary_database,
        cloud_provider: techStack.cloud_provider
    };
    createNode('tech-stack', nodeId, data);
}

function createPersonaNode(persona) {
    const nodeId = persona.id || `PERSONA-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: persona.name,
        role: persona.role,
        goals: persona.goals || [],
        pain_points: persona.pain_points || [],
        tech_savviness: persona.tech_savviness
    };
    createNode('persona', nodeId, data);
}

function createUserFlowNode(flow) {
    const nodeId = flow.id || `FLOW-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: flow.name,
        description: flow.description,
        actor: flow.actor,
        steps: flow.steps || [],
        trigger: flow.trigger,
        mermaid_code: flow.mermaid_code || '',
        file_path: flow.file_path || ''
    };
    createNode('user-flow', nodeId, data);
}

function createUIComponentNode(component) {
    const nodeId = component.id || `COMP-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: component.name,
        component_type: component.component_type,
        variants: component.variants || [],
        props: component.props || {},
        states: component.states || []
    };
    createNode('component', nodeId, data);
}

function createScreenNode(screen) {
    const nodeId = screen.id || `SCREEN-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: screen.name,
        route: screen.route,
        layout: screen.layout,
        components: screen.components || [],
        parent_user_story: screen.parent_user_story
    };
    createNode('screen', nodeId, data);
}

function createTaskNode(task) {
    const nodeId = task.id || `TASK-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        title: task.title,
        description: task.description,
        task_type: task.task_type,
        estimated_hours: task.estimated_hours,
        complexity: task.complexity,
        parent_feature_id: task.parent_feature_id
    };
    createNode('task', nodeId, data);
}

// ============================================
// Auto-Linking from Traceability Data
// ============================================

function applyTraceabilityLinks(traceability) {
    if (!traceability || traceability.length === 0) return;

    console.log(`[Auto-Link] Applying ${traceability.length} traceability entries`);

    traceability.forEach(trace => {
        const reqId = trace.req_id;

        // Link requirement to user stories
        (trace.user_stories || []).forEach(usId => {
            const reqNode = findNodeByPartialId('requirement', reqId);
            const usNode = findNodeByPartialId('user-story', usId);

            if (reqNode && usNode) {
                addConnection(reqNode.element.dataset.nodeId, usNode.element.dataset.nodeId);
            }
        });

        // Link user stories to test cases
        (trace.test_cases || []).forEach(tcId => {
            // First find which user story this test belongs to
            (trace.user_stories || []).forEach(usId => {
                const usNode = findNodeByPartialId('user-story', usId);
                const testNode = findNodeByPartialId('test', tcId);

                if (usNode && testNode) {
                    addConnection(usNode.element.dataset.nodeId, testNode.element.dataset.nodeId);
                }
            });
        });
    });

    updateConnections();
    log('info', `Applied ${traceability.length} traceability links`);
}

function applyEpicStoryLinks(epics, userStories) {
    if (!epics || epics.length === 0) return;

    let epicLinksCreated = 0;
    let reqLinksCreated = 0;

    epics.forEach(epic => {
        const epicNode = state.nodes[epic.id];
        if (!epicNode) {
            console.log(`[Epic-Story] Epic NOT found: ${epic.id}`);
            return;
        }

        (epic.linked_user_stories || []).forEach(usId => {
            const usNode = findNodeByPartialId('user-story', usId);
            if (usNode) {
                addConnection(epic.id, usNode.element.dataset.nodeId);
                epicLinksCreated++;
            } else {
                console.log(`[Epic-Story] User Story NOT found: ${usId}`);
            }
        });

        (epic.linked_requirements || []).forEach(reqId => {
            const reqNode = findNodeByPartialId('requirement', reqId);
            if (reqNode) {
                addConnection(reqNode.element.dataset.nodeId, epic.id);
                reqLinksCreated++;
            } else {
                console.log(`[Epic-Story] Requirement NOT found: ${reqId}`);
            }
        });
    });

    console.log(`[Epic-Story] Created ${epicLinksCreated} epic->story links, ${reqLinksCreated} req->epic links`);
}

function applyUserStoryLinks(userStories) {
    if (!userStories || userStories.length === 0) return;

    let linksCreated = 0;
    userStories.forEach(story => {
        if (story.linked_requirement) {
            const usNode = state.nodes[story.id];
            const reqNode = findNodeByPartialId('requirement', story.linked_requirement);

            if (usNode && reqNode) {
                addConnection(reqNode.element.dataset.nodeId, story.id);
                linksCreated++;
            } else {
                console.log(`[US-Link] Story ${story.id} or Req ${story.linked_requirement} NOT found. usNode=${!!usNode}, reqNode=${!!reqNode}`);
            }
        }
    });
    console.log(`[US-Link] Created ${linksCreated} req->story links`);
}

function findNodeByPartialId(type, partialId) {
    // Find node where ID contains partialId
    return Object.values(state.nodes).find(n =>
        n.type === type && n.element.dataset.nodeId.includes(partialId)
    ) || Object.values(state.nodes).find(n =>
        n.element.dataset.nodeId.includes(partialId)
    );
}

// ============================================
// NEW: Auto-Linking for 4 New Generators
// ============================================

function applyPersonaStoryLinks(personas, userStories) {
    if (!personas || !userStories) return;
    console.log(`[Auto-Link] Linking ${personas.length} personas to user stories`);

    personas.forEach(persona => {
        const personaNode = state.nodes[persona.id];
        if (!personaNode) return;

        // Find user stories that mention this persona's role
        userStories.forEach(story => {
            const storyPersona = (story.persona || '').toLowerCase();
            const personaRole = (persona.role || '').toLowerCase();
            const personaName = (persona.name || '').toLowerCase();

            if (storyPersona.includes(personaRole) || storyPersona.includes(personaName)) {
                const storyNode = state.nodes[story.id];
                if (storyNode) {
                    addConnection(persona.id, story.id);
                }
            }
        });
    });
}

function applyFlowScreenLinks(userFlows, screens) {
    if (!userFlows || !screens) return;
    console.log(`[Auto-Link] Linking ${userFlows.length} user flows to ${screens.length} screens`);

    let linkCount = 0;
    userFlows.forEach(flow => {
        const flowNode = state.nodes[flow.id];
        if (!flowNode || !flow.steps) return;

        // Get all screen names mentioned in flow steps
        const screenNames = [...new Set(flow.steps.map(s => s.screen).filter(Boolean))];

        screenNames.forEach(screenName => {
            const screenNameLower = screenName.toLowerCase().replace(/[^a-z0-9]/g, '');

            // Try multiple matching strategies
            const screen = screens.find(s => {
                if (!s.name) return false;
                const sNameLower = s.name.toLowerCase().replace(/[^a-z0-9]/g, '');

                // Exact match
                if (sNameLower === screenNameLower) return true;

                // Partial match (screen name contains flow step screen or vice versa)
                if (sNameLower.includes(screenNameLower) || screenNameLower.includes(sNameLower)) return true;

                // Word-based match (any word matches)
                const screenWords = screenNameLower.split(/\s+/);
                const sWords = sNameLower.split(/\s+/);
                if (screenWords.some(w => sWords.includes(w) && w.length > 3)) return true;

                return false;
            });

            if (screen) {
                const screenNode = state.nodes[screen.id];
                if (screenNode) {
                    addConnection(flow.id, screen.id);
                    linkCount++;
                }
            }
        });
    });
    console.log(`[Auto-Link] Created ${linkCount} flow → screen links`);
}

function applyScreenStoryLinks(screens) {
    if (!screens) return;
    console.log(`[Auto-Link] Linking ${screens.length} screens to user stories`);

    screens.forEach(screen => {
        if (!screen.parent_user_story) return;

        const screenNode = state.nodes[screen.id];
        const storyNode = findNodeByPartialId('user-story', screen.parent_user_story);

        if (screenNode && storyNode) {
            addConnection(storyNode.element.dataset.nodeId, screen.id);
        }
    });
}

function applyScreenComponentLinks(screens, components) {
    if (!screens || !components) return;
    console.log(`[Auto-Link] Linking ${screens.length} screens to ${components.length} components`);

    // Map component types to content_types for matching
    const contentTypeToComponentType = {
        'dashboard': ['card', 'chart'],
        'kpis': ['card', 'chart'],
        'real-time-dashboard': ['card', 'chart', 'table'],
        'form': ['input', 'button', 'select'],
        'forms': ['input', 'button', 'select'],
        'list': ['table'],
        'table': ['table'],
        'filters': ['input', 'select', 'button'],
        'search': ['input'],
        'status': ['badge'],
        'status-overview': ['badge', 'card'],
        'alerts': ['badge', 'modal'],
        'configuration': ['input', 'select', 'button'],
        'security': ['input', 'button'],
        'detail-view': ['card', 'table'],
        'rules-engine': ['table', 'input'],
        'charts': ['chart'],
        'logs': ['table'],
        'queue': ['table', 'badge'],
        'quick-actions': ['button'],
        'modal': ['modal'],
        'navigation': ['navigation'],
        'progress': ['progress']
    };

    let linkCount = 0;
    screens.forEach(screen => {
        const screenNode = state.nodes[screen.id];
        if (!screenNode) return;

        // Method 1: Direct component list (from ui_spec.json screens)
        if (screen.components && screen.components.length > 0) {
            screen.components.forEach(compId => {
                let compNode = state.nodes[compId];
                if (!compNode) {
                    const comp = components.find(c => c.id === compId || c.name === compId);
                    if (comp) compNode = state.nodes[comp.id];
                }
                if (compNode) {
                    addConnection(screen.id, compNode.element.dataset.nodeId);
                    linkCount++;
                }
            });
        }

        // Method 2: Match content_types to component types (for IA-based screens)
        if (screen.content_types && screen.content_types.length > 0) {
            const matchingCompTypes = new Set();
            screen.content_types.forEach(ct => {
                const types = contentTypeToComponentType[ct] || [];
                types.forEach(t => matchingCompTypes.add(t));
            });

            if (matchingCompTypes.size > 0) {
                components.forEach(comp => {
                    const compType = (comp.component_type || '').toLowerCase();
                    if (matchingCompTypes.has(compType)) {
                        const compNode = state.nodes[comp.id];
                        if (compNode) {
                            addConnection(screen.id, comp.id);
                            linkCount++;
                        }
                    }
                });
            }
        }
    });
    console.log(`[Auto-Link] Created ${linkCount} screen → component links`);
}

function applyFeatureTaskLinks(tasks) {
    if (!tasks) return;

    let linkCount = 0;
    Object.entries(tasks).forEach(([featureId, taskList]) => {
        if (!Array.isArray(taskList)) return;

        taskList.forEach(task => {
            const taskNode = state.nodes[task.id];
            const featureNode = findNodeByPartialId('feature', featureId) ||
                               findNodeByPartialId('epic', featureId);

            if (taskNode && featureNode) {
                addConnection(featureNode.element.dataset.nodeId, task.id);
                linkCount++;
            }
        });
    });
    console.log(`[Auto-Link] Linked ${linkCount} tasks to features`);
}

/**
 * Comprehensive metadata-based auto-linking
 * Links nodes based on their metadata fields (parent_*, linked_*, etc.)
 */
function applyMetadataLinks() {
    let linkCount = 0;

    Object.entries(state.nodes).forEach(([id, node]) => {
        if (!node.data) return;

        // Diagram -> Parent Links (from parent_id, requirement_id, feature_id, parent_requirement)
        if (node.type === 'diagram') {
            const parentId = node.data.parent_id || node.data.requirement_id ||
                           node.data.feature_id || node.data.parent_requirement;
            if (parentId && state.nodes[parentId]) {
                addConnection(parentId, id);
                linkCount++;
            } else if (parentId) {
                // Try partial match
                const parentNode = findNodeByPartialId('requirement', parentId) ||
                                  findNodeByPartialId('feature', parentId) ||
                                  findNodeByPartialId('epic', parentId);
                if (parentNode) {
                    addConnection(parentNode.element.dataset.nodeId, id);
                    linkCount++;
                }
            }
        }

        // Entity -> Requirement Links (from source_requirement, requirement_id)
        if (node.type === 'entity') {
            const parentId = node.data.source_requirement || node.data.requirement_id;
            if (parentId && state.nodes[parentId]) {
                addConnection(parentId, id);
                linkCount++;
            } else if (parentId) {
                const parentNode = findNodeByPartialId('requirement', parentId);
                if (parentNode) {
                    addConnection(parentNode.element.dataset.nodeId, id);
                    linkCount++;
                }
            }
        }

        // API -> Requirement Links (from linked_requirements array or requirement_id)
        if (node.type === 'api') {
            if (node.data.linked_requirements && Array.isArray(node.data.linked_requirements)) {
                node.data.linked_requirements.forEach(reqId => {
                    if (state.nodes[reqId]) {
                        addConnection(reqId, id);
                        linkCount++;
                    }
                });
            }
            if (node.data.requirement_id && state.nodes[node.data.requirement_id]) {
                addConnection(node.data.requirement_id, id);
                linkCount++;
            }
        }

        // Tech Stack -> Feature/Requirement Links
        if (node.type === 'tech-stack') {
            const parentId = node.data.feature_id || node.data.requirement_id;
            if (parentId && state.nodes[parentId]) {
                addConnection(parentId, id);
                linkCount++;
            }
        }

        // Task -> Feature Links (additional check for parent_feature_id in task.data)
        if (node.type === 'task') {
            const parentId = node.data.parent_feature_id || node.data.feature_id;
            if (parentId) {
                const featureNode = state.nodes[parentId] ||
                                   findNodeByPartialId('feature', parentId) ||
                                   findNodeByPartialId('epic', parentId);
                if (featureNode) {
                    const featureNodeId = featureNode.element?.dataset?.nodeId || parentId;
                    addConnection(featureNodeId, id);
                    linkCount++;
                }
            }
        }

        // Screen -> User Story Links (from parent_user_story, user_story_id)
        if (node.type === 'screen') {
            const parentId = node.data.parent_user_story || node.data.user_story_id;
            if (parentId) {
                const usNode = state.nodes[parentId] || findNodeByPartialId('user-story', parentId);
                if (usNode) {
                    const usNodeId = usNode.element?.dataset?.nodeId || parentId;
                    addConnection(usNodeId, id);
                    linkCount++;
                }
            }
        }

        // Component -> Screen Links (from parent_screen, screen_id)
        if (node.type === 'component') {
            const parentId = node.data.parent_screen || node.data.screen_id;
            if (parentId) {
                const screenNode = state.nodes[parentId] || findNodeByPartialId('screen', parentId);
                if (screenNode) {
                    const screenNodeId = screenNode.element?.dataset?.nodeId || parentId;
                    addConnection(screenNodeId, id);
                    linkCount++;
                }
            }
        }

        // Test -> Requirement Links (from requirement_id, parent_requirement)
        if (node.type === 'test') {
            const parentId = node.data.requirement_id || node.data.parent_requirement || node.data.parent_req;
            if (parentId) {
                const reqNode = state.nodes[parentId] || findNodeByPartialId('requirement', parentId);
                if (reqNode) {
                    const reqNodeId = reqNode.element?.dataset?.nodeId || parentId;
                    addConnection(reqNodeId, id);
                    linkCount++;
                }
            }
        }
    });

    console.log(`[Auto-Link] Applied ${linkCount} metadata-based links`);
}

// ============================================
// Detail Panel
// ============================================

function showDetailPanel(nodeId, nodeData) {
    let panel = document.getElementById('detail-panel');

    // Create panel if not exists
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'detail-panel';
        panel.className = 'detail-panel';
        document.body.appendChild(panel);
    }

    // Build content based on node type
    let content = `
        <div class="detail-header">
            <h3>${nodeId}</h3>
            <button onclick="hideDetailPanel()" class="close-btn">×</button>
        </div>
        <div class="detail-type">${nodeData.type}</div>
        <div class="detail-title">${nodeData.data.title || ''}</div>
    `;

    // Show description if available
    if (nodeData.data.description) {
        content += `<div class="detail-description">${nodeData.data.description}</div>`;
    }

    // Show connections
    const incoming = state.connections.filter(c => c.to === nodeId);
    const outgoing = state.connections.filter(c => c.from === nodeId);

    if (incoming.length > 0) {
        content += `
            <div class="detail-section">
                <h4>← Eingehende Links (${incoming.length})</h4>
                <ul class="link-list">
                    ${incoming.map(c => `<li onclick="focusNode('${c.from}')">${c.from}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    if (outgoing.length > 0) {
        content += `
            <div class="detail-section">
                <h4>→ Ausgehende Links (${outgoing.length})</h4>
                <ul class="link-list">
                    ${outgoing.map(c => `<li onclick="focusNode('${c.to}')">${c.to}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Type-specific content
    if (nodeData.type === 'user-story') {
        content += `
            <div class="detail-story">
                <p><b>As a</b> ${nodeData.data.persona || 'user'}</p>
                <p><b>I want to</b> ${nodeData.data.action || '...'}</p>
                <p><b>So that</b> ${nodeData.data.benefit || '...'}</p>
            </div>
        `;
    }

    if (nodeData.type === 'api') {
        content += `
            <div class="detail-api">
                <code>${nodeData.data.method} ${nodeData.data.path}</code>
            </div>
        `;
    }

    // Test-specific content with Gherkin highlighting
    if (nodeData.type === 'test') {
        // Scenario count
        const scenarioCount = nodeData.data.scenario_count || 0;
        content += `<div class="detail-scenario-count">${scenarioCount} ${scenarioCount === 1 ? 'Scenario' : 'Scenarios'}</div>`;

        // Tags as badges
        if (nodeData.data.tags && nodeData.data.tags.length > 0) {
            content += `
                <div class="detail-tags">
                    ${nodeData.data.tags.map(tag =>
                        `<span class="tag-badge tag-${getTagType(tag)}">${tag}</span>`
                    ).join('')}
                </div>
            `;
        }

        // Gherkin code with syntax highlighting
        if (nodeData.data.content) {
            content += `
                <div class="detail-gherkin">
                    <pre><code>${highlightGherkin(nodeData.data.content)}</code></pre>
                </div>
            `;
        }
    }

    panel.innerHTML = content;
    panel.classList.add('visible');
}

function hideDetailPanel() {
    const panel = document.getElementById('detail-panel');
    if (panel) {
        panel.classList.remove('visible');
    }
}

// Add click handler to nodes for detail panel
function addNodeClickHandler(nodeElement, nodeId) {
    nodeElement.addEventListener('click', (e) => {
        // Don't show panel if dragging
        if (state.dragging.active) return;

        const nodeData = state.nodes[nodeId];
        if (nodeData) {
            showDetailPanel(nodeId, nodeData);
        }
    });
}

// ============================================
// Work Package Layout Mode
// ============================================

const LAYOUT_MODES = {
    BY_TYPE: 'by_type',
    BY_PACKAGE: 'by_package',
    BY_TRACE: 'by_trace',
    BY_CLUSTER: 'by_cluster',
    BY_HIERARCHY: 'by_hierarchy',
    BY_MATRIX: 'by_matrix',
    LINK_BASED: 'link_based'  // NEW: Hub-and-spoke based on link similarity
};

let currentLayout = LAYOUT_MODES.LINK_BASED;  // Default to new link-based layout
let packageIndex = {};

// ============================================
// Arbeitspakete (Work Packages) Layout Configuration
// ============================================

// Columns sorted by abstraction level: Detail (left) → Abstract (right)
const WORKPACKAGE_COLUMNS = [
    // Detail level (many incoming links)
    { id: 'task', name: 'Tasks', order: 0, width: 320, color: '#f59e0b' },
    { id: 'test', name: 'Tests', order: 1, width: 320, color: '#f4212e' },
    { id: 'component', name: 'Components', order: 2, width: 320, color: '#84cc16' },
    { id: 'screen', name: 'Screens', order: 3, width: 320, color: '#8b5cf6' },
    { id: 'api', name: 'API', order: 4, width: 320, color: '#ff7a00' },
    // Diagrams (by type)
    { id: 'diagram_flowchart', name: 'Flowchart', order: 5, width: 480, color: '#ffd400', isDiagram: true },
    { id: 'diagram_class', name: 'Class', order: 6, width: 480, color: '#ffd400', isDiagram: true },
    { id: 'diagram_sequence', name: 'Sequence', order: 7, width: 480, color: '#ffd400', isDiagram: true },
    { id: 'diagram_er', name: 'ER', order: 8, width: 480, color: '#ffd400', isDiagram: true },
    { id: 'diagram_c4', name: 'C4', order: 9, width: 480, color: '#ffd400', isDiagram: true },
    { id: 'diagram_state', name: 'State', order: 10, width: 480, color: '#ffd400', isDiagram: true },
    // Middle level
    { id: 'user-flow', name: 'User Flows', order: 11, width: 320, color: '#ec4899' },
    { id: 'persona', name: 'Personas', order: 12, width: 320, color: '#f97316' },
    { id: 'user-story', name: 'User Stories', order: 13, width: 320, color: '#00ba7c' },
    // Abstract level (few links, roots)
    { id: 'epic', name: 'Epics', order: 14, width: 320, color: '#7856ff' },
    { id: 'requirement', name: 'Requirements', order: 15, width: 320, color: '#1d9bf0' },
    { id: 'tech-stack', name: 'Tech Stack', order: 16, width: 320, color: '#06b6d4' }
];

// Diagram type order for sub-column sorting
const DIAGRAM_TYPE_ORDER = {
    'flowchart': 0,
    'class': 1,
    'sequence': 2,
    'er': 3,
    'c4': 4,
    'state': 5
};

// Track work package state
let currentWorkPackages = [];

/**
 * Calculate link statistics for each column type
 * Returns object with incoming/outgoing counts and score per column
 * Score: -1 (only outgoing) to +1 (only incoming)
 */
function calculateColumnLinkStats() {
    const columnStats = {};

    // For each non-diagram column, calculate link stats
    WORKPACKAGE_COLUMNS.filter(col => !col.isDiagram).forEach(col => {
        // Find all nodes that would be in this column
        const nodesInColumn = Object.entries(state.nodes)
            .filter(([id, node]) => getWorkPackageColumn(node) === col.id)
            .map(([id, node]) => id);

        let totalIncoming = 0;
        let totalOutgoing = 0;

        nodesInColumn.forEach(nodeId => {
            totalIncoming += state.connections.filter(c => c.to === nodeId).length;
            totalOutgoing += state.connections.filter(c => c.from === nodeId).length;
        });

        // Score: -1 (only outgoing/sources) to +1 (only incoming/sinks)
        const total = totalIncoming + totalOutgoing;
        const score = total === 0 ? 0 : (totalIncoming - totalOutgoing) / total;

        columnStats[col.id] = {
            incoming: totalIncoming,
            outgoing: totalOutgoing,
            nodeCount: nodesInColumn.length,
            score: score
        };
    });

    return columnStats;
}

/**
 * Get columns sorted by link direction
 * Left: columns with mostly outgoing links (sources)
 * Middle: columns with mixed links + diagrams (fixed)
 * Right: columns with mostly incoming links (sinks)
 */
function getSortedColumns() {
    const stats = calculateColumnLinkStats();

    // Separate diagram columns (stay fixed in middle)
    const diagramCols = WORKPACKAGE_COLUMNS.filter(col => col.isDiagram);
    const otherCols = WORKPACKAGE_COLUMNS.filter(col => !col.isDiagram);

    // Sort non-diagram columns by score (low to high = left to right)
    const sortedOtherCols = [...otherCols].sort((a, b) => {
        const scoreA = stats[a.id]?.score ?? 0;
        const scoreB = stats[b.id]?.score ?? 0;
        return scoreA - scoreB;
    });

    // Insert diagrams in the middle
    const midPoint = Math.floor(sortedOtherCols.length / 2);
    const result = [
        ...sortedOtherCols.slice(0, midPoint),
        ...diagramCols,
        ...sortedOtherCols.slice(midPoint)
    ];

    // Debug log
    console.log('[Matrix] Column link stats:', stats);
    console.log('[Matrix] Sorted column order:', result.map(c => `${c.id}(${stats[c.id]?.score?.toFixed(2) ?? 'diag'})`).join(' → '));

    return result;
}

/**
 * Detect work packages from traceability links
 * Returns groups of connected nodes forming traceability chains
 */
function detectWorkPackages() {
    const nodeIds = Object.keys(state.nodes);
    if (nodeIds.length === 0) return [];

    // Build adjacency lists for bidirectional traversal
    const adjacency = {};
    nodeIds.forEach(id => adjacency[id] = new Set());

    state.connections.forEach(conn => {
        if (state.nodes[conn.from] && state.nodes[conn.to]) {
            adjacency[conn.from].add(conn.to);
            adjacency[conn.to].add(conn.from);
        }
    });

    // AUTO-LINK: Connect diagrams to their parent requirements based on ID naming convention
    // e.g., "REQ-001_flowchart" -> "REQ-001", "FR-IMP-001_sequence" -> "FR-IMP-001"
    let autoLinkedCount = 0;
    nodeIds.forEach(id => {
        const node = state.nodes[id];
        if (node.type === 'diagram') {
            // Try to extract requirement ID from diagram ID
            // Patterns: REQ-001_xxx, FR-IMP-001_xxx, NFR-xxx_xxx, etc.
            const match = id.match(/^([A-Z]+-[A-Z]*-?\d+|[A-Z]+-\d+)/i);
            if (match) {
                const reqId = match[1].toUpperCase();
                // Find matching requirement node (case-insensitive)
                const reqNodeId = nodeIds.find(nid =>
                    nid.toUpperCase() === reqId && state.nodes[nid].type === 'requirement'
                );
                if (reqNodeId && !adjacency[reqNodeId].has(id)) {
                    adjacency[reqNodeId].add(id);
                    adjacency[id].add(reqNodeId);
                    autoLinkedCount++;
                }
            }
            // Also try parent_requirement from data
            const parentReq = node.data?.parent_requirement;
            if (parentReq) {
                const reqNodeId = nodeIds.find(nid =>
                    nid.toUpperCase() === parentReq.toUpperCase() && state.nodes[nid].type === 'requirement'
                );
                if (reqNodeId && !adjacency[reqNodeId].has(id)) {
                    adjacency[reqNodeId].add(id);
                    adjacency[id].add(reqNodeId);
                    autoLinkedCount++;
                }
            }
        }
    });
    if (autoLinkedCount > 0) {
        console.log(`[WorkPackages] Auto-linked ${autoLinkedCount} diagrams to requirements`);
    }

    // Find root nodes (Requirements, Epics without parent - nodes with only incoming links)
    const rootTypes = ['requirement', 'epic', 'tech-stack'];
    const potentialRoots = nodeIds.filter(id => {
        const node = state.nodes[id];
        const type = node.type;
        // Check if it's a root type
        if (rootTypes.includes(type)) {
            // Check if it has no outgoing links to other root types
            const hasOutgoingToRoot = state.connections.some(conn =>
                conn.from === id && rootTypes.includes(state.nodes[conn.to]?.type)
            );
            return !hasOutgoingToRoot;
        }
        return false;
    });

    // If no roots found, use nodes with most connections as pseudo-roots
    let roots = potentialRoots;
    if (roots.length === 0) {
        // Fallback: find nodes with highest connectivity
        const connectivity = {};
        nodeIds.forEach(id => connectivity[id] = adjacency[id].size);
        const sortedByConnectivity = [...nodeIds].sort((a, b) => connectivity[b] - connectivity[a]);
        // Take top nodes as roots
        roots = sortedByConnectivity.slice(0, Math.max(1, Math.ceil(nodeIds.length / 10)));
    }

    // Find all connected nodes for each root using BFS
    const visited = new Set();
    const workPackages = [];

    roots.forEach(rootId => {
        if (visited.has(rootId)) return;

        const package_ = {
            id: rootId,
            name: state.nodes[rootId].data?.title || state.nodes[rootId].data?.id || rootId,
            rootType: state.nodes[rootId].type,
            nodes: []
        };

        // BFS to find all connected nodes
        const queue = [rootId];
        while (queue.length > 0) {
            const nodeId = queue.shift();
            if (visited.has(nodeId)) continue;
            visited.add(nodeId);

            const nodeData = state.nodes[nodeId];
            if (nodeData) {
                package_.nodes.push({
                    id: nodeId,
                    type: nodeData.type,
                    data: nodeData.data,
                    element: nodeData.element
                });
            }

            // Add all connected nodes to queue
            adjacency[nodeId].forEach(connectedId => {
                if (!visited.has(connectedId)) {
                    queue.push(connectedId);
                }
            });
        }

        if (package_.nodes.length > 0) {
            workPackages.push(package_);
        }
    });

    // Collect orphan nodes (not in any work package)
    const orphans = nodeIds.filter(id => !visited.has(id));
    if (orphans.length > 0) {
        workPackages.push({
            id: '__orphans__',
            name: 'Unverlinkt',
            rootType: 'orphan',
            isOrphanPackage: true,
            nodes: orphans.map(id => ({
                id,
                type: state.nodes[id].type,
                data: state.nodes[id].data,
                element: state.nodes[id].element
            }))
        });
    }

    return workPackages;
}

/**
 * Get the column ID for a node based on its type
 */
function getWorkPackageColumn(node) {
    const type = node.type;

    // Handle diagrams - map to specific diagram type column
    if (type === 'diagram') {
        const diagramType = getDiagramType(node.data);
        return `diagram_${diagramType}`;
    }

    // Direct type mapping
    const typeToColumn = {
        'requirement': 'requirement',
        'epic': 'epic',
        'user-story': 'user-story',
        'test': 'test',
        'api': 'api',
        'persona': 'persona',
        'user-flow': 'user-flow',
        'screen': 'screen',
        'component': 'component',
        'task': 'task',
        'tech-stack': 'tech-stack'
    };

    return typeToColumn[type] || 'requirement';
}

function setLayout(mode) {
    currentLayout = mode;
    console.log(`[Layout] Switching to: ${mode}`);

    // Clean up previous layout structures
    cleanupLayoutStructures();

    // Apply new layout
    if (mode === LAYOUT_MODES.BY_PACKAGE) {
        reorganizeNodesByPackage();  // NEW: Package-based layout
    } else if (mode === LAYOUT_MODES.LINK_BASED) {
        reorganizeNodesLinkBased();
    } else if (mode === LAYOUT_MODES.BY_CLUSTER) {
        reorganizeNodesAsCluster();
    } else if (mode === LAYOUT_MODES.BY_HIERARCHY) {
        reorganizeNodesHierarchical();
    } else if (mode === LAYOUT_MODES.BY_MATRIX) {
        reorganizeNodesMatrix();
    } else {
        reorganizeNodes();
    }

    // Toggle grid visibility based on mode
    const gridStructure = document.getElementById('matrix-grid-structure');
    if (gridStructure) {
        gridStructure.style.display = mode === LAYOUT_MODES.BY_MATRIX ? 'block' : 'none';
    }

    // Update UI
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.layout === mode);
    });

    // Fit to view after layout change
    setTimeout(() => fitToView(), 150);
}

/**
 * Clean up layout-specific DOM structures when switching layouts.
 */
function cleanupLayoutStructures() {
    // Remove matrix grid structure
    const matrixGrid = document.getElementById('matrix-grid-structure');
    if (matrixGrid) matrixGrid.style.display = 'none';

    // Remove link layout structure
    const linkStructure = document.getElementById('link-layout-structure');
    if (linkStructure) linkStructure.remove();
}

function reorganizeNodes() {
    // Reset package index
    packageIndex = {};

    Object.entries(state.nodes).forEach(([nodeId, nodeData]) => {
        const newPos = calculateNodePositionByLayout(nodeData.type, nodeId, nodeData.data);
        nodeData.x = newPos.x;
        nodeData.y = newPos.y;
        nodeData.element.style.left = `${newPos.x}px`;
        nodeData.element.style.top = `${newPos.y}px`;
    });

    updateConnections();
    updateMinimap();

    // Now that layout is complete, re-render all diagrams
    setTimeout(() => reRenderAllDiagrams(), 500);
}

function calculateNodePositionByLayout(type, id, data) {
    switch (currentLayout) {
        case LAYOUT_MODES.BY_PACKAGE:
            return calculatePackagePosition(type, id, data);
        case LAYOUT_MODES.BY_TRACE:
            return calculateTracePosition(type, id, data);
        case LAYOUT_MODES.BY_CLUSTER:
            return calculateClusterPosition(type, id, data);
        default:
            return calculateNodePosition(type, id);
    }
}

function calculateClusterPosition(type, id, data) {
    // Group connected nodes together in clusters
    const clusters = detectClusters();

    // Find which cluster this node belongs to
    let clusterIndex = clusters.findIndex(cluster => cluster.includes(id));

    // If not in any cluster, place in "unassigned" area
    if (clusterIndex === -1) {
        const unassignedNodes = Object.keys(state.nodes).filter(nodeId =>
            !clusters.some(cluster => cluster.includes(nodeId))
        );
        const unassignedIndex = unassignedNodes.indexOf(id);
        return {
            x: 5000 + 1500, // Far right for unassigned
            y: 5000 + (unassignedIndex >= 0 ? unassignedIndex : 0) * 120
        };
    }

    const cluster = clusters[clusterIndex];
    const nodeIndexInCluster = cluster.indexOf(id);

    // Calculate cluster layout - arrange in a grid within the cluster
    const clusterCols = 3;  // Reduced from 4 for better spacing
    const nodeCol = nodeIndexInCluster % clusterCols;
    const nodeRow = Math.floor(nodeIndexInCluster / clusterCols);

    // Cluster positioning - spread clusters horizontally
    const clusterWidth = 600;  // Increased from 400
    const clusterGap = 150;    // Increased from 100
    const clusterX = 5000 + clusterIndex * (clusterWidth + clusterGap);
    const clusterY = 5000;

    // Node positioning within cluster - increased spacing
    const nodeWidth = 280;    // Increased from 220
    const nodeHeight = 200;   // Increased from 120
    const nodePadding = 30;   // Increased from 20

    return {
        x: clusterX + nodeCol * (nodeWidth + nodePadding),
        y: clusterY + nodeRow * (nodeHeight + nodePadding) + 40 // +40 for cluster label
    };
}

function calculatePackagePosition(type, id, data) {
    // Group nodes by their parent Epic/Feature
    const packageId = getPackageId(type, id, data);

    if (!packageIndex[packageId]) {
        packageIndex[packageId] = {
            index: Object.keys(packageIndex).length,
            counts: {}
        };
    }

    const pkg = packageIndex[packageId];
    const typeOrder = { 'epic': 0, 'requirement': 1, 'user-story': 2, 'test': 3, 'diagram': 4, 'api': 5 };

    if (!pkg.counts[type]) pkg.counts[type] = 0;
    const instanceIndex = pkg.counts[type]++;

    // Increased vertical spacing - diagrams need more space
    const isDiagram = type === 'diagram';
    const verticalSpacing = isDiagram ? 450 : 200;  // Was 120 for all
    const typeHeight = isDiagram ? 500 : 250;  // Was 200 for all

    const baseX = 5000 + pkg.index * 500;
    const typeY = (typeOrder[type] || 5) * typeHeight;
    const instanceY = instanceIndex * verticalSpacing;

    return { x: baseX, y: 5000 + typeY + instanceY };
}

function calculateTracePosition(type, id, data) {
    // Layout in trace chains: REQ -> US -> TEST (horizontal)
    const typeColumns = {
        'epic': 0,
        'requirement': 1,
        'user-story': 2,
        'test': 3,
        'diagram': 4,
        'api': 5
    };

    const column = typeColumns[type] || 0;
    const nodesOfType = Object.values(state.nodes).filter(n => n.type === type);
    const rowIndex = nodesOfType.findIndex(n => n.element.dataset.nodeId === id);
    const row = rowIndex >= 0 ? rowIndex : nodesOfType.length;

    // Increased spacing - diagrams need more vertical space
    const isDiagram = type === 'diagram';
    const rowHeight = isDiagram ? 450 : 200;  // Was 150 for all
    const colWidth = isDiagram ? 500 : 350;   // Wider columns for diagrams

    return {
        x: 5000 + column * colWidth,
        y: 5000 + row * rowHeight
    };
}

function getPackageId(type, id, data) {
    // Determine which package this node belongs to
    if (type === 'epic' || type === 'requirement' && id.startsWith('FEAT-')) {
        return id;
    }

    // Check if user story is linked to a requirement/epic
    if (type === 'user-story' && data && data.linked_requirement) {
        return data.linked_requirement;
    }

    // Check through connections
    const incoming = state.connections.filter(c => c.to === id);
    if (incoming.length > 0) {
        const parent = state.nodes[incoming[0].from];
        if (parent && (parent.type === 'epic' || parent.type === 'requirement')) {
            return incoming[0].from;
        }
    }

    return 'unassigned';
}

// ============================================
// Cluster Visualization
// ============================================

/**
 * Check if two rectangles collide/overlap.
 * @param {Object} rect1 - First rectangle with {minX, minY, maxX, maxY}
 * @param {Object} rect2 - Second rectangle with {minX, minY, maxX, maxY}
 * @param {number} padding - Additional padding/margin to enforce between rectangles
 * @returns {boolean} - True if rectangles overlap
 */
function rectsCollide(rect1, rect2, padding = 0) {
    return !(rect1.maxX + padding < rect2.minX ||
             rect2.maxX + padding < rect1.minX ||
             rect1.maxY + padding < rect2.minY ||
             rect2.maxY + padding < rect1.minY);
}

/**
 * Calculate bounding box for a cluster of nodes.
 * @param {Array} cluster - Array of node IDs in the cluster
 * @param {number} padding - Padding around the bounding box
 * @returns {Object} - Bounding box {minX, minY, maxX, maxY, width, height}
 */
function calculateClusterBounds(cluster, padding = 30) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    cluster.forEach(nodeId => {
        const node = state.nodes[nodeId];
        if (node) {
            const x = node.x;
            const y = node.y;
            const isDiagram = node.type === 'diagram';

            // Use actual element size if available, otherwise use type-specific defaults
            // Diagrams are typically much larger than regular nodes
            let width = node.element?.offsetWidth || (isDiagram ? 400 : 200);
            let height = node.element?.offsetHeight || (isDiagram ? 300 : 100);

            // Ensure minimum sizes for diagrams (Mermaid SVGs can be large)
            if (isDiagram) {
                width = Math.max(width, 350);
                height = Math.max(height, 250);
            }

            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x + width);
            maxY = Math.max(maxY, y + height);
        }
    });

    // Add padding
    minX -= padding;
    minY -= padding;
    maxX += padding;
    maxY += padding;

    return {
        minX,
        minY,
        maxX,
        maxY,
        width: maxX - minX,
        height: maxY - minY
    };
}

function detectClusters() {
    const MAX_FIND_DEPTH = 1000;

    console.log('[DEBUG] Starting detectClusters');

    // Find connected components using Union-Find
    const parent = {};
    const nodeIds = Object.keys(state.nodes);

    // Initialize each node as its own parent
    nodeIds.forEach(id => parent[id] = id);

    function find(id, depth = 0) {
        // Safety check: prevent infinite recursion
        if (depth > MAX_FIND_DEPTH) {
            console.warn(`[Layout] Union-Find depth limit reached for ${id}`);
            return id;
        }
        if (parent[id] !== id) {
            parent[id] = find(parent[id], depth + 1); // Path compression
        }
        return parent[id];
    }

    function union(a, b) {
        const rootA = find(a);
        const rootB = find(b);
        if (rootA !== rootB) {
            parent[rootA] = rootB;
        }
    }

    // Union connected nodes
    state.connections.forEach(conn => {
        if (state.nodes[conn.from] && state.nodes[conn.to]) {
            union(conn.from, conn.to);
        }
    });

    // Group nodes by cluster root
    const clusters = {};
    nodeIds.forEach(id => {
        const root = find(id);
        if (!clusters[root]) {
            clusters[root] = [];
        }
        clusters[root].push(id);
    });

    const result = Object.values(clusters).filter(c => c.length >= 2);
    console.log(`[DEBUG] detectClusters completed: ${result.length} clusters found`);

    // Filter to only clusters with 2+ nodes
    return result;
}

function renderClusterBackgrounds() {
    // Remove existing cluster backgrounds
    const existingClusters = elements.connectionsLayer.querySelectorAll('.cluster-bg');
    existingClusters.forEach(el => el.remove());

    const clusters = detectClusters();

    // Cluster colors (semi-transparent)
    const clusterColors = [
        'rgba(30, 58, 95, 0.25)',   // Blue
        'rgba(30, 77, 58, 0.25)',   // Green
        'rgba(74, 30, 95, 0.25)',   // Purple
        'rgba(95, 58, 30, 0.25)',   // Orange
        'rgba(58, 58, 30, 0.25)',   // Yellow
        'rgba(95, 30, 30, 0.25)',   // Red
    ];

    // First pass: calculate all cluster bounds and detect collisions
    const clusterData = clusters.map((cluster, index) => {
        const bounds = calculateClusterBounds(cluster, 30);
        return { cluster, bounds, index, offsetX: 0 };
    });

    // Sort by X position for consistent collision detection
    clusterData.sort((a, b) => a.bounds.minX - b.bounds.minX);

    // NOTE: Collision detection for node repositioning is now ONLY done in layout functions
    // (reorganizeNodesAsCluster, reorganizeNodesHierarchical, etc.)
    // This function only renders backgrounds at current node positions - no repositioning here!

    // Draw backgrounds at current node positions
    clusterData.forEach(({ cluster, bounds, index }) => {
        // Use current bounds directly - no offset adjustment
        const finalMinX = bounds.minX;
        const finalMaxX = bounds.maxX;
        const { minY, maxY } = bounds;

        // Create background rectangle
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.classList.add('cluster-bg');
        rect.setAttribute('x', finalMinX);
        rect.setAttribute('y', minY);
        rect.setAttribute('width', finalMaxX - finalMinX);
        rect.setAttribute('height', maxY - minY);
        rect.setAttribute('rx', '16');
        rect.setAttribute('ry', '16');
        rect.setAttribute('fill', clusterColors[index % clusterColors.length]);
        rect.setAttribute('stroke', clusterColors[index % clusterColors.length].replace('0.25', '0.5'));
        rect.setAttribute('stroke-width', '2');
        rect.setAttribute('stroke-dasharray', '8 4');

        // Find cluster root for label
        const rootId = cluster[0];
        const rootNode = state.nodes[rootId];
        const clusterLabel = rootNode?.data?.title || rootId;

        // Add label
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.classList.add('cluster-bg');
        text.setAttribute('x', finalMinX + 12);
        text.setAttribute('y', minY + 20);
        text.setAttribute('fill', 'rgba(255, 255, 255, 0.6)');
        text.setAttribute('font-size', '12');
        text.setAttribute('font-weight', '500');
        text.textContent = `Cluster: ${clusterLabel} (${cluster.length} nodes)`;

        // Insert at beginning so it's behind nodes
        elements.connectionsLayer.prepend(text);
        elements.connectionsLayer.prepend(rect);
    });

    console.log(`[Cluster] Rendered ${clusters.length} cluster backgrounds`);
}

// ============================================
// Cluster Layout: Vertical Organization
// ============================================

/**
 * Reorganize all nodes so that connected nodes are arranged vertically in clusters.
 * Each cluster is positioned horizontally, with nodes stacked vertically by hierarchy.
 * Uses collision detection to prevent cluster overlap.
 */
function reorganizeNodesAsCluster() {
    // 1. Find all connected components (clusters)
    const clusters = findConnectedComponents();

    // 2. Configuration
    const minClusterGap = 100;          // Minimum gap between cluster boundaries
    const nodeSpacingH = 240;           // Horizontal spacing between nodes
    const nodeSpacingV = 140;           // Vertical spacing between nodes
    const diagramSpacingH = 420;        // Horizontal spacing for diagrams
    const diagramSpacingV = 320;        // Vertical spacing for diagrams
    const startX = 3500;
    const startY = 3000;

    // Sort clusters by size (largest first)
    clusters.sort((a, b) => b.length - a.length);

    // Track placed cluster bounds for collision detection
    const placedClusterBounds = [];

    clusters.forEach((cluster, clusterIndex) => {
        // Group nodes by type
        const nodesByType = {
            epic: [],
            requirement: [],
            'user-story': [],
            persona: [],
            'user-flow': [],
            screen: [],
            component: [],
            test: [],
            diagram: [],
            api: [],
            entity: [],
            feature: [],
            task: [],
            'tech-stack': []
        };

        cluster.forEach(nodeId => {
            const node = state.nodes[nodeId];
            if (node) {
                const type = node.type || 'other';
                if (nodesByType[type]) {
                    nodesByType[type].push(nodeId);
                }
            }
        });

        // Sort each type by ID
        Object.keys(nodesByType).forEach(type => {
            nodesByType[type].sort((a, b) => a.localeCompare(b));
        });

        // Calculate cluster layout with Epic centered
        // Layout structure:
        //        [Requirements row]
        //      [Epic centered row]
        //       [User Stories row]
        //          [Tests row]
        //        [Diagrams row]

        const positions = [];
        let clusterMinX = Infinity, clusterMinY = Infinity;
        let clusterMaxX = -Infinity, clusterMaxY = -Infinity;

        // Helper to add a node position
        const addPosition = (nodeId, x, y, isDiagram = false) => {
            positions.push({ nodeId, x, y });
            const w = isDiagram ? 400 : 220;
            const h = isDiagram ? 280 : 100;
            clusterMinX = Math.min(clusterMinX, x);
            clusterMinY = Math.min(clusterMinY, y);
            clusterMaxX = Math.max(clusterMaxX, x + w);
            clusterMaxY = Math.max(clusterMaxY, y + h);
        };

        let centerX = 0;
        let currentY = 0;

        // Row 1: Requirements (above Epic)
        if (nodesByType.requirement.length > 0) {
            const reqCount = nodesByType.requirement.length;
            const reqRowWidth = reqCount * nodeSpacingH;
            let reqX = centerX - reqRowWidth / 2 + nodeSpacingH / 2;
            nodesByType.requirement.forEach(nodeId => {
                addPosition(nodeId, reqX, currentY);
                reqX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 2: Epics (centered)
        if (nodesByType.epic.length > 0) {
            const epicCount = nodesByType.epic.length;
            const epicRowWidth = epicCount * nodeSpacingH;
            let epicX = centerX - epicRowWidth / 2 + nodeSpacingH / 2;
            nodesByType.epic.forEach(nodeId => {
                addPosition(nodeId, epicX, currentY);
                epicX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 3: User Stories (below Epic)
        if (nodesByType['user-story'].length > 0) {
            const usCount = nodesByType['user-story'].length;
            const usRowWidth = usCount * nodeSpacingH;
            let usX = centerX - usRowWidth / 2 + nodeSpacingH / 2;
            nodesByType['user-story'].forEach(nodeId => {
                addPosition(nodeId, usX, currentY);
                usX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 4: Tests (below User Stories)
        if (nodesByType.test.length > 0) {
            const testCount = nodesByType.test.length;
            const testRowWidth = testCount * nodeSpacingH;
            let testX = centerX - testRowWidth / 2 + nodeSpacingH / 2;
            nodesByType.test.forEach(nodeId => {
                addPosition(nodeId, testX, currentY);
                testX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 5: Personas and User Flows (below Tests)
        const uxNodes = [...nodesByType.persona, ...nodesByType['user-flow']];
        if (uxNodes.length > 0) {
            const uxCount = uxNodes.length;
            const uxRowWidth = uxCount * nodeSpacingH;
            let uxX = centerX - uxRowWidth / 2 + nodeSpacingH / 2;
            uxNodes.forEach(nodeId => {
                addPosition(nodeId, uxX, currentY);
                uxX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 6: Screens and Components (below UX)
        const uiNodes = [...nodesByType.screen, ...nodesByType.component];
        if (uiNodes.length > 0) {
            const uiCount = uiNodes.length;
            const uiRowWidth = uiCount * nodeSpacingH;
            let uiX = centerX - uiRowWidth / 2 + nodeSpacingH / 2;
            uiNodes.forEach(nodeId => {
                addPosition(nodeId, uiX, currentY);
                uiX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 7: APIs, Entities, Features (below UI)
        const miscNodes = [...nodesByType.api, ...nodesByType.entity, ...nodesByType.feature];
        if (miscNodes.length > 0) {
            const miscCount = miscNodes.length;
            const miscRowWidth = miscCount * nodeSpacingH;
            let miscX = centerX - miscRowWidth / 2 + nodeSpacingH / 2;
            miscNodes.forEach(nodeId => {
                addPosition(nodeId, miscX, currentY);
                miscX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 8: Tasks and Tech Stack (below misc)
        const devNodes = [...nodesByType.task, ...nodesByType['tech-stack']];
        if (devNodes.length > 0) {
            const devCount = devNodes.length;
            const devRowWidth = devCount * nodeSpacingH;
            let devX = centerX - devRowWidth / 2 + nodeSpacingH / 2;
            devNodes.forEach(nodeId => {
                addPosition(nodeId, devX, currentY);
                devX += nodeSpacingH;
            });
            currentY += nodeSpacingV;
        }

        // Row 6: Diagrams (at the bottom, with larger spacing)
        if (nodesByType.diagram.length > 0) {
            currentY += 50; // Extra gap before diagrams
            const diagCount = nodesByType.diagram.length;
            const diagsPerRow = 3;
            const diagRows = Math.ceil(diagCount / diagsPerRow);

            for (let row = 0; row < diagRows; row++) {
                const startIdx = row * diagsPerRow;
                const endIdx = Math.min(startIdx + diagsPerRow, diagCount);
                const rowDiags = nodesByType.diagram.slice(startIdx, endIdx);
                const rowWidth = rowDiags.length * diagramSpacingH;
                let diagX = centerX - rowWidth / 2 + diagramSpacingH / 2;

                rowDiags.forEach(nodeId => {
                    addPosition(nodeId, diagX, currentY, true);
                    diagX += diagramSpacingH;
                });
                currentY += diagramSpacingV;
            }
        }

        // Calculate cluster dimensions
        const clusterWidth = clusterMaxX - clusterMinX + 60;
        const clusterHeight = clusterMaxY - clusterMinY + 60;

        // Find X position that doesn't collide with existing clusters
        let offsetX = startX - clusterMinX + 30;
        let offsetY = startY - clusterMinY + 30;

        const proposedBounds = {
            minX: startX,
            minY: startY,
            maxX: startX + clusterWidth,
            maxY: startY + clusterHeight
        };

        // Check for collisions and adjust X position
        let collisionFound = true;
        let iterations = 0;
        const maxIterations = 100;

        while (collisionFound && iterations < maxIterations) {
            collisionFound = false;

            for (const existingBounds of placedClusterBounds) {
                if (rectsCollide(proposedBounds, existingBounds, minClusterGap)) {
                    const shiftX = existingBounds.maxX + minClusterGap - proposedBounds.minX;
                    offsetX += shiftX;
                    proposedBounds.minX += shiftX;
                    proposedBounds.maxX += shiftX;
                    collisionFound = true;
                    break;
                }
            }
            iterations++;
        }

        // Apply positions to nodes
        positions.forEach(({ nodeId, x, y }) => {
            const node = state.nodes[nodeId];
            if (node && node.element) {
                node.x = x + offsetX;
                node.y = y + offsetY;
                node.element.style.left = `${node.x}px`;
                node.element.style.top = `${node.y}px`;
            }
        });

        // Store final bounds
        placedClusterBounds.push({
            minX: proposedBounds.minX,
            minY: proposedBounds.minY,
            maxX: proposedBounds.maxX,
            maxY: proposedBounds.maxY
        });
    });

    // 3. Handle unconnected nodes (place them to the right of all clusters)
    const connectedNodeIds = new Set(clusters.flat());
    const unconnectedNodes = Object.keys(state.nodes).filter(id => !connectedNodeIds.has(id));

    if (unconnectedNodes.length > 0) {
        // Find the rightmost cluster boundary
        let maxRightX = startX;
        placedClusterBounds.forEach(bounds => {
            maxRightX = Math.max(maxRightX, bounds.maxX);
        });

        const unconnectedX = maxRightX + minClusterGap + 100;
        let currentUnconnectedY = startY;
        unconnectedNodes.forEach((nodeId) => {
            const node = state.nodes[nodeId];
            if (node && node.element) {
                const isDiagram = node.type === 'diagram';
                node.x = unconnectedX;
                node.y = currentUnconnectedY;
                node.element.style.left = `${unconnectedX}px`;
                node.element.style.top = `${currentUnconnectedY}px`;
                // Increment Y based on current node type for next node
                currentUnconnectedY += isDiagram ? diagramSpacingV : nodeSpacingV;
            }
        });
    }

    updateConnections();
    updateMinimap();
    log('info', `Reorganized ${clusters.length} clusters + ${unconnectedNodes.length} unconnected nodes (no overlaps)`);

    // Now that layout is complete, re-render all diagrams
    setTimeout(() => reRenderAllDiagrams(), 500);
}

/**
 * Find all connected components using DFS.
 * Returns array of arrays, each containing node IDs in a cluster.
 */
function findConnectedComponents() {
    const MAX_ITERATIONS = 1000;
    let iterations = 0;

    console.log('[DEBUG] Starting findConnectedComponents');

    const visited = new Set();
    const clusters = [];

    // Get all node IDs
    const allNodeIds = Object.keys(state.nodes);

    // Build adjacency list from connections (bidirectional)
    const adjacency = {};
    allNodeIds.forEach(id => adjacency[id] = []);

    state.connections.forEach(conn => {
        if (adjacency[conn.from] && state.nodes[conn.to]) {
            adjacency[conn.from].push(conn.to);
        }
        if (adjacency[conn.to] && state.nodes[conn.from]) {
            adjacency[conn.to].push(conn.from);
        }
    });

    // DFS to find connected components with safety limit
    function dfs(nodeId, cluster) {
        if (iterations++ > MAX_ITERATIONS) {
            console.warn('[Layout] DFS iteration limit reached in findConnectedComponents');
            return;
        }
        if (visited.has(nodeId)) return;
        visited.add(nodeId);
        cluster.push(nodeId);

        (adjacency[nodeId] || []).forEach(neighbor => {
            dfs(neighbor, cluster);
        });
    }

    allNodeIds.forEach(nodeId => {
        if (!visited.has(nodeId)) {
            const cluster = [];
            dfs(nodeId, cluster);
            if (cluster.length > 1) {
                // Only include clusters with connections
                clusters.push(cluster);
            }
        }
    });

    console.log(`[DEBUG] findConnectedComponents completed: ${clusters.length} clusters, ${iterations} iterations`);
    return clusters;
}

/**
 * Hierarchical layout based on connection topology.
 * Places nodes left-to-right based on their hierarchy level (root -> children -> grandchildren).
 * Better for visualizing parent-child relationships.
 */
/**
 * Recursively layout a tree from root.
 * Children are positioned vertically below their parent, one level to the right.
 * Returns the total height used by this subtree.
 */
function layoutTreeRecursive(nodeId, x, y, hierarchy, positions, config, visited, depth = 0) {
    const MAX_DEPTH = 100;
    const { levelSpacing, nodeSpacing, diagramSpacing } = config;

    // Safety check: max recursion depth
    if (depth > MAX_DEPTH) {
        console.warn(`[Layout] Max recursion depth reached for node ${nodeId}`);
        return 0;
    }

    // Prevent infinite loops in cyclic graphs
    if (visited.has(nodeId)) {
        return 0;
    }
    visited.add(nodeId);

    // Position this node
    positions.set(nodeId, { x, y });

    // Get spacing based on THIS node's type (diagrams need more space)
    const nodeType = state.nodes[nodeId]?.type;
    const thisNodeSpacing = nodeType === 'diagram' ? diagramSpacing : nodeSpacing;

    // Get children (sorted by ID for consistency)
    const childrenIds = (hierarchy.children.get(nodeId) || [])
        .filter(id => !visited.has(id))
        .sort((a, b) => a.localeCompare(b));

    if (childrenIds.length === 0) {
        return thisNodeSpacing;  // Leaf node height based on type
    }

    // Separate diagram children from regular children
    const diagramChildren = childrenIds.filter(id => state.nodes[id]?.type === 'diagram');
    const regularChildren = childrenIds.filter(id => state.nodes[id]?.type !== 'diagram');

    let totalHeight = 0;
    let currentY = y;

    // Layout regular children vertically (normal tree layout)
    regularChildren.forEach((childId) => {
        const subtreeHeight = layoutTreeRecursive(
            childId,
            x + levelSpacing,
            currentY,
            hierarchy,
            positions,
            config,
            visited,
            depth + 1
        );
        currentY += subtreeHeight;
        totalHeight += subtreeHeight;
    });

    // Layout diagram children in a GRID (max 3 columns) for better space usage
    if (diagramChildren.length > 0) {
        const DIAGRAM_COLS = 3;  // Max diagrams per row
        const diagramWidth = 450;   // Width of each diagram cell
        const diagramHeight = diagramSpacing;  // Height of each diagram cell

        diagramChildren.forEach((childId, index) => {
            const col = index % DIAGRAM_COLS;
            const row = Math.floor(index / DIAGRAM_COLS);

            // Mark as visited to prevent re-processing
            visited.add(childId);

            // Position in grid
            const diagX = x + levelSpacing + (col * diagramWidth);
            const diagY = currentY + (row * diagramHeight);
            positions.set(childId, { x: diagX, y: diagY });
        });

        // Calculate total height used by diagram grid
        const diagramRows = Math.ceil(diagramChildren.length / DIAGRAM_COLS);
        const diagramGridHeight = diagramRows * diagramHeight;
        totalHeight += diagramGridHeight;
    }

    // Ensure minimum height based on this node's type
    return Math.max(totalHeight, thisNodeSpacing);
}

function reorganizeNodesHierarchical() {
    const clusters = findConnectedComponents();

    // Sort clusters by size (largest first)
    clusters.sort((a, b) => b.length - a.length);

    const startX = 3200;
    const startY = 3200;
    const clusterGap = 400;       // Gap between different trees
    const levelSpacing = 350;     // Horizontal spacing (right)
    const nodeSpacing = 160;      // Vertical spacing for regular nodes (100px + 60px gap)
    const diagramSpacing = 380;   // Vertical spacing for diagrams (280px + 100px gap)

    let currentY = startY;

    clusters.forEach((cluster, clusterIndex) => {
        // Build hierarchy for this cluster
        const hierarchy = buildClusterHierarchy(cluster);
        const positions = new Map();
        const visited = new Set();

        // Sort roots by type and ID for consistent ordering
        // Prioritize epics, requirements, features as roots
        const ROOT_TYPE_ORDER = ['epic', 'requirement', 'feature', 'persona'];
        const sortedRoots = hierarchy.roots.sort((a, b) => {
            const typeA = state.nodes[a]?.type || '';
            const typeB = state.nodes[b]?.type || '';
            const orderA = ROOT_TYPE_ORDER.indexOf(typeA);
            const orderB = ROOT_TYPE_ORDER.indexOf(typeB);
            // Prioritize known root types
            if (orderA !== -1 && orderB === -1) return -1;
            if (orderA === -1 && orderB !== -1) return 1;
            if (orderA !== orderB) return orderA - orderB;
            return a.localeCompare(b);
        });

        // Layout each root's tree
        sortedRoots.forEach(rootId => {
            const subtreeHeight = layoutTreeRecursive(
                rootId,
                startX,
                currentY,
                hierarchy,
                positions,
                { levelSpacing, nodeSpacing, diagramSpacing },
                visited
            );
            currentY += subtreeHeight + nodeSpacing;  // Gap between root trees
        });

        // Handle any orphaned nodes not reachable from roots
        cluster.forEach(nodeId => {
            if (!positions.has(nodeId)) {
                positions.set(nodeId, { x: startX, y: currentY });
                const nodeType = state.nodes[nodeId]?.type;
                currentY += nodeType === 'diagram' ? diagramSpacing : nodeSpacing;
            }
        });

        // Apply positions to nodes
        positions.forEach(({ x, y }, nodeId) => {
            const node = state.nodes[nodeId];
            if (node && node.element) {
                node.x = x;
                node.y = y;
                node.element.style.left = `${x}px`;
                node.element.style.top = `${y}px`;
            }
        });

        currentY += clusterGap;  // Gap before next cluster
    });

    // Handle unconnected nodes - separate diagrams from regular nodes
    const connectedNodeIds = new Set(clusters.flat());
    const unconnectedNodes = Object.keys(state.nodes).filter(id => !connectedNodeIds.has(id));

    if (unconnectedNodes.length > 0) {
        // Separate diagrams from regular nodes
        const unconnectedDiagrams = unconnectedNodes.filter(id => state.nodes[id]?.type === 'diagram');
        const unconnectedRegular = unconnectedNodes.filter(id => state.nodes[id]?.type !== 'diagram');

        currentY += 150;  // Extra gap before unconnected nodes

        // Layout regular nodes in a grid
        if (unconnectedRegular.length > 0) {
            const gridCols = 6;
            const nodeWidth = 260;
            const nodeHeight = 170;

            unconnectedRegular.forEach((nodeId, index) => {
                const col = index % gridCols;
                const row = Math.floor(index / gridCols);
                const node = state.nodes[nodeId];
                if (node && node.element) {
                    node.x = startX + col * nodeWidth;
                    node.y = currentY + row * nodeHeight;
                    node.element.style.left = `${node.x}px`;
                    node.element.style.top = `${node.y}px`;
                }
            });
            currentY += Math.ceil(unconnectedRegular.length / gridCols) * nodeHeight + 100;
        }

        // Layout diagrams in a grid with larger spacing
        if (unconnectedDiagrams.length > 0) {
            const diagramCols = 3;
            const diagramWidth = 450;
            const diagramHeight = 350;

            unconnectedDiagrams.forEach((nodeId, index) => {
                const col = index % diagramCols;
                const row = Math.floor(index / diagramCols);
                const node = state.nodes[nodeId];
                if (node && node.element) {
                    node.x = startX + col * diagramWidth;
                    node.y = currentY + row * diagramHeight;
                    node.element.style.left = `${node.x}px`;
                    node.element.style.top = `${node.y}px`;
                }
            });
        }
    }

    updateConnections();
    updateMinimap();
    log('info', `Tree layout: ${clusters.length} clusters, ${unconnectedNodes.length} unconnected`);

    // DEBUG: Log link summary
    console.log('[DEBUG] === LAYOUT COMPLETE ===');
    console.log(`[DEBUG] Total nodes: ${Object.keys(state.nodes).length}`);
    console.log(`[DEBUG] Total connections: ${state.connections.length}`);

    // Count nodes by type
    const typeCounts = {};
    Object.values(state.nodes).forEach(n => {
        typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
    });
    console.log('[DEBUG] Nodes by type:', typeCounts);

    // Check for broken connections (missing nodes)
    const brokenLinks = state.connections.filter(c => !state.nodes[c.from] || !state.nodes[c.to]);
    if (brokenLinks.length > 0) {
        console.warn(`[DEBUG] BROKEN LINKS (${brokenLinks.length}):`, brokenLinks);
    }

    // Now that layout is complete, re-render all diagrams
    setTimeout(() => reRenderAllDiagrams(), 500);

    // Collapse diagrams when more than 3 per requirement
    setTimeout(() => collapseDiagramsByRequirement(), 600);
}

// ============================================
// Diagram Collapse/Expand Functions
// ============================================

/**
 * Group diagrams by parent requirement and collapse groups with >3 diagrams.
 */
function collapseDiagramsByRequirement() {
    const diagramsByReq = {};

    // Group diagrams by parent requirement
    Object.entries(state.nodes).forEach(([id, node]) => {
        if (node.type === 'diagram') {
            const parentReq = node.data?.parent_requirement || 'orphan';
            if (!diagramsByReq[parentReq]) diagramsByReq[parentReq] = [];
            diagramsByReq[parentReq].push(id);
        }
    });

    console.log('[Collapse] Diagrams by requirement:', Object.keys(diagramsByReq).length, 'groups');

    // Collapse groups with more than 3 diagrams
    Object.entries(diagramsByReq).forEach(([reqId, diagIds]) => {
        if (diagIds.length > 3) {
            console.log(`[Collapse] Collapsing ${diagIds.length} diagrams for ${reqId}`);
            collapseDiagramsInCell(diagIds, reqId);
        }
    });
}

/**
 * Collapse diagrams in a cell, showing only the first one with a "+N more" button.
 */
function collapseDiagramsInCell(diagramIds, parentReqId) {
    if (diagramIds.length <= 1) return;

    const firstId = diagramIds[0];
    const hiddenIds = diagramIds.slice(1);
    const hiddenCount = hiddenIds.length;

    // Hide extra diagrams
    hiddenIds.forEach(id => {
        const node = state.nodes[id];
        if (node?.element) {
            node.element.style.display = 'none';
            node.element.dataset.collapsed = 'true';
            node.element.dataset.collapseGroup = parentReqId;
        }
    });

    // Add "+N more" button to first diagram
    const firstNode = state.nodes[firstId];
    if (firstNode?.element) {
        // Remove existing button if any
        const existingBtn = firstNode.element.querySelector('.expand-diagrams-btn');
        if (existingBtn) existingBtn.remove();

        const expandBtn = document.createElement('button');
        expandBtn.className = 'expand-diagrams-btn';
        expandBtn.textContent = `+${hiddenCount} more`;
        expandBtn.dataset.collapseGroup = parentReqId;
        expandBtn.onclick = (e) => {
            e.stopPropagation();
            expandDiagramGroup(parentReqId);
        };
        firstNode.element.appendChild(expandBtn);
        firstNode.element.dataset.collapseGroup = parentReqId;
    }
}

/**
 * Expand a collapsed diagram group, showing all diagrams in a grid.
 */
function expandDiagramGroup(groupId) {
    console.log(`[Expand] Expanding diagram group: ${groupId}`);

    // Show all hidden diagrams in this group
    const hiddenElements = document.querySelectorAll(`[data-collapse-group="${groupId}"][data-collapsed="true"]`);
    hiddenElements.forEach(el => {
        el.style.display = '';
        el.dataset.collapsed = 'false';
    });

    // Remove the expand button
    const btn = document.querySelector(`.expand-diagrams-btn[data-collapse-group="${groupId}"]`);
    if (btn) btn.remove();

    // Re-layout the expanded diagrams in a grid
    reLayoutDiagramGroup(groupId);
}

/**
 * Re-layout expanded diagrams in a 3-column grid below the first diagram.
 */
function reLayoutDiagramGroup(groupId) {
    const diagrams = [];
    Object.entries(state.nodes).forEach(([id, node]) => {
        if (node.type === 'diagram' && node.element?.dataset.collapseGroup === groupId) {
            diagrams.push({ id, node });
        }
    });

    if (diagrams.length === 0) return;

    // Get position of first diagram as anchor
    const firstDiagram = diagrams[0];
    const baseX = firstDiagram.node.x;
    const baseY = firstDiagram.node.y;

    const COLS = 3;
    const diagramWidth = 450;
    const diagramHeight = 380;

    // Position all diagrams in grid
    diagrams.forEach(({ id, node }, index) => {
        const col = index % COLS;
        const row = Math.floor(index / COLS);

        node.x = baseX + (col * diagramWidth);
        node.y = baseY + (row * diagramHeight);
        node.element.style.left = `${node.x}px`;
        node.element.style.top = `${node.y}px`;
    });

    // Update connections after re-layout
    updateConnections();
}

// ============================================
// Package-Based Layout Functions (NEW)
// ============================================

/**
 * Package layout configuration
 */
const PACKAGE_CONFIG = {
    packageMinWidth: 1800,
    packageMinHeight: 1200,
    packagePadding: 600,
    nodeSpacingX: 420,
    nodeSpacingY: 380,
    rowPadding: 100,
    baseX: 500,
    baseY: 500,
    colors: [
        '88, 133, 255',    // Blue
        '139, 92, 246',    // Purple
        '236, 72, 153',    // Pink
        '245, 158, 11',    // Orange
        '16, 185, 129',    // Green
        '99, 102, 241',    // Indigo
        '244, 63, 94',     // Rose
        '34, 211, 238'     // Cyan
    ]
};

/**
 * Reorganize nodes by work package (connected components).
 * Groups related nodes together in visual boxes.
 */
function reorganizeNodesByPackage() {
    const packages = detectWorkPackagesForLayout();

    if (packages.length === 0) {
        console.log('[PackageLayout] No packages to layout');
        return;
    }

    console.log(`[PackageLayout] Laying out ${packages.length} packages`);

    // Calculate grid dimensions
    const cols = Math.max(1, Math.ceil(Math.sqrt(packages.length)));

    // Calculate max package size
    let maxWidth = PACKAGE_CONFIG.packageMinWidth;
    let maxHeight = PACKAGE_CONFIG.packageMinHeight;

    packages.forEach(pkg => {
        const dims = calculatePackageDimensions(pkg.nodes);
        maxWidth = Math.max(maxWidth, dims.width);
        maxHeight = Math.max(maxHeight, dims.height);
    });

    // Position each package
    packages.forEach((pkg, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;

        const baseX = PACKAGE_CONFIG.baseX + col * (maxWidth + PACKAGE_CONFIG.packagePadding);
        const baseY = PACKAGE_CONFIG.baseY + row * (maxHeight + PACKAGE_CONFIG.packagePadding);

        layoutPackageNodes(pkg.nodes, baseX, baseY, maxWidth, maxHeight);
    });

    // Render package backgrounds
    renderPackageBackgrounds(packages, maxWidth, maxHeight, cols);

    // Update connections
    updateConnections();
    updateMinimap();

    console.log(`[PackageLayout] Positioned ${packages.length} packages in ${cols} columns`);

    // Re-render diagrams and fit to view
    setTimeout(() => reRenderAllDiagrams(), 500);
    setTimeout(() => fitToView(), 600);
}

/**
 * Detect connected components for package layout.
 */
function detectWorkPackagesForLayout() {
    // Build bidirectional adjacency map
    const adj = new Map();
    Object.keys(state.nodes).forEach(id => adj.set(id, new Set()));

    state.connections.forEach(({ from, to }) => {
        if (adj.has(from) && adj.has(to)) {
            adj.get(from).add(to);
            adj.get(to).add(from);
        }
    });

    // Auto-link diagrams to requirements based on ID pattern
    let autoLinked = 0;
    Object.keys(state.nodes).forEach(nodeId => {
        const node = state.nodes[nodeId];
        if (node?.type !== 'diagram') return;

        const reqMatch = nodeId.match(/^(REQ-[a-zA-Z0-9-]+?)[-_](flowchart|sequence|class|er|state|c4)/i);
        if (reqMatch) {
            const parentReqId = reqMatch[1];
            if (adj.has(parentReqId)) {
                adj.get(nodeId).add(parentReqId);
                adj.get(parentReqId).add(nodeId);
                autoLinked++;
            }
        }
    });

    if (autoLinked > 0) {
        console.log(`[PackageLayout] Auto-linked ${autoLinked} diagrams to requirements`);
    }

    // BFS to find connected components
    const visited = new Set();
    const packages = [];

    Object.keys(state.nodes).forEach(startId => {
        if (visited.has(startId)) return;

        const pkg = { nodes: [], root: null, label: '' };
        const queue = [startId];

        while (queue.length > 0) {
            const current = queue.shift();
            if (visited.has(current)) continue;

            visited.add(current);
            pkg.nodes.push(current);

            const node = state.nodes[current];
            if (!pkg.root && (node?.type === 'requirement' || node?.type === 'epic')) {
                pkg.root = current;
                pkg.label = node?.data?.title || node?.data?.id || current;
            }

            adj.get(current)?.forEach(neighbor => {
                if (!visited.has(neighbor)) queue.push(neighbor);
            });
        }

        if (pkg.nodes.length > 0) {
            if (!pkg.label) pkg.label = `Package (${pkg.nodes.length} nodes)`;
            packages.push(pkg);
        }
    });

    packages.sort((a, b) => b.nodes.length - a.nodes.length);
    return packages;
}

/**
 * Calculate dimensions needed for a package.
 */
function calculatePackageDimensions(nodeIds) {
    const byType = groupNodesByTypeForPackage(nodeIds);

    let maxNodesInRow = 0;
    Object.values(byType).forEach(nodes => {
        maxNodesInRow = Math.max(maxNodesInRow, nodes.length);
    });

    const rowCount = Object.values(byType).filter(arr => arr.length > 0).length;

    return {
        width: PACKAGE_CONFIG.rowPadding * 2 + maxNodesInRow * PACKAGE_CONFIG.nodeSpacingX,
        height: PACKAGE_CONFIG.rowPadding * 2 + rowCount * PACKAGE_CONFIG.nodeSpacingY
    };
}

/**
 * Group nodes by type for package layout.
 */
function groupNodesByTypeForPackage(nodeIds) {
    const byType = {
        'requirement': [], 'epic': [], 'user-story': [], 'diagram': [],
        'test': [], 'task': [], 'api-endpoint': [], 'other': []
    };

    nodeIds.forEach(id => {
        const node = state.nodes[id];
        const type = node?.type || 'other';
        (byType[type] || byType.other).push(id);
    });

    return byType;
}

/**
 * Layout nodes within a single package.
 */
function layoutPackageNodes(nodeIds, baseX, baseY, width, height) {
    const byType = groupNodesByTypeForPackage(nodeIds);
    const typeOrder = ['requirement', 'epic', 'user-story', 'api-endpoint', 'diagram', 'test', 'task', 'other'];

    let currentY = baseY + PACKAGE_CONFIG.rowPadding;

    typeOrder.forEach(type => {
        const typeNodes = byType[type];
        if (!typeNodes || typeNodes.length === 0) return;

        const spacing = Math.min(
            PACKAGE_CONFIG.nodeSpacingX,
            (width - PACKAGE_CONFIG.rowPadding * 2) / Math.max(typeNodes.length, 1)
        );

        const rowWidth = typeNodes.length * spacing;
        const startX = baseX + (width - rowWidth) / 2;

        typeNodes.forEach((nodeId, i) => {
            const node = state.nodes[nodeId];
            if (node?.element) {
                const x = startX + i * spacing;
                node.x = x;
                node.y = currentY;
                node.element.style.left = `${x}px`;
                node.element.style.top = `${currentY}px`;
            }
        });

        currentY += PACKAGE_CONFIG.nodeSpacingY;
    });
}

/**
 * Render package background boxes.
 */
function renderPackageBackgrounds(packages, maxWidth, maxHeight, cols) {
    // Remove existing
    document.querySelectorAll('.package-bg').forEach(el => el.remove());

    const container = document.getElementById('canvas-nodes');
    if (!container) return;

    packages.forEach((pkg, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;

        const x = PACKAGE_CONFIG.baseX + col * (maxWidth + PACKAGE_CONFIG.packagePadding);
        const y = PACKAGE_CONFIG.baseY + row * (maxHeight + PACKAGE_CONFIG.packagePadding);

        const color = PACKAGE_CONFIG.colors[i % PACKAGE_CONFIG.colors.length];

        const bg = document.createElement('div');
        bg.className = 'package-bg';
        bg.dataset.packageIndex = i;
        bg.style.cssText = `
            position: absolute;
            left: ${x - 40}px;
            top: ${y - 60}px;
            width: ${maxWidth + 80}px;
            height: ${maxHeight + 100}px;
            background: rgba(${color}, 0.06);
            border: 2px solid rgba(${color}, 0.2);
            border-radius: 24px;
            pointer-events: none;
            z-index: 0;
        `;

        // Package label
        const label = document.createElement('div');
        label.className = 'package-label';
        label.style.cssText = `
            position: absolute;
            top: 12px;
            left: 20px;
            font-size: 14px;
            font-weight: 600;
            color: rgb(${color});
            display: flex;
            align-items: center;
            gap: 8px;
        `;

        const truncatedLabel = pkg.label.length > 40 ? pkg.label.substring(0, 37) + '...' : pkg.label;
        label.innerHTML = `
            <span style="font-size: 18px;">📦</span>
            <span>${truncatedLabel}</span>
            <span style="opacity: 0.6; font-weight: 400;">(${pkg.nodes.length})</span>
        `;
        bg.appendChild(label);

        container.insertBefore(bg, container.firstChild);
    });
}

// ============================================
// Link-Based Layout Functions (Hub-and-Spoke)
// ============================================

/**
 * Reorganize nodes using link-based hub-and-spoke layout.
 * Hubs (most connected nodes) are placed in a circle around center.
 * Spokes radiate outward from their hub based on connections.
 */
function reorganizeNodesLinkBased() {
    const nodeIds = Object.keys(state.nodes);
    if (nodeIds.length === 0) {
        console.log('[LinkLayout] No nodes to layout');
        return;
    }

    console.log(`[LinkLayout] Starting hub-and-spoke layout for ${nodeIds.length} nodes`);

    // Configuration
    const baseX = 3200;
    const baseY = 3200;
    const hubRadius = 800;
    const spokeRadius = 300;
    const maxSpokesPerRing = 8;
    const orphanZoneY = 5500;
    const orphanSpacing = 400;

    // 1. Calculate degree centrality for each node
    const degrees = {};
    nodeIds.forEach(id => degrees[id] = { in: 0, out: 0, total: 0 });

    state.connections.forEach(conn => {
        if (degrees[conn.from]) {
            degrees[conn.from].out++;
            degrees[conn.from].total++;
        }
        if (degrees[conn.to]) {
            degrees[conn.to].in++;
            degrees[conn.to].total++;
        }
    });

    // 2. Detect hubs (top 15% by degree, min 2 connections)
    const sortedByDegree = Object.entries(degrees)
        .filter(([id, deg]) => deg.total >= 2)
        .sort((a, b) => b[1].total - a[1].total);

    const hubCount = Math.max(1, Math.min(12, Math.ceil(nodeIds.length * 0.15)));
    const hubs = sortedByDegree.slice(0, hubCount).map(([id, deg]) => ({
        id,
        degree: deg.total,
        inDegree: deg.in,
        outDegree: deg.out
    }));

    console.log(`[LinkLayout] Detected ${hubs.length} hubs:`, hubs.map(h => `${h.id}(${h.degree})`).join(', '));

    // 3. Assign each non-hub node to its closest hub
    const hubIds = new Set(hubs.map(h => h.id));
    const assignments = {};

    nodeIds.forEach(nodeId => {
        if (hubIds.has(nodeId)) {
            assignments[nodeId] = { hubId: nodeId, isHub: true, connectionCount: 0 };
            return;
        }

        let bestHub = null;
        let maxConnections = 0;

        hubs.forEach(hub => {
            const connections = state.connections.filter(c =>
                (c.from === nodeId && c.to === hub.id) ||
                (c.to === nodeId && c.from === hub.id)
            ).length;

            if (connections > maxConnections) {
                maxConnections = connections;
                bestHub = hub;
            }
        });

        assignments[nodeId] = {
            hubId: bestHub?.id || hubs[0]?.id,
            isHub: false,
            connectionCount: maxConnections
        };
    });

    // 4. Calculate positions
    const positions = {};
    const centerX = baseX;
    const centerY = baseY;

    // Position hubs in a circle
    const hubPositions = {};
    hubs.forEach((hub, i) => {
        const angle = (2 * Math.PI * i) / Math.max(hubs.length, 1) - Math.PI / 2;
        hubPositions[hub.id] = {
            x: centerX + hubRadius * Math.cos(angle),
            y: centerY + hubRadius * Math.sin(angle)
        };
        positions[hub.id] = hubPositions[hub.id];
    });

    // Group spokes by hub
    const spokesByHub = {};
    hubs.forEach(hub => spokesByHub[hub.id] = []);

    Object.entries(assignments).forEach(([nodeId, assignment]) => {
        if (!assignment.isHub && assignment.hubId && spokesByHub[assignment.hubId]) {
            spokesByHub[assignment.hubId].push({
                id: nodeId,
                connectionCount: assignment.connectionCount
            });
        }
    });

    // Position spokes around their hubs
    Object.entries(spokesByHub).forEach(([hubId, spokes]) => {
        if (spokes.length === 0) return;

        const hubPos = hubPositions[hubId];
        if (!hubPos) return;

        spokes.sort((a, b) => b.connectionCount - a.connectionCount);

        let ring = 0;
        let spokeInRing = 0;
        const spokesPerRing = Math.min(maxSpokesPerRing, Math.max(4, Math.ceil(spokes.length / 2)));

        spokes.forEach((spoke, i) => {
            const ringRadius = spokeRadius + ring * 200;
            const spokesInThisRing = Math.min(spokesPerRing * (ring + 1), spokes.length - ring * spokesPerRing);
            const angle = (2 * Math.PI * spokeInRing) / spokesInThisRing + (ring * Math.PI / 6);

            positions[spoke.id] = {
                x: hubPos.x + ringRadius * Math.cos(angle),
                y: hubPos.y + ringRadius * Math.sin(angle)
            };

            spokeInRing++;
            if (spokeInRing >= spokesPerRing * (ring + 1)) {
                ring++;
                spokeInRing = 0;
            }
        });
    });

    // Position orphans (nodes with no connections)
    const orphans = nodeIds.filter(id =>
        !positions[id] && degrees[id].total === 0
    );

    if (orphans.length > 0) {
        const orphanRowWidth = Math.ceil(Math.sqrt(orphans.length));
        orphans.forEach((nodeId, i) => {
            const row = Math.floor(i / orphanRowWidth);
            const col = i % orphanRowWidth;
            positions[nodeId] = {
                x: baseX - (orphanRowWidth * orphanSpacing / 2) + col * orphanSpacing,
                y: orphanZoneY + row * orphanSpacing
            };
        });
        console.log(`[LinkLayout] Positioned ${orphans.length} orphan nodes`);
    }

    // 5. Apply positions to DOM
    Object.entries(positions).forEach(([nodeId, pos]) => {
        const nodeData = state.nodes[nodeId];
        if (nodeData && nodeData.element) {
            nodeData.x = pos.x;
            nodeData.y = pos.y;
            nodeData.element.style.left = `${pos.x}px`;
            nodeData.element.style.top = `${pos.y}px`;
        }
    });

    // 6. Render hub structure
    renderLinkLayoutStructure(hubs, hubPositions, spokeRadius, orphans);

    // 7. Update connections and minimap
    updateConnections();
    updateMinimap();

    console.log(`[LinkLayout] Applied: ${hubs.length} hubs, ${orphans.length} orphans`);
    setTimeout(() => reRenderAllDiagrams(), 500);
}

/**
 * Render visual structure for hubs and their zones.
 */
function renderLinkLayoutStructure(hubs, hubPositions, spokeRadius, orphans) {
    const existing = document.getElementById('link-layout-structure');
    if (existing) existing.remove();

    const container = document.getElementById('canvas-nodes');
    if (!container) return;

    const structure = document.createElement('div');
    structure.id = 'link-layout-structure';
    structure.className = 'link-layout-structure';

    // Render hub zones
    hubs.forEach(hub => {
        const hubPos = hubPositions[hub.id];
        if (!hubPos) return;

        const zoneRadius = spokeRadius + 100;

        // Hub zone circle
        const hubZone = document.createElement('div');
        hubZone.className = 'hub-zone';
        hubZone.style.left = `${hubPos.x - zoneRadius}px`;
        hubZone.style.top = `${hubPos.y - zoneRadius}px`;
        hubZone.style.width = `${zoneRadius * 2}px`;
        hubZone.style.height = `${zoneRadius * 2}px`;
        hubZone.style.borderRadius = '50%';

        // Hub label
        const hubLabel = document.createElement('div');
        hubLabel.className = 'hub-label';
        hubLabel.style.left = `${hubPos.x - 100}px`;
        hubLabel.style.top = `${hubPos.y - zoneRadius - 40}px`;

        const nodeData = state.nodes[hub.id];
        const title = nodeData?.data?.title || nodeData?.data?.id || hub.id;
        hubLabel.innerHTML = `
            <span class="hub-icon">★</span>
            <span class="hub-title">${title.substring(0, 25)}${title.length > 25 ? '...' : ''}</span>
            <span class="hub-degree">${hub.degree} links</span>
        `;

        structure.appendChild(hubZone);
        structure.appendChild(hubLabel);
    });

    // Render orphan zone
    if (orphans.length > 0) {
        const orphanZone = document.createElement('div');
        orphanZone.className = 'orphan-zone';
        orphanZone.style.left = `${3200 - 600}px`;
        orphanZone.style.top = `${5500 - 60}px`;
        orphanZone.innerHTML = `<span class="orphan-label">Unlinked (${orphans.length})</span>`;
        structure.appendChild(orphanZone);
    }

    container.insertBefore(structure, container.firstChild);
}

// ============================================
// Arbeitspakete (Work Package) Layout Functions
// ============================================

/**
 * Reorganize nodes using Arbeitspakete (Work Packages) layout
 * Rows = Work packages (groups of connected nodes via traceability)
 * Columns = Node types sorted by abstraction level (Detail → Abstract)
 */
function reorganizeNodesMatrix() {
    const baseX = 3200;
    const baseY = 3200;
    const padding = 40;              // Increased from 25 for better spacing
    const rowHeaderWidth = 220;      // Slightly wider headers
    const regularNodeWidth = 350;    // Increased from 300
    const regularNodeHeight = 200;   // Increased from 180
    const diagramNodeWidth = 480;    // Increased from 440
    const diagramNodeHeight = 420;   // Increased from 380
    const rowGap = 100;              // Increased from 60 for clearer separation
    const minRowHeight = 280;        // Increased from 220

    // Detect work packages from traceability links
    currentWorkPackages = detectWorkPackages();
    log('info', `Detected ${currentWorkPackages.length} work packages`);

    // Sort work packages by requirement ID/name, orphans at end
    currentWorkPackages.sort((a, b) => {
        // Orphans always at the end
        if (a.isOrphanPackage) return 1;
        if (b.isOrphanPackage) return -1;

        // Get sortable ID from the root node's data
        const getSortKey = (wp) => {
            const rootNode = state.nodes[wp.id];
            return rootNode?.data?.id || wp.id || wp.name;
        };

        const idA = getSortKey(a);
        const idB = getSortKey(b);

        // Natural sort: handles both "auto 001" < "auto 002" and "FR-FE-A" < "FR-FE-B"
        return idA.localeCompare(idB, undefined, { numeric: true, sensitivity: 'base' });
    });
    log('info', `Sorted work packages: ${currentWorkPackages.map(wp => {
        const rootNode = state.nodes[wp.id];
        const sortKey = rootNode?.data?.id || wp.id;
        return sortKey;
    }).join(', ')}`);

    // Get columns sorted by link direction (left=sources, middle=mixed+diagrams, right=sinks)
    const sortedColumns = getSortedColumns();

    // Calculate column positions using sorted order
    let columnX = baseX + rowHeaderWidth;
    const columnPositions = {};
    sortedColumns.forEach(col => {
        columnPositions[col.id] = {
            x: columnX,
            width: col.width,
            name: col.name,
            color: col.color,
            isDiagram: col.isDiagram || false
        };
        columnX += col.width;
    });

    const totalWidth = columnX - baseX;

    // Calculate layout for each work package
    let currentY = baseY + 80; // Space for column headers
    const workPackageLayouts = [];

    currentWorkPackages.forEach((wp, wpIndex) => {
        // Group nodes by column
        const nodesByColumn = {};
        sortedColumns.forEach(col => nodesByColumn[col.id] = []);

        wp.nodes.forEach(node => {
            const colId = getWorkPackageColumn(node);
            if (nodesByColumn[colId]) {
                nodesByColumn[colId].push(node);
            } else {
                // Fallback to requirement column
                nodesByColumn['requirement'].push(node);
            }
        });

        // Calculate max height needed for this work package
        let maxColHeight = 0;
        sortedColumns.forEach(col => {
            const colNodes = nodesByColumn[col.id] || [];
            const isDiagram = col.isDiagram || false;
            const nh = isDiagram ? diagramNodeHeight : regularNodeHeight;
            const colHeight = colNodes.length > 0
                ? padding + colNodes.length * (nh + padding)
                : 0;
            maxColHeight = Math.max(maxColHeight, colHeight);
        });

        const rowHeight = Math.max(minRowHeight, maxColHeight);

        // Position nodes in this work package
        sortedColumns.forEach(col => {
            const colData = columnPositions[col.id];
            const colNodes = nodesByColumn[col.id] || [];
            const isDiagram = col.isDiagram || false;
            const nw = isDiagram ? diagramNodeWidth : regularNodeWidth;
            const nh = isDiagram ? diagramNodeHeight : regularNodeHeight;

            colNodes.forEach((node, nodeIndex) => {
                const nodeData = state.nodes[node.id];
                if (nodeData && nodeData.element) {
                    const x = colData.x + padding;
                    const y = currentY + padding + nodeIndex * (nh + padding);
                    nodeData.x = x;
                    nodeData.y = y;
                    nodeData.element.style.left = `${x}px`;
                    nodeData.element.style.top = `${y}px`;
                }
            });
        });

        workPackageLayouts.push({
            id: wp.id,
            name: wp.name,
            rootType: wp.rootType,
            isOrphanPackage: wp.isOrphanPackage || false,
            y: currentY,
            height: rowHeight,
            nodeCount: wp.nodes.length
        });

        currentY += rowHeight + rowGap;
    });

    // Render the grid structure (pass sortedColumns for correct header order)
    renderWorkPackageGridStructure(baseX, baseY, columnPositions, workPackageLayouts, totalWidth, sortedColumns);

    updateConnections();
    updateMinimap();
    log('info', `Arbeitspakete layout applied: ${currentWorkPackages.length} packages, ${Object.keys(state.nodes).length} nodes`);

    // Re-queue and re-render all diagrams (queue may be empty from initial load)
    setTimeout(() => reRenderAllDiagrams(), 500);
}

/**
 * Render the visual grid structure for work packages
 * @param {Array} sortedColumns - Columns in sorted order for header display
 */
function renderWorkPackageGridStructure(baseX, baseY, columnPositions, workPackageLayouts, totalWidth, sortedColumns) {
    // Remove existing grid structure
    const existing = document.getElementById('matrix-grid-structure');
    if (existing) {
        existing.remove();
    }

    const container = document.getElementById('canvas-nodes');
    if (!container) return;

    const gridStructure = document.createElement('div');
    gridStructure.id = 'matrix-grid-structure';
    gridStructure.className = 'matrix-grid-structure workpackage-layout';

    const rowHeaderWidth = 220;  // Match the increased value in reorganizeNodesMatrix

    // Calculate total height
    const totalHeight = workPackageLayouts.reduce((sum, wp) => sum + wp.height, 0) +
                       workPackageLayouts.length * 60 + 100;

    // Create column headers (using sorted order)
    sortedColumns.forEach((col, index) => {
        const colData = columnPositions[col.id];
        const header = document.createElement('div');
        header.className = 'matrix-column-header workpackage-col-header';
        header.style.left = `${colData.x}px`;
        header.style.top = `${baseY}px`;
        header.style.width = `${colData.width - 10}px`;
        header.style.borderBottomColor = col.color;
        header.textContent = col.name;
        gridStructure.appendChild(header);

        // Vertical column separator
        if (index > 0) {
            const line = document.createElement('div');
            line.className = 'matrix-grid-line-vertical workpackage-col-line';
            line.style.left = `${colData.x}px`;
            line.style.top = `${baseY + 50}px`;
            line.style.height = `${totalHeight}px`;
            gridStructure.appendChild(line);
        }
    });

    // Create work package row headers and backgrounds
    workPackageLayouts.forEach((wp, index) => {
        // Row header
        const header = document.createElement('div');
        header.className = `matrix-row-header workpackage-row-header ${wp.isOrphanPackage ? 'orphan-package' : ''}`;
        header.style.left = `${baseX}px`;
        header.style.top = `${wp.y}px`;
        header.style.width = `${rowHeaderWidth - 10}px`;
        header.style.height = `${Math.min(wp.height, 80)}px`;

        // Color based on root type
        const rootCol = WORKPACKAGE_COLUMNS.find(c => c.id === wp.rootType);
        header.style.borderLeftColor = rootCol ? rootCol.color : '#666';

        header.innerHTML = `
            <span class="row-label">${wp.name}</span>
            <span class="row-count">${wp.nodeCount} Nodes</span>
        `;
        gridStructure.appendChild(header);

        // Row background stripe
        const rowBg = document.createElement('div');
        rowBg.className = `matrix-row-bg ${wp.isOrphanPackage ? 'orphan-row-bg' : ''}`;
        rowBg.style.left = `${baseX + rowHeaderWidth}px`;
        rowBg.style.top = `${wp.y}px`;
        rowBg.style.width = `${totalWidth - rowHeaderWidth}px`;
        rowBg.style.height = `${wp.height}px`;
        rowBg.style.background = wp.isOrphanPackage
            ? 'rgba(255, 100, 100, 0.05)'
            : (index % 2 === 0 ? 'rgba(255, 255, 255, 0.015)' : 'rgba(0, 0, 0, 0.1)');
        gridStructure.appendChild(rowBg);

        // Horizontal grid line
        const line = document.createElement('div');
        line.className = 'matrix-grid-line-horizontal';
        line.style.left = `${baseX}px`;
        line.style.top = `${wp.y}px`;
        line.style.width = `${totalWidth}px`;
        gridStructure.appendChild(line);
    });

    // Bottom border line
    if (workPackageLayouts.length > 0) {
        const lastWp = workPackageLayouts[workPackageLayouts.length - 1];
        const bottomLine = document.createElement('div');
        bottomLine.className = 'matrix-grid-line-horizontal';
        bottomLine.style.left = `${baseX}px`;
        bottomLine.style.top = `${lastWp.y + lastWp.height}px`;
        bottomLine.style.width = `${totalWidth}px`;
        gridStructure.appendChild(bottomLine);
    }

    // Insert at the beginning of canvas-nodes (behind actual nodes)
    container.insertBefore(gridStructure, container.firstChild);
}

/**
 * Get diagram type from node data
 */
function getDiagramType(data) {
    if (!data) return 'flowchart';

    // Check diagram_type field
    if (data.diagram_type) {
        const dt = data.diagram_type.toLowerCase();
        if (dt.includes('class')) return 'class';
        if (dt.includes('sequence')) return 'sequence';
        if (dt.includes('er') || dt.includes('entity')) return 'er';
        if (dt.includes('c4')) return 'c4';
        if (dt.includes('state')) return 'state';
        if (dt.includes('flow')) return 'flowchart';
    }

    // Check mermaid content for type
    if (data.mermaid_code) {
        const code = data.mermaid_code.toLowerCase();
        if (code.startsWith('classdiagram')) return 'class';
        if (code.startsWith('sequencediagram')) return 'sequence';
        if (code.startsWith('erdiagram')) return 'er';
        if (code.includes('c4context') || code.includes('c4container')) return 'c4';
        if (code.startsWith('statediagram')) return 'state';
    }

    // Check filename/path for type hints
    if (data.file_path || data.source_file) {
        const path = (data.file_path || data.source_file).toLowerCase();
        if (path.includes('/class/') || path.includes('_class')) return 'class';
        if (path.includes('/sequence/') || path.includes('_sequence')) return 'sequence';
        if (path.includes('/er/') || path.includes('_er')) return 'er';
        if (path.includes('/c4/') || path.includes('_c4')) return 'c4';
        if (path.includes('/state/') || path.includes('_state')) return 'state';
        if (path.includes('/flowchart/') || path.includes('_flow')) return 'flowchart';
    }

    return 'flowchart';
}

/**
 * Build hierarchy levels for a cluster based on connection directions.
 * Root nodes (no incoming connections) are level 0, their children level 1, etc.
 */
function buildClusterHierarchy(nodeIds) {
    // Count incoming connections for each node
    const incoming = new Map();
    nodeIds.forEach(id => incoming.set(id, []));

    state.connections.forEach(conn => {
        if (incoming.has(conn.to) && nodeIds.includes(conn.from)) {
            incoming.get(conn.to).push(conn.from);
        }
    });

    // Find root nodes (no incoming connections from within the cluster)
    const roots = nodeIds.filter(id => incoming.get(id).length === 0);

    // If no clear roots, use nodes with smallest indegree
    let effectiveRoots = roots;
    if (roots.length === 0) {
        const minIncoming = Math.min(...nodeIds.map(id => incoming.get(id).length));
        effectiveRoots = nodeIds.filter(id => incoming.get(id).length === minIncoming);
    }

    // NEW: Build parent-children relationships for tree layout
    const children = new Map();  // nodeId -> [childIds]
    const parents = new Map();   // nodeId -> parentId (first parent only for tree)

    nodeIds.forEach(id => children.set(id, []));

    state.connections.forEach(conn => {
        if (nodeIds.includes(conn.from) && nodeIds.includes(conn.to)) {
            // Add to children list
            if (!children.get(conn.from).includes(conn.to)) {
                children.get(conn.from).push(conn.to);
            }
            // Set parent (first parent wins for tree structure)
            if (!parents.has(conn.to)) {
                parents.set(conn.to, conn.from);
            }
        }
    });

    // BFS to assign levels with safety limit
    const MAX_BFS_ITERATIONS = 1000;
    let bfsIterations = 0;

    console.log('[DEBUG] Starting buildClusterHierarchy BFS');

    const levels = new Map();
    const queue = effectiveRoots.map(id => ({ id, level: 0 }));
    const visited = new Set();

    while (queue.length > 0 && bfsIterations++ < MAX_BFS_ITERATIONS) {
        const { id, level } = queue.shift();
        if (visited.has(id)) continue;
        visited.add(id);
        levels.set(id, level);

        // Find children (nodes this node connects to)
        state.connections.forEach(conn => {
            if (conn.from === id && nodeIds.includes(conn.to) && !visited.has(conn.to)) {
                queue.push({ id: conn.to, level: level + 1 });
            }
        });
    }

    if (bfsIterations >= MAX_BFS_ITERATIONS) {
        console.warn('[Layout] BFS iteration limit reached in buildClusterHierarchy');
    }

    console.log(`[DEBUG] buildClusterHierarchy BFS completed: ${bfsIterations} iterations`);

    // Assign level 0 to any remaining unvisited nodes
    nodeIds.forEach(id => {
        if (!levels.has(id)) levels.set(id, 0);
    });

    return { levels, roots: effectiveRoots, children, parents };
}

/**
 * Sort nodes by their type hierarchy.
 * Order: Epic -> Requirement -> UserStory -> Test -> Diagram -> API
 */
function sortNodesByHierarchy(nodeIds) {
    const order = {
        'epic': 0,
        'requirement': 1,
        'user-story': 2,
        'persona': 3,
        'user-flow': 4,
        'screen': 5,
        'component': 6,
        'test': 7,
        'diagram': 8,
        'api': 9,
        'entity': 10,
        'feature': 11,
        'task': 12,
        'tech-stack': 13
    };

    return nodeIds.sort((a, b) => {
        const typeA = state.nodes[a]?.type || 'other';
        const typeB = state.nodes[b]?.type || 'other';
        const orderA = order[typeA] !== undefined ? order[typeA] : 99;
        const orderB = order[typeB] !== undefined ? order[typeB] : 99;

        if (orderA !== orderB) {
            return orderA - orderB;
        }

        // Same type: sort by ID
        return a.localeCompare(b);
    });
}

/**
 * Apply cluster layout and fit to view.
 */
function applyClusterLayout() {
    reorganizeNodesAsCluster();
    setTimeout(() => fitToView(), 100);
}


// ============================================
// Kilo Agent Chat Integration
// ============================================

/**
 * Add chat button to a node element.
 * @param {HTMLElement} nodeElement - The node DOM element
 * @param {string} nodeId - The node ID
 */
function addChatButton(nodeElement, nodeId) {
    // Check if button already exists
    if (nodeElement.querySelector('.kilo-chat-btn')) return;

    const chatBtn = document.createElement('button');
    chatBtn.className = 'kilo-chat-btn';
    chatBtn.innerHTML = '<span class="chat-icon">💬</span>';
    chatBtn.title = 'Mit Kilo Agent bearbeiten';
    chatBtn.onclick = (e) => {
        e.stopPropagation();
        openChatPanel(nodeId);
    };

    // Add to node header or create action container
    const header = nodeElement.querySelector('.node-header');
    if (header) {
        header.appendChild(chatBtn);
    } else {
        nodeElement.appendChild(chatBtn);
    }
}

/**
 * Open chat panel for a specific node.
 * @param {string} nodeId - The node ID
 */
function openChatPanel(nodeId) {
    // Close existing panel
    closeChatPanel();

    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    const panel = document.createElement('div');
    panel.id = 'kilo-chat-panel';
    panel.className = 'kilo-chat-panel';
    panel.dataset.nodeId = nodeId;

    const title = nodeData.data?.title || nodeData.data?.diagram_type || nodeId;

    panel.innerHTML = `
        <div class="chat-header">
            <span class="chat-title">Kilo Agent - ${title}</span>
            <button class="chat-close-btn" onclick="closeChatPanel()">×</button>
        </div>
        <div class="chat-messages" id="chat-messages-${nodeId}">
            <div class="chat-message system">Was soll geändert werden?</div>
        </div>
        <div class="chat-input-area">
            <textarea
                id="chat-input"
                placeholder="Beschreibe die gewünschte Änderung..."
                rows="3"
            ></textarea>
            <button class="chat-send-btn" onclick="sendKiloTask('${nodeId}')">
                Senden
            </button>
        </div>
    `;

    document.body.appendChild(panel);

    // Focus input
    const input = document.getElementById('chat-input');
    if (input) {
        input.focus();
        // Allow Enter to send (Shift+Enter for newline)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendKiloTask(nodeId);
            }
        });
    }
}

/**
 * Close the chat panel.
 */
function closeChatPanel() {
    const panel = document.getElementById('kilo-chat-panel');
    if (panel) {
        panel.remove();
    }
}

/**
 * Send a task to the Kilo Agent.
 * @param {string} nodeId - The node ID
 */
function sendKiloTask(nodeId) {
    console.log('[KILO] sendKiloTask called for node:', nodeId);
    const input = document.getElementById('chat-input');
    const task = input?.value?.trim();

    if (!task) {
        console.log('[KILO] No task provided');
        return;
    }

    const nodeData = state.nodes[nodeId];
    if (!nodeData) {
        console.log('[KILO] No node data found for:', nodeId);
        return;
    }

    // Determine content and type
    let content = '';
    let contentType = 'generic';
    let filePath = '';

    if (nodeData.type === 'diagram') {
        content = nodeData.data?.mermaid_code || '';
        contentType = 'diagram';
        filePath = nodeData.data?.file_path || '';
    } else if (nodeData.type === 'requirement') {
        content = JSON.stringify(nodeData.data, null, 2);
        contentType = 'requirement';
    } else {
        content = JSON.stringify(nodeData.data, null, 2);
    }

    console.log('[KILO] Sending message:', { nodeId, contentType, taskLength: task.length });
    console.log('[KILO] WebSocket state:', state.ws?.readyState);

    // Send to server
    sendMessage({
        type: 'kilo_task',
        node_id: nodeId,
        content: content,
        file_path: filePath,
        task: task,
        content_type: contentType
    });

    // Add user message to chat
    addChatMessage(nodeId, 'user', task);

    // Show processing indicator immediately
    addChatMessage(nodeId, 'system', 'Sende an Kilo Agent...');

    // Clear input
    input.value = '';
}

/**
 * Add a message to the chat panel.
 * @param {string} nodeId - The node ID
 * @param {string} type - Message type (user, agent, system, error)
 * @param {string} message - The message text
 */
function addChatMessage(nodeId, type, message) {
    const messagesContainer = document.getElementById(`chat-messages-${nodeId}`);
    if (!messagesContainer) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${type}`;
    msgDiv.textContent = message;

    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

/**
 * Show processing indicator on a node.
 * @param {string} nodeId - The node ID
 */
function showKiloProcessing(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (nodeData?.element) {
        nodeData.element.classList.add('kilo-processing');
    }
}

/**
 * Hide processing indicator on a node.
 * @param {string} nodeId - The node ID
 */
function hideKiloProcessing(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (nodeData?.element) {
        nodeData.element.classList.remove('kilo-processing');
    }
}

/**
 * Update a diagram node with new content.
 * @param {Object} data - Update data with node_id and mermaid_code
 */
function updateDiagramNode(data) {
    const nodeId = data.node_id;
    const nodeData = state.nodes[nodeId];

    if (!nodeData) return;

    // Update state
    nodeData.data.mermaid_code = data.mermaid_code;

    // Re-render Mermaid
    const mermaidContainer = nodeData.element?.querySelector('.node-diagram-content');
    if (mermaidContainer) {
        mermaidContainer.textContent = data.mermaid_code;
        renderMermaid(nodeId, data.mermaid_code);
    }

    hideKiloProcessing(nodeId);
}

/**
 * Update node content (generic).
 * @param {Object} data - Update data
 */
function updateNodeContent(data) {
    const nodeId = data.node_id;
    const nodeData = state.nodes[nodeId];

    if (!nodeData) return;

    // Try to parse and merge the content
    try {
        const newContent = JSON.parse(data.content);
        Object.assign(nodeData.data, newContent);
    } catch {
        // If not JSON, store as raw content
        nodeData.data.content = data.content;
    }

    hideKiloProcessing(nodeId);
}

/**
 * Initialize chat buttons on all existing nodes.
 */
function initializeChatButtons() {
    Object.entries(state.nodes).forEach(([nodeId, nodeData]) => {
        if (nodeData.element) {
            addChatButton(nodeData.element, nodeId);
        }
    });
}

// Override createNode to add chat button
const originalCreateNode = createNode;
createNode = function(type, id, data) {
    const node = originalCreateNode(type, id, data);
    if (node) {
        setTimeout(() => addChatButton(node, id), 100);
    }
    return node;
};

// ============================================
// Change Propagation & Auto-Link Functions
// ============================================

// Storage for suggestions
const propagationSuggestions = {};
const linkSuggestions = {};
let isWatching = false;

/**
 * Show a notification toast
 */
function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container') || createNotificationContainer();

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span class="notification-icon">${type === 'success' ? '✓' : type === 'warn' ? '⚠' : 'ℹ'}</span>
        <span class="notification-message">${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 10px;
    `;
    document.body.appendChild(container);
    return container;
}

/**
 * Add a propagation suggestion to the sidebar
 */
function addPropagationSuggestion(data) {
    propagationSuggestions[data.id] = data;
    renderPropagationSuggestions();
}

/**
 * Remove a propagation suggestion
 */
function removePropagationSuggestion(id) {
    delete propagationSuggestions[id];
    renderPropagationSuggestions();
}

/**
 * Render all propagation suggestions
 */
function renderPropagationSuggestions() {
    const container = document.getElementById('propagation-suggestions');
    if (!container) return;

    const suggestions = Object.values(propagationSuggestions);

    if (suggestions.length === 0) {
        container.innerHTML = '<p class="empty-state">Keine ausstehenden Vorschläge</p>';
        return;
    }

    container.innerHTML = suggestions.map(s => `
        <div class="suggestion-card" data-id="${s.id}">
            <div class="suggestion-header">
                <span class="suggestion-source">${s.source_node_id}</span>
                <span class="suggestion-arrow">→</span>
                <span class="suggestion-target">${s.target_node_id}</span>
            </div>
            <div class="suggestion-link-type">${s.link_type}</div>
            <div class="suggestion-reasoning">${s.reasoning}</div>
            <div class="suggestion-confidence">
                <span class="confidence-label">Konfidenz:</span>
                <span class="confidence-value ${s.confidence >= 0.7 ? 'high' : s.confidence >= 0.5 ? 'medium' : 'low'}">
                    ${Math.round(s.confidence * 100)}%
                </span>
            </div>
            <div class="suggestion-actions">
                <button class="btn-approve" onclick="approvePropagation('${s.id}')">Annehmen</button>
                <button class="btn-reject" onclick="rejectPropagation('${s.id}')">Ablehnen</button>
            </div>
        </div>
    `).join('');
}

/**
 * Approve a propagation suggestion
 */
async function approvePropagation(suggestionId) {
    try {
        const response = await fetch(`/api/propagation/approve/${suggestionId}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (!result.success) {
            log('error', 'Fehler beim Anwenden der Änderung');
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Reject a propagation suggestion
 */
async function rejectPropagation(suggestionId) {
    try {
        const response = await fetch(`/api/propagation/reject/${suggestionId}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (!result.success) {
            log('error', 'Fehler beim Ablehnen der Änderung');
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Add a link suggestion to the sidebar
 */
function addLinkSuggestion(data) {
    linkSuggestions[data.id] = data;
    renderLinkSuggestions();
}

/**
 * Remove a link suggestion
 */
function removeLinkSuggestion(id) {
    delete linkSuggestions[id];
    renderLinkSuggestions();
}

/**
 * Render all link suggestions
 */
function renderLinkSuggestions() {
    const container = document.getElementById('link-suggestions');
    if (!container) return;

    const suggestions = Object.values(linkSuggestions);

    if (suggestions.length === 0) {
        container.innerHTML = '<p class="empty-state">Keine Link-Vorschläge</p>';
        return;
    }

    container.innerHTML = suggestions.map(s => `
        <div class="suggestion-card link-suggestion" data-id="${s.id}">
            <div class="suggestion-header">
                <span class="orphan-node">${s.orphan_node_title || s.orphan_node_id}</span>
            </div>
            <div class="suggestion-target-info">
                <span class="link-type-badge">${s.link_type}</span>
                <span class="target-node">${s.target_node_title || s.target_node_id}</span>
            </div>
            <div class="suggestion-reasoning">${s.reasoning}</div>
            <div class="suggestion-confidence">
                <span class="confidence-label">Konfidenz:</span>
                <span class="confidence-value ${s.confidence >= 0.7 ? 'high' : s.confidence >= 0.5 ? 'medium' : 'low'}">
                    ${Math.round(s.confidence * 100)}%
                </span>
            </div>
            <div class="suggestion-actions">
                <button class="btn-approve" onclick="approveLink('${s.id}')">Link erstellen</button>
                <button class="btn-reject" onclick="rejectLink('${s.id}')">Ablehnen</button>
            </div>
        </div>
    `).join('');
}

/**
 * Approve a link suggestion
 */
async function approveLink(suggestionId) {
    try {
        // Get suggestion data before removing
        const suggestion = linkSuggestions[suggestionId];
        if (!suggestion) {
            log('error', 'Link-Vorschlag nicht gefunden');
            return;
        }

        const response = await fetch(`/api/links/approve/${suggestionId}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (result.success) {
            // Add visual connection
            addConnection(suggestion.orphan_node_id, suggestion.target_node_id, suggestion.link_type || 'related');
            scheduleConnectionUpdate();

            // Remove from suggestions list
            removeLinkSuggestion(suggestionId);

            // Log success
            log('success', `Link erstellt: ${suggestion.orphan_node_id} → ${suggestion.target_node_id}`);
        } else {
            log('error', 'Fehler beim Erstellen des Links');
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Reject a link suggestion
 */
async function rejectLink(suggestionId) {
    try {
        // Get suggestion data for logging
        const suggestion = linkSuggestions[suggestionId];

        const response = await fetch(`/api/links/reject/${suggestionId}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (result.success) {
            // Remove from suggestions list
            removeLinkSuggestion(suggestionId);

            // Log rejection
            if (suggestion) {
                log('info', `Link abgelehnt: ${suggestion.orphan_node_id} → ${suggestion.target_node_id}`);
            }
        } else {
            log('error', 'Fehler beim Ablehnen des Links');
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Update watching status display
 */
function updateWatchingStatus(watching) {
    isWatching = watching;
    const btn = document.getElementById('watch-toggle-btn');
    if (btn) {
        btn.textContent = watching ? 'Watching stoppen' : 'Watching starten';
        btn.className = watching ? 'btn-danger' : 'btn-primary';
    }

    const indicator = document.getElementById('watching-indicator');
    if (indicator) {
        indicator.className = watching ? 'indicator active' : 'indicator';
        indicator.title = watching ? 'File Watching aktiv' : 'File Watching inaktiv';
    }
}

/**
 * Toggle file watching
 */
async function toggleFileWatching() {
    const endpoint = isWatching ? '/api/propagation/stop-watching' : '/api/propagation/start-watching';

    try {
        const body = isWatching ? {} : { project_id: getCurrentProjectId() };
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        if (!result.success) {
            log('error', 'Fehler beim Umschalten des File Watching');
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Get current project ID
 */
function getCurrentProjectId() {
    const projectName = elements.projectInfo?.querySelector('.project-name')?.textContent;
    return projectName || '';
}

/**
 * Update orphan count display
 */
function updateOrphanCount(count) {
    const badge = document.getElementById('orphan-count');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline' : 'none';
    }
}

/**
 * Discover links for orphan nodes
 */
async function discoverLinks() {
    log('info', 'Starte Link-Erkennung für verwaiste Nodes...');

    try {
        const response = await fetch('/api/links/discover', {
            method: 'POST'
        });
        const result = await response.json();

        if (result.success) {
            log('success', `${result.suggestions.length} Link-Vorschläge generiert`);
        } else {
            log('error', `Fehler: ${result.error}`);
        }
    } catch (e) {
        log('error', `Fehler: ${e.message}`);
    }
}

/**
 * Load pending suggestions on startup
 */
async function loadPendingSuggestions() {
    try {
        // Load propagation suggestions
        const propResponse = await fetch('/api/propagation/pending');
        const propData = await propResponse.json();
        propData.suggestions?.forEach(s => {
            propagationSuggestions[s.id] = s;
        });
        renderPropagationSuggestions();

        // Load link suggestions
        const linkResponse = await fetch('/api/links/pending');
        const linkData = await linkResponse.json();
        linkData.suggestions?.forEach(s => {
            linkSuggestions[s.id] = s;
        });
        renderLinkSuggestions();
    } catch (e) {
        console.error('Failed to load pending suggestions:', e);
    }
}

// Initialize chat buttons when DOM is ready
if (document.readyState === 'complete') {
    setTimeout(initializeChatButtons, 500);
} else {
    window.addEventListener('load', () => {
        setTimeout(initializeChatButtons, 500);
    });
}

// ============================================
// Global Exports for HTML onclick handlers
// (Required for ES6 module compatibility)
// ============================================

window.setLayout = setLayout;
window.toggleFileWatching = toggleFileWatching;
window.discoverLinks = discoverLinks;
window.hideDetailPanel = hideDetailPanel;
window.focusNode = focusNode;
window.approvePropagation = approvePropagation;
window.rejectPropagation = rejectPropagation;
window.approveLink = approveLink;
window.rejectLink = rejectLink;
