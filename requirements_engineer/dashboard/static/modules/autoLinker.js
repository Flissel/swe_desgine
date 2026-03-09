/**
 * RE System Dashboard - Auto Linker Module
 *
 * Contains all auto-linking functions for connecting nodes based on
 * traceability data, metadata, and relationship patterns.
 */

import { state, log } from './state.js';
import { addConnection, updateConnections } from './connections.js';
import { findNodeByPartialId } from './nodeFactory.js';

// ============================================
// API Package Helpers
// ============================================

const COMMON_API_PREFIXES = new Set(['api', 'v1', 'v2', 'v3', 'rest', 'graphql']);

/**
 * Extract the resource name from an API path, skipping common prefixes.
 */
function extractResource(path) {
    const segments = path.replace(/^ws:\/\//, '/').split('/').filter(s => s && !s.startsWith('{'));
    // Skip common API prefixes to get the actual resource name
    while (segments.length && COMMON_API_PREFIXES.has(segments[0].toLowerCase())) {
        segments.shift();
    }
    const resource = segments[0] || 'root';
    if (resource.startsWith('ws:')) return 'websocket';
    return resource;
}

/**
 * Find the canvas node for an API endpoint.
 * Checks for individual 'api' nodes first, then falls back to 'api-package' nodes.
 * Returns the nodeId string or null.
 */
function findApiNode(ep) {
    const epId = ep.id || ep.path;
    // Try individual node first
    let node = state.nodes[epId] || findNodeByPartialId('api', epId);
    if (node) return node.element?.dataset?.nodeId || epId;

    // Fall back to package node: derive resource from path
    const resource = extractResource(ep.path || '');
    const pkgId = `API-PKG-${resource.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`;
    node = state.nodes[pkgId];
    if (node) return pkgId;

    return null;
}

/**
 * Find package node for an endpoint path string.
 */
function findApiNodeByPath(path) {
    const resource = extractResource(path);
    const pkgId = `API-PKG-${resource.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`;
    const node = state.nodes[pkgId];
    if (node) return pkgId;

    // Try individual node
    const indNode = findNodeByPartialId('api', path);
    if (indNode) return indNode.element?.dataset?.nodeId || path;

    return null;
}

// ============================================
// Traceability Links
// ============================================

/**
 * Apply links from traceability matrix data
 * @param {Array} traceability - Traceability entries from project data
 */
export function applyTraceabilityLinks(traceability) {
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

// ============================================
// Epic & User Story Links
// ============================================

/**
 * Apply links between epics and user stories
 * @param {Array} epics - Epic data
 * @param {Array} userStories - User story data
 */
export function applyEpicStoryLinks(epics, userStories) {
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

/**
 * Apply links from user stories to requirements
 * @param {Array} userStories - User story data
 */
export function applyUserStoryLinks(userStories) {
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

// ============================================
// New Generator Links
// ============================================

/**
 * Link personas to user stories based on role matching
 * @param {Array} personas - Persona data
 * @param {Array} userStories - User story data
 */
export function applyPersonaStoryLinks(personas, userStories) {
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

/**
 * Link user flows to screens based on flow steps
 * @param {Array} userFlows - User flow data
 * @param {Array} screens - Screen data
 */
export function applyFlowScreenLinks(userFlows, screens) {
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

                // Partial match
                if (sNameLower.includes(screenNameLower) || screenNameLower.includes(sNameLower)) return true;

                // Word-based match
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
    console.log(`[Auto-Link] Created ${linkCount} flow -> screen links`);
}

/**
 * Link screens to user stories based on parent_user_story
 * @param {Array} screens - Screen data
 */
export function applyScreenStoryLinks(screens) {
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

/**
 * Link screens to UI components
 * @param {Array} screens - Screen data
 * @param {Array} components - UI component data
 */
export function applyScreenComponentLinks(screens, components) {
    if (!screens || !components) return;
    console.log(`[Auto-Link] Linking ${screens.length} screens to ${components.length} components`);

    // Map content types to component types for matching
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

        // Method 1: Direct component list
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

        // Method 2: Match content_types to component types
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
    console.log(`[Auto-Link] Created ${linkCount} screen -> component links`);
}

/**
 * Link features to tasks based on parent_feature_id
 * @param {Object} tasks - Tasks object { feature_id: [tasks] }
 */
export function applyFeatureTaskLinks(tasks) {
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

// ============================================
// Metadata-Based Links
// ============================================

/**
 * Comprehensive metadata-based auto-linking.
 * Links nodes based on their metadata fields (parent_*, linked_*, etc.)
 */
export function applyMetadataLinks() {
    let linkCount = 0;

    Object.entries(state.nodes).forEach(([id, node]) => {
        if (!node.data) return;

        // Diagram -> Parent Links
        if (node.type === 'diagram') {
            const parentId = node.data.parent_id || node.data.requirement_id ||
                           node.data.feature_id || node.data.parent_requirement;
            if (parentId && state.nodes[parentId]) {
                addConnection(parentId, id);
                linkCount++;
            } else if (parentId) {
                const parentNode = findNodeByPartialId('requirement', parentId) ||
                                  findNodeByPartialId('feature', parentId) ||
                                  findNodeByPartialId('epic', parentId);
                if (parentNode) {
                    addConnection(parentNode.element.dataset.nodeId, id);
                    linkCount++;
                }
            }
        }

        // Entity -> Requirement Links
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

        // API -> Requirement Links
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

        // Task -> Feature Links
        if (node.type === 'task') {
            const parentId = node.data.parent_feature_id || node.data.feature_id;
            let linked = false;
            const title = node.data.title || '';

            // PRIORITY 1: Use explicit parent_entity_id if available (new generator format)
            if (node.data.parent_entity_id && state.nodes[node.data.parent_entity_id]) {
                addConnection(node.data.parent_entity_id, id);
                linkCount++;
                linked = true;
            }

            // PRIORITY 2: Use explicit parent_api_resource if available (new generator format)
            if (!linked && node.data.parent_api_resource && state.nodes[node.data.parent_api_resource]) {
                addConnection(node.data.parent_api_resource, id);
                linkCount++;
                linked = true;
            }

            // PRIORITY 3: Fallback heuristics for old data format
            if (!linked && parentId) {
                const upperParentId = parentId.toUpperCase();

                // DATABASE category → link to matching entity (fallback)
                if (upperParentId === 'DATABASE') {
                    const entityMatch = title.match(/Create\s+(\w+)\s+model/i);
                    if (entityMatch) {
                        const entityName = entityMatch[1];
                        const entityNode = Object.entries(state.nodes).find(([nodeId, n]) =>
                            n.type === 'entity' &&
                            (n.data?.name?.toLowerCase() === entityName.toLowerCase() ||
                             nodeId.toLowerCase().includes(entityName.toLowerCase()))
                        );
                        if (entityNode) {
                            addConnection(entityNode[0], id);
                            linkCount++;
                            linked = true;
                        }
                    }
                }

                // API category → link to matching API node (fallback)
                if (upperParentId === 'API' && !linked) {
                    const apiMatch = title.match(/Implement\s+(\w+)\s+API/i);
                    if (apiMatch) {
                        const resourceName = apiMatch[1];
                        const apiNode = Object.entries(state.nodes).find(([nodeId, n]) =>
                            n.type === 'api' &&
                            (nodeId.toLowerCase().includes(resourceName.toLowerCase()) ||
                             n.data?.path?.toLowerCase().includes(resourceName.toLowerCase()))
                        );
                        if (apiNode) {
                            addConnection(apiNode[0], id);
                            linkCount++;
                            linked = true;
                        }
                    }
                }

                // Standard feature/epic linking (for real node IDs)
                if (!linked && !['DATABASE', 'API', 'FRONTEND', 'BACKEND', 'INFRASTRUCTURE'].includes(upperParentId)) {
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
        }

        // Screen -> User Story Links
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

        // Component -> Screen Links
        if (node.type === 'component') {
            // PRIORITY 1: Use explicit parent_screen_ids array (new generator format)
            if (node.data.parent_screen_ids && Array.isArray(node.data.parent_screen_ids)) {
                node.data.parent_screen_ids.forEach(screenId => {
                    if (state.nodes[screenId]) {
                        addConnection(screenId, id);
                        linkCount++;
                    }
                });
            }
            // PRIORITY 2: Fallback to single parent_screen (old format)
            else {
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
        }

        // User Flow -> Screen Links
        if (node.type === 'user-flow') {
            // Link to screens involved in this flow
            if (node.data.linked_screen_ids && Array.isArray(node.data.linked_screen_ids)) {
                node.data.linked_screen_ids.forEach(screenId => {
                    if (state.nodes[screenId]) {
                        addConnection(id, screenId);
                        linkCount++;
                    }
                });
            }
            // Link to persona performing this flow
            if (node.data.linked_persona_id && state.nodes[node.data.linked_persona_id]) {
                addConnection(node.data.linked_persona_id, id);
                linkCount++;
            }
            // Link to user stories this flow implements
            if (node.data.linked_user_story_ids && Array.isArray(node.data.linked_user_story_ids)) {
                node.data.linked_user_story_ids.forEach(usId => {
                    if (state.nodes[usId]) {
                        addConnection(usId, id);
                        linkCount++;
                    }
                });
            }
        }

        // Test -> Requirement Links
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

            // Test -> User Story Links (via linked_user_story field)
            const linkedStory = node.data.linked_user_story || node.data.user_story_id || node.data.parent_user_story;
            if (linkedStory) {
                const usNode = state.nodes[linkedStory] || findNodeByPartialId('user-story', linkedStory);
                if (usNode) {
                    const usNodeId = usNode.element?.dataset?.nodeId || linkedStory;
                    addConnection(usNodeId, id);
                    linkCount++;
                    console.log(`[Auto-Link] Linked test ${id} to user story ${usNodeId}`);
                }
            }
        }
    });

    console.log(`[Auto-Link] Applied ${linkCount} metadata-based links`);
}

/**
 * Apply links between tests and user stories based on test data
 * @param {Array} tests - Test data
 * @param {Array} userStories - User story data
 */
export function applyTestStoryLinks(tests, userStories) {
    if (!tests || tests.length === 0) return;

    let linkCount = 0;
    tests.forEach(test => {
        const linkedStory = test.linked_user_story || test.user_story_id;
        if (!linkedStory) return;

        const testNode = state.nodes[test.id];
        const usNode = state.nodes[linkedStory] || findNodeByPartialId('user-story', linkedStory);

        if (testNode && usNode) {
            const usNodeId = usNode.element?.dataset?.nodeId || linkedStory;
            addConnection(usNodeId, test.id);
            linkCount++;
        }
    });

    console.log(`[Auto-Link] Created ${linkCount} test -> user story links`);
}

// ============================================
// API / Entity / Screen Cross-Links (Graph Enhancement)
// ============================================

/**
 * Link API endpoints to their parent requirements.
 * Uses parent_requirement_id or linked_requirements from endpoint data.
 * @param {Array} apiEndpoints - API endpoint data
 */
export function applyApiRequirementLinks(apiEndpoints) {
    if (!apiEndpoints || apiEndpoints.length === 0) return;

    const linked = new Set();
    let linkCount = 0;
    apiEndpoints.forEach(ep => {
        const epNodeId = findApiNode(ep);
        if (!epNodeId) return;

        // Primary: parent_requirement_id
        const parentReq = ep.parent_requirement_id || ep.requirement_id;
        if (parentReq) {
            const reqNode = state.nodes[parentReq] || findNodeByPartialId('requirement', parentReq);
            if (reqNode) {
                const reqNodeId = reqNode.element?.dataset?.nodeId || parentReq;
                const key = `${reqNodeId}->${epNodeId}`;
                if (!linked.has(key)) {
                    addConnection(reqNodeId, epNodeId);
                    linked.add(key);
                    linkCount++;
                }
            }
        }

        // Secondary: linked_requirements array
        const linkedReqs = ep.linked_requirements || [];
        linkedReqs.forEach(reqId => {
            const reqNode = state.nodes[reqId] || findNodeByPartialId('requirement', reqId);
            if (reqNode) {
                const reqNodeId = reqNode.element?.dataset?.nodeId || reqId;
                const key = `${reqNodeId}->${epNodeId}`;
                if (!linked.has(key)) {
                    addConnection(reqNodeId, epNodeId);
                    linked.add(key);
                    linkCount++;
                }
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} requirement -> API links`);
}

/**
 * Link API endpoints to screens that consume them.
 * Matches screen.data_requirements against endpoint paths.
 * @param {Array} apiEndpoints - API endpoint data
 * @param {Array} screens - Screen data
 */
export function applyApiScreenLinks(apiEndpoints, screens) {
    if (!apiEndpoints || !screens) return;

    const linked = new Set();
    let linkCount = 0;
    screens.forEach(screen => {
        const screenId = screen.id;
        const screenNode = state.nodes[screenId] || findNodeByPartialId('screen', screenId);
        if (!screenNode) return;
        const screenNodeId = screenNode.element?.dataset?.nodeId || screenId;

        const dataReqs = screen.data_requirements || [];
        dataReqs.forEach(apiRef => {
            const pathPart = apiRef.replace(/^(GET|POST|PUT|DELETE|PATCH|WS)\s+/i, '').trim().toLowerCase();
            const apiNodeId = findApiNodeByPath(pathPart);
            if (apiNodeId) {
                const key = `${apiNodeId}->${screenNodeId}`;
                if (!linked.has(key)) {
                    addConnection(apiNodeId, screenNodeId);
                    linked.add(key);
                    linkCount++;
                }
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} API -> screen links`);
}

/**
 * Link entities to API endpoints that manage them.
 * Derives entity name from API path segments.
 * @param {Array} entities - Entity/data dictionary entries
 * @param {Array} apiEndpoints - API endpoint data
 */
export function applyEntityApiLinks(entities, apiEndpoints) {
    if (!entities || !apiEndpoints) return;

    // Build entity name lookup (lowercase, singular forms)
    const entityMap = {};
    entities.forEach(ent => {
        const name = ent.name || ent.id || '';
        if (name) {
            entityMap[name.toLowerCase()] = ent.id || ent.name;
            if (name.toLowerCase().endsWith('s')) {
                entityMap[name.toLowerCase().slice(0, -1)] = ent.id || ent.name;
            }
        }
    });

    const linked = new Set();
    let linkCount = 0;
    apiEndpoints.forEach(ep => {
        const path = ep.path || '';
        const segments = path.split('/').filter(s => s && !s.startsWith('{'));
        segments.forEach(seg => {
            const segLower = seg.toLowerCase();
            const entId = entityMap[segLower] || entityMap[segLower.replace(/s$/, '')];
            if (entId) {
                const entNode = state.nodes[entId] || findNodeByPartialId('entity', entId);
                const epNodeId = findApiNode(ep);
                if (entNode && epNodeId) {
                    const entNodeId = entNode.element?.dataset?.nodeId || entId;
                    const key = `${entNodeId}->${epNodeId}`;
                    if (!linked.has(key)) {
                        addConnection(entNodeId, epNodeId);
                        linked.add(key);
                        linkCount++;
                    }
                }
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} entity -> API links`);
}

/**
 * Link screens to entities they display.
 * Derives entity names from screen.data_requirements API paths.
 * @param {Array} screens - Screen data
 * @param {Array} entities - Entity/data dictionary entries
 */
export function applyScreenEntityLinks(screens, entities) {
    if (!screens || !entities) return;

    const entityMap = {};
    entities.forEach(ent => {
        const name = ent.name || ent.id || '';
        if (name) {
            entityMap[name.toLowerCase()] = ent.id || ent.name;
            if (name.toLowerCase().endsWith('s')) {
                entityMap[name.toLowerCase().slice(0, -1)] = ent.id || ent.name;
            }
        }
    });

    let linkCount = 0;
    screens.forEach(screen => {
        const screenId = screen.id;
        const screenNode = state.nodes[screenId] || findNodeByPartialId('screen', screenId);
        if (!screenNode) return;
        const screenNodeId = screenNode.element?.dataset?.nodeId || screenId;

        const dataReqs = screen.data_requirements || [];
        const linkedEntities = new Set();

        dataReqs.forEach(apiRef => {
            const pathPart = apiRef.replace(/^(GET|POST|PUT|DELETE|PATCH|WS)\s+/i, '').trim();
            const segments = pathPart.split('/').filter(s => s && !s.startsWith('{'));
            segments.forEach(seg => {
                const segLower = seg.toLowerCase();
                const entId = entityMap[segLower] || entityMap[segLower.replace(/s$/, '')];
                if (entId && !linkedEntities.has(entId)) {
                    linkedEntities.add(entId);
                    const entNode = state.nodes[entId] || findNodeByPartialId('entity', entId);
                    if (entNode) {
                        const entNodeId = entNode.element?.dataset?.nodeId || entId;
                        addConnection(screenNodeId, entNodeId);
                        linkCount++;
                    }
                }
            });
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} screen -> entity links`);
}

/**
 * Link tests to API endpoints they validate.
 * Searches test content for API path patterns.
 * @param {Array} tests - Test data
 * @param {Array} apiEndpoints - API endpoint data
 */
export function applyTestApiLinks(tests, apiEndpoints) {
    if (!tests || !apiEndpoints) return;

    const linked = new Set();
    let linkCount = 0;
    tests.forEach(test => {
        const testId = test.id;
        const testNode = state.nodes[testId] || findNodeByPartialId('test', testId);
        if (!testNode) return;
        const testNodeId = testNode.element?.dataset?.nodeId || testId;

        const content = (test.gherkin_content || test.title || '').toLowerCase();

        apiEndpoints.forEach(ep => {
            const path = (ep.path || '').toLowerCase();
            if (path && content.includes(path)) {
                const apiNodeId = findApiNode(ep);
                if (apiNodeId) {
                    const key = `${testNodeId}->${apiNodeId}`;
                    if (!linked.has(key)) {
                        addConnection(testNodeId, apiNodeId);
                        linked.add(key);
                        linkCount++;
                    }
                }
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} test -> API links`);
}

// ============================================
// Phase 3: Complete all 24 link types
// ============================================

/**
 * Link personas to screens via user story intermediary.
 * Persona -> UserStory (role match) -> Screen (parent_user_story match).
 * @param {Array} personas - Persona data
 * @param {Array} userStories - User story data
 * @param {Array} screens - Screen data
 */
export function applyPersonaScreenLinks(personas, userStories, screens) {
    if (!personas || !userStories || !screens) return;

    // Build story-id -> screen-ids lookup
    const storyToScreens = {};
    screens.forEach(screen => {
        const storyId = screen.parent_user_story;
        if (storyId) {
            if (!storyToScreens[storyId]) storyToScreens[storyId] = [];
            storyToScreens[storyId].push(screen.id);
        }
    });

    let linkCount = 0;
    personas.forEach(persona => {
        const personaNode = state.nodes[persona.id];
        if (!personaNode) return;

        const personaRole = (persona.role || '').toLowerCase();
        const personaName = (persona.name || '').toLowerCase();

        // Find stories matching this persona
        userStories.forEach(story => {
            const storyPersona = (story.persona || '').toLowerCase();
            if (!storyPersona.includes(personaRole) && !storyPersona.includes(personaName)) return;

            // Find screens linked to this story
            const screenIds = storyToScreens[story.id] || [];
            screenIds.forEach(screenId => {
                const screenNode = state.nodes[screenId] || findNodeByPartialId('screen', screenId);
                if (screenNode) {
                    const screenNodeId = screenNode.element?.dataset?.nodeId || screenId;
                    addConnection(persona.id, screenNodeId);
                    linkCount++;
                }
            });
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} persona -> screen links`);
}

/**
 * Link UI components to API endpoints via parent screen's data_requirements.
 * Component -> Screen (parent_screen_ids) -> data_requirements -> API.
 * @param {Array} components - UI component data
 * @param {Array} screens - Screen data
 * @param {Array} apiEndpoints - API endpoint data
 */
export function applyComponentApiLinks(components, screens, apiEndpoints) {
    if (!components || !screens || !apiEndpoints) return;

    // Build screen-id -> screen lookup
    const screenById = {};
    screens.forEach(s => { screenById[s.id] = s; });

    // Build API path lookup
    const pathToEpId = {};
    apiEndpoints.forEach(ep => {
        const path = ep.path || '';
        if (path) pathToEpId[path.toLowerCase()] = ep.id || ep.path;
    });

    let linkCount = 0;
    components.forEach(comp => {
        const compNode = state.nodes[comp.id] || findNodeByPartialId('component', comp.id);
        if (!compNode) return;
        const compNodeId = compNode.element?.dataset?.nodeId || comp.id;

        const parentScreenIds = comp.parent_screen_ids || [];
        const linkedApis = new Set();

        parentScreenIds.forEach(screenId => {
            const screen = screenById[screenId];
            if (!screen) return;

            const dataReqs = screen.data_requirements || [];
            dataReqs.forEach(apiRef => {
                const pathPart = apiRef.replace(/^(GET|POST|PUT|DELETE|PATCH|WS)\s+/i, '').trim().toLowerCase();
                const apiNodeId = findApiNodeByPath(pathPart);
                if (apiNodeId && !linkedApis.has(apiNodeId)) {
                    linkedApis.add(apiNodeId);
                    addConnection(compNodeId, apiNodeId);
                    linkCount++;
                }
            });
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} component -> API links`);
}

/**
 * Link API endpoints to entities they manage (API -> Entity direction).
 * Derives entity name from API path segments.
 * @param {Array} apiEndpoints - API endpoint data
 * @param {Array} entities - Entity/data dictionary entries
 */
export function applyApiEntityLinks(apiEndpoints, entities) {
    if (!apiEndpoints || !entities) return;

    const entityMap = {};
    entities.forEach(ent => {
        const name = ent.name || ent.id || '';
        if (name) {
            entityMap[name.toLowerCase()] = ent.id || ent.name;
            if (name.toLowerCase().endsWith('s')) {
                entityMap[name.toLowerCase().slice(0, -1)] = ent.id || ent.name;
            }
        }
    });

    const linked = new Set();
    let linkCount = 0;
    apiEndpoints.forEach(ep => {
        const path = ep.path || '';
        const epNodeId = findApiNode(ep);
        if (!epNodeId) return;

        const segments = path.split('/').filter(s => s && !s.startsWith('{'));
        segments.forEach(seg => {
            const segLower = seg.toLowerCase();
            const entId = entityMap[segLower] || entityMap[segLower.replace(/s$/, '')];
            if (entId) {
                const entNode = state.nodes[entId] || findNodeByPartialId('entity', entId);
                if (entNode) {
                    const entNodeId = entNode.element?.dataset?.nodeId || entId;
                    const key = `${epNodeId}->${entNodeId}`;
                    if (!linked.has(key)) {
                        addConnection(epNodeId, entNodeId);
                        linked.add(key);
                        linkCount++;
                    }
                }
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} API -> entity links`);
}

/**
 * Link diagrams to entities they visualize.
 * Parses ER diagram mermaid code for entity references.
 * @param {Array} diagrams - Diagram data (with mermaid_code)
 * @param {Array} entities - Entity/data dictionary entries
 */
export function applyDiagramEntityLinks(diagrams, entities) {
    if (!diagrams || !entities) return;

    const entityNames = entities.map(e => (e.name || e.id || '').toLowerCase()).filter(Boolean);

    let linkCount = 0;
    diagrams.forEach(diagram => {
        const code = diagram.mermaid_code || diagram.code || '';
        if (!code) return;

        const diagramId = diagram.id;
        const diagramNode = state.nodes[diagramId] || findNodeByPartialId('diagram', diagramId);
        if (!diagramNode) return;
        const diagramNodeId = diagramNode.element?.dataset?.nodeId || diagramId;

        const linkedEntities = new Set();
        const codeLower = code.toLowerCase();

        if (codeLower.includes('erdiagram')) {
            // ER diagram: extract entity definitions like "User {" or "User ||"
            const erEntityPattern = /^\s*(\w+)\s*(?:\{|\|\||\|o|o\|)/gm;
            let match;
            while ((match = erEntityPattern.exec(code)) !== null) {
                const name = match[1].toLowerCase();
                if (entityNames.includes(name) && !linkedEntities.has(name)) {
                    linkedEntities.add(name);
                }
            }
        }

        // Fallback: search for entity names in any diagram code
        if (linkedEntities.size === 0) {
            entityNames.forEach(name => {
                if (name.length > 2 && codeLower.includes(name) && !linkedEntities.has(name)) {
                    linkedEntities.add(name);
                }
            });
        }

        // Create links for matched entities
        linkedEntities.forEach(entName => {
            const entity = entities.find(e => (e.name || e.id || '').toLowerCase() === entName);
            if (!entity) return;
            const entId = entity.id || entity.name;
            const entNode = state.nodes[entId] || findNodeByPartialId('entity', entId);
            if (entNode) {
                const entNodeId = entNode.element?.dataset?.nodeId || entId;
                addConnection(diagramNodeId, entNodeId);
                linkCount++;
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} diagram -> entity links`);
}

/**
 * Link requirements to features via feature.requirements[] array.
 * @param {Array} features - Feature data with requirements arrays
 */
export function applyRequirementFeatureLinks(features) {
    if (!features) return;

    let linkCount = 0;
    features.forEach(feature => {
        const featureId = feature.id;
        const featureNode = state.nodes[featureId] || findNodeByPartialId('feature', featureId);
        if (!featureNode) return;
        const featureNodeId = featureNode.element?.dataset?.nodeId || featureId;

        const reqIds = feature.requirements || [];
        reqIds.forEach(reqId => {
            const reqNode = state.nodes[reqId] || findNodeByPartialId('requirement', reqId);
            if (reqNode) {
                const reqNodeId = reqNode.element?.dataset?.nodeId || reqId;
                addConnection(reqNodeId, featureNodeId);
                linkCount++;
            }
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} requirement -> feature links`);
}

/**
 * Link features to user stories via shared requirements.
 * Feature -> feature.requirements[] -> story.linked_requirement match.
 * @param {Array} features - Feature data
 * @param {Array} userStories - User story data
 */
export function applyFeatureStoryLinks(features, userStories) {
    if (!features || !userStories) return;

    // Build requirement-id -> story-ids lookup
    const reqToStories = {};
    userStories.forEach(story => {
        const reqId = story.linked_requirement;
        if (reqId) {
            if (!reqToStories[reqId]) reqToStories[reqId] = [];
            reqToStories[reqId].push(story.id);
        }
    });

    let linkCount = 0;
    features.forEach(feature => {
        const featureId = feature.id;
        const featureNode = state.nodes[featureId] || findNodeByPartialId('feature', featureId);
        if (!featureNode) return;
        const featureNodeId = featureNode.element?.dataset?.nodeId || featureId;

        const reqIds = feature.requirements || [];
        const linkedStories = new Set();

        reqIds.forEach(reqId => {
            const storyIds = reqToStories[reqId] || [];
            storyIds.forEach(storyId => {
                if (linkedStories.has(storyId)) return;
                linkedStories.add(storyId);

                const storyNode = state.nodes[storyId] || findNodeByPartialId('user-story', storyId);
                if (storyNode) {
                    const storyNodeId = storyNode.element?.dataset?.nodeId || storyId;
                    addConnection(featureNodeId, storyNodeId);
                    linkCount++;
                }
            });
        });
    });

    console.log(`[Auto-Link] Created ${linkCount} feature -> story links`);
}

/**
 * Link tech stack to UI components it enables.
 * All UI components are built on the tech stack, so link tech node to each component.
 * @param {Object} techStack - Tech stack data (single object)
 * @param {Array} components - UI component data
 */
export function applyTechComponentLinks(techStack, components) {
    if (!techStack || !components) return;

    // Find tech-stack node (could be single global or by ID)
    const techId = techStack.id || 'TECH-STACK';
    const techNode = state.nodes[techId] || findNodeByPartialId('tech-stack', techId);
    if (!techNode) return;
    const techNodeId = techNode.element?.dataset?.nodeId || techId;

    let linkCount = 0;
    components.forEach(comp => {
        const compNode = state.nodes[comp.id] || findNodeByPartialId('component', comp.id);
        if (compNode) {
            const compNodeId = compNode.element?.dataset?.nodeId || comp.id;
            addConnection(techNodeId, compNodeId);
            linkCount++;
        }
    });

    console.log(`[Auto-Link] Created ${linkCount} tech-stack -> component links`);
}
