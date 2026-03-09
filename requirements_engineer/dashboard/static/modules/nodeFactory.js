/**
 * RE System Dashboard - Node Factory Module
 *
 * Contains all node creation functions for different artifact types.
 * Creates nodes from various data sources (journal, folder, API responses).
 */

import { state, log } from './state.js';
import { addConnection } from './connections.js';
import { queueMermaidRender } from './mermaidRenderer.js';

// ============================================
// Sidebar Helper (will be replaced by ui/sidebar.js import)
// ============================================

let sidebarCallback = null;

export function setSidebarCallback(cb) {
    sidebarCallback = cb;
}

function addSidebarItem(listId, nodeId, title, badge) {
    if (sidebarCallback) {
        sidebarCallback(listId, nodeId, title, badge);
    }
}

// ============================================
// Core Node Creation
// ============================================

let createNodeFn = null;

export function setCreateNodeFunction(fn) {
    createNodeFn = fn;
}

function createNode(type, id, data) {
    if (createNodeFn) {
        return createNodeFn(type, id, data);
    }
    console.warn('[NodeFactory] createNode function not set');
}

// ============================================
// Helper Functions
// ============================================

/**
 * Find node by partial ID match
 * @param {string} type - Node type to match
 * @param {string} partialId - Partial ID to search for
 * @returns {Object|null} Found node or null
 */
export function findNodeByPartialId(type, partialId) {
    const needle = partialId.toUpperCase();
    return Object.values(state.nodes).find(n =>
        n.type === type && n.element.dataset.nodeId.toUpperCase().includes(needle)
    ) || Object.values(state.nodes).find(n =>
        n.element.dataset.nodeId.toUpperCase().includes(needle)
    );
}

// ============================================
// Journal Format Node Creators
// ============================================

/**
 * Create node from journal.json format
 */
export function createNodeFromJournal(nodeId, nodeData) {
    let type = 'requirement';
    let displayId = nodeId;

    if (nodeId.startsWith('node-')) {
        displayId = nodeData.requirement_id || nodeId.replace('node-', '');
    }

    const data = {
        title: nodeData.title || nodeData.description || 'Untitled',
        type: nodeData.type || 'functional',
        priority: nodeData.priority || 'should',
        description: nodeData.description || '',
        source: nodeData.source || '',
        // Quality scores from journal
        completeness_score: nodeData.completeness_score,
        consistency_score: nodeData.consistency_score,
        testability_score: nodeData.testability_score,
        clarity_score: nodeData.clarity_score,
        feasibility_score: nodeData.feasibility_score,
        traceability_score: nodeData.traceability_score,
        // Status flags
        is_buggy: nodeData.is_buggy,
        is_complete: nodeData.is_complete,
        // Analysis
        analysis: nodeData.analysis || '',
        improvement_suggestions: nodeData.improvement_suggestions || [],
        quality_issues: nodeData.quality_issues || [],
        // Relationships
        dependencies: nodeData.dependencies || [],
        conflicts: nodeData.conflicts || [],
        related_requirements: nodeData.related_requirements || [],
        parent_requirement: nodeData.parent_requirement || null,
        // Work info
        work_package: nodeData.work_package || '',
        estimated_effort: nodeData.estimated_effort || '',
        assigned_to: nodeData.assigned_to || '',
        // Timestamps
        created_at: nodeData.created_at || '',
        updated_at: nodeData.updated_at || '',
        // Version
        version: nodeData.version,
        stage_name: nodeData.stage_name || ''
    };

    createNode(type, displayId, data);
    addSidebarItem('requirements-list', displayId, data.title, data.priority);

    // Create diagram nodes if mermaid_diagrams exist
    if (nodeData.mermaid_diagrams && typeof nodeData.mermaid_diagrams === 'object') {
        const diagramTypes = Object.keys(nodeData.mermaid_diagrams);
        diagramTypes.forEach((diagramType, index) => {
            const mermaidCode = nodeData.mermaid_diagrams[diagramType];
            if (mermaidCode && mermaidCode.trim()) {
                // Use underscore separator for consistent ID format
                const diagramId = `${displayId}_${diagramType}`;
                const diagramData = {
                    diagram_type: diagramType.charAt(0).toUpperCase() + diagramType.slice(1),
                    mermaid_code: mermaidCode,
                    parent_requirement: displayId
                };
                createNode('diagram', diagramId, diagramData);
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

    // Create test nodes if acceptance criteria exist
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

/**
 * Create requirement from requirements array (simpler format from journal.json)
 */
export function createRequirementFromArray(req) {
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
                // Use underscore separator for consistent ID format
                const diagramId = `${reqId}_${diagramType}`;
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
// Folder Format Node Creators
// ============================================

/**
 * Create epic from folder-based format
 */
export function createEpicFromFolder(epic) {
    const epicId = epic.id || `EPIC-${Date.now()}`;
    const data = {
        title: epic.title || 'Untitled Epic',
        description: epic.description || '',
        status: epic.status || '',
        linked_requirements: epic.linked_requirements || [],
        linked_user_stories: epic.linked_user_stories || [],
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

/**
 * Create user story from folder-based format
 */
export function createUserStoryFromFolder(story) {
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

/**
 * Create diagram from folder-based format
 */
export function createDiagramFromFolder(diagram) {
    const diagramId = diagram.id || `DIAG-${Date.now()}`;
    console.log(`[NodeFactory] Creating diagram: ${diagramId}`, {
        hasCode: !!diagram.mermaid_code,
        codeLength: diagram.mermaid_code?.length || 0,
        type: diagram.type
    });

    // Extract requirement ID from diagram ID
    let parentReqId = diagram.requirement_id;
    if (!parentReqId && diagramId.includes('_')) {
        const parts = diagramId.split('_');
        if (parts.length >= 2) {
            parentReqId = parts.slice(0, -1).join('_');
        }
    }
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

    console.log(`[NodeFactory] Diagram data prepared: ${diagramId}`, {
        diagram_type: data.diagram_type,
        mermaid_code_length: data.mermaid_code.length,
        parent_requirement: data.parent_requirement
    });

    createNode('diagram', diagramId, data);

    // Add standalone diagrams (ER, Architecture, Dependencies, Gantt) to sidebar
    const isStandalone = !parentReqId;
    if (isStandalone) {
        const title = diagram.title || diagramId;
        addSidebarItem('diagrams-list', diagramId, title, diagram.type || '');
    }

    // Create connection to parent requirement if exists
    if (parentReqId) {
        setTimeout(() => {
            let reqNode = state.nodes[parentReqId];
            if (!reqNode) {
                reqNode = findNodeByPartialId('requirement', parentReqId);
            }

            if (reqNode) {
                const reqNodeId = reqNode.element ? reqNode.element.dataset.nodeId : parentReqId;
                addConnection(reqNodeId, diagramId);
                console.log(`[Diagram Link] Connected ${diagramId} to ${reqNodeId}`);
            } else {
                console.log(`[Diagram Link] No requirement found for ${diagramId} (tried: ${parentReqId})`);
            }
        }, 100);
    }
}

/**
 * Create test from folder-based format
 */
export function createTestFromFolder(test) {
    const testId = test.id || `TEST-${Date.now()}`;
    const data = {
        title: test.title || 'Untitled Test',
        test_type: test.type || 'acceptance',
        content: test.content || '',
        scenario_count: test.scenario_count || 0,
        tags: test.tags || [],
        gherkin_content: test.gherkin_content || '',
        feature_file: test.feature_file || '',
        linked_user_story: test.linked_user_story || ''
    };

    createNode('test', testId, data);
    addSidebarItem('tests-list', testId, data.title, '');

    // Link to user story if linked_user_story is provided
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
// Entity & Feature Node Creators
// ============================================

/**
 * Create entity from data dictionary
 */
export function createEntityFromDictionary(entity) {
    const entityId = `ENTITY-${entity.name}`;
    const data = {
        title: entity.name,
        description: entity.description,
        attributes: entity.attributes || [],
        source_requirements: entity.source_requirements || []
    };

    createNode('entity', entityId, data);
    addSidebarItem('requirements-list', entityId, data.title, 'entity');

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

/**
 * Create feature from work breakdown
 */
export function createFeatureFromBreakdown(feature) {
    const featureId = feature.id || `FEAT-${Date.now()}`;
    const data = {
        title: feature.title,
        priority: feature.priority,
        complexity: feature.complexity,
        requirements: feature.requirements || []
    };

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

/**
 * Create API endpoint node
 */
export function createApiEndpointNode(endpoint) {
    const apiId = endpoint.id || `API-${endpoint.method}-${endpoint.path.replace(/\//g, '-').replace(/[{}]/g, '')}`.replace(/-+/g, '-');
    const data = {
        method: endpoint.method,
        path: endpoint.path,
        description: endpoint.description,
        parent_requirement_id: endpoint.parent_requirement_id || ''
    };

    createNode('api', apiId, data);
    addSidebarItem('api-list', apiId, `${endpoint.method} ${endpoint.path}`, endpoint.method);
}

/**
 * Create API package node (stacked endpoints by resource)
 */
export function createApiPackageNode(pkg) {
    const nodeId = `API-PKG-${pkg.tag.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`;
    const data = {
        tag: pkg.tag,
        endpoint_count: pkg.endpoints.length,
        method_counts: pkg.method_counts || {},
        endpoints: pkg.endpoints
    };
    createNode('api-package', nodeId, data);
    addSidebarItem('api-list', nodeId, `${pkg.tag} (${pkg.endpoints.length})`, 'PKG');
}

/**
 * Create task group node (stacked tasks by feature)
 */
export function createTaskGroupNode(featureId, featureName, tasks) {
    const nodeId = `TASK-GRP-${featureId}`;
    const totalHours = tasks.reduce((s, t) => s + (t.estimated_hours || 0), 0);
    const data = {
        title: featureName || featureId,
        feature_id: featureId,
        task_count: tasks.length,
        total_hours: totalHours,
        tasks: tasks
    };
    createNode('task-group', nodeId, data);
    addSidebarItem('tasks-list', nodeId, `${data.title} (${tasks.length})`, `${totalHours}h`);
}

/**
 * Create architecture service node
 */
export function createServiceNode(service) {
    const nodeId = service.id || `SVC-${(service.name || 'unknown').replace(/[^a-zA-Z0-9]/g, '-')}`;
    const data = {
        name: service.name,
        type: service.type,
        technology: service.technology,
        responsibilities: service.responsibilities || [],
        dependencies: service.dependencies || [],
        ports: service.ports || []
    };
    createNode('service', nodeId, data);
    addSidebarItem('services-list', nodeId, data.name, data.type || '');
}

/**
 * Create state machine node
 */
export function createStateMachineNode(sm) {
    const entity = sm.entity || sm.name || 'unknown';
    const nodeId = `SM-${entity.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`;
    const data = {
        entity: entity,
        name: sm.name || entity,
        state_count: (sm.states || []).length,
        transition_count: (sm.transitions || []).length,
        initial_state: sm.initial_state || (sm.states || [])[0] || '',
        states: sm.states || [],
        transitions: sm.transitions || [],
        mermaid_code: sm.mermaid_code || ''
    };
    createNode('state-machine', nodeId, data);
    addSidebarItem('state-machines-list', nodeId, data.name, `${data.state_count} states`);
}

/**
 * Create infrastructure summary node
 */
export function createInfrastructureNode(infra) {
    const nodeId = 'INFRASTRUCTURE';
    const data = {
        architecture_style: infra.architecture_style || infra.cloud_provider || '',
        has_dockerfile: infra.has_dockerfile || false,
        has_k8s: infra.has_k8s || false,
        has_ci: infra.has_ci || false,
        service_count: infra.service_count || 0,
        services: infra.services || [],
        env_vars: infra.env_vars || []
    };
    createNode('infrastructure', nodeId, data);
}

/**
 * Create design tokens summary node
 */
export function createDesignTokensNode(tokens) {
    const nodeId = 'DESIGN-TOKENS';
    const data = {
        colors: tokens.colors || {},
        typography: tokens.typography || {},
        spacing: tokens.spacing || {},
        breakpoints: tokens.breakpoints || {}
    };
    createNode('design-tokens', nodeId, data);
}

// ============================================
// New Generator Node Creators
// ============================================

/**
 * Create tech stack node
 */
export function createTechStackNode(techStack) {
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

/**
 * Create persona node
 */
export function createPersonaNode(persona) {
    const nodeId = persona.id || `PERSONA-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: persona.name,
        role: persona.role,
        goals: persona.goals || [],
        pain_points: persona.pain_points || [],
        tech_savviness: persona.tech_savviness
    };
    createNode('persona', nodeId, data);
    addSidebarItem('personas-list', nodeId, data.name || nodeId, data.role || '');
}

/**
 * Create user flow node
 */
export function createUserFlowNode(flow) {
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

/**
 * Create UI component node
 */
export function createUIComponentNode(component) {
    const nodeId = component.id || `COMP-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: component.name,
        component_type: component.component_type,
        variants: component.variants || [],
        props: component.props || {},
        states: component.states || []
    };
    createNode('component', nodeId, data);
    addSidebarItem('components-list', nodeId, data.name || nodeId, data.component_type || '');
}

/**
 * Create screen node
 */
export function createScreenNode(screen) {
    const nodeId = screen.id || `SCREEN-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const data = {
        name: screen.name,
        route: screen.route,
        layout: screen.layout,
        components: screen.components || [],
        component_layout: screen.component_layout || [],
        parent_user_story: screen.parent_user_story,
        wireframe_ascii: screen.wireframe_ascii || '',
        wireframe_mermaid: screen.wireframe_mermaid || '',
        description: screen.description || '',
        data_requirements: screen.data_requirements || []
    };
    createNode('screen', nodeId, data);

    // Add to sidebar with wireframe indicator
    const hasWireframe = !!screen.wireframe_ascii;
    const badge = hasWireframe ? 'wireframe' : screen.layout || '';
    addSidebarItem('screens-list', nodeId, screen.name || nodeId, badge);
}

/**
 * Create task node
 */
export function createTaskNode(task) {
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
    addSidebarItem('tasks-list', nodeId, data.title || nodeId, data.complexity || '');
}
