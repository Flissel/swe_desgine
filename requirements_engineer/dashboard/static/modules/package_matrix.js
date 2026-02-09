/**
 * RE System Dashboard - Package Matrix Module
 *
 * Compact overview of work packages in a matrix view:
 * - Rows: Work Packages (grouped by root node)
 * - Columns: Node Types
 * - Cells: Node counts + mini-statistics
 */

import { state, log } from './state.js';
import { detectWorkPackages, WORKPACKAGE_COLUMNS } from './layouts/index.js';

// ============================================
// Matrix Data Structure
// ============================================

/**
 * Build matrix data from work packages.
 *
 * @returns {Object} Matrix data with columns, rows, and totals
 */
export function buildPackageMatrix() {
    const packages = detectWorkPackages();

    // Get columns from WORKPACKAGE_COLUMNS
    const columns = WORKPACKAGE_COLUMNS.map(c => c.id);

    const matrix = {
        columns: columns,
        rows: [],
        totals: {}
    };

    // Initialize totals
    columns.forEach(col => matrix.totals[col] = 0);
    matrix.totals._total = 0;

    // For each package
    packages.forEach(pkg => {
        const row = {
            id: pkg.id,
            name: pkg.name || pkg.id,
            rootType: pkg.rootType || 'unknown',
            isOrphan: pkg.isOrphanPackage || false,
            cells: {},
            total: 0,
            links: { incoming: 0, outgoing: 0 }
        };

        // Initialize cells
        columns.forEach(col => row.cells[col] = 0);

        // Count nodes per type
        // pkg.nodes is an array of { id, type, data, element } objects
        const nodeObjs = pkg.nodes || [];
        nodeObjs.forEach(nodeObj => {
            const type = nodeObj.type || 'unknown';
            if (columns.includes(type)) {
                row.cells[type]++;
                matrix.totals[type]++;
            }
            row.total++;
            matrix.totals._total++;
        });

        // Link statistics - extract IDs from node objects
        const nodeIdSet = new Set(nodeObjs.map(n => n.id));
        state.connections.forEach(conn => {
            if (nodeIdSet.has(conn.to)) row.links.incoming++;
            if (nodeIdSet.has(conn.from)) row.links.outgoing++;
        });

        matrix.rows.push(row);
    });

    // Sort: Largest packages first, orphans last
    matrix.rows.sort((a, b) => {
        if (a.isOrphan) return 1;
        if (b.isOrphan) return -1;
        return b.total - a.total;
    });

    return matrix;
}

// ============================================
// Matrix Rendering
// ============================================

/**
 * Render matrix as HTML table.
 *
 * @param {HTMLElement} container - Container element (optional, uses #package-matrix)
 */
export function renderPackageMatrix(container) {
    const matrix = buildPackageMatrix();

    if (!container) {
        container = document.getElementById('package-matrix');
        if (!container) {
            log('warn', '[Matrix] No container found for package matrix');
            return;
        }
    }

    // Only show columns with content
    const activeColumns = matrix.columns.filter(col => matrix.totals[col] > 0);

    if (matrix.rows.length === 0) {
        container.innerHTML = `
            <div class="package-matrix-container">
                <h3>📦 Package Matrix</h3>
                <p class="matrix-empty">No packages detected. Load a project first.</p>
            </div>
        `;
        return;
    }

    let html = `
        <div class="package-matrix-container">
            <h3>📦 Package Matrix</h3>
            <table class="package-matrix">
                <thead>
                    <tr>
                        <th>Package</th>
                        ${activeColumns.map(col => `<th>${getColumnIcon(col)} ${getColumnLabel(col)}</th>`).join('')}
                        <th>Total</th>
                        <th>Links</th>
                    </tr>
                </thead>
                <tbody>
    `;

    matrix.rows.forEach(row => {
        const rowClass = row.isOrphan ? 'orphan-row' : '';
        html += `
            <tr class="${rowClass}" data-package="${row.id}">
                <td class="pkg-name">
                    <span class="pkg-icon">${getRootIcon(row.rootType)}</span>
                    ${truncateName(row.name, 20)}
                </td>
                ${activeColumns.map(col => `
                    <td class="pkg-cell ${row.cells[col] > 0 ? 'has-items' : 'empty'}">
                        ${row.cells[col] || '-'}
                    </td>
                `).join('')}
                <td class="pkg-total">${row.total}</td>
                <td class="pkg-links">
                    <span class="in">↓${row.links.incoming}</span>
                    <span class="out">↑${row.links.outgoing}</span>
                </td>
            </tr>
        `;
    });

    // Footer with totals
    html += `
                </tbody>
                <tfoot>
                    <tr class="totals-row">
                        <td><strong>TOTAL</strong></td>
                        ${activeColumns.map(col => `<td>${matrix.totals[col]}</td>`).join('')}
                        <td><strong>${matrix.totals._total}</strong></td>
                        <td></td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;

    container.innerHTML = html;

    // Click handler for package focus
    container.querySelectorAll('tr[data-package]').forEach(row => {
        row.addEventListener('click', () => {
            const pkgId = row.dataset.package;
            focusPackage(pkgId);
        });
    });

    log('info', `[Matrix] Rendered ${matrix.rows.length} packages, ${activeColumns.length} columns`);
}

// ============================================
// Helper Functions
// ============================================

/**
 * Get icon for column type.
 */
function getColumnIcon(type) {
    const icons = {
        'requirement': '📋',
        'epic': '🎯',
        'user-story': '📖',
        'test': '🧪',
        'diagram': '📊',
        'persona': '👤',
        'screen': '🖥️',
        'component': '🧩',
        'api': '🔌',
        'task': '✅',
        'user-flow': '🔄',
        'tech-stack': '🛠️'
    };
    return icons[type] || '📄';
}

/**
 * Get label for column type.
 */
function getColumnLabel(type) {
    const column = WORKPACKAGE_COLUMNS.find(c => c.id === type);
    if (column) return column.name;

    // Fallback: capitalize and replace dashes
    return type.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

/**
 * Get icon for root node type.
 */
function getRootIcon(type) {
    const icons = {
        'requirement': '📋',
        'epic': '🎯',
        'feature': '⭐',
        'orphan': '🔗',
        'unknown': '📦'
    };
    return icons[type] || '📦';
}

/**
 * Truncate name to max length.
 */
function truncateName(name, maxLen) {
    if (!name) return 'Unnamed';
    if (name.length <= maxLen) return name;
    return name.substring(0, maxLen - 3) + '...';
}

/**
 * Focus on a package - highlight its nodes.
 */
function focusPackage(packageId) {
    const packages = detectWorkPackages();
    const pkg = packages.find(p => p.id === packageId);

    if (!pkg) {
        log('warn', `[Matrix] Package not found: ${packageId}`);
        return;
    }

    // Remove all existing highlights
    document.querySelectorAll('.node-card').forEach(el => {
        el.classList.remove('package-highlight');
    });

    // Highlight package nodes
    const nodeIds = pkg.nodes || [];
    nodeIds.forEach(nodeId => {
        const node = state.nodes[nodeId];
        if (node && node.element) {
            node.element.classList.add('package-highlight');
        }
    });

    log('info', `[Matrix] Focused on package: ${pkg.name || packageId} (${nodeIds.length} nodes)`);
}

/**
 * Toggle matrix visibility.
 */
export function togglePackageMatrix() {
    const panel = document.getElementById('package-matrix-panel');
    if (panel) {
        panel.classList.toggle('collapsed');
    }
}

/**
 * Refresh matrix (call after data changes).
 */
export function refreshPackageMatrix() {
    renderPackageMatrix();
}
