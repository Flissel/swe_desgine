/**
 * RE System Dashboard - Wizard Module
 *
 * Embeddable 6-step requirement mining wizard.
 * Ported from wizard.html into an ES module with callbacks.
 */

import { escapeHtml } from '../state.js';

// ============================================
// Wizard State
// ============================================

const wizardState = {
    currentStep: 1,
    maxStep: 6,
    project: {
        name: '',
        description: '',
        domain: 'custom',
        autonomy_level: 'medium',
        target_users: []
    },
    context: {
        summary: '',
        business: '',
        technical: '',
        user: ''
    },
    stakeholders: [],
    files: [],
    requirements: [],
    constraints: {
        technical: [],
        regulatory: [],
        budget: '',
        timeline: '',
        team_size: ''
    },
    workDivision: 'per_feature'
};

const validationState = {
    mode: 'AUTO',
    isRunning: false,
    results: [],
    stats: { passed: 0, failed: 0, improved: 0, split: 0 },
    currentClarification: null,
    clarificationResolve: null
};

// ============================================
// Callbacks
// ============================================

let onAnalysisComplete = null;

export function setOnAnalysisComplete(cb) {
    onAnalysisComplete = cb;
}

export function getWizardRequirements() {
    return wizardState.requirements;
}

// ============================================
// Container Reference
// ============================================

let container = null;

function q(selector) {
    return container ? container.querySelector(selector) : null;
}

function qAll(selector) {
    return container ? container.querySelectorAll(selector) : [];
}

// ============================================
// Init: Build DOM + Bind Events
// ============================================

export function initWizard(containerEl) {
    container = containerEl;
    container.innerHTML = buildWizardHTML();
    bindEvents();
}

export function resetWizard() {
    wizardState.currentStep = 1;
    wizardState.project = { name: '', description: '', domain: 'custom', autonomy_level: 'medium', target_users: [] };
    wizardState.context = { summary: '', business: '', technical: '', user: '' };
    wizardState.stakeholders = [];
    wizardState.files = [];
    wizardState.requirements = [];
    wizardState.constraints = { technical: [], regulatory: [], budget: '', timeline: '', team_size: '' };
    wizardState.workDivision = 'per_feature';
    validationState.mode = 'AUTO';
    validationState.isRunning = false;
    validationState.results = [];
    validationState.stats = { passed: 0, failed: 0, improved: 0, split: 0 };

    if (container) {
        container.innerHTML = buildWizardHTML();
        bindEvents();
    }
}

// ============================================
// HTML Template
// ============================================

function buildWizardHTML() {
    return `
    <div class="wizard-inner">
        <div class="wizard-header">
            <h1>Requirements Wizard</h1>
            <p>Erfassen Sie Ihre Anforderungen schrittweise</p>
        </div>

        <div class="step-indicator">
            <div class="step active" data-step="1">
                <span class="step-number">1</span><span>Projekt</span>
            </div>
            <div class="step" data-step="2">
                <span class="step-number">2</span><span>Dokumente</span>
            </div>
            <div class="step" data-step="3">
                <span class="step-number">3</span><span>Requirements</span>
            </div>
            <div class="step" data-step="4">
                <span class="step-number">4</span><span>Validierung</span>
            </div>
            <div class="step" data-step="5">
                <span class="step-number">5</span><span>Constraints</span>
            </div>
            <div class="step" data-step="6">
                <span class="step-number">6</span><span>Export</span>
            </div>
        </div>

        <!-- Step 1: Project Info -->
        <div class="wizard-step active" data-step="1">
            <h2>Projekt-Grunddaten</h2>
            <div class="form-group">
                <label for="wiz-project-name">Projektname *</label>
                <input type="text" id="wiz-project-name" placeholder="z.B. Abrechnungssystem 2.0">
            </div>
            <div class="form-group">
                <label for="wiz-project-description">Beschreibung</label>
                <textarea id="wiz-project-description" placeholder="Kurze Beschreibung des Projekts..."></textarea>
            </div>
            <div class="form-group">
                <label for="wiz-project-domain">Domain</label>
                <select id="wiz-project-domain">
                    <option value="custom">Benutzerdefiniert</option>
                    <option value="Finance">Finance / Banking</option>
                    <option value="Healthcare">Healthcare</option>
                    <option value="E-Commerce">E-Commerce</option>
                    <option value="Enterprise">Enterprise Software</option>
                    <option value="IoT">IoT / Embedded</option>
                </select>
            </div>
            <div class="form-group">
                <label for="wiz-autonomy-level">Automatisierungsgrad</label>
                <select id="wiz-autonomy-level">
                    <option value="none">Keine Automatisierung</option>
                    <option value="low">Gering (manuelle Bestaetigug)</option>
                    <option value="medium" selected>Mittel (teilautomatisiert)</option>
                    <option value="high">Hoch (weitgehend autonom)</option>
                    <option value="full">Vollautomatisiert</option>
                </select>
            </div>
            <div class="form-group">
                <label>Zielgruppen</label>
                <div class="tag-input" id="wiz-target-users-input">
                    <input type="text" placeholder="Eingabe + Enter..." id="wiz-target-user-text">
                </div>
            </div>
            <hr style="border-color: var(--border-color); margin: 1.5rem 0;">
            <h3 style="margin-bottom: 1rem;">Kontext (optional)</h3>
            <div class="form-group">
                <label for="wiz-context-summary">Zusammenfassung</label>
                <textarea id="wiz-context-summary" rows="2" placeholder="Kurze Zusammenfassung des Projektkontexts..."></textarea>
            </div>
            <div class="form-group">
                <label for="wiz-context-business">Business-Kontext</label>
                <input type="text" id="wiz-context-business" placeholder="z.B. Online retail, B2C market in DACH region">
            </div>
            <div class="form-group">
                <label for="wiz-context-technical">Technischer Kontext</label>
                <input type="text" id="wiz-context-technical" placeholder="z.B. Cloud-native, microservices, REST APIs">
            </div>
            <div class="form-group">
                <label for="wiz-context-user">Nutzer-Kontext</label>
                <input type="text" id="wiz-context-user" placeholder="z.B. 10k+ daily active users, internal admin staff">
            </div>
            <div class="wizard-nav">
                <div></div>
                <button class="wiz-btn wiz-btn-primary" data-action="next">Weiter &rarr;</button>
            </div>
        </div>

        <!-- Step 2: Documents -->
        <div class="wizard-step" data-step="2">
            <h2>Dokumente hochladen (optional)</h2>
            <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                Laden Sie bestehende Anforderungsdokumente hoch. Diese werden automatisch analysiert.
            </p>
            <div class="file-drop-zone" id="wiz-file-drop-zone">
                <input type="file" id="wiz-file-input" multiple accept=".pdf,.docx,.doc,.md,.txt">
                <p>Dateien hierher ziehen oder <strong>klicken</strong> zum Auswaehlen</p>
                <p style="color: var(--text-secondary); font-size: 0.8rem; margin-top: 0.5rem;">
                    PDF, DOCX, MD, TXT
                </p>
            </div>
            <div class="file-list" id="wiz-file-list"></div>
            <div class="wiz-loading" id="wiz-extract-loading">
                <div class="wiz-spinner"></div>
                <span>Extrahiere Requirements...</span>
            </div>
            <div class="wizard-nav">
                <button class="wiz-btn wiz-btn-secondary" data-action="prev">&larr; Zurueck</button>
                <div style="display:flex;gap:0.5rem;">
                    <button class="wiz-btn wiz-btn-secondary" data-action="next">Ueberspringen</button>
                    <button class="wiz-btn wiz-btn-primary" id="wiz-extract-btn" disabled data-action="extract">
                        Analysieren &rarr;
                    </button>
                </div>
            </div>
        </div>

        <!-- Step 3: Requirements -->
        <div class="wizard-step" data-step="3">
            <h2>Requirements</h2>
            <div class="wiz-requirements-list" id="wiz-requirements-list"></div>
            <button class="add-requirement-btn" data-action="add-req">+ Requirement hinzufuegen</button>
            <div class="wizard-nav">
                <button class="wiz-btn wiz-btn-secondary" data-action="prev">&larr; Zurueck</button>
                <button class="wiz-btn wiz-btn-primary" data-action="next">Weiter &rarr;</button>
            </div>
        </div>

        <!-- Step 4: Validation -->
        <div class="wizard-step" data-step="4">
            <h2>Validierung & Qualitaetspruefung</h2>
            <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
                Die KI prueft Ihre Requirements nach IEEE 29148 Qualitaetskriterien und verbessert sie automatisch.
            </p>
            <div class="validation-mode-selector">
                <div class="mode-option selected" data-mode="AUTO">
                    <h4>AUTO-Modus</h4>
                    <p>KI validiert und verbessert automatisch. Schneller Durchlauf ohne Unterbrechungen.</p>
                </div>
                <div class="mode-option" data-mode="MANUAL">
                    <h4>MANUAL-Modus</h4>
                    <p>Sie entscheiden bei jeder Verbesserung. Klaerungsfragen werden gestellt.</p>
                </div>
            </div>
            <button class="wiz-btn wiz-btn-primary start-validation-btn" data-action="start-validation">
                Validierung starten
            </button>
            <div class="wiz-progress" id="wiz-validation-progress">
                <div class="wiz-progress-bar">
                    <div class="wiz-progress-fill" id="wiz-progress-fill" style="width: 0%"></div>
                </div>
                <div class="wiz-progress-text">
                    <span id="wiz-progress-message">Validiere Requirements...</span>
                    <span id="wiz-progress-percent">0%</span>
                </div>
            </div>
            <div class="validation-stats" id="wiz-validation-stats" style="display: none;">
                <div class="stat-card passed">
                    <div class="stat-value" id="wiz-stat-passed">0</div>
                    <div class="stat-label">Bestanden</div>
                </div>
                <div class="stat-card failed">
                    <div class="stat-value" id="wiz-stat-failed">0</div>
                    <div class="stat-label">Nicht bestanden</div>
                </div>
                <div class="stat-card improved">
                    <div class="stat-value" id="wiz-stat-improved">0</div>
                    <div class="stat-label">Verbessert</div>
                </div>
                <div class="stat-card split">
                    <div class="stat-value" id="wiz-stat-split">0</div>
                    <div class="stat-label">Aufgeteilt</div>
                </div>
            </div>
            <div class="validation-results-list" id="wiz-validation-results">
                <div class="validation-empty">
                    <p>Noch keine Validierungsergebnisse.</p>
                    <p>Klicken Sie auf "Validierung starten" um die Qualitaetspruefung zu beginnen.</p>
                </div>
            </div>
            <div class="wizard-nav">
                <button class="wiz-btn wiz-btn-secondary" data-action="prev">&larr; Zurueck</button>
                <button class="wiz-btn wiz-btn-primary" data-action="next">Weiter &rarr;</button>
            </div>
        </div>

        <!-- Clarification Modal -->
        <div class="wiz-modal-overlay" id="wiz-clarification-modal">
            <div class="wiz-modal-content">
                <div class="wiz-modal-header">
                    <h3>Klaerung erforderlich</h3>
                    <button class="wiz-modal-close" data-action="close-modal">&times;</button>
                </div>
                <div id="wiz-clarification-content"></div>
                <div class="wiz-modal-actions">
                    <button class="wiz-btn wiz-btn-secondary" data-action="skip-clarification">Ueberspringen</button>
                    <button class="wiz-btn wiz-btn-primary" data-action="submit-clarification">Antwort senden</button>
                </div>
            </div>
        </div>

        <!-- Step 5: Constraints -->
        <div class="wizard-step" data-step="5">
            <h2>Constraints & Rahmenbedingungen</h2>
            <div class="form-group">
                <label>Technische Constraints</label>
                <div class="tag-input" id="wiz-tech-constraints-input">
                    <input type="text" placeholder="z.B. Python 3.11+, PostgreSQL..." id="wiz-tech-constraint-text">
                </div>
            </div>
            <div class="form-group">
                <label>Regulatorische Constraints</label>
                <div class="tag-input" id="wiz-reg-constraints-input">
                    <input type="text" placeholder="z.B. DSGVO, PCI-DSS..." id="wiz-reg-constraint-text">
                </div>
            </div>
            <div class="form-group">
                <label for="wiz-budget">Budget</label>
                <input type="text" id="wiz-budget" placeholder="z.B. 200k EUR">
            </div>
            <div class="form-group">
                <label for="wiz-timeline">Timeline</label>
                <input type="text" id="wiz-timeline" placeholder="z.B. 6 Monate MVP">
            </div>
            <div class="form-group">
                <label for="wiz-team-size">Team-Groesse</label>
                <input type="text" id="wiz-team-size" placeholder="z.B. 5 Entwickler, 1 QA, 1 DevOps">
            </div>
            <hr style="border-color: var(--border-color); margin: 1.5rem 0;">
            <div class="form-group">
                <label for="wiz-work-division">Arbeitsaufteilung</label>
                <select id="wiz-work-division">
                    <option value="per_feature" selected>Per Feature</option>
                    <option value="per_service">Per Service (Microservices)</option>
                    <option value="per_application">Per Application</option>
                </select>
            </div>
            <div class="wizard-nav">
                <button class="wiz-btn wiz-btn-secondary" data-action="prev">&larr; Zurueck</button>
                <button class="wiz-btn wiz-btn-primary" data-action="next">Weiter &rarr;</button>
            </div>
        </div>

        <!-- Step 6: Export -->
        <div class="wizard-step" data-step="6">
            <h2>Export & Analyse starten</h2>
            <div class="form-group">
                <label>Generierte JSON-Konfiguration:</label>
                <div class="json-preview" id="wiz-json-preview"></div>
            </div>
            <div class="wizard-nav">
                <button class="wiz-btn wiz-btn-secondary" data-action="prev">&larr; Zurueck</button>
                <div style="display:flex;gap:0.5rem;">
                    <button class="wiz-btn wiz-btn-secondary" data-action="download-json">JSON herunterladen</button>
                    <button class="wiz-btn wiz-btn-success" data-action="start-analysis">Analyse starten &rarr;</button>
                </div>
            </div>
        </div>
    </div>
    `;
}

// ============================================
// Event Binding
// ============================================

function bindEvents() {
    // Action buttons (data-action delegation)
    container.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const action = btn.dataset.action;
        switch (action) {
            case 'next': nextStep(); break;
            case 'prev': prevStep(); break;
            case 'extract': extractRequirements(); break;
            case 'add-req': addRequirement(); break;
            case 'start-validation': startValidation(); break;
            case 'download-json': downloadJSON(); break;
            case 'start-analysis': startAnalysis(); break;
            case 'close-modal': closeClarificationModal(); break;
            case 'skip-clarification': closeClarificationModal(); break;
            case 'submit-clarification': submitClarification(); break;
        }
    });

    // Validation mode selector
    qAll('.mode-option').forEach(el => {
        el.addEventListener('click', () => setValidationMode(el.dataset.mode));
    });

    // Requirement edit/delete delegation
    container.addEventListener('click', (e) => {
        const editBtn = e.target.closest('[data-edit-req]');
        if (editBtn) editRequirement(parseInt(editBtn.dataset.editReq));

        const delBtn = e.target.closest('[data-delete-req]');
        if (delBtn) removeRequirement(parseInt(delBtn.dataset.deleteReq));

        const expandBtn = e.target.closest('[data-expand-criteria]');
        if (expandBtn) toggleCriteria(parseInt(expandBtn.dataset.expandCriteria));

        const sugBtn = e.target.closest('[data-suggest]');
        if (sugBtn) {
            const [qIdx, sIdx] = sugBtn.dataset.suggest.split(',').map(Number);
            selectSuggestedAnswer(qIdx, sIdx);
        }
    });

    // Tag inputs
    setupTagInput('wiz-target-users-input', 'wiz-target-user-text', wizardState.project.target_users);
    setupTagInput('wiz-tech-constraints-input', 'wiz-tech-constraint-text', wizardState.constraints.technical);
    setupTagInput('wiz-reg-constraints-input', 'wiz-reg-constraint-text', wizardState.constraints.regulatory);

    // File upload
    const dropZone = q('#wiz-file-drop-zone');
    const fileInput = q('#wiz-file-input');

    if (dropZone && fileInput) {
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            handleFiles(e.dataTransfer.files);
        });
        fileInput.addEventListener('change', () => handleFiles(fileInput.files));
    }
}

// ============================================
// Step Navigation
// ============================================

function showStep(step) {
    qAll('.wizard-step').forEach(el => el.classList.remove('active'));
    qAll('.step').forEach(el => {
        el.classList.remove('active');
        if (parseInt(el.dataset.step) < step) {
            el.classList.add('completed');
        } else {
            el.classList.remove('completed');
        }
    });

    const stepEl = q(`.wizard-step[data-step="${step}"]`);
    if (stepEl) stepEl.classList.add('active');

    const indicatorEl = q(`.step[data-step="${step}"]`);
    if (indicatorEl) indicatorEl.classList.add('active');

    wizardState.currentStep = step;

    if (step === 6) generateJSONPreview();

    // Trigger auto-enrichment for steps that support it
    if (step === 1 || step === 3 || step === 5) {
        triggerAutoEnrichment(step);
    }
}

function nextStep() {
    saveCurrentStep();
    if (wizardState.currentStep < wizardState.maxStep) {
        showStep(wizardState.currentStep + 1);
    }
}

function prevStep() {
    if (wizardState.currentStep > 1) {
        showStep(wizardState.currentStep - 1);
    }
}

// ============================================
// Auto-Enrichment (AutoGen Agent Teams)
// ============================================

let _enrichmentRunning = false;

async function triggerAutoEnrichment(step) {
    // Only trigger if we have enough data
    if (step === 1 && !wizardState.project.name && !wizardState.project.description) return;
    if (step === 3 && wizardState.requirements.length === 0) return;
    if (step === 5 && wizardState.requirements.length === 0) return;

    // Debounce - don't run if already running
    if (_enrichmentRunning) return;
    _enrichmentRunning = true;

    // Save current step data first
    saveCurrentStep();

    const body = { step };
    if (step === 1) {
        body.project_name = wizardState.project.name;
        body.description = wizardState.project.description;
        body.domain = wizardState.project.domain;
        body.target_users = wizardState.project.target_users;
    } else if (step === 3) {
        body.requirements = wizardState.requirements.map(r =>
            typeof r === 'string' ? r : (r.title || r.text || r.description || '')
        );
        body.description = wizardState.project.description;
        body.domain = wizardState.project.domain;
    } else if (step === 5) {
        body.requirements = wizardState.requirements.map(r =>
            typeof r === 'string' ? r : (r.title || r.text || r.description || '')
        );
        body.constraints = wizardState.constraints;
        body.description = wizardState.project.description;
    }

    try {
        const resp = await fetch('/api/wizard/auto-enrich', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const result = await resp.json();
        if (result.success) {
            applyAutoSuggestions(step, result.auto_applied || []);
        }
        if (result.errors && result.errors.length > 0) {
            console.warn('[Wizard] Enrichment errors:', result.errors);
        }
    } catch (err) {
        console.warn('[Wizard] Auto-enrich failed:', err);
    } finally {
        _enrichmentRunning = false;
    }
}

function applyAutoSuggestions(step, autoApplied) {
    for (const suggestion of autoApplied) {
        const content = suggestion.content || {};
        switch (suggestion.type) {
            case 'stakeholder':
                if (content.role || content.name) {
                    const exists = wizardState.stakeholders.some(s =>
                        (s.role || s.name) === (content.role || content.name)
                    );
                    if (!exists) {
                        wizardState.stakeholders.push(content);
                    }
                }
                break;
            case 'context':
                // Merge context fields (don't overwrite user input)
                if (content.summary && !wizardState.context.summary) {
                    wizardState.context.summary = content.summary;
                    const el = q('#wiz-context-summary');
                    if (el) el.value = content.summary;
                }
                if (content.business && !wizardState.context.business) {
                    wizardState.context.business = content.business;
                    const el = q('#wiz-context-business');
                    if (el) el.value = content.business;
                }
                if (content.technical && !wizardState.context.technical) {
                    wizardState.context.technical = content.technical;
                    const el = q('#wiz-context-technical');
                    if (el) el.value = content.technical;
                }
                if (content.user && !wizardState.context.user) {
                    wizardState.context.user = content.user;
                    const el = q('#wiz-context-user');
                    if (el) el.value = content.user;
                }
                break;
            case 'requirement':
                if (content.title || content.text) {
                    const title = content.title || content.text;
                    const exists = wizardState.requirements.some(r =>
                        (typeof r === 'string' ? r : (r.title || '')) === title
                    );
                    if (!exists) {
                        wizardState.requirements.push({
                            title: title,
                            description: content.description || title,
                            priority: content.priority || 'should',
                            category: content.category || 'functional',
                            _auto_generated: true,
                        });
                    }
                }
                break;
            case 'constraint':
                if (content.description || content.title) {
                    const cat = content.category || 'technical';
                    const text = content.description || content.title;
                    if (Array.isArray(wizardState.constraints[cat])) {
                        if (!wizardState.constraints[cat].includes(text)) {
                            wizardState.constraints[cat].push(text);
                        }
                    }
                }
                break;
        }
    }
}

function saveCurrentStep() {
    switch (wizardState.currentStep) {
        case 1:
            wizardState.project.name = q('#wiz-project-name')?.value || '';
            wizardState.project.description = q('#wiz-project-description')?.value || '';
            wizardState.project.domain = q('#wiz-project-domain')?.value || 'custom';
            wizardState.project.autonomy_level = q('#wiz-autonomy-level')?.value || 'medium';
            wizardState.context.summary = q('#wiz-context-summary')?.value || '';
            wizardState.context.business = q('#wiz-context-business')?.value || '';
            wizardState.context.technical = q('#wiz-context-technical')?.value || '';
            wizardState.context.user = q('#wiz-context-user')?.value || '';
            break;
        case 5:
            wizardState.constraints.budget = q('#wiz-budget')?.value || '';
            wizardState.constraints.timeline = q('#wiz-timeline')?.value || '';
            wizardState.constraints.team_size = q('#wiz-team-size')?.value || '';
            wizardState.workDivision = q('#wiz-work-division')?.value || 'per_feature';
            break;
    }
}

// ============================================
// Tag Input
// ============================================

function setupTagInput(inputId, textInputId, array) {
    const containerEl = q(`#${inputId}`);
    const textInput = q(`#${textInputId}`);
    if (!containerEl || !textInput) return;

    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && textInput.value.trim()) {
            e.preventDefault();
            const value = textInput.value.trim();
            if (!array.includes(value)) {
                array.push(value);
                renderTags(containerEl, array);
            }
            textInput.value = '';
        }
    });

    renderTags(containerEl, array);
}

function renderTags(containerEl, array) {
    const textInput = containerEl.querySelector('input');
    containerEl.innerHTML = '';
    array.forEach((tag, idx) => {
        const tagEl = document.createElement('span');
        tagEl.className = 'wiz-tag';
        tagEl.innerHTML = `${escapeHtml(tag)} <button data-remove-tag="${containerEl.id}:${idx}">&times;</button>`;
        containerEl.appendChild(tagEl);
    });
    containerEl.appendChild(textInput);

    // Re-bind tag removal
    containerEl.querySelectorAll('[data-remove-tag]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const [cId, idxStr] = btn.dataset.removeTag.split(':');
            removeTag(parseInt(idxStr), cId);
        });
    });
}

function removeTag(idx, containerId) {
    let array;
    if (containerId === 'wiz-target-users-input') array = wizardState.project.target_users;
    else if (containerId === 'wiz-tech-constraints-input') array = wizardState.constraints.technical;
    else if (containerId === 'wiz-reg-constraints-input') array = wizardState.constraints.regulatory;
    else return;

    array.splice(idx, 1);
    const containerEl = q(`#${containerId}`);
    if (containerEl) renderTags(containerEl, array);
}

// ============================================
// File Upload
// ============================================

function handleFiles(files) {
    for (const file of files) {
        if (!wizardState.files.find(f => f.name === file.name)) {
            wizardState.files.push(file);
        }
    }
    renderFileList();
}

function renderFileList() {
    const list = q('#wiz-file-list');
    const extractBtn = q('#wiz-extract-btn');
    if (!list) return;

    list.innerHTML = wizardState.files.map((file, idx) => `
        <div class="file-item">
            <div class="file-info">
                <span>📄</span>
                <span>${escapeHtml(file.name)}</span>
                <span style="color: var(--text-secondary)">(${formatSize(file.size)})</span>
            </div>
            <button class="remove-file" data-remove-file="${idx}">&times;</button>
        </div>
    `).join('');

    if (extractBtn) extractBtn.disabled = wizardState.files.length === 0;

    // Bind remove
    list.querySelectorAll('[data-remove-file]').forEach(btn => {
        btn.addEventListener('click', () => {
            wizardState.files.splice(parseInt(btn.dataset.removeFile), 1);
            renderFileList();
        });
    });
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ============================================
// Extract Requirements
// ============================================

async function extractRequirements() {
    if (wizardState.files.length === 0) return;

    const loading = q('#wiz-extract-loading');
    const extractBtn = q('#wiz-extract-btn');
    if (loading) loading.classList.add('active');
    if (extractBtn) extractBtn.disabled = true;

    try {
        const formData = new FormData();
        wizardState.files.forEach(file => formData.append('documents', file));

        const response = await fetch('/api/wizard/extract', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (result.success) {
            wizardState.requirements = [...wizardState.requirements, ...result.requirements];
            renderRequirements();
            nextStep();
        } else {
            alert('Fehler: ' + (result.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler bei der Extraktion: ' + error.message);
    } finally {
        if (loading) loading.classList.remove('active');
        if (extractBtn) extractBtn.disabled = false;
    }
}

// ============================================
// Requirements Management
// ============================================

function renderRequirements() {
    const list = q('#wiz-requirements-list');
    if (!list) return;

    list.innerHTML = wizardState.requirements.map((req, idx) => `
        <div class="requirement-item ${escapeHtml(req.category || req.type || '')}">
            <div class="requirement-header">
                <span class="requirement-id">${escapeHtml(req.id || '')}</span>
                <div class="requirement-actions">
                    <button data-edit-req="${idx}" title="Bearbeiten">✏️</button>
                    <button data-delete-req="${idx}" title="Loeschen">🗑️</button>
                </div>
            </div>
            <div class="requirement-title">${escapeHtml(req.title || '')}</div>
            <div class="requirement-meta">
                <span>📁 ${escapeHtml(req.category || req.type || 'functional')}</span>
                <span>⚡ ${escapeHtml(req.priority || 'should')}</span>
                ${req.source_file ? `<span>📄 ${escapeHtml(req.source_file)}</span>` : ''}
            </div>
        </div>
    `).join('');
}

function addRequirement() {
    const id = `REQ-${(wizardState.requirements.length + 1).toString().padStart(3, '0')}`;
    const title = prompt('Requirement Titel:');
    if (title) {
        wizardState.requirements.push({
            id,
            title,
            description: title,
            category: 'functional',
            type: 'functional',
            priority: 'should',
            acceptance_criteria: [],
            tags: []
        });
        renderRequirements();
    }
}

function editRequirement(idx) {
    const req = wizardState.requirements[idx];
    if (!req) return;
    const newTitle = prompt('Requirement Titel:', req.title);
    if (newTitle) {
        req.title = newTitle;
        req.description = newTitle;
        renderRequirements();
    }
}

function removeRequirement(idx) {
    if (confirm('Requirement wirklich loeschen?')) {
        wizardState.requirements.splice(idx, 1);
        renderRequirements();
    }
}

// ============================================
// JSON Generation
// ============================================

function generateJSONPreview() {
    const json = buildJSON();
    const preview = q('#wiz-json-preview');
    if (preview) preview.textContent = JSON.stringify(json, null, 2);
}

function buildJSON() {
    // Build Context object (use description as summary fallback)
    const context = {};
    const summary = wizardState.context.summary || wizardState.project.description;
    if (summary) context.summary = summary;
    if (wizardState.context.business) context.business = wizardState.context.business;
    if (wizardState.project.domain) context.domain = wizardState.project.domain;
    if (wizardState.context.technical) context.technical = wizardState.context.technical;
    if (wizardState.context.user) context.user = wizardState.context.user;

    // Build Initial Requirements as string array (RE-System format)
    const initialRequirements = wizardState.requirements.map(r => {
        if (typeof r === 'string') return r;
        // Requirement objects: combine title + description
        const title = r.title || r.name || '';
        const desc = r.description || '';
        return desc ? `${title}: ${desc}` : title;
    }).filter(r => r.length > 0);

    // Build Constraints object
    const constraints = {};
    if (wizardState.constraints.technical.length > 0) {
        constraints.technical = wizardState.constraints.technical;
    }
    if (wizardState.constraints.regulatory.length > 0) {
        constraints.regulatory = wizardState.constraints.regulatory;
    }
    if (wizardState.constraints.budget) constraints.budget = wizardState.constraints.budget;
    if (wizardState.constraints.timeline) constraints.timeline = wizardState.constraints.timeline;
    if (wizardState.constraints.team_size) constraints.team_size = wizardState.constraints.team_size;

    // Build Stakeholders from target_users
    const stakeholders = wizardState.stakeholders.length > 0
        ? wizardState.stakeholders
        : wizardState.project.target_users.map(user => ({
            role: "End User",
            persona: user,
            concerns: [],
            goals: []
        }));

    // RE-System compatible format (matches sample_project.json)
    const output = {
        Name: (wizardState.project.name || 'unnamed_project').replace(/\s+/g, '_').toLowerCase(),
        Title: wizardState.project.name || 'Unnamed Project',
        Domain: wizardState.project.domain || 'custom',
        Context: context,
        Stakeholders: stakeholders,
        "Initial Requirements": initialRequirements,
        Constraints: constraints,
        "Work Division": wizardState.workDivision || 'per_feature',
        "Enterprise Options": {
            generate_user_stories: true,
            generate_api_spec: true,
            generate_data_dictionary: true,
            generate_gherkin: true,
            enable_self_critique: true,
            max_passes: 5,
            output_format: "markdown"
        }
    };

    // Also keep _imported_requirements for pre-parsed requirement objects
    if (wizardState.requirements.length > 0 && typeof wizardState.requirements[0] === 'object') {
        output._imported_requirements = wizardState.requirements.map((r, i) => ({
            requirement_id: r.id || `REQ-${String(i + 1).padStart(3, '0')}`,
            title: r.title || r.name || `Requirement ${i + 1}`,
            description: r.description || '',
            type: r.type || 'functional',
            priority: r.priority || 'should',
            source: 'wizard'
        }));
    }

    return output;
}

function downloadJSON() {
    saveCurrentStep();
    const json = buildJSON();
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(wizardState.project.name || 'project').replace(/\s+/g, '_')}_input.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ============================================
// Start Analysis (canvas integration)
// ============================================

async function startAnalysis() {
    saveCurrentStep();
    const json = buildJSON();

    try {
        // Step 1: Save JSON
        const response = await fetch('/api/wizard/generate-json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ...json,
                save_path: true
            })
        });

        const result = await response.json();
        if (!result.success) {
            alert('Fehler: ' + (result.error || 'Unbekannt'));
            return;
        }

        const savedPath = result.file_path || null;

        // Step 2: Validate config
        const configResp = await fetch('/api/config/validate');
        const configResult = await configResp.json();

        if (!configResult.valid) {
            const issues = configResult.issues.join('\n- ');
            alert('Konfiguration unvollstaendig:\n- ' + issues);
            return;
        }

        // Step 3: Start pipeline
        if (savedPath) {
            const pipeResp = await fetch('/api/pipeline/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_path: savedPath
                })
            });
            const pipeResult = await pipeResp.json();

            if (pipeResult.error) {
                alert('Pipeline-Fehler: ' + pipeResult.error);
                return;
            }
        }

        // Step 4: Callback to app.js (switch to canvas + show progress)
        if (onAnalysisComplete) {
            onAnalysisComplete({
                requirements: wizardState.requirements,
                project: wizardState.project,
                constraints: wizardState.constraints,
                savedPath: savedPath,
                pipelineStarted: !!savedPath
            });
        }
    } catch (error) {
        alert('Fehler: ' + error.message);
    }
}

// ============================================
// Validation
// ============================================

function setValidationMode(mode) {
    validationState.mode = mode;
    qAll('.mode-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.mode === mode);
    });
}

async function startValidation() {
    if (wizardState.requirements.length === 0) {
        alert('Keine Requirements vorhanden.');
        return;
    }

    validationState.isRunning = true;
    validationState.results = [];
    validationState.stats = { passed: 0, failed: 0, improved: 0, split: 0 };

    const progress = q('#wiz-validation-progress');
    const startBtn = q('[data-action="start-validation"]');
    const stats = q('#wiz-validation-stats');

    if (progress) progress.classList.add('active');
    if (startBtn) startBtn.disabled = true;
    if (stats) stats.style.display = 'none';

    updateProgress(0, 'Starte Validierung...');

    try {
        // Step 1: Batch validation
        updateProgress(20, 'Validiere Requirements...');
        const validationResult = await fetch('/api/wizard/validate-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requirements: wizardState.requirements, threshold: 0.7 })
        }).then(r => r.json());

        if (!validationResult.success) {
            throw new Error(validationResult.error || 'Validierung fehlgeschlagen');
        }

        validationState.results = validationResult.results;
        validationState.stats.passed = validationResult.passed_count;
        validationState.stats.failed = validationResult.failed_count;

        // Step 2: Decisions for failed
        const failedReqs = validationResult.results.filter(r => r.verdict !== 'pass');

        if (failedReqs.length > 0) {
            updateProgress(40, 'Analysiere fehlerhafte Requirements...');

            const decisionResult = await fetch('/api/wizard/decide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    requirements: failedReqs.map(r => ({
                        id: r.req_id, title: r.title, score: r.score, evaluation: r.evaluation
                    }))
                })
            }).then(r => r.json());

            if (decisionResult.success && decisionResult.decisions) {
                decisionResult.decisions.forEach(decision => {
                    const resultIdx = validationState.results.findIndex(r => r.req_id === decision.req_id);
                    if (resultIdx !== -1) {
                        validationState.results[resultIdx].decision = decision.action;
                        validationState.results[resultIdx].reason = decision.reason;
                    }
                });
            }

            // Step 3: Auto-improve
            if (validationState.mode === 'AUTO' && failedReqs.length > 0) {
                updateProgress(60, 'Verbessere Requirements automatisch...');

                const improveResult = await fetch('/api/wizard/improve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        requirements: wizardState.requirements,
                        config: { quality_threshold: 0.7, max_iterations: 3, mode: 'AUTO' }
                    })
                }).then(r => r.json());

                if (improveResult.success) {
                    wizardState.requirements = improveResult.requirements;
                    validationState.stats.improved = improveResult.improved_count || 0;
                    validationState.stats.split = improveResult.split_count || 0;

                    updateProgress(80, 'Ueberprüfe Verbesserungen...');
                    const revalidateResult = await fetch('/api/wizard/validate-batch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ requirements: wizardState.requirements, threshold: 0.7 })
                    }).then(r => r.json());

                    if (revalidateResult.success) {
                        validationState.results = revalidateResult.results;
                        validationState.stats.passed = revalidateResult.passed_count;
                        validationState.stats.failed = revalidateResult.failed_count;
                    }
                }
            }

            // Step 4: Manual clarifications
            if (validationState.mode === 'MANUAL' && decisionResult.decisions) {
                const clarifyReqs = decisionResult.decisions.filter(d => d.action === 'CLARIFY');
                for (const clarifyReq of clarifyReqs) {
                    updateProgress(70, `Klaerung fuer ${clarifyReq.req_id}...`);
                    await handleClarification(clarifyReq);
                }
            }
        }

        updateProgress(100, 'Validierung abgeschlossen');

    } catch (error) {
        console.error('Validation error:', error);
        alert('Fehler bei der Validierung: ' + error.message);
    } finally {
        validationState.isRunning = false;
        if (startBtn) startBtn.disabled = false;
        if (progress) progress.classList.remove('active');
        if (stats) stats.style.display = 'grid';
        renderValidationResults();
        updateValidationStats();
    }
}

function updateProgress(percent, message) {
    const fill = q('#wiz-progress-fill');
    const pct = q('#wiz-progress-percent');
    const msg = q('#wiz-progress-message');
    if (fill) fill.style.width = `${percent}%`;
    if (pct) pct.textContent = `${percent}%`;
    if (msg) msg.textContent = message;
}

function updateValidationStats() {
    const s = validationState.stats;
    const el = (id) => q(`#wiz-stat-${id}`);
    if (el('passed')) el('passed').textContent = s.passed;
    if (el('failed')) el('failed').textContent = s.failed;
    if (el('improved')) el('improved').textContent = s.improved;
    if (el('split')) el('split').textContent = s.split;
}

function renderValidationResults() {
    const list = q('#wiz-validation-results');
    if (!list) return;

    if (validationState.results.length === 0) {
        list.innerHTML = `<div class="validation-empty"><p>Noch keine Validierungsergebnisse.</p></div>`;
        return;
    }

    list.innerHTML = validationState.results.map((result, idx) => {
        const scoreClass = result.score >= 0.7 ? '' : (result.score >= 0.5 ? 'medium' : 'low');
        const itemClass = result.verdict === 'pass' ? 'pass' : (result.decision === 'REWRITE' ? 'improved' : 'fail');
        const decision = result.decision || (result.verdict === 'pass' ? 'ACCEPT' : 'FAIL');

        let criteriaHtml = '';
        if (result.evaluation && result.evaluation.length > 0) {
            criteriaHtml = result.evaluation.map(crit => {
                const critScore = crit.score !== undefined ? crit.score : (crit.passed ? 1 : 0);
                const critClass = critScore >= 0.7 ? 'pass' : 'fail';
                return `<div class="criterion-item"><span>${escapeHtml(crit.criterion || crit.name || '')}</span><span class="criterion-score ${critClass}">${(critScore * 100).toFixed(0)}%</span></div>`;
            }).join('');
        }

        return `
            <div class="validation-result-item ${itemClass}">
                <div class="result-header">
                    <span class="result-id">${escapeHtml(result.req_id || '')}</span>
                    <div class="result-badges">
                        <span class="wiz-badge wiz-badge-score ${scoreClass}">${(result.score * 100).toFixed(0)}%</span>
                        <span class="wiz-badge wiz-badge-decision ${decision}">${decision}</span>
                    </div>
                </div>
                <div class="result-title">${escapeHtml(result.title || '')}</div>
                <div class="result-details">
                    ${result.reason ? `<em>${escapeHtml(result.reason)}</em>` : ''}
                    <button data-expand-criteria="${idx}" class="expand-btn">Details ▼</button>
                </div>
                <div class="result-criteria" id="wiz-criteria-${idx}">${criteriaHtml}</div>
            </div>
        `;
    }).join('');
}

function toggleCriteria(idx) {
    const el = q(`#wiz-criteria-${idx}`);
    if (el) el.classList.toggle('expanded');
}

// ============================================
// Clarification
// ============================================

async function handleClarification(clarifyReq) {
    const clarifyResult = await fetch('/api/wizard/clarify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            req_id: clarifyReq.req_id,
            requirement_text: clarifyReq.title || wizardState.requirements.find(r => r.id === clarifyReq.req_id)?.title,
            evaluation: clarifyReq.evaluation || []
        })
    }).then(r => r.json());

    if (clarifyResult.success && clarifyResult.questions && clarifyResult.questions.length > 0) {
        validationState.currentClarification = {
            req_id: clarifyReq.req_id,
            questions: clarifyResult.questions
        };
        showClarificationModal(clarifyResult);
        await new Promise(resolve => {
            validationState.clarificationResolve = resolve;
        });
    }
}

function showClarificationModal(clarifyResult) {
    const content = q('#wiz-clarification-content');
    const reqId = validationState.currentClarification.req_id;
    const req = wizardState.requirements.find(r => r.id === reqId);

    content.innerHTML = `
        <p style="margin-bottom: 1rem;"><strong>${escapeHtml(reqId)}:</strong> ${escapeHtml(req?.title || '')}</p>
        ${clarifyResult.questions.map((qItem, idx) => `
            <div class="clarification-question" data-question-idx="${idx}">
                <h4>${escapeHtml(qItem.criterion || 'Frage')}</h4>
                <p>${escapeHtml(qItem.question || '')}</p>
                ${qItem.suggestions && qItem.suggestions.length > 0 ? `
                    <div class="suggested-answers">
                        ${qItem.suggestions.map((s, sIdx) => `
                            <button class="suggested-answer" data-suggest="${idx},${sIdx}">${escapeHtml(s)}</button>
                        `).join('')}
                    </div>
                ` : ''}
                <div class="custom-answer">
                    <textarea placeholder="Oder eigene Antwort eingeben..." id="wiz-clarify-answer-${idx}"></textarea>
                </div>
            </div>
        `).join('')}
    `;

    q('#wiz-clarification-modal').classList.add('active');
}

function selectSuggestedAnswer(questionIdx, suggestionIdx) {
    const question = validationState.currentClarification.questions[questionIdx];
    if (!question) return;
    const suggestion = question.suggestions[suggestionIdx];
    const textarea = q(`#wiz-clarify-answer-${questionIdx}`);
    if (textarea) textarea.value = suggestion;
}

function closeClarificationModal() {
    q('#wiz-clarification-modal')?.classList.remove('active');
    if (validationState.clarificationResolve) {
        validationState.clarificationResolve();
        validationState.clarificationResolve = null;
    }
}

async function submitClarification() {
    const answers = [];
    if (validationState.currentClarification) {
        validationState.currentClarification.questions.forEach((qItem, idx) => {
            const answerEl = q(`#wiz-clarify-answer-${idx}`);
            if (answerEl && answerEl.value.trim()) {
                answers.push({ criterion: qItem.criterion, answer: answerEl.value.trim() });
            }
        });
    }

    if (answers.length > 0) {
        try {
            const response = await fetch('/api/wizard/answer-clarification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    req_id: validationState.currentClarification.req_id,
                    answers
                })
            }).then(r => r.json());

            if (response.success && response.improved_requirement) {
                const reqIdx = wizardState.requirements.findIndex(r => r.id === validationState.currentClarification.req_id);
                if (reqIdx !== -1) {
                    wizardState.requirements[reqIdx] = { ...wizardState.requirements[reqIdx], ...response.improved_requirement };
                    validationState.stats.improved++;
                }
            }
        } catch (error) {
            console.error('Clarification submission error:', error);
        }
    }

    closeClarificationModal();
}
