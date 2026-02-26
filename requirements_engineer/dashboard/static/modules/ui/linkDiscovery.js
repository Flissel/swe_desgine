/**
 * Link Discovery - Auto-discover orphan node links via LLM agent
 *
 * Manages the sidebar #link-suggestions section:
 * - discoverLinks(): POST /api/links/discover, renders suggestion cards
 * - approveLink(id): POST /api/links/approve/{id}, creates canvas connection
 * - rejectLink(id): POST /api/links/reject/{id}, removes card
 * - updateOrphanCount(count): updates #orphan-count badge
 * - getOrphanCount(): client-side orphan detection
 *
 * Backend: requirements_engineer/propagation/auto_linker.py
 * CSS: style.css lines 4430-4520 (.suggestion-card, .link-suggestion, etc.)
 */

import { state, log, escapeHtml } from '../state.js';
import { addConnection, updateConnections } from '../connections.js';

// ============================================
// State
// ============================================

const linkSuggestions = {};

// ============================================
// Orphan Detection (client-side)
// ============================================

/**
 * Count nodes with zero connections.
 * @returns {number} Number of orphan nodes
 */
export function getOrphanCount() {
    const connectedIds = new Set();
    for (const c of state.connections) {
        connectedIds.add(c.from);
        connectedIds.add(c.to);
    }
    let count = 0;
    for (const id of Object.keys(state.nodes)) {
        if (!connectedIds.has(id)) count++;
    }
    return count;
}

/**
 * Update the #orphan-count badge.
 * @param {number} count
 */
export function updateOrphanCount(count) {
    const badge = document.getElementById('orphan-count');
    if (badge) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline' : 'none';
    }
}

// ============================================
// Discovery
// ============================================

/**
 * Discover link suggestions for all orphan nodes.
 * Calls POST /api/links/discover (backend runs LLM in parallel).
 */
export async function discoverLinks() {
    const btn = document.getElementById('btn-discover-links');
    const originalText = btn ? btn.textContent : '';

    // Loading state
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Suche...';
    }

    try {
        const response = await fetch('/api/links/discover', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            const suggestions = result.suggestions || [];
            suggestions.forEach(s => addLinkSuggestion(s));
            updateOrphanCount(result.orphan_count || 0);
            log('success', `${suggestions.length} Link-Vorschlag(e) generiert`);
        } else {
            log('error', `Link-Erkennung fehlgeschlagen: ${result.error || 'Unbekannter Fehler'}`);
        }
    } catch (e) {
        log('error', `Link-Erkennung fehlgeschlagen: ${e.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

// ============================================
// Suggestion Management
// ============================================

function addLinkSuggestion(data) {
    if (linkSuggestions[data.id]) return; // dedupe
    linkSuggestions[data.id] = data;
    renderLinkSuggestions();
}

function removeLinkSuggestion(id) {
    delete linkSuggestions[id];
    renderLinkSuggestions();
}

// ============================================
// Rendering
// ============================================

function renderLinkSuggestions() {
    const container = document.getElementById('link-suggestions');
    if (!container) return;

    const items = Object.values(linkSuggestions);

    if (items.length === 0) {
        container.innerHTML = '<p class="empty-state">Keine Link-Vorschlage</p>';
        return;
    }

    container.innerHTML = items.map(s => {
        const pct = Math.round((s.confidence || 0) * 100);
        const cls = pct >= 70 ? 'high' : pct >= 40 ? 'medium' : 'low';

        return `
        <div class="suggestion-card link-suggestion" data-suggestion-id="${escapeHtml(s.id)}">
            <div class="suggestion-header">
                <span class="orphan-node">${escapeHtml(s.orphan_node_title || s.orphan_node_id)}</span>
            </div>
            <div class="suggestion-target-info">
                <span class="link-type-badge">${escapeHtml(s.link_type || 'related')}</span>
                <span class="target-node">${escapeHtml(s.target_node_title || s.target_node_id)}</span>
            </div>
            <div class="suggestion-reasoning">${escapeHtml(s.reasoning || '')}</div>
            <div class="suggestion-confidence">
                <span class="confidence-label">Konfidenz:</span>
                <span class="confidence-value ${cls}">${pct}%</span>
            </div>
            <div class="suggestion-actions">
                <button class="btn-approve" data-action="approve" data-id="${escapeHtml(s.id)}">Link erstellen</button>
                <button class="btn-reject" data-action="reject" data-id="${escapeHtml(s.id)}">Ablehnen</button>
            </div>
        </div>`;
    }).join('');
}

// Bind the Auto-Discover button (replaces inline onclick)
const discoverBtn = document.getElementById('btn-discover-links');
if (discoverBtn) {
    discoverBtn.addEventListener('click', discoverLinks);
}

// Event delegation for approve/reject clicks
document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;

    const container = btn.closest('#link-suggestions');
    if (!container) return;

    const action = btn.dataset.action;
    const id = btn.dataset.id;
    if (!id) return;

    if (action === 'approve') approveLink(id);
    else if (action === 'reject') rejectLink(id);
});

// ============================================
// Approve / Reject
// ============================================

/**
 * Approve a link suggestion — creates a canvas connection.
 * @param {string} suggestionId
 */
export async function approveLink(suggestionId) {
    const suggestion = linkSuggestions[suggestionId];

    try {
        const response = await fetch(`/api/links/approve/${suggestionId}`, { method: 'POST' });
        const result = await response.json();

        if (result.success && suggestion) {
            addConnection(suggestion.orphan_node_id, suggestion.target_node_id, suggestion.link_type || 'discovered');
            updateConnections();
            log('success', `Link erstellt: ${suggestion.orphan_node_title || suggestion.orphan_node_id} -> ${suggestion.target_node_title || suggestion.target_node_id}`);
        }
    } catch (e) {
        log('error', `Link-Genehmigung fehlgeschlagen: ${e.message}`);
    }

    removeLinkSuggestion(suggestionId);
    updateOrphanCount(getOrphanCount());
}

/**
 * Reject a link suggestion.
 * @param {string} suggestionId
 */
export async function rejectLink(suggestionId) {
    try {
        await fetch(`/api/links/reject/${suggestionId}`, { method: 'POST' });
    } catch (e) {
        log('error', `Link-Ablehnung fehlgeschlagen: ${e.message}`);
    }

    removeLinkSuggestion(suggestionId);
}

// ============================================
// WebSocket Handlers
// ============================================

/**
 * Handle incoming link_suggestion WebSocket event.
 */
export function handleLinkSuggestion(data) {
    addLinkSuggestion(data);
}

/**
 * Handle link_created WebSocket event — add connection + remove card.
 */
export function handleLinkCreated(data) {
    if (data.orphan_node_id && data.target_node_id) {
        addConnection(data.orphan_node_id, data.target_node_id, data.link_type || 'discovered');
        updateConnections();
    }
    if (data.id) removeLinkSuggestion(data.id);
    updateOrphanCount(getOrphanCount());
}

/**
 * Handle link_rejected WebSocket event — remove card.
 */
export function handleLinkRejected(data) {
    if (data.id) removeLinkSuggestion(data.id);
}
