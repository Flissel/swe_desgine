/**
 * Pipeline View — Stage I/O Dashboard Tab
 *
 * Visualises the 15-stage enterprise pipeline with:
 * - Status icons (pending / running / completed / failed / skipped)
 * - Expandable I/O sections per stage
 * - Quality-gate badges between stages
 * - Live WebSocket updates while pipeline runs
 */

// ── State ────────────────────────────────────────────────────
let _manifest = null;   // latest pipeline_manifest.json data
let _container = null;  // #pipeline-container DOM node

// Quality gate positions (inserted AFTER these steps)
const GATE_POSITIONS = {
    3: { label: 'Discovery', key: 'discovery' },
    4: { label: 'Analysis',  key: 'analysis'  },
    8: { label: 'Testing',   key: 'testing'   },
};

// ── Public API ───────────────────────────────────────────────

/** Initialise the Pipeline tab inside the given container element. */
export function initPipelineView(container) {
    _container = container;
    _container.innerHTML = `
        <div class="pipeline-empty">
            <div class="empty-icon">&#9881;</div>
            <h3>Pipeline-Ansicht</h3>
            <p>Starte eine Pipeline oder lade ein bestehendes Projekt,
               um die Stage-Inputs und Outputs zu sehen.</p>
        </div>`;
    // Fetch manifest from server (may already exist from a previous run)
    _fetchManifest();
}

/** Called by app.js when a stage_started / stage_completed / stage_skipped event arrives. */
export function onStageEvent(eventData) {
    if (!_manifest) {
        _manifest = { stages: [], project_name: '', pipeline_id: '' };
    }
    const { step, name } = eventData;

    if (eventData.type === 'stage_started' || eventData.type === 'stage_completed' ||
        eventData.type === 'stage_skipped' || eventData.type === 'stage_failed') {

        // Upsert stage in local manifest mirror
        let existing = _manifest.stages.find(s => s.step === step);
        if (!existing) {
            existing = { step, name, description: eventData.description || name, inputs: [], outputs: [] };
            _manifest.stages.push(existing);
            _manifest.stages.sort((a, b) => _stepOrder(a.step) - _stepOrder(b.step));
        }

        if (eventData.type === 'stage_started') {
            existing.status = 'running';
            existing.description = eventData.description || existing.description;
            if (eventData.inputs) existing.inputs = eventData.inputs;
        } else if (eventData.type === 'stage_completed') {
            existing.status = 'completed';
            if (eventData.outputs) existing.outputs = eventData.outputs;
            if (eventData.duration_ms) existing.duration_ms = eventData.duration_ms;
            if (eventData.cost_usd) existing.cost_usd = eventData.cost_usd;
        } else if (eventData.type === 'stage_skipped') {
            existing.status = 'skipped';
            if (eventData.reason) existing.error = eventData.reason;
        } else if (eventData.type === 'stage_failed') {
            existing.status = 'failed';
            if (eventData.error) existing.error = eventData.error;
        }
    }

    _render();
}

/** Called when pipeline_complete arrives — do a full refresh from server. */
export function onPipelineComplete() {
    _fetchManifest();
}

/** Called when switching to this tab — refresh if empty. */
export function refreshPipelineView() {
    _fetchManifest();
}

// ── Data fetching ────────────────────────────────────────────

async function _fetchManifest() {
    try {
        const resp = await fetch('/api/pipeline/manifest');
        if (resp.ok) {
            _manifest = await resp.json();
            _render();
        }
    } catch (e) {
        // Silently ignore — no manifest yet
    }
}

// ── Rendering ────────────────────────────────────────────────

function _render() {
    if (!_container || !_manifest) return;

    const m = _manifest;
    const totalCost = m.total_cost_usd || m.stages.reduce((s, st) => s + (st.cost_usd || 0), 0);
    const totalDuration = m.total_duration_ms || m.stages.reduce((s, st) => s + (st.duration_ms || 0), 0);
    const completedStages = m.stages.filter(s => s.status === 'completed').length;

    _container.innerHTML = `
        <div class="pipeline-header">
            <h2>${_esc(m.project_name || 'Pipeline')}</h2>
            <div class="pipeline-meta">
                <span class="meta-item">Stages: <span class="meta-value">${completedStages}/${m.stages.length}</span></span>
                <span class="meta-item">Dauer: <span class="meta-value">${_fmtDuration(totalDuration)}</span></span>
                <span class="meta-item">Kosten: <span class="meta-value">$${totalCost.toFixed(4)}</span></span>
            </div>
        </div>
        <div class="pipeline-stages">
            ${m.stages.map((stg, idx) => _renderStage(stg, idx, m.stages)).join('')}
        </div>`;

    // Attach expand/collapse handlers
    _container.querySelectorAll('.stage-header').forEach(hdr => {
        hdr.addEventListener('click', () => {
            hdr.closest('.stage-card').classList.toggle('expanded');
        });
    });
}

function _renderStage(stg, idx, allStages) {
    const statusIcon = _statusIcon(stg.status);
    const duration = stg.duration_ms ? _fmtDuration(stg.duration_ms) : '-';
    const cost = stg.cost_usd ? `$${stg.cost_usd.toFixed(4)}` : '-';

    // Quality gate divider AFTER this stage?
    let gateHtml = '';
    const gateInfo = GATE_POSITIONS[stg.step];
    if (gateInfo && stg.quality_gate) {
        const gateStatus = (stg.quality_gate.status || 'PASS').toUpperCase();
        const cls = gateStatus === 'PASS' ? 'pass' : gateStatus === 'FAIL' ? 'fail' : 'warn';
        gateHtml = `
            <div class="quality-gate-divider">
                <span class="gate-line"></span>
                <span class="gate-badge ${cls}">${gateInfo.label}: ${gateStatus}</span>
                <span class="gate-line"></span>
            </div>`;
    }

    return `
        <div class="stage-card status-${stg.status || 'pending'}">
            <div class="stage-header">
                <span class="stage-status-icon">${statusIcon}</span>
                <span class="stage-step">${stg.step}</span>
                <span class="stage-name">${_esc(stg.description || stg.name)}</span>
                <div class="stage-stats">
                    <span class="stat">${duration}</span>
                    <span class="stat">${cost}</span>
                    ${stg.llm_calls ? `<span class="stat">${stg.llm_calls} LLM</span>` : ''}
                </div>
                <span class="stage-expand-arrow">&#9654;</span>
            </div>
            <div class="stage-detail">
                ${_renderIO(stg)}
                ${stg.error && stg.status === 'failed' ? `<div class="stage-error">${_esc(stg.error)}</div>` : ''}
            </div>
        </div>
        ${gateHtml}`;
}

function _renderIO(stg) {
    const inputs = stg.inputs || [];
    const outputs = stg.outputs || [];
    if (!inputs.length && !outputs.length) {
        return '<p style="font-size:12px;color:var(--text-secondary,#8b949e);margin:8px 0">Keine I/O-Details verfuegbar</p>';
    }
    return `
        <div class="stage-io">
            <div class="io-section inputs">
                <h4>Inputs</h4>
                <div class="io-items">
                    ${inputs.length ? inputs.map(_renderIOItem).join('') : '<span style="font-size:12px;color:#484f58">-</span>'}
                </div>
            </div>
            <div class="io-section outputs">
                <h4>Outputs</h4>
                <div class="io-items">
                    ${outputs.length ? outputs.map(_renderIOItem).join('') : '<span style="font-size:12px;color:#484f58">-</span>'}
                </div>
            </div>
        </div>`;
}

function _renderIOItem(item) {
    const icon = _ioIcon(item.type);
    const countBadge = item.count ? `<span class="io-count">${item.count}</span>` : '';
    const pathSpan = item.path ? `<span class="io-path">${_esc(item.path)}</span>` : '';
    const desc = item.description ? `<span class="io-desc">${_esc(item.description)}</span>` : '';
    return `
        <div class="io-item">
            <span class="io-icon">${icon}</span>
            <span class="io-name">${_esc(item.name)}</span>
            ${countBadge}${pathSpan}${desc}
        </div>`;
}

// ── Helpers ──────────────────────────────────────────────────

function _statusIcon(status) {
    switch (status) {
        case 'completed': return '<span style="color:#3fb950">&#10003;</span>';
        case 'running':   return '<span style="color:#d29922">&#9654;</span>';
        case 'failed':    return '<span style="color:#f85149">&#10007;</span>';
        case 'skipped':   return '<span style="color:#484f58">&#9679;</span>';
        default:          return '<span style="color:#484f58">&#9675;</span>';
    }
}

function _ioIcon(type) {
    switch (type) {
        case 'file':   return '&#128196;';
        case 'config': return '&#9881;';
        case 'gate':   return '&#128737;';
        case 'data':
        default:       return '&#9656;';
    }
}

function _fmtDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    const s = ms / 1000;
    if (s < 60) return `${s.toFixed(1)}s`;
    const m = Math.floor(s / 60);
    const remainder = (s % 60).toFixed(0);
    return `${m}m ${remainder}s`;
}

/** Sort key for step values (handles "8.5", "5b" etc.) */
function _stepOrder(step) {
    if (typeof step === 'number') return step;
    const s = String(step);
    if (s === '5b') return 5.5;
    const n = parseFloat(s);
    return isNaN(n) ? 99 : n;
}

function _esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}
