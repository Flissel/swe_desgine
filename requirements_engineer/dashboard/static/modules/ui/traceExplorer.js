/**
 * Trace Explorer — Three-Pane Artifact Browser
 *
 * Left:   Tree navigation (types with counts)
 * Center: Paginated sortable table + detail panel
 * Right:  Upstream/downstream trace chain + impact
 */

// ── State ────────────────────────────────────────────────────────
let _container = null;
let _currentType = null;      // selected type in tree (null = all)
let _currentPage = 1;
let _pageSize = 50;
let _sortBy = 'id';
let _sortDir = 'asc';
let _searchText = '';
let _selectedId = null;        // selected artifact in table
let _totalPages = 1;
let _treeData = null;
let _statsData = null;
let _searchTimer = null;

// Type icons
const TYPE_ICONS = {
    epic:        '&#9733;',  // star
    requirement: '&#9679;',  // bullet
    'user-story':'&#9998;',  // pencil
    test:        '&#10003;', // check
    api:         '&#9889;',  // lightning
    screen:      '&#9634;',  // square
    entity:      '&#9638;',  // filled sq
    component:   '&#9881;',  // gear
    task:        '&#9744;',  // checkbox
    persona:     '&#9786;',  // smiley
    'user-flow': '&#8644;',  // arrows
    diagram:     '&#9672;',  // diamond
    feature:     '&#9660;',  // triangle
    'tech-stack':'&#9877;',  // staff
};

// ── Public API ───────────────────────────────────────────────────

/** Initialise the Trace Explorer tab inside the given container. */
export function initTraceExplorer(container) {
    _container = container;
    _container.innerHTML = `<div class="trace-loading"><div class="spinner"></div> Loading Trace Explorer...</div>`;
    _loadInitial();
}

/** Called when a trace-related WebSocket event arrives. */
export function onTraceEvent(eventData) {
    if (eventData.type === 'trace_edit' || eventData.type === 'trace_impact') {
        // Refresh current view after an edit
        _fetchTable();
        if (_selectedId) _fetchChain(_selectedId);
    }
}

/** Called when switching to this tab — refresh if needed. */
export function refreshTraceView() {
    if (!_treeData) _loadInitial();
}

// ── Initial load ─────────────────────────────────────────────────

async function _loadInitial() {
    try {
        const [statsResp, treeResp] = await Promise.all([
            fetch('/api/trace/stats'),
            fetch('/api/trace/tree'),
        ]);

        if (!statsResp.ok || !treeResp.ok) {
            _container.innerHTML = `
                <div class="trace-empty">
                    <div class="empty-icon">&#128269;</div>
                    <h3>Trace Explorer</h3>
                    <p>Lade zuerst ein Projekt, um die Artefakte zu durchsuchen.</p>
                </div>`;
            return;
        }

        _statsData = await statsResp.json();
        _treeData = await treeResp.json();
        _renderShell();
        _renderTree();
        // Auto-select first type if available
        if (_treeData.types && _treeData.types.length > 0) {
            _selectType(_treeData.types[0].type);
        }
    } catch (e) {
        _container.innerHTML = `
            <div class="trace-empty">
                <div class="empty-icon">&#9888;</div>
                <h3>Fehler</h3>
                <p>${_esc(e.message)}</p>
            </div>`;
    }
}

// ── Shell (three-pane layout) ────────────────────────────────────

function _renderShell() {
    _container.innerHTML = `
        <div class="trace-tree-pane" id="trace-tree"></div>
        <div class="trace-table-pane" id="trace-table-pane">
            <div class="trace-table-toolbar">
                <span class="toolbar-title" id="trace-toolbar-title">All Artifacts</span>
                <input class="trace-search-input" id="trace-search"
                       type="text" placeholder="Search..." />
            </div>
            <div class="trace-table-wrap" id="trace-table-wrap">
                <div class="trace-loading"><div class="spinner"></div></div>
            </div>
            <div class="trace-pagination" id="trace-pagination"></div>
            <div id="trace-detail"></div>
        </div>
        <div class="trace-chain-pane" id="trace-chain">
            <div class="trace-chain-header">Trace Chain</div>
            <div class="trace-chain-empty">Select an artifact to see its trace chain</div>
        </div>`;

    // Bind search
    const searchInput = _container.querySelector('#trace-search');
    searchInput.addEventListener('input', () => {
        clearTimeout(_searchTimer);
        _searchTimer = setTimeout(() => {
            _searchText = searchInput.value.trim();
            _currentPage = 1;
            _fetchTable();
        }, 300);
    });
}

// ── Tree Pane ────────────────────────────────────────────────────

function _renderTree() {
    const treeEl = _container.querySelector('#trace-tree');
    if (!treeEl || !_treeData) return;

    const types = _treeData.types || [];
    let html = `
        <div class="trace-tree-header">Artifact Types</div>
        <div class="trace-tree-search">
            <input type="text" placeholder="Filter types..." id="trace-tree-filter" />
        </div>`;

    for (const t of types) {
        const icon = TYPE_ICONS[t.type] || '&#9656;';
        const active = _currentType === t.type ? ' active' : '';
        html += `
            <div class="trace-tree-item${active}" data-type="${_esc(t.type)}">
                <span class="tree-icon">${icon}</span>
                <span class="tree-label">${_esc(t.label)}</span>
                <span class="tree-count">${t.count}</span>
            </div>`;
    }

    // Stats footer
    if (_statsData) {
        html += `
            <div class="trace-tree-stats">
                <div class="stat-row">
                    <span>Total artifacts</span>
                    <span class="stat-value">${_statsData.total_artifacts}</span>
                </div>
                <div class="stat-row">
                    <span>Total links</span>
                    <span class="stat-value">${_statsData.total_links}</span>
                </div>
                <div class="stat-row">
                    <span>Orphans</span>
                    <span class="stat-value">${_statsData.orphan_count}</span>
                </div>
            </div>`;
    }

    treeEl.innerHTML = html;

    // Bind click handlers
    treeEl.querySelectorAll('.trace-tree-item').forEach(item => {
        item.addEventListener('click', () => {
            _selectType(item.dataset.type);
        });
    });

    // Bind tree filter
    const filterInput = treeEl.querySelector('#trace-tree-filter');
    if (filterInput) {
        filterInput.addEventListener('input', () => {
            const q = filterInput.value.toLowerCase();
            treeEl.querySelectorAll('.trace-tree-item').forEach(item => {
                const label = item.querySelector('.tree-label').textContent.toLowerCase();
                item.style.display = label.includes(q) ? '' : 'none';
            });
        });
    }
}

function _selectType(type) {
    _currentType = type;
    _currentPage = 1;
    _selectedId = null;

    // Update tree active state
    const treeEl = _container.querySelector('#trace-tree');
    if (treeEl) {
        treeEl.querySelectorAll('.trace-tree-item').forEach(item => {
            item.classList.toggle('active', item.dataset.type === type);
        });
    }

    // Update toolbar title
    const titleEl = _container.querySelector('#trace-toolbar-title');
    if (titleEl) {
        const typeInfo = (_treeData?.types || []).find(t => t.type === type);
        titleEl.textContent = typeInfo ? typeInfo.label : 'All Artifacts';
    }

    // Clear detail & chain
    const detailEl = _container.querySelector('#trace-detail');
    if (detailEl) detailEl.innerHTML = '';
    const chainEl = _container.querySelector('#trace-chain');
    if (chainEl) {
        chainEl.innerHTML = `
            <div class="trace-chain-header">Trace Chain</div>
            <div class="trace-chain-empty">Select an artifact to see its trace chain</div>`;
    }

    _fetchTable();
}

// ── Table Pane ───────────────────────────────────────────────────

async function _fetchTable() {
    const wrap = _container.querySelector('#trace-table-wrap');
    if (wrap) wrap.innerHTML = `<div class="trace-loading"><div class="spinner"></div></div>`;

    const params = new URLSearchParams({
        page: _currentPage,
        page_size: _pageSize,
        sort_by: _sortBy,
        sort_dir: _sortDir,
    });
    if (_currentType) params.set('type', _currentType);
    if (_searchText) params.set('search', _searchText);

    try {
        const resp = await fetch(`/api/trace/artifacts?${params}`);
        if (!resp.ok) throw new Error('Failed to load artifacts');
        const data = await resp.json();
        _totalPages = data.total_pages;
        _renderTable(data);
        _renderPagination(data);
    } catch (e) {
        if (wrap) wrap.innerHTML = `<div class="trace-loading">Error: ${_esc(e.message)}</div>`;
    }
}

function _renderTable(data) {
    const wrap = _container.querySelector('#trace-table-wrap');
    if (!wrap) return;

    const items = data.items || [];
    if (!items.length) {
        wrap.innerHTML = `<div class="trace-loading">No artifacts found</div>`;
        return;
    }

    const sortIcon = (col) => {
        if (_sortBy !== col) return '<span class="sort-indicator">&#9650;</span>';
        return _sortDir === 'asc'
            ? '<span class="sort-indicator active">&#9650;</span>'
            : '<span class="sort-indicator active">&#9660;</span>';
    };

    let html = `<table class="trace-table">
        <thead><tr>
            <th data-col="id">ID ${sortIcon('id')}</th>
            <th data-col="title">Title ${sortIcon('title')}</th>
            <th data-col="priority">Priority ${sortIcon('priority')}</th>
            <th data-col="status">Status ${sortIcon('status')}</th>
            <th>Links</th>
        </tr></thead>
        <tbody>`;

    for (const item of items) {
        const selected = item.id === _selectedId ? ' selected' : '';
        const prioClass = (item.priority || '').toLowerCase().replace(/\s+/g, '');
        const links = (item.upstream_count || 0) + (item.downstream_count || 0);
        html += `
            <tr class="${selected}" data-id="${_esc(item.id)}">
                <td class="cell-id">${_esc(item.id)}</td>
                <td>${_esc(item.title)}</td>
                <td>${item.priority ? `<span class="cell-priority ${prioClass}">${_esc(item.priority)}</span>` : '-'}</td>
                <td>${_esc(item.status || '-')}</td>
                <td class="cell-badge">${links > 0 ? links : '-'}</td>
            </tr>`;
    }

    html += '</tbody></table>';
    wrap.innerHTML = html;

    // Bind row clicks
    wrap.querySelectorAll('tbody tr').forEach(row => {
        row.addEventListener('click', () => {
            _selectArtifact(row.dataset.id);
            // Update row selection
            wrap.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
            row.classList.add('selected');
        });
    });

    // Bind sort clicks
    wrap.querySelectorAll('th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            if (_sortBy === col) {
                _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                _sortBy = col;
                _sortDir = 'asc';
            }
            _currentPage = 1;
            _fetchTable();
        });
    });
}

function _renderPagination(data) {
    const pagEl = _container.querySelector('#trace-pagination');
    if (!pagEl) return;

    const { page, total_pages, total } = data;
    pagEl.innerHTML = `
        <button id="trace-prev" ${page <= 1 ? 'disabled' : ''}>&#9664; Prev</button>
        <span class="page-info">Page ${page} / ${total_pages} (${total} items)</span>
        <button id="trace-next" ${page >= total_pages ? 'disabled' : ''}>Next &#9654;</button>`;

    pagEl.querySelector('#trace-prev')?.addEventListener('click', () => {
        if (_currentPage > 1) { _currentPage--; _fetchTable(); }
    });
    pagEl.querySelector('#trace-next')?.addEventListener('click', () => {
        if (_currentPage < _totalPages) { _currentPage++; _fetchTable(); }
    });
}

// ── Artifact Selection (detail + chain) ──────────────────────────

async function _selectArtifact(id) {
    _selectedId = id;
    // Fetch detail + chain in parallel
    const [detailResp, chainResp] = await Promise.all([
        fetch(`/api/trace/artifacts/${encodeURIComponent(id)}`),
        fetch(`/api/trace/chain/${encodeURIComponent(id)}`),
    ]);

    if (detailResp.ok) {
        const detail = await detailResp.json();
        _renderDetail(detail);
    }

    if (chainResp.ok) {
        const chain = await chainResp.json();
        _renderChain(chain);
    }
}

// ── Detail Panel ─────────────────────────────────────────────────

function _renderDetail(detail) {
    const el = _container.querySelector('#trace-detail');
    if (!el) return;

    const editableFields = ['title', 'description', 'priority', 'status'];
    const data = detail.data || {};

    let fieldsHtml = '';
    // Main editable fields
    for (const fld of editableFields) {
        const val = detail[fld] || data[fld] || '';
        const isWide = fld === 'description';
        fieldsHtml += `
            <div class="trace-detail-field${isWide ? ' full-width' : ''}">
                <label>${fld}</label>
                <div class="field-value" contenteditable="true"
                     data-field="${fld}" data-id="${_esc(detail.id)}">${_esc(val)}</div>
            </div>`;
    }

    // Extra data fields (read-only)
    const skip = new Set([...editableFields, 'id', 'type', 'data', 'connections', 'file_path']);
    for (const [key, val] of Object.entries(data)) {
        if (skip.has(key) || !val) continue;
        const display = typeof val === 'object' ? JSON.stringify(val).slice(0, 200) : String(val);
        fieldsHtml += `
            <div class="trace-detail-field">
                <label>${_esc(key)}</label>
                <div class="field-value">${_esc(display)}</div>
            </div>`;
    }

    el.innerHTML = `
        <div class="trace-detail-panel">
            <div class="detail-header">
                <span class="detail-title">${_esc(detail.title || detail.id)}</span>
                <span class="detail-type-badge">${_esc(detail.type)}</span>
            </div>
            <div class="trace-detail-fields">${fieldsHtml}</div>
            <div class="trace-detail-actions">
                <button class="primary" id="trace-save-btn">Save Changes</button>
                <button id="trace-kilo-btn">Edit with Kilo</button>
            </div>
        </div>`;

    // Bind save
    el.querySelector('#trace-save-btn')?.addEventListener('click', async () => {
        const fields = el.querySelectorAll('.field-value[contenteditable="true"]');
        for (const field of fields) {
            const fld = field.dataset.field;
            const id = field.dataset.id;
            const newVal = field.textContent.trim();
            const origVal = detail[fld] || (detail.data || {})[fld] || '';
            if (newVal !== origVal) {
                await _saveField(id, fld, newVal);
            }
        }
    });

    // Bind kilo edit
    el.querySelector('#trace-kilo-btn')?.addEventListener('click', () => {
        _openKiloModal(detail.id, detail);
    });
}

async function _saveField(id, field, value) {
    try {
        const resp = await fetch(`/api/trace/edit/${encodeURIComponent(id)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field, value }),
        });
        const result = await resp.json();
        if (result.success) {
            console.log(`[TraceExplorer] Saved ${field} for ${id}, impacted: ${(result.impacted_ids || []).length}`);
            // Refresh table to show updated data
            _fetchTable();
            // Refresh chain to show impact
            if (_selectedId) _fetchChain(_selectedId);
        }
    } catch (e) {
        console.error('[TraceExplorer] Save failed:', e);
    }
}

// ── Kilo Modal ───────────────────────────────────────────────────

function _openKiloModal(artifactId, detail) {
    // Simple prompt modal
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.6); z-index: 9999;
        display: flex; align-items: center; justify-content: center;
    `;
    modal.innerHTML = `
        <div style="background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                    padding: 24px; width: 500px; max-width: 90vw;">
            <h3 style="margin:0 0 12px; color: #e6edf3; font-size: 15px;">
                Edit with Kilo: ${_esc(detail.title || artifactId)}</h3>
            <p style="font-size: 12px; color: #8b949e; margin: 0 0 12px;">
                Type: ${_esc(detail.type)} | ID: ${_esc(artifactId)}</p>
            <textarea id="kilo-prompt-input" rows="4" placeholder="Describe the change..."
                style="width:100%; background:#0d1117; border:1px solid #30363d; border-radius:4px;
                       color:#e6edf3; padding:10px; font-size:13px; resize:vertical;
                       box-sizing:border-box; outline:none;"></textarea>
            <div style="display:flex; gap:8px; margin-top:12px; justify-content:flex-end;">
                <button id="kilo-cancel" style="padding:6px 14px; background:#0d1117;
                    border:1px solid #30363d; border-radius:4px; color:#e6edf3;
                    cursor:pointer; font-size:12px;">Cancel</button>
                <button id="kilo-submit" style="padding:6px 14px; background:rgba(88,166,255,0.12);
                    border:1px solid #58a6ff; border-radius:4px; color:#58a6ff;
                    cursor:pointer; font-size:12px; font-weight:600;">Send to Kilo</button>
            </div>
            <div id="kilo-result" style="margin-top:12px; display:none;"></div>
        </div>`;

    document.body.appendChild(modal);

    modal.querySelector('#kilo-cancel').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    modal.querySelector('#kilo-submit').addEventListener('click', async () => {
        const prompt = modal.querySelector('#kilo-prompt-input').value.trim();
        if (!prompt) return;

        const resultDiv = modal.querySelector('#kilo-result');
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<div class="trace-loading"><div class="spinner"></div> Processing...</div>';

        try {
            const resp = await fetch(`/api/trace/kilo/${encodeURIComponent(artifactId)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt }),
            });
            const data = await resp.json();

            if (data.success) {
                resultDiv.innerHTML = `
                    <div style="padding:10px; background:rgba(63,185,80,0.1); border:1px solid rgba(63,185,80,0.3);
                                border-radius:4px; font-size:12px; color:#3fb950;">
                        Done! ${(data.affected_ids || []).length} affected artifacts.
                        <br><span style="color:#8b949e;">${_esc(data.kilo_response || '')}</span>
                    </div>`;
                // Refresh views
                _fetchTable();
                if (_selectedId) _fetchChain(_selectedId);
            } else {
                resultDiv.innerHTML = `
                    <div style="padding:10px; background:rgba(248,81,73,0.1); border:1px solid rgba(248,81,73,0.3);
                                border-radius:4px; font-size:12px; color:#f85149;">
                        ${_esc(data.error || 'Unknown error')}
                    </div>`;
            }
        } catch (e) {
            resultDiv.innerHTML = `<div style="color:#f85149; font-size:12px;">Error: ${_esc(e.message)}</div>`;
        }
    });
}

// ── Trace Chain Pane ─────────────────────────────────────────────

async function _fetchChain(id) {
    const chainEl = _container.querySelector('#trace-chain');
    if (!chainEl) return;

    chainEl.innerHTML = `
        <div class="trace-chain-header">Trace Chain</div>
        <div class="trace-loading"><div class="spinner"></div></div>`;

    try {
        const resp = await fetch(`/api/trace/chain/${encodeURIComponent(id)}`);
        if (!resp.ok) throw new Error('Failed');
        const chain = await resp.json();
        _renderChain(chain);
    } catch (e) {
        chainEl.innerHTML = `
            <div class="trace-chain-header">Trace Chain</div>
            <div class="trace-chain-empty">Error loading chain</div>`;
    }
}

function _renderChain(chain) {
    const chainEl = _container.querySelector('#trace-chain');
    if (!chainEl) return;

    const art = chain.artifact;
    const upstream = chain.upstream || [];
    const downstream = chain.downstream || [];

    let html = `<div class="trace-chain-header">Trace Chain</div>`;

    // Upstream section
    if (upstream.length) {
        html += `<div class="trace-chain-section">
            <div class="trace-chain-section-title upstream">&#9650; Upstream (${upstream.length})</div>`;
        for (const node of upstream) {
            const typeAbbr = _typeAbbr(node.type);
            html += `
                <div class="trace-chain-node" style="--depth:${node.depth - 1}"
                     data-id="${_esc(node.id)}">
                    <span class="chain-connector">&#8593;</span>
                    <span class="chain-type-icon">${typeAbbr}</span>
                    <span class="chain-title">${_esc(node.title)}</span>
                    <span class="chain-edge-type">${_esc(node.link_type)}</span>
                </div>`;
        }
        html += '</div>';
    }

    // Focus node
    if (art) {
        html += `
            <div class="trace-chain-focus">
                <span class="focus-type">${_esc(art.type)}</span>
                ${_esc(art.title || art.id)}
            </div>`;
    }

    // Downstream section
    if (downstream.length) {
        html += `<div class="trace-chain-section">
            <div class="trace-chain-section-title downstream">&#9660; Downstream (${downstream.length})</div>`;
        for (const node of downstream) {
            const typeAbbr = _typeAbbr(node.type);
            html += `
                <div class="trace-chain-node" style="--depth:${node.depth - 1}"
                     data-id="${_esc(node.id)}">
                    <span class="chain-connector">&#8595;</span>
                    <span class="chain-type-icon">${typeAbbr}</span>
                    <span class="chain-title">${_esc(node.title)}</span>
                    <span class="chain-edge-type">${_esc(node.link_type)}</span>
                </div>`;
        }
        html += '</div>';
    }

    // Impact summary (counts by type)
    if (upstream.length || downstream.length) {
        const counts = {};
        for (const n of [...upstream, ...downstream]) {
            counts[n.type] = (counts[n.type] || 0) + 1;
        }
        html += `<div class="trace-impact-summary">
            <div class="impact-title">Impact: ${upstream.length + downstream.length} artifacts</div>`;
        for (const [type, count] of Object.entries(counts).sort((a, b) => b[1] - a[1])) {
            html += `<div class="trace-impact-row">
                <span>${_esc(type)}</span>
                <span class="impact-count">${count}</span>
            </div>`;
        }
        html += '</div>';
    }

    if (!upstream.length && !downstream.length) {
        html += '<div class="trace-chain-empty">No trace links found for this artifact</div>';
    }

    chainEl.innerHTML = html;

    // Bind chain node clicks (navigate to that artifact)
    chainEl.querySelectorAll('.trace-chain-node').forEach(node => {
        node.addEventListener('click', () => {
            const id = node.dataset.id;
            _selectedId = id;
            _selectArtifact(id);
            // Also refresh table selection
            _fetchTable();
        });
    });
}

// ── Helpers ──────────────────────────────────────────────────────

function _typeAbbr(type) {
    const abbrs = {
        epic: 'EPIC', requirement: 'REQ', 'user-story': 'US', test: 'TC',
        api: 'API', screen: 'SCR', entity: 'ENT', component: 'CMP',
        task: 'TSK', persona: 'PER', 'user-flow': 'FLW', diagram: 'DIA',
        feature: 'FEA', 'tech-stack': 'TEC',
    };
    return abbrs[type] || type?.toUpperCase()?.slice(0, 3) || '???';
}

function _esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}
