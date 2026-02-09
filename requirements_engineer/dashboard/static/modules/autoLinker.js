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
