/**
 * RE System Dashboard - Sidebar Module
 *
 * Handles sidebar list management, item creation, and node focus.
 */

import { state, elements } from '../state.js';

// ============================================
// Update Canvas Transform (injected)
// ============================================

let updateCanvasTransformFn = null;
let updateMinimapFn = null;

export function setSidebarCallbacks(cbs) {
    updateCanvasTransformFn = cbs.updateCanvasTransform || (() => {});
    updateMinimapFn = cbs.updateMinimap || (() => {});
}

// ============================================
// Sidebar Items
// ============================================

/**
 * Add an item to a sidebar list
 * @param {string} listId - DOM ID of the target list
 * @param {string} id - Node ID
 * @param {string} title - Item title
 * @param {string} priority - Priority badge (optional)
 */
export function addSidebarItem(listId, id, title, priority) {
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

/**
 * Focus on a specific node (center in viewport)
 * @param {string} nodeId - Node ID to focus
 */
export function focusNode(nodeId) {
    const nodeData = state.nodes[nodeId];
    if (!nodeData) return;

    const containerRect = elements.canvasContainer.getBoundingClientRect();
    state.canvas.x = -nodeData.x * state.canvas.zoom + containerRect.width / 2 - 100;
    state.canvas.y = -nodeData.y * state.canvas.zoom + containerRect.height / 2 - 50;

    if (updateCanvasTransformFn) updateCanvasTransformFn();
    if (updateMinimapFn) updateMinimapFn();

    // Highlight node
    document.querySelectorAll('.canvas-node').forEach(n => n.classList.remove('selected'));
    nodeData.element.classList.add('selected');
}

/**
 * Update sidebar count badges
 */
export function updateCounts() {
    const pairs = [
        [elements.reqCount, elements.requirementsList],
        [elements.usCount, elements.userStoriesList],
        [elements.epicCount, elements.epicsList],
        [elements.testCount, elements.testsList],
        [elements.diagramCount, elements.diagramsList],
        [elements.screenCount, elements.screensList],
        [elements.apiCount, elements.apiList],
        [elements.personaCount, elements.personasList],
        [elements.componentCount, elements.componentsList],
        [elements.taskCount, elements.tasksList],
        [elements.serviceCount, elements.servicesList],
        [elements.stateMachineCount, elements.stateMachinesList],
    ];
    pairs.forEach(([badge, list]) => {
        if (!badge || !list) return;
        const count = list.children.length || 0;
        badge.textContent = count;
        // Auto-hide empty sidebar sections
        const section = list.closest('.sidebar-section');
        if (section) {
            section.style.display = count === 0 ? 'none' : '';
        }
    });
}

/**
 * Clear all sidebar lists
 */
export function clearSidebar() {
    if (elements.requirementsList) elements.requirementsList.innerHTML = '';
    if (elements.userStoriesList) elements.userStoriesList.innerHTML = '';
    if (elements.epicsList) elements.epicsList.innerHTML = '';
    if (elements.testsList) elements.testsList.innerHTML = '';
    if (elements.diagramsList) elements.diagramsList.innerHTML = '';
    if (elements.screensList) elements.screensList.innerHTML = '';
    if (elements.apiList) elements.apiList.innerHTML = '';
    if (elements.personasList) elements.personasList.innerHTML = '';
    if (elements.componentsList) elements.componentsList.innerHTML = '';
    if (elements.tasksList) elements.tasksList.innerHTML = '';
    if (elements.servicesList) elements.servicesList.innerHTML = '';
    if (elements.stateMachinesList) elements.stateMachinesList.innerHTML = '';
    updateCounts();
}
