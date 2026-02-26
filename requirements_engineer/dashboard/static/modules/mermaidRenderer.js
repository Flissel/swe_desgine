/**
 * RE System Dashboard - Mermaid Renderer Module
 *
 * Handles lazy loading and batch rendering of Mermaid diagrams.
 * Provides queue management and error handling for diagram rendering.
 */

import { state, log } from './state.js';

// ============================================
// Queue Management
// ============================================

const mermaidRenderQueue = [];
let mermaidRenderInProgress = false;
let mermaidRenderEnabled = false;  // Disabled by default until layout is complete

// Batch loading configuration
const MERMAID_BATCH_SIZE = 5;        // Render 5 diagrams per batch
const MERMAID_BATCH_DELAY_MS = 150;  // 150ms pause between batches
let mermaidBatchCount = 0;
let mermaidTotalCount = 0;

// Re-render debounce state
let reRenderTimeout = null;

// ============================================
// ID Sanitization
// ============================================

/**
 * Sanitize ID for use as HTML element ID.
 * Removes/replaces special characters that break getElementById().
 * @param {string} id - Original node ID
 * @returns {string} Sanitized ID safe for HTML element IDs
 */
export function sanitizeIdForHtml(id) {
    if (!id) return '';
    return id
        .replace(/[\/\\{}()<>[\]|^$*+?.:!@#%&='"`,;~\s]/g, '_')
        .replace(/_+/g, '_')  // Collapse multiple underscores
        .replace(/^_|_$/g, ''); // Remove leading/trailing underscores
}

// ============================================
// Queue Operations
// ============================================

/**
 * Queue a diagram for rendering
 * @param {string} id - Node ID
 * @param {string} code - Mermaid code
 */
export function queueMermaidRender(id, code) {
    console.log(`[Mermaid] Queuing diagram: ${id} (code length: ${code?.length || 0})`);
    mermaidRenderQueue.push({ id, code });

    // If rendering is enabled, start processing
    if (mermaidRenderEnabled && !mermaidRenderInProgress) {
        console.log('[Mermaid] Rendering is enabled, starting batch processing');
        processMermaidBatch();
    }
}

/**
 * Clear the mermaid render queue.
 * Call this when switching projects to prevent rendering orphaned diagrams.
 */
export function clearMermaidQueue() {
    mermaidRenderQueue.length = 0;
    mermaidRenderInProgress = false;
    mermaidRenderEnabled = false;
    mermaidBatchCount = 0;
    mermaidTotalCount = 0;
    console.log('[Mermaid] Queue cleared');
}

/**
 * Start rendering all queued diagrams.
 * Call this after layout is complete.
 */
export function startMermaidRendering() {
    mermaidTotalCount = mermaidRenderQueue.length;
    mermaidBatchCount = 0;

    console.log(`[Mermaid] startMermaidRendering called`);
    console.log(`[Mermaid] Queue length: ${mermaidTotalCount}`);
    console.log(`[Mermaid] mermaid global available: ${typeof mermaid !== 'undefined'}`);

    if (mermaidTotalCount === 0) {
        console.log('[Mermaid] No diagrams in queue to render');
        return;
    }

    console.log(`[Mermaid] Starting batch rendering of ${mermaidTotalCount} diagrams (batch size: ${MERMAID_BATCH_SIZE})...`);
    mermaidRenderEnabled = true;

    if (!mermaidRenderInProgress && mermaidRenderQueue.length > 0) {
        processMermaidBatch();
    }
}

/**
 * Re-queue and re-render all diagrams.
 * Call this when switching layouts to ensure diagrams are rendered.
 */
export function reRenderAllDiagrams() {
    // Debounce: If multiple calls come in rapid succession, only execute once
    if (reRenderTimeout) {
        clearTimeout(reRenderTimeout);
    }

    reRenderTimeout = setTimeout(() => {
        reRenderTimeout = null;

        // Clear the existing queue to avoid duplicates
        mermaidRenderQueue.length = 0;
        mermaidRenderEnabled = false;
        mermaidRenderInProgress = false;

        // Re-queue all diagrams that have mermaid_code (including user-flow nodes)
        let requeued = 0;
        Object.entries(state.nodes).forEach(([id, node]) => {
            if ((node.type === 'diagram' || node.type === 'user-flow') && node.data?.mermaid_code) {
                const sanitizedId = sanitizeIdForHtml(id);
                queueMermaidRender(sanitizedId, node.data.mermaid_code);
                requeued++;
            }
        });

        console.log(`[Mermaid] Re-queued ${requeued} diagrams for layout rendering`);
        startMermaidRendering();
    }, 100);  // 100ms debounce
}

/**
 * Check if mermaid rendering is currently in progress
 * @returns {boolean}
 */
export function isRenderingInProgress() {
    return mermaidRenderInProgress;
}

/**
 * Get queue status
 * @returns {Object} Queue status info
 */
export function getQueueStatus() {
    return {
        queued: mermaidRenderQueue.length,
        processed: mermaidBatchCount,
        total: mermaidTotalCount,
        inProgress: mermaidRenderInProgress,
        enabled: mermaidRenderEnabled
    };
}

// ============================================
// Batch Processing
// ============================================

/**
 * Process a batch of diagrams from the queue.
 * Renders MERMAID_BATCH_SIZE diagrams in parallel, then pauses before next batch.
 */
async function processMermaidBatch() {
    if (!mermaidRenderEnabled || mermaidRenderQueue.length === 0) {
        mermaidRenderInProgress = false;
        const batchesProcessed = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE);
        console.log(`[Mermaid] Batch rendering complete: ${mermaidBatchCount}/${mermaidTotalCount} diagrams in ${batchesProcessed} batches`);
        return;
    }

    mermaidRenderInProgress = true;

    // Take up to MERMAID_BATCH_SIZE items from the queue
    const batch = [];
    while (batch.length < MERMAID_BATCH_SIZE && mermaidRenderQueue.length > 0) {
        batch.push(mermaidRenderQueue.shift());
    }

    const batchNum = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE) + 1;
    const remaining = mermaidRenderQueue.length;
    console.log(`[Mermaid] Processing batch ${batchNum}: ${batch.length} diagrams (${remaining} remaining)`);

    // Render all items in this batch in parallel
    const renderPromises = batch.map(async ({ id, code }) => {
        try {
            await renderMermaid(id, code);
            mermaidBatchCount++;
        } catch (e) {
            console.warn(`[Mermaid] Error rendering ${id}:`, e);
            mermaidBatchCount++;  // Count failed renders too
        }
    });

    // Wait for all renders in this batch to complete
    await Promise.all(renderPromises);

    // If more diagrams remain, schedule next batch with delay
    if (mermaidRenderQueue.length > 0) {
        // Pause between batches to let UI breathe
        setTimeout(processMermaidBatch, MERMAID_BATCH_DELAY_MS);
    } else {
        // All done
        mermaidRenderInProgress = false;
        const batchesProcessed = Math.ceil(mermaidBatchCount / MERMAID_BATCH_SIZE);
        console.log(`[Mermaid] Batch rendering complete: ${mermaidBatchCount}/${mermaidTotalCount} diagrams in ${batchesProcessed} batches`);
    }
}

// ============================================
// Mermaid Rendering
// ============================================

/**
 * Render a single Mermaid diagram
 * @param {string} id - Node ID
 * @param {string} code - Mermaid code
 */
export async function renderMermaid(id, code) {
    const elementId = `mermaid-${id}`;
    let element = document.getElementById(elementId);

    console.log(`[Mermaid] Attempting to render: ${id}, element exists:`, !!element);

    if (!element) {
        console.error(`[Mermaid] ❌ Element not found: ${elementId}`);
        // Debug: List all mermaid elements
        const allMermaidEls = document.querySelectorAll('[id^="mermaid-"]');
        console.log(`[Mermaid] Available mermaid elements (${allMermaidEls.length}):`,
            Array.from(allMermaidEls).map(el => el.id).slice(0, 5));

        // Try to find by original ID stored in dataset
        const fallbackElement = document.querySelector(`[data-original-id="${id}"]`) ||
                                document.querySelector(`[data-node-id="${id}"]`);
        if (fallbackElement) {
            const container = fallbackElement.classList.contains('node-diagram-content') ?
                fallbackElement : fallbackElement.querySelector('.node-diagram-content');
            if (container) {
                container.innerHTML = `<div class="diagram-error">Element ID mismatch: ${elementId}</div>`;
                console.log(`[Mermaid] Showed error in fallback container for: ${id}`);
            }
        }
        return;
    }

    // Check for empty code
    if (!code || !code.trim()) {
        console.warn(`[Mermaid] Empty code for: ${id}`);
        element.innerHTML = '<div class="diagram-loading">No diagram code</div>';
        return;
    }

    // Detect diagram type for logging
    const diagramType = code.trim().split('\n')[0].split(/\s/)[0];
    console.log(`[Mermaid] Rendering ${diagramType} diagram: ${id}`);

    // Sanitize the code to fix common syntax errors
    // TEMPORARILY DISABLED - may be causing parse errors
    // const sanitizedCode = sanitizeMermaidCode(code);
    const sanitizedCode = code;  // Pass through raw code

    // Generate unique SVG ID to avoid conflicts
    const svgId = `mermaid-svg-${id}-${Date.now()}`;

    try {
        // Verify mermaid is available
        if (typeof mermaid === 'undefined') {
            console.error('[Mermaid] Library not available for rendering');
            element.innerHTML = '<div class="diagram-error">Mermaid library not loaded</div>';
            return;
        }

        // Clean up any existing temporary Mermaid elements with similar IDs
        const existingTempElement = document.getElementById(svgId);
        if (existingTempElement) {
            existingTempElement.remove();
        }

        console.log(`[Mermaid] Calling mermaid.render for ${id}...`);
        console.log(`[Mermaid] Code preview for ${id}:`, sanitizedCode.substring(0, 200));

        // Verify mermaid.render exists and is a function
        if (typeof mermaid.render !== 'function') {
            console.error('[Mermaid] mermaid.render is not a function!');
            element.innerHTML = '<div class="diagram-error">Mermaid render function not available</div>';
            return;
        }

        const result = await mermaid.render(svgId, sanitizedCode);
        console.log(`[Mermaid] Render result for ${id}:`, {
            hasSvg: !!result?.svg,
            svgLength: result?.svg?.length || 0
        });

        if (!result || !result.svg) {
            console.error(`[Mermaid] No SVG returned for ${id}`);
            element.innerHTML = '<div class="diagram-error">No diagram generated</div>';
            return;
        }

        // Check if SVG has actual content (not just empty wrapper)
        const svgContent = result.svg;
        const hasVisibleContent = svgContent.includes('<g') || svgContent.includes('<rect') ||
                                   svgContent.includes('<path') || svgContent.includes('<text');

        if (!hasVisibleContent || svgContent.length < 200) {
            console.warn(`[Mermaid] SVG appears empty for ${id}: length=${svgContent.length}`);
            console.warn(`[Mermaid] SVG preview: ${svgContent.substring(0, 300)}`);
            element.innerHTML = `<div class="diagram-error">Diagram rendered but appears empty (${diagramType})</div>`;
            return;
        }

        element.innerHTML = result.svg;
        console.log(`[Mermaid] Successfully rendered: ${id} (${svgContent.length} chars)`);

        // Clean up any temporary element Mermaid creates OUTSIDE our container
        // Important: Don't remove the SVG we just inserted (it has the same ID)
        const tempElement = document.getElementById(svgId);
        if (tempElement && tempElement !== element && !element.contains(tempElement)) {
            console.log(`[Mermaid] Cleaning up external temp element: ${svgId}`);
            tempElement.remove();
        }

        console.log(`[Mermaid] Render complete for: ${id}`);
    } catch (error) {
        // Show original code in error for debugging
        const errorMsg = error?.message || String(error) || 'Unknown error';
        console.warn(`[Mermaid] Error rendering ${id}:`, errorMsg);
        console.warn(`[Mermaid] Sanitized code:\n${sanitizedCode?.substring(0, 500) || '(no code)'}...`);

        // Show a user-friendly error with CSS class for proper styling
        const shortError = errorMsg.length > 80 ? errorMsg.substring(0, 80) + '...' : errorMsg;
        try {
            element.innerHTML = `<div class="diagram-error"><span>${shortError}</span></div>`;
        } catch (innerError) {
            console.error(`[Mermaid] Failed to set error message for ${id}:`, innerError);
        }
    }

    // SAFETY: Ensure element is never empty after render attempt
    if (element && (!element.innerHTML || element.innerHTML.trim() === '')) {
        console.error(`[Mermaid] SAFETY: Element was empty after render, adding fallback for: ${id}`);
        element.innerHTML = '<div class="diagram-error">Render completed but no content</div>';
    }
}

// ============================================
// Thumbnail Rendering
// ============================================

/**
 * Render a diagram as a small thumbnail
 * @param {string} diagramId - Diagram ID
 * @param {string} code - Mermaid code
 * @param {HTMLElement} targetElement - Container element for the thumbnail
 * @param {number} maxSize - Maximum width/height in pixels (default: 80)
 * @returns {Promise<boolean>} Success status
 */
export async function renderDiagramThumbnail(diagramId, code, targetElement, maxSize = 80) {
    if (!code || !targetElement) {
        console.warn(`[Mermaid] Thumbnail: Missing code or target for ${diagramId}`);
        return false;
    }

    // Check if mermaid is available
    if (typeof mermaid === 'undefined') {
        console.warn('[Mermaid] Thumbnail: Library not available');
        targetElement.innerHTML = '<div class="thumb-error">⚠️</div>';
        return false;
    }

    try {
        const svgId = `thumb-${sanitizeIdForHtml(diagramId)}-${Date.now()}`;

        // Render the diagram
        const result = await mermaid.render(svgId, code);

        if (!result || !result.svg) {
            targetElement.innerHTML = '<div class="thumb-error">⚠️</div>';
            return false;
        }

        // Parse SVG and scale to thumbnail size
        const parser = new DOMParser();
        const svgDoc = parser.parseFromString(result.svg, 'image/svg+xml');
        const svgEl = svgDoc.querySelector('svg');

        if (!svgEl) {
            targetElement.innerHTML = '<div class="thumb-error">⚠️</div>';
            return false;
        }

        // Get original dimensions from viewBox or width/height attributes
        let width, height;
        const viewBox = svgEl.getAttribute('viewBox');
        if (viewBox) {
            const parts = viewBox.split(' ').map(Number);
            width = parts[2] || 100;
            height = parts[3] || 100;
        } else {
            width = parseFloat(svgEl.getAttribute('width')) || 100;
            height = parseFloat(svgEl.getAttribute('height')) || 100;
        }

        // Calculate scale to fit maxSize while maintaining aspect ratio
        const scale = Math.min(maxSize / width, maxSize / height);
        const scaledWidth = Math.round(width * scale);
        const scaledHeight = Math.round(height * scale);

        // Apply thumbnail styling
        svgEl.setAttribute('width', `${scaledWidth}px`);
        svgEl.setAttribute('height', `${scaledHeight}px`);
        svgEl.style.maxWidth = `${maxSize}px`;
        svgEl.style.maxHeight = `${maxSize}px`;
        svgEl.style.display = 'block';

        // Clear loading state and insert SVG
        targetElement.innerHTML = '';
        targetElement.appendChild(svgEl);

        // Clean up any temporary element mermaid created outside our container
        const tempElement = document.getElementById(svgId);
        if (tempElement && !targetElement.contains(tempElement)) {
            tempElement.remove();
        }

        return true;
    } catch (e) {
        console.warn(`[Mermaid] Thumbnail error for ${diagramId}:`, e.message);
        targetElement.innerHTML = '<div class="thumb-error">⚠️</div>';
        return false;
    }
}

/**
 * Render multiple thumbnails with rate limiting
 * @param {Array} diagrams - Array of {id, code, element} objects
 * @param {number} maxSize - Maximum thumbnail size
 * @param {number} batchSize - Diagrams per batch
 * @param {number} delayMs - Delay between batches
 */
export async function renderThumbnailBatch(diagrams, maxSize = 80, batchSize = 3, delayMs = 50) {
    for (let i = 0; i < diagrams.length; i += batchSize) {
        const batch = diagrams.slice(i, i + batchSize);

        await Promise.all(batch.map(({ id, code, element }) =>
            renderDiagramThumbnail(id, code, element, maxSize)
        ));

        // Small delay between batches to prevent UI freeze
        if (i + batchSize < diagrams.length) {
            await new Promise(r => setTimeout(r, delayMs));
        }
    }
}

// ============================================
// Code Sanitization
// ============================================

/**
 * Sanitize Mermaid code to fix common syntax errors.
 * Fixes missing closing braces in classDiagram and erDiagram.
 * Fixes state diagram 'as' keyword issues.
 * Fixes sequence diagram multi-line messages.
 * @param {string} code - Raw Mermaid code
 * @returns {string} Sanitized code
 */
export function sanitizeMermaidCode(code) {
    if (!code) return code;

    const trimmed = code.trim();
    if (!trimmed) return code;

    // Detect diagram type (case-insensitive for robustness)
    const firstLine = trimmed.split('\n')[0];
    const firstLineLower = firstLine.toLowerCase();

    // Class diagrams - add missing closing braces
    if (firstLineLower.startsWith('classdiagram')) {
        return fixClassDiagram(code);
    }

    // ER diagrams - add missing closing braces
    if (firstLineLower.startsWith('erdiagram')) {
        return fixERDiagram(code);
    }

    // State diagrams - remove problematic "state X as Y" lines (keep other lines)
    if (firstLineLower.startsWith('statediagram')) {
        const lines = code.split('\n');
        const filtered = lines.filter(line => !line.match(/^\s*state\s+\w+\s+as\s+/));
        // Only return filtered if we didn't remove everything
        if (filtered.length > 1) {
            return filtered.join('\n');
        }
        return code;  // Return original if filtering would empty it
    }

    // Flowchart diagrams - escape parentheses inside node labels
    if (firstLineLower.startsWith('flowchart')) {
        return fixFlowchartDiagram(code);
    }

    // All other diagram types (sequence, C4, etc.) - pass through as-is
    return code;
}

/**
 * Fix class diagrams by adding missing closing braces before new class definitions
 * or relationship lines.
 */
function fixClassDiagram(code) {
    const lines = code.split('\n');
    const result = [];
    let inClassBlock = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();

        // Check if this line starts a new class definition
        const isClassStart = /^class\s+\w+/.test(trimmedLine);

        // Check if this line is a relationship (outside class block)
        // Relationships have arrows like -->, --|>, ..|>, etc.
        const isRelationship = /^\w+\s*(--|\.\.|\*--|o--|<\||>\|)/.test(trimmedLine) ||
                               /^\w+\s*:\s*/.test(trimmedLine);

        // If we're in a class block and encounter a new class or relationship
        if (inClassBlock && (isClassStart || isRelationship)) {
            result.push('    }');
            inClassBlock = false;
        }

        result.push(line);

        // If this line starts a class block (has { but no })
        if (isClassStart) {
            const hasOpenBrace = line.includes('{');
            const hasCloseBrace = line.includes('}');
            if (hasOpenBrace && !hasCloseBrace) {
                inClassBlock = true;
            }
        }
    }

    // Close any remaining open block
    if (inClassBlock) {
        result.push('    }');
    }

    return result.join('\n');
}

/**
 * Fix ER diagrams by adding missing closing braces before new entity definitions
 * or relationship lines.
 */
function fixERDiagram(code) {
    const lines = code.split('\n');
    const result = [];
    let inEntityBlock = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();

        // Check if this line starts a new entity definition
        // Pattern: ENTITY_NAME { (entity names are typically UPPERCASE)
        const isEntityStart = /^[A-Z][A-Z0-9_]*\s*\{/.test(trimmedLine);

        // Check if this line is a relationship
        // Pattern: ENTITY ||--o{ OTHER_ENTITY : label
        // Contains cardinality symbols: ||, |o, o|, }|, |{, etc.
        const isRelationship = /^[A-Z][A-Z0-9_]*\s*(\|\||\|o|o\||\}\||\|\{|\{o|o\{|\}\{)/.test(trimmedLine);

        // If we're in an entity block and encounter a new entity or relationship
        if (inEntityBlock && (isEntityStart || isRelationship)) {
            result.push('    }');
            inEntityBlock = false;
        }

        result.push(line);

        // If this line starts an entity block (has { but no })
        if (isEntityStart) {
            const hasOpenBrace = line.includes('{');
            const hasCloseBrace = line.includes('}');
            // Only mark as in block if we see { without corresponding }
            // Also check it's not a cardinality brace like }|
            if (hasOpenBrace && !hasCloseBrace && !isRelationship) {
                inEntityBlock = true;
            }
        }
    }

    // Close any remaining open block
    if (inEntityBlock) {
        result.push('    }');
    }

    return result.join('\n');
}

/**
 * Fix flowchart diagrams by escaping parentheses inside node labels.
 * Mermaid uses () for stadium-shaped nodes, so parentheses in text
 * like [Mahnstufe bestimmen(DunningLevelCalculator)] cause parse errors.
 * We replace them with fullwidth parentheses which render similarly but don't break parsing.
 */
function fixFlowchartDiagram(code) {
    const lines = code.split('\n');
    const result = [];

    for (const line of lines) {
        let fixedLine = line;

        // Match node definitions with square brackets: ID[text] or after arrow like --> B[text]
        // The key is to find [...] content and escape parentheses inside
        fixedLine = fixedLine.replace(/(\w+)\[([^\]]+)\]/g, (match, nodeId, content) => {
            // Only fix if content has parentheses
            if (!content.includes('(') && !content.includes(')')) {
                return match;
            }
            // Replace parentheses with fullwidth versions inside the label
            const fixedContent = content
                .replace(/\(/g, '（')  // Fullwidth left parenthesis U+FF08
                .replace(/\)/g, '）'); // Fullwidth right parenthesis U+FF09
            return `${nodeId}[${fixedContent}]`;
        });

        // Also handle curly brace nodes: ID{text}
        fixedLine = fixedLine.replace(/(\w+)\{([^}]+)\}/g, (match, nodeId, content) => {
            if (!content.includes('(') && !content.includes(')')) {
                return match;
            }
            const fixedContent = content
                .replace(/\(/g, '（')
                .replace(/\)/g, '）');
            return `${nodeId}{${fixedContent}}`;
        });

        // Note: Stadium nodes ID(text) are left as-is to avoid breaking shape syntax
        // If nested parens cause issues, they need manual fixing in the source data

        result.push(fixedLine);
    }

    return result.join('\n');
}

// ============================================
// Debug Helpers (exposed on window for console access)
// ============================================

if (typeof window !== 'undefined') {
    window.mermaidDebug = {
        getQueueStatus: () => getQueueStatus(),
        forceRerender: () => reRenderAllDiagrams(),
        listFailedDiagrams: () => {
            const loading = document.querySelectorAll('.diagram-loading');
            const errors = document.querySelectorAll('.diagram-error');
            const result = {
                loading: Array.from(loading).map(el => {
                    const nodeEl = el.closest('[data-node-id]');
                    return nodeEl?.dataset.nodeId || 'unknown';
                }),
                errors: Array.from(errors).map(el => {
                    const nodeEl = el.closest('[data-node-id]');
                    return {
                        id: nodeEl?.dataset.nodeId || 'unknown',
                        message: el.textContent?.substring(0, 50)
                    };
                })
            };
            console.table(result.loading.length > 0 ? result.loading : ['(none)']);
            console.table(result.errors.length > 0 ? result.errors : [{ id: '(none)', message: '' }]);
            return result;
        },
        checkElementExists: (id) => {
            const exists = !!document.getElementById(`mermaid-${id}`);
            console.log(`Element mermaid-${id}: ${exists ? '✓ exists' : '❌ missing'}`);
            return exists;
        },
        retryFailed: async () => {
            const loading = document.querySelectorAll('.diagram-loading');
            console.log(`[MermaidDebug] Retrying ${loading.length} failed diagrams...`);
            for (const el of loading) {
                const nodeEl = el.closest('[data-node-id]');
                if (nodeEl) {
                    const nodeId = nodeEl.dataset.nodeId;
                    // Try to find the code from state
                    if (window.dashboardState?.nodes?.[nodeId]?.data?.mermaid_code) {
                        const sanitizedId = sanitizeIdForHtml(nodeId);
                        queueMermaidRender(sanitizedId, window.dashboardState.nodes[nodeId].data.mermaid_code);
                    }
                }
            }
            startMermaidRendering();
        }
    };
    console.log('[Mermaid] Debug helpers available at window.mermaidDebug');
}
