/**
 * RE System Dashboard - Detail Panel Module
 *
 * Shows detailed information about selected nodes.
 */

import { state, getTagType, highlightGherkin, escapeHtml } from '../state.js';

// ============================================
// Type Tag Utilities
// ============================================

const TYPE_LABELS = {
    'requirement': 'REQ',
    'epic': 'EPIC',
    'user-story': 'US',
    'test': 'TEST',
    'api': 'API',
    'api-package': 'PKG',
    'persona': 'PERS',
    'user-flow': 'FLOW',
    'screen': 'SCR',
    'component': 'COMP',
    'task': 'TASK',
    'task-group': 'TASKS',
    'diagram': 'DIAG',
    'entity': 'ENT',
    'tech-stack': 'TECH',
    'service': 'SVC',
    'state-machine': 'SM',
    'infrastructure': 'INFRA',
    'design-tokens': 'TOKEN'
};

const TYPE_COLORS = {
    'requirement': '#1d9bf0',
    'epic': '#7856ff',
    'user-story': '#00ba7c',
    'test': '#f4212e',
    'api': '#ff7a00',
    'api-package': '#ff7a00',
    'persona': '#f97316',
    'user-flow': '#ec4899',
    'screen': '#8b5cf6',
    'component': '#84cc16',
    'task': '#f59e0b',
    'task-group': '#f59e0b',
    'diagram': '#ffd400',
    'entity': '#14b8a6',
    'tech-stack': '#06b6d4',
    'service': '#0ea5e9',
    'state-machine': '#a855f7',
    'infrastructure': '#64748b',
    'design-tokens': '#ec4899'
};

/**
 * Render a link item with type tag
 * @param {string} nodeId - Target node ID
 * @param {string} direction - 'from' or 'to'
 * @returns {string} HTML for link item
 */
function renderLinkItem(nodeId, direction) {
    const nodeData = state.nodes[nodeId];
    const nodeType = nodeData?.type || 'unknown';
    const typeLabel = TYPE_LABELS[nodeType] || nodeType.toUpperCase().slice(0, 4);
    const typeColor = TYPE_COLORS[nodeType] || '#888';
    const title = nodeData?.data?.title || nodeData?.data?.name || '';
    const titleDisplay = title ? ` - ${escapeHtml(title.slice(0, 30))}${title.length > 30 ? '...' : ''}` : '';

    return `
        <li onclick="window.focusNode('${escapeHtml(nodeId)}')" title="${escapeHtml(title)}">
            <span class="link-type-tag" style="background: ${typeColor}">${typeLabel}</span>
            <span class="link-id">${escapeHtml(nodeId)}</span>
            <span class="link-title">${titleDisplay}</span>
        </li>
    `;
}

// ============================================
// Focus Node Callback
// ============================================

let focusNodeFn = null;

export function setDetailPanelCallbacks(cbs) {
    focusNodeFn = cbs.focusNode || (() => {});
}

// ============================================
// Detail Panel Management
// ============================================

/**
 * Show the detail panel for a node
 * @param {string} nodeId - Node ID
 * @param {Object} nodeData - Node data object
 */
export function showDetailPanel(nodeId, nodeData) {
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
            <h3>${escapeHtml(nodeId)}</h3>
            <button onclick="window.hideDetailPanel()" class="close-btn">×</button>
        </div>
        <div class="detail-type">${escapeHtml(nodeData.type)}</div>
        <div class="detail-title">${escapeHtml(nodeData.data.title || nodeData.data.name || '')}</div>
    `;

    // Show description if available
    if (nodeData.data.description) {
        content += `<div class="detail-description">${escapeHtml(nodeData.data.description)}</div>`;
    }

    // Show connections
    const incoming = state.connections.filter(c => c.to === nodeId);
    const outgoing = state.connections.filter(c => c.from === nodeId);

    if (incoming.length > 0) {
        content += `
            <div class="detail-section">
                <h4>← Eingehende Links (${incoming.length})</h4>
                <ul class="link-list">
                    ${incoming.map(c => renderLinkItem(c.from, 'from')).join('')}
                </ul>
            </div>
        `;
    }

    if (outgoing.length > 0) {
        content += `
            <div class="detail-section">
                <h4>→ Ausgehende Links (${outgoing.length})</h4>
                <ul class="link-list">
                    ${outgoing.map(c => renderLinkItem(c.to, 'to')).join('')}
                </ul>
            </div>
        `;
    }

    // Type-specific content
    content += buildTypeSpecificContent(nodeData);

    panel.innerHTML = content;
    panel.classList.add('visible');

    // Add body class for panel overlap management
    document.body.classList.add('detail-panel-open');
}

/**
 * Build type-specific detail content
 * @param {Object} nodeData - Node data object
 * @returns {string} HTML content
 */
function buildTypeSpecificContent(nodeData) {
    let content = '';
    const d = nodeData.data;

    switch (nodeData.type) {
        case 'requirement': {
            // Quality scores
            const scores = [
                { name: 'Completeness', val: d.completeness_score },
                { name: 'Consistency', val: d.consistency_score },
                { name: 'Testability', val: d.testability_score },
                { name: 'Clarity', val: d.clarity_score },
                { name: 'Feasibility', val: d.feasibility_score },
                { name: 'Traceability', val: d.traceability_score }
            ].filter(s => s.val !== undefined && s.val !== null && s.val > 0);
            if (scores.length > 0) {
                content += `<div class="detail-section"><h4>Quality Scores</h4><div class="detail-score-grid">`;
                scores.forEach(s => {
                    const pct = Math.round(s.val * 100);
                    const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
                    content += `<div class="score-row"><span class="score-label">${s.name}</span><div class="score-bar"><div class="score-fill" style="width:${pct}%;background:${color}"></div></div><span class="score-val">${pct}%</span></div>`;
                });
                content += `</div></div>`;
            }
            // Description
            if (d.description) {
                content += `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            // Analysis & suggestions
            if (d.analysis) {
                content += `<div class="detail-section"><h4>Analysis</h4><p>${escapeHtml(d.analysis)}</p></div>`;
            }
            if (d.improvement_suggestions && d.improvement_suggestions.length) {
                content += `<div class="detail-section"><h4>Improvement Suggestions</h4><ul>${d.improvement_suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul></div>`;
            }
            if (d.quality_issues && d.quality_issues.length) {
                content += `<div class="detail-section"><h4>Quality Issues</h4><ul>${d.quality_issues.map(i => `<li class="issue-item">${escapeHtml(i)}</li>`).join('')}</ul></div>`;
            }
            // Dependencies & relationships
            if (d.dependencies && d.dependencies.length) {
                content += `<div class="detail-section"><h4>Dependencies</h4><div class="detail-chip-list">${d.dependencies.map(dep => `<span class="detail-chip">${escapeHtml(dep)}</span>`).join('')}</div></div>`;
            }
            if (d.related_requirements && d.related_requirements.length) {
                content += `<div class="detail-section"><h4>Related Requirements</h4><div class="detail-chip-list">${d.related_requirements.map(r => `<span class="detail-chip">${escapeHtml(r)}</span>`).join('')}</div></div>`;
            }
            // Work info
            if (d.work_package || d.estimated_effort || d.assigned_to) {
                content += `<div class="detail-section"><h4>Work Info</h4>`;
                if (d.work_package) content += `<p><b>Package:</b> ${escapeHtml(d.work_package)}</p>`;
                if (d.estimated_effort) content += `<p><b>Effort:</b> ${escapeHtml(d.estimated_effort)}</p>`;
                if (d.assigned_to) content += `<p><b>Assigned:</b> ${escapeHtml(d.assigned_to)}</p>`;
                content += `</div>`;
            }
            // Metadata
            if (d.created_at || d.version) {
                content += `<div class="detail-meta">`;
                if (d.version) content += `<span>v${d.version}</span>`;
                if (d.stage_name) content += `<span>${escapeHtml(d.stage_name)}</span>`;
                if (d.created_at) content += `<span>${new Date(d.created_at).toLocaleDateString('de-DE')}</span>`;
                content += `</div>`;
            }
            break;
        }

        case 'epic': {
            if (d.description) {
                content = `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            if (d.status) {
                content += `<div class="detail-status"><b>Status:</b> ${escapeHtml(d.status)}</div>`;
            }
            if (d.linked_requirements && d.linked_requirements.length) {
                content += `<div class="detail-section"><h4>Requirements (${d.linked_requirements.length})</h4><div class="detail-chip-list">${d.linked_requirements.map(r => `<span class="detail-chip chip-clickable" onclick="window.modalFocusNode && window.modalFocusNode('${escapeHtml(r)}')">${escapeHtml(r)}</span>`).join('')}</div></div>`;
            }
            if (d.linked_user_stories && d.linked_user_stories.length) {
                content += `<div class="detail-section"><h4>User Stories (${d.linked_user_stories.length})</h4><div class="detail-chip-list">${d.linked_user_stories.map(s => `<span class="detail-chip chip-clickable" onclick="window.modalFocusNode && window.modalFocusNode('${escapeHtml(s)}')">${escapeHtml(s)}</span>`).join('')}</div></div>`;
            }
            break;
        }

        case 'user-story':
            content = `
                <div class="detail-story">
                    <p><b>As a</b> ${escapeHtml(d.persona || 'user')}</p>
                    <p><b>I want to</b> ${escapeHtml(d.action || '...')}</p>
                    <p><b>So that</b> ${escapeHtml(d.benefit || '...')}</p>
                </div>
            `;
            if (d.acceptance_criteria && d.acceptance_criteria.length) {
                content += `<div class="detail-section"><h4>Acceptance Criteria (${d.acceptance_criteria.length})</h4><ul>${d.acceptance_criteria.map(ac => {
                    if (typeof ac === 'object') {
                        return `<li><b>Given</b> ${escapeHtml(ac.given || '')}<br><b>When</b> ${escapeHtml(ac.when || '')}<br><b>Then</b> ${escapeHtml(ac.then || '')}</li>`;
                    }
                    return `<li>${escapeHtml(ac)}</li>`;
                }).join('')}</ul></div>`;
            }
            break;

        case 'api':
            content = `
                <div class="detail-api">
                    <code class="api-method method-${(d.method || 'GET').toLowerCase()}">${escapeHtml(d.method || 'GET')}</code>
                    <code class="api-path">${escapeHtml(d.path || '/')}</code>
                </div>
            `;
            if (d.description) {
                content += `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            break;

        case 'test': {
            const scenarioCount = d.scenario_count || 0;
            content = `<div class="detail-scenario-count">${scenarioCount} ${scenarioCount === 1 ? 'Scenario' : 'Scenarios'}</div>`;
            if (d.tags && d.tags.length > 0) {
                content += `<div class="detail-tags">${d.tags.map(tag =>
                    `<span class="tag-badge tag-${getTagType(tag)}">${escapeHtml(tag)}</span>`
                ).join('')}</div>`;
            }
            if (d.linked_user_story) {
                content += `<div class="detail-link"><b>Linked Story:</b> <span class="detail-chip chip-clickable" onclick="window.modalFocusNode && window.modalFocusNode('${escapeHtml(d.linked_user_story)}')">${escapeHtml(d.linked_user_story)}</span></div>`;
            }
            // Gherkin content
            if (d.gherkin_content) {
                content += `<div class="detail-gherkin"><pre><code>${highlightGherkin(d.gherkin_content)}</code></pre></div>`;
            } else if (d.content) {
                content += `<div class="detail-gherkin"><pre><code>${highlightGherkin(d.content)}</code></pre></div>`;
            }
            break;
        }

        case 'persona':
            if (d.role) {
                content = `<div class="detail-role"><b>Role:</b> ${escapeHtml(d.role)}</div>`;
            }
            if (d.tech_savviness) {
                content += `<div class="detail-tech-level"><b>Tech Level:</b> ${escapeHtml(d.tech_savviness)}</div>`;
            }
            if (d.goals && d.goals.length > 0) {
                content += `<div class="detail-section"><h4>Goals (${d.goals.length})</h4><ul>${d.goals.map(g => `<li>${escapeHtml(g)}</li>`).join('')}</ul></div>`;
            }
            if (d.pain_points && d.pain_points.length > 0) {
                content += `<div class="detail-section"><h4>Pain Points (${d.pain_points.length})</h4><ul>${d.pain_points.map(p => `<li>${escapeHtml(p)}</li>`).join('')}</ul></div>`;
            }
            break;

        case 'tech-stack':
            content = `
                <div class="detail-tech">
                    <p><b>Frontend:</b> ${escapeHtml(d.frontend_framework || 'N/A')}</p>
                    <p><b>Backend:</b> ${escapeHtml(d.backend_framework || 'N/A')}</p>
                    <p><b>Database:</b> ${escapeHtml(d.primary_database || 'N/A')}</p>
                    <p><b>Cloud:</b> ${escapeHtml(d.cloud_provider || 'N/A')}</p>
                </div>
            `;
            break;

        case 'screen':
            if (d.route) {
                content = `<div class="detail-route"><code>${escapeHtml(d.route)}</code></div>`;
            }
            if (d.description) {
                content += `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            if (d.layout) {
                content += `<div class="detail-layout"><b>Layout:</b> ${escapeHtml(d.layout)}</div>`;
            }
            if (d.wireframe_ascii) {
                content += `<div class="detail-section detail-wireframe-section"><h4>Wireframe</h4><pre class="detail-wireframe-ascii">${escapeHtml(d.wireframe_ascii)}</pre></div>`;
            }
            if (d.components && d.components.length > 0) {
                content += `<div class="detail-section"><h4>Components (${d.components.length})</h4><div class="detail-chip-list">${d.components.map(c => `<span class="detail-chip">${escapeHtml(c)}</span>`).join('')}</div></div>`;
            }
            if (d.data_requirements && d.data_requirements.length > 0) {
                content += `<div class="detail-section"><h4>Data Requirements</h4><ul>${d.data_requirements.map(dr => `<li><code>${escapeHtml(dr)}</code></li>`).join('')}</ul></div>`;
            }
            break;

        case 'component':
            if (d.component_type) {
                content = `<div class="detail-type"><b>Type:</b> ${escapeHtml(d.component_type)}</div>`;
            }
            if (d.variants && d.variants.length) {
                content += `<div class="detail-section"><h4>Variants (${d.variants.length})</h4><div class="detail-chip-list">${d.variants.map(v => `<span class="detail-chip">${escapeHtml(v)}</span>`).join('')}</div></div>`;
            }
            if (d.states && d.states.length) {
                content += `<div class="detail-section"><h4>States</h4><div class="detail-chip-list">${d.states.map(s => `<span class="detail-chip">${escapeHtml(s)}</span>`).join('')}</div></div>`;
            }
            if (d.props && Object.keys(d.props).length) {
                content += `<div class="detail-section"><h4>Props</h4><ul>${Object.entries(d.props).map(([k,v]) => `<li><code>${escapeHtml(k)}</code>: ${escapeHtml(String(v))}</li>`).join('')}</ul></div>`;
            }
            break;

        case 'entity':
            if (d.description) {
                content = `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            if (d.attributes && d.attributes.length) {
                content += `<div class="detail-section"><h4>Attributes (${d.attributes.length})</h4><table class="detail-attr-table"><thead><tr><th>Name</th><th>Type</th><th>Req</th></tr></thead><tbody>`;
                d.attributes.forEach(attr => {
                    content += `<tr><td>${escapeHtml(attr.name || '')}</td><td><code>${escapeHtml(attr.type || '')}</code></td><td>${attr.required ? 'Yes' : ''}</td></tr>`;
                });
                content += `</tbody></table></div>`;
            }
            if (d.source_requirements && d.source_requirements.length) {
                content += `<div class="detail-section"><h4>Source Requirements</h4><div class="detail-chip-list">${d.source_requirements.map(r => `<span class="detail-chip">${escapeHtml(r)}</span>`).join('')}</div></div>`;
            }
            break;

        case 'task':
            content = `
                <div class="detail-task">
                    <p><b>Type:</b> ${escapeHtml(d.task_type || 'N/A')}</p>
                    <p><b>Estimated Hours:</b> ${d.estimated_hours || 'N/A'}</p>
                    <p><b>Complexity:</b> ${escapeHtml(d.complexity || 'N/A')}</p>
                </div>
            `;
            if (d.description) {
                content += `<div class="detail-description">${escapeHtml(d.description)}</div>`;
            }
            if (d.parent_feature_id) {
                content += `<div class="detail-link"><b>Feature:</b> <span class="detail-chip">${escapeHtml(d.parent_feature_id)}</span></div>`;
            }
            break;

        case 'api-package': {
            content = `<div class="detail-api-pkg"><p><b>Resource:</b> ${escapeHtml(d.tag || '')}</p><p><b>Endpoints:</b> ${d.endpoint_count || 0}</p></div>`;
            const mc = d.method_counts || {};
            if (Object.keys(mc).length) {
                content += `<div class="detail-section"><h4>Methods</h4><div class="detail-chip-list">${Object.entries(mc).map(([m, c]) => `<span class="method-chip method-${m.toLowerCase()}">${m}: ${c}</span>`).join(' ')}</div></div>`;
            }
            if (d.endpoints?.length) {
                content += `<div class="detail-section"><h4>Endpoints (preview)</h4><ul class="detail-ep-list">`;
                d.endpoints.slice(0, 8).forEach(ep => {
                    content += `<li><span class="method-chip method-${(ep.method||'GET').toLowerCase()}">${ep.method}</span> <code>${escapeHtml(ep.path)}</code></li>`;
                });
                if (d.endpoints.length > 8) content += `<li class="detail-more">+${d.endpoints.length - 8} more...</li>`;
                content += `</ul></div>`;
            }
            break;
        }

        case 'task-group': {
            content = `<div class="detail-task-group"><p><b>Feature:</b> ${escapeHtml(d.title || d.feature_id || '')}</p><p><b>Tasks:</b> ${d.task_count || 0}</p><p><b>Total Hours:</b> ${d.total_hours || 0}h</p></div>`;
            if (d.tasks?.length) {
                content += `<div class="detail-section"><h4>Tasks (preview)</h4><ul>`;
                d.tasks.slice(0, 6).forEach(t => {
                    content += `<li><code>${escapeHtml(t.id || '')}</code> ${escapeHtml(t.title || '')} <span class="detail-chip">${t.estimated_hours || 0}h</span></li>`;
                });
                if (d.tasks.length > 6) content += `<li class="detail-more">+${d.tasks.length - 6} more...</li>`;
                content += `</ul></div>`;
            }
            break;
        }

        case 'service': {
            content = `<div class="detail-service">`;
            if (d.technology) content += `<p><b>Technology:</b> <span class="detail-chip">${escapeHtml(d.technology)}</span></p>`;
            if (d.type) content += `<p><b>Type:</b> ${escapeHtml(d.type)}</p>`;
            if (d.ports?.length) content += `<p><b>Ports:</b> ${d.ports.join(', ')}</p>`;
            content += `</div>`;
            if (d.responsibilities?.length) {
                content += `<div class="detail-section"><h4>Responsibilities</h4><ul>${d.responsibilities.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul></div>`;
            }
            if (d.dependencies?.length) {
                content += `<div class="detail-section"><h4>Dependencies</h4><div class="detail-chip-list">${d.dependencies.map(dep => `<span class="detail-chip">${escapeHtml(dep)}</span>`).join('')}</div></div>`;
            }
            break;
        }

        case 'state-machine': {
            content = `<div class="detail-sm"><p><b>Entity:</b> ${escapeHtml(d.entity || '')}</p><p><b>States:</b> ${d.state_count || 0}</p><p><b>Transitions:</b> ${d.transition_count || 0}</p></div>`;
            if (d.states?.length) {
                content += `<div class="detail-section"><h4>States</h4><div class="detail-chip-list">${d.states.map(s => `<span class="detail-chip">${escapeHtml(typeof s === 'string' ? s : s.name || s.id || '')}</span>`).join('')}</div></div>`;
            }
            break;
        }

        case 'infrastructure': {
            content = `<div class="detail-infra">`;
            if (d.architecture_style) content += `<p><b>Style:</b> ${escapeHtml(d.architecture_style)}</p>`;
            if (d.service_count) content += `<p><b>Services:</b> ${d.service_count}</p>`;
            const infraFlags = [];
            if (d.has_dockerfile) infraFlags.push('Dockerfile');
            if (d.has_k8s) infraFlags.push('Kubernetes');
            if (d.has_ci) infraFlags.push('CI/CD');
            if (infraFlags.length) content += `<p><b>Features:</b> ${infraFlags.join(', ')}</p>`;
            if (d.services?.length) {
                content += `<div class="detail-section"><h4>Services</h4><div class="detail-chip-list">${d.services.map(s => `<span class="detail-chip">${escapeHtml(s.name || s.id || '')}</span>`).join('')}</div></div>`;
            }
            content += `</div>`;
            break;
        }

        case 'design-tokens': {
            content = '<div class="detail-tokens">';
            const colors = d.colors || {};
            if (Object.keys(colors).length) {
                content += `<div class="detail-section"><h4>Colors</h4><div class="detail-color-grid">`;
                Object.entries(colors).forEach(([name, val]) => {
                    const hex = typeof val === 'string' ? val : val.value || '';
                    content += `<div class="detail-color-swatch"><span style="background:${hex};width:16px;height:16px;display:inline-block;border-radius:3px;border:1px solid rgba(0,0,0,0.2);"></span> <code>${escapeHtml(name)}</code></div>`;
                });
                content += `</div></div>`;
            }
            content += '</div>';
            break;
        }
    }

    return content;
}

/**
 * Hide the detail panel
 */
export function hideDetailPanel() {
    const panel = document.getElementById('detail-panel');
    if (panel) {
        panel.classList.remove('visible');
    }
    // Remove body class for panel overlap management
    document.body.classList.remove('detail-panel-open');
}

/**
 * Add click handler to a node for showing detail panel
 * @param {HTMLElement} nodeElement - Node DOM element
 * @param {string} nodeId - Node ID
 */
export function addNodeClickHandler(nodeElement, nodeId) {
    nodeElement.addEventListener('click', (e) => {
        // Don't show panel if dragging
        if (state.dragging && state.dragging.active) return;

        const nodeData = state.nodes[nodeId];
        if (nodeData) {
            showDetailPanel(nodeId, nodeData);
        }
    });

    // Double-click opens full modal for expandable node types
    nodeElement.addEventListener('dblclick', (e) => {
        const nodeData = state.nodes[nodeId];
        if (!nodeData) return;
        e.preventDefault();
        e.stopPropagation();
        if (nodeData.type === 'screen' && typeof window.openScreenWireframeModal === 'function') {
            window.openScreenWireframeModal(nodeId);
        } else if (nodeData.type === 'api-package' && typeof window.openApiPackageModal === 'function') {
            window.openApiPackageModal(nodeId);
        } else if (nodeData.type === 'task-group' && typeof window.openTaskGroupModal === 'function') {
            window.openTaskGroupModal(nodeId);
        } else if (nodeData.type === 'state-machine' && typeof window.openStateMachineModal === 'function') {
            window.openStateMachineModal(nodeId);
        }
    });
}

// Export hideDetailPanel and showDetailPanel to window for HTML onclick handlers
if (typeof window !== 'undefined') {
    window.hideDetailPanel = hideDetailPanel;
    window.showDetailPanel = showDetailPanel;
}
