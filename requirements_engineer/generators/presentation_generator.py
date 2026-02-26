"""
Presentation Stage Generator
Analyzes RE outputs and creates human-readable HTML pages.

This generator consolidates all artifacts from previous stages and creates
a navigable, human-readable presentation for stakeholders.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import json
import logging
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class PageSection:
    """A section within an HTML page."""
    id: str
    title: str
    content: str
    subsections: List['PageSection'] = field(default_factory=list)
    diagrams: List[str] = field(default_factory=list)


@dataclass
class HTMLPage:
    """Represents a generated HTML page."""
    filename: str
    title: str
    sections: List[PageSection] = field(default_factory=list)
    nav_links: List[Dict[str, str]] = field(default_factory=list)
    template: str = "default"


class PresentationAnalyzer:
    """Analyzes generated artifacts for consolidation."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.artifacts = {}
        self.statistics = {}

    def load_artifacts(self) -> None:
        """Load all generated artifacts from project directory."""
        # Requirements
        req_file = self.project_dir / 'requirements.json'
        if req_file.exists():
            try:
                self.artifacts['requirements'] = json.loads(req_file.read_text(encoding='utf-8'))
            except Exception as e:
                log.warning(f"Could not load requirements.json: {e}")

        # User Stories
        stories_dir = self.project_dir / 'user_stories'
        if stories_dir.exists():
            self.artifacts['user_stories'] = self._load_json_files(stories_dir)

        # Diagrams
        diagrams_dir = self.project_dir / 'diagrams'
        if diagrams_dir.exists():
            self.artifacts['diagrams'] = list(diagrams_dir.glob('*.mmd'))

        # Tasks
        tasks_file = self.project_dir / 'tasks' / 'task_list.json'
        if tasks_file.exists():
            try:
                self.artifacts['tasks'] = json.loads(tasks_file.read_text(encoding='utf-8'))
            except Exception as e:
                log.warning(f"Could not load task_list.json: {e}")

        # Tech Stack
        tech_file = self.project_dir / 'tech_stack' / 'tech_stack.json'
        if tech_file.exists():
            try:
                self.artifacts['tech_stack'] = json.loads(tech_file.read_text(encoding='utf-8'))
            except Exception as e:
                log.warning(f"Could not load tech_stack.json: {e}")

        # UX Design
        ux_dir = self.project_dir / 'ux_design'
        if ux_dir.exists():
            self.artifacts['ux_design'] = self._load_json_files(ux_dir)

        # UI Design
        ui_dir = self.project_dir / 'ui_design'
        if ui_dir.exists():
            self.artifacts['ui_design'] = self._load_json_files(ui_dir)

        log.info(f"Loaded artifacts: {list(self.artifacts.keys())}")

    def _load_json_files(self, directory: Path) -> List[Dict]:
        """Load all JSON files from a directory."""
        result = []
        for f in directory.glob('*.json'):
            try:
                result.append(json.loads(f.read_text(encoding='utf-8')))
            except Exception as e:
                log.warning(f"Could not load {f}: {e}")
        return result

    def analyze_redundancy(self) -> Dict[str, Any]:
        """Find redundant or duplicate content."""
        analysis = {
            'duplicate_requirements': [],
            'similar_stories': [],
            'orphan_diagrams': [],
            'consolidation_suggestions': []
        }

        # Find similar requirements
        reqs = self.artifacts.get('requirements', [])
        if isinstance(reqs, list):
            titles = [r.get('title', '') for r in reqs if isinstance(r, dict)]
            seen = set()
            for i, title in enumerate(titles):
                normalized = title.lower().strip()
                if normalized in seen:
                    analysis['duplicate_requirements'].append(i)
                seen.add(normalized)

        # Find orphan diagrams (diagrams not linked to any requirement)
        diagrams = self.artifacts.get('diagrams', [])
        for diagram in diagrams:
            diagram_name = diagram.stem if hasattr(diagram, 'stem') else str(diagram)
            # Simple check: if diagram name doesn't contain a requirement ID
            if not any(req_id in diagram_name for req_id in ['REQ-', 'EPIC-', 'US-']):
                analysis['orphan_diagrams'].append(diagram_name)

        return analysis

    def calculate_statistics(self) -> Dict[str, int]:
        """Calculate artifact statistics."""
        stats = {
            'total_requirements': 0,
            'total_user_stories': 0,
            'total_diagrams': 0,
            'total_tasks': 0,
            'total_pages_needed': 0
        }

        if 'requirements' in self.artifacts:
            reqs = self.artifacts['requirements']
            stats['total_requirements'] = len(reqs) if isinstance(reqs, list) else 1

        if 'user_stories' in self.artifacts:
            stats['total_user_stories'] = len(self.artifacts['user_stories'])

        if 'diagrams' in self.artifacts:
            stats['total_diagrams'] = len(self.artifacts['diagrams'])

        if 'tasks' in self.artifacts:
            tasks = self.artifacts['tasks']
            if isinstance(tasks, dict):
                stats['total_tasks'] = len(tasks.get('tasks', []))
            elif isinstance(tasks, list):
                stats['total_tasks'] = len(tasks)

        # Estimated page count
        stats['total_pages_needed'] = 3 + (stats['total_requirements'] // 10) + \
                                      (stats['total_diagrams'] // 5)

        self.statistics = stats
        return stats


class PresentationGenerator:
    """Generates HTML presentation from analyzed artifacts."""

    def __init__(self, project_id: str, project_dir: Path, output_dir: Path):
        self.project_id = project_id
        self.project_dir = project_dir
        self.output_dir = output_dir
        self.analyzer = PresentationAnalyzer(project_dir)
        self.pages: List[HTMLPage] = []

    def analyze_and_consolidate(self) -> Dict[str, Any]:
        """Analyze artifacts and prepare for consolidation."""
        self.analyzer.load_artifacts()
        redundancy = self.analyzer.analyze_redundancy()
        stats = self.analyzer.calculate_statistics()

        return {
            'statistics': stats,
            'redundancy': redundancy,
            'consolidation_plan': self._create_consolidation_plan(stats, redundancy)
        }

    def _create_consolidation_plan(self, stats: Dict, redundancy: Dict) -> List[str]:
        """Create plan for consolidating artifacts."""
        plan = []

        if stats['total_requirements'] > 20:
            plan.append("Group requirements by category/epic")

        if redundancy['duplicate_requirements']:
            plan.append(f"Merge {len(redundancy['duplicate_requirements'])} duplicate requirements")

        if stats['total_diagrams'] > 10:
            plan.append("Create diagram overview page with thumbnails")

        if redundancy['orphan_diagrams']:
            plan.append(f"Review {len(redundancy['orphan_diagrams'])} orphan diagrams")

        return plan

    def generate_pages(self) -> List[HTMLPage]:
        """Generate all HTML pages."""
        self.pages = []

        # 1. Index page
        self.pages.append(self._generate_index_page())

        # 2. Requirements page
        self.pages.append(self._generate_requirements_page())

        # 3. User Stories (grouped)
        self.pages.append(self._generate_stories_page())

        # 4. Diagrams overview
        self.pages.append(self._generate_diagrams_page())

        # 5. Traceability Matrix
        self.pages.append(self._generate_traceability_page())

        # 6. Executive Summary
        self.pages.append(self._generate_summary_page())

        return self.pages

    def _generate_index_page(self) -> HTMLPage:
        """Generate main index page."""
        stats = self.analyzer.statistics

        return HTMLPage(
            filename="index.html",
            title=f"{self.project_id} - Requirements Overview",
            sections=[
                PageSection(
                    id="overview",
                    title="Project Overview",
                    content=f"""
                        <div class="stats-grid">
                            <div class="stat-card">
                                <span class="stat-number">{stats.get('total_requirements', 0)}</span>
                                <span class="stat-label">Requirements</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number">{stats.get('total_user_stories', 0)}</span>
                                <span class="stat-label">User Stories</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number">{stats.get('total_diagrams', 0)}</span>
                                <span class="stat-label">Diagrams</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number">{stats.get('total_tasks', 0)}</span>
                                <span class="stat-label">Tasks</span>
                            </div>
                        </div>
                    """
                )
            ],
            nav_links=[
                {"href": "requirements.html", "label": "Requirements"},
                {"href": "stories.html", "label": "User Stories"},
                {"href": "diagrams.html", "label": "Diagrams"},
                {"href": "traceability.html", "label": "Traceability"},
                {"href": "summary.html", "label": "Summary"}
            ]
        )

    def _generate_requirements_page(self) -> HTMLPage:
        """Generate requirements listing page."""
        reqs = self.analyzer.artifacts.get('requirements', [])

        sections = []
        if isinstance(reqs, list):
            for req in reqs[:50]:  # Limit
                if isinstance(req, dict):
                    sections.append(PageSection(
                        id=req.get('id', 'unknown'),
                        title=req.get('title', 'Untitled'),
                        content=self._format_requirement(req)
                    ))

        return HTMLPage(
            filename="requirements.html",
            title="Requirements",
            sections=sections,
            nav_links=self._get_default_nav()
        )

    def _generate_stories_page(self) -> HTMLPage:
        """Generate user stories page."""
        stories = self.analyzer.artifacts.get('user_stories', [])

        return HTMLPage(
            filename="stories.html",
            title="User Stories",
            sections=[
                PageSection(
                    id="all-stories",
                    title="All User Stories",
                    content=self._format_stories_list(stories)
                )
            ],
            nav_links=self._get_default_nav()
        )

    def _generate_diagrams_page(self) -> HTMLPage:
        """Generate diagrams overview page."""
        diagrams = self.analyzer.artifacts.get('diagrams', [])

        return HTMLPage(
            filename="diagrams.html",
            title="Diagrams",
            sections=[
                PageSection(
                    id="diagram-gallery",
                    title="Diagram Gallery",
                    content=self._format_diagram_gallery(diagrams)
                )
            ],
            nav_links=self._get_default_nav()
        )

    def _generate_traceability_page(self) -> HTMLPage:
        """Generate traceability matrix page."""
        matrix_html = self._build_traceability_matrix()

        return HTMLPage(
            filename="traceability.html",
            title="Traceability Matrix",
            sections=[
                PageSection(
                    id="matrix",
                    title="Requirements Traceability",
                    content=matrix_html
                )
            ],
            nav_links=self._get_default_nav()
        )

    def _generate_summary_page(self) -> HTMLPage:
        """Generate executive summary page."""
        stats = self.analyzer.statistics
        redundancy = self.analyzer.analyze_redundancy()

        summary_content = f"""
            <div class="summary-content">
                <h3>Scope</h3>
                <p>This project contains <strong>{stats.get('total_requirements', 0)}</strong> requirements
                   organized into <strong>{stats.get('total_user_stories', 0)}</strong> user stories.</p>

                <h3>Visualization</h3>
                <p><strong>{stats.get('total_diagrams', 0)}</strong> diagrams have been generated
                   to illustrate the system architecture and workflows.</p>

                <h3>Work Breakdown</h3>
                <p><strong>{stats.get('total_tasks', 0)}</strong> tasks have been identified
                   for implementation.</p>
        """

        if redundancy['duplicate_requirements']:
            summary_content += f"""
                <h3>Quality Notes</h3>
                <p class="warning">{len(redundancy['duplicate_requirements'])} potential duplicate requirements detected.
                   Review recommended.</p>
            """

        summary_content += "</div>"

        return HTMLPage(
            filename="summary.html",
            title="Executive Summary",
            sections=[
                PageSection(
                    id="summary",
                    title="Project Summary",
                    content=summary_content
                )
            ],
            nav_links=self._get_default_nav()
        )

    def _get_default_nav(self) -> List[Dict[str, str]]:
        """Get default navigation links."""
        return [
            {"href": "index.html", "label": "Home"},
            {"href": "requirements.html", "label": "Requirements"},
            {"href": "stories.html", "label": "User Stories"},
            {"href": "diagrams.html", "label": "Diagrams"},
            {"href": "traceability.html", "label": "Traceability"},
            {"href": "summary.html", "label": "Summary"}
        ]

    def _format_requirement(self, req: Dict) -> str:
        """Format a single requirement as HTML."""
        priority_class = req.get('priority', 'medium').lower()
        return f"""
            <div class="requirement-card">
                <div class="req-header">
                    <span class="req-id">{req.get('id', 'N/A')}</span>
                    <span class="req-priority priority-{priority_class}">{req.get('priority', 'medium')}</span>
                </div>
                <p class="req-description">{req.get('description', '')}</p>
                {self._format_acceptance_criteria(req.get('acceptance_criteria', []))}
            </div>
        """

    def _format_acceptance_criteria(self, criteria: List) -> str:
        """Format acceptance criteria as HTML list."""
        if not criteria:
            return ""

        items = "".join([f"<li>{c}</li>" for c in criteria[:5]])
        return f"<div class='acceptance-criteria'><strong>Acceptance Criteria:</strong><ul>{items}</ul></div>"

    def _format_stories_list(self, stories: List) -> str:
        """Format user stories as HTML list."""
        if not stories:
            return "<p>No user stories found.</p>"

        html = "<div class='stories-list'>"
        for story in stories[:30]:
            if isinstance(story, dict):
                title = story.get('title', 'Untitled')
                story_id = story.get('id', '')
                html += f"<div class='story-item'><span class='story-id'>{story_id}</span> {title}</div>"
            else:
                html += f"<div class='story-item'>{str(story)}</div>"
        html += "</div>"
        return html

    def _format_diagram_gallery(self, diagrams: List[Path]) -> str:
        """Format diagrams as gallery."""
        if not diagrams:
            return "<p>No diagrams found.</p>"

        html = "<div class='diagram-gallery'>"
        for diagram in diagrams[:20]:
            name = diagram.stem if hasattr(diagram, 'stem') else str(diagram)
            diagram_type = self._detect_diagram_type(name)
            icon = self._get_diagram_icon(diagram_type)
            html += f"""
                <div class="diagram-card" data-type="{diagram_type}">
                    <div class="diagram-preview">{icon}</div>
                    <span class="diagram-name">{name}</span>
                    <span class="diagram-type">{diagram_type}</span>
                </div>
            """
        html += "</div>"
        return html

    def _detect_diagram_type(self, name: str) -> str:
        """Detect diagram type from filename."""
        name_lower = name.lower()
        if 'class' in name_lower:
            return 'Class Diagram'
        elif 'sequence' in name_lower:
            return 'Sequence Diagram'
        elif 'flow' in name_lower:
            return 'Flowchart'
        elif 'er' in name_lower or 'entity' in name_lower:
            return 'ER Diagram'
        elif 'state' in name_lower:
            return 'State Diagram'
        elif 'c4' in name_lower:
            return 'C4 Diagram'
        else:
            return 'Diagram'

    def _get_diagram_icon(self, diagram_type: str) -> str:
        """Get icon for diagram type."""
        icons = {
            'Class Diagram': '📐',
            'Sequence Diagram': '📋',
            'Flowchart': '🔀',
            'ER Diagram': '🗄️',
            'State Diagram': '⚡',
            'C4 Diagram': '🏗️',
            'Diagram': '📊'
        }
        return icons.get(diagram_type, '📊')

    def _build_traceability_matrix(self) -> str:
        """Build traceability matrix HTML."""
        reqs = self.analyzer.artifacts.get('requirements', [])
        stories = self.analyzer.artifacts.get('user_stories', [])

        if not reqs or not stories:
            return "<p>Insufficient data to build traceability matrix.</p>"

        # Simplified matrix for demo
        html = """
            <div class="traceability-matrix">
                <table>
                    <thead>
                        <tr>
                            <th>Requirement</th>
                            <th>User Stories</th>
                            <th>Tests</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for req in reqs[:20]:
            if isinstance(req, dict):
                req_id = req.get('id', 'N/A')
                html += f"""
                    <tr>
                        <td>{req_id}</td>
                        <td>-</td>
                        <td>-</td>
                        <td><span class="status-pending">Pending</span></td>
                    </tr>
                """

        html += """
                    </tbody>
                </table>
            </div>
        """
        return html

    def render_html(self, page: HTMLPage) -> str:
        """Render a page to HTML string."""
        nav_html = "".join([
            f'<a href="{link["href"]}" class="nav-link">{link["label"]}</a>'
            for link in page.nav_links
        ])

        sections_html = ""
        for section in page.sections:
            sections_html += f"""
                <section id="{section.id}">
                    <h2>{section.title}</h2>
                    {section.content}
                </section>
            """

        return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page.title}</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <nav class="main-nav">
        <a href="index.html" class="logo">{self.project_id}</a>
        <div class="nav-links">{nav_html}</div>
    </nav>

    <main>
        <h1>{page.title}</h1>
        {sections_html}
    </main>

    <footer>
        <p>Generated by RE-System on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </footer>

    <script src="assets/navigation.js"></script>
</body>
</html>
"""

    def save_all(self) -> List[Path]:
        """Save all generated pages."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Assets folder
        assets_dir = self.output_dir / 'assets'
        assets_dir.mkdir(exist_ok=True)

        # Save CSS
        self._save_stylesheet(assets_dir / 'style.css')

        # Save JS
        self._save_javascript(assets_dir / 'navigation.js')

        # Save pages
        saved = []
        for page in self.pages:
            html = self.render_html(page)
            path = self.output_dir / page.filename
            path.write_text(html, encoding='utf-8')
            saved.append(path)
            log.info(f"Saved: {path}")

        return saved

    def _save_stylesheet(self, path: Path) -> None:
        """Save CSS stylesheet."""
        css = """
/* RE-System Presentation Styles */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #7d8590;
    --accent: #1d9bf0;
    --accent-hover: #1a8cd8;
    --success: #00ba7c;
    --warning: #f59e0b;
    --error: #f4212e;
    --border: rgba(255,255,255,0.1);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
}

/* Navigation */
.main-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 32px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 100;
}

.main-nav .logo {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
    text-decoration: none;
}

.nav-links {
    display: flex;
    gap: 8px;
}

.nav-links a {
    color: var(--text-secondary);
    text-decoration: none;
    padding: 8px 16px;
    border-radius: 6px;
    transition: all 0.2s;
}

.nav-links a:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

/* Main Content */
main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 32px;
}

h1 {
    font-size: 32px;
    margin-bottom: 32px;
    color: var(--text-primary);
}

h2 {
    font-size: 24px;
    margin: 32px 0 16px;
    color: var(--accent);
}

h3 {
    font-size: 18px;
    margin: 24px 0 12px;
    color: var(--text-primary);
}

/* Sections */
section {
    background: var(--bg-secondary);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    border: 1px solid var(--border);
}

/* Stats Grid */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
}

.stat-card {
    background: rgba(29, 155, 240, 0.1);
    border: 1px solid rgba(29, 155, 240, 0.2);
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    transition: transform 0.2s;
}

.stat-card:hover {
    transform: translateY(-2px);
}

.stat-number {
    display: block;
    font-size: 48px;
    font-weight: 700;
    color: var(--accent);
}

.stat-label {
    color: var(--text-secondary);
    font-size: 14px;
    margin-top: 8px;
}

/* Requirement Cards */
.requirement-card {
    background: var(--bg-tertiary);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid var(--border);
}

.req-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.req-id {
    font-weight: 600;
    color: var(--accent);
    font-family: monospace;
}

.req-priority {
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    text-transform: uppercase;
}

.priority-must { background: var(--error); color: white; }
.priority-should { background: var(--warning); color: black; }
.priority-could { background: var(--success); color: white; }
.priority-medium { background: var(--text-secondary); color: white; }

.req-description {
    color: var(--text-primary);
    margin-bottom: 12px;
}

.acceptance-criteria {
    font-size: 14px;
    color: var(--text-secondary);
}

.acceptance-criteria ul {
    margin-left: 20px;
    margin-top: 8px;
}

/* Stories List */
.stories-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.story-item {
    padding: 12px 16px;
    background: var(--bg-tertiary);
    border-radius: 6px;
    border: 1px solid var(--border);
}

.story-id {
    font-family: monospace;
    color: var(--accent);
    margin-right: 8px;
}

/* Diagram Gallery */
.diagram-gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
}

.diagram-card {
    background: var(--bg-tertiary);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    border: 1px solid var(--border);
    transition: all 0.2s;
    cursor: pointer;
}

.diagram-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
}

.diagram-preview {
    font-size: 48px;
    margin-bottom: 12px;
}

.diagram-name {
    display: block;
    font-size: 12px;
    color: var(--text-primary);
    word-break: break-word;
}

.diagram-type {
    display: block;
    font-size: 10px;
    color: var(--text-secondary);
    margin-top: 4px;
}

/* Traceability Matrix */
.traceability-matrix table {
    width: 100%;
    border-collapse: collapse;
}

.traceability-matrix th,
.traceability-matrix td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

.traceability-matrix th {
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    font-weight: 500;
}

.status-pending {
    background: var(--warning);
    color: black;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
}

.status-complete {
    background: var(--success);
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
}

/* Summary */
.summary-content p {
    margin-bottom: 16px;
}

.summary-content .warning {
    color: var(--warning);
    padding: 12px;
    background: rgba(245, 158, 11, 0.1);
    border-radius: 6px;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

/* Footer */
footer {
    text-align: center;
    padding: 32px;
    color: var(--text-secondary);
    font-size: 12px;
    border-top: 1px solid var(--border);
    margin-top: 40px;
}

/* Responsive */
@media (max-width: 768px) {
    .main-nav {
        flex-direction: column;
        gap: 16px;
    }

    .nav-links {
        flex-wrap: wrap;
        justify-content: center;
    }

    main {
        padding: 20px 16px;
    }

    h1 {
        font-size: 24px;
    }
}
"""
        path.write_text(css, encoding='utf-8')

    def _save_javascript(self, path: Path) -> None:
        """Save JavaScript for navigation."""
        js = """
// RE-System Presentation Navigation
document.addEventListener('DOMContentLoaded', function() {
    // Highlight current page in navigation
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.nav-links a').forEach(link => {
        if (link.getAttribute('href') === currentPage) {
            link.style.color = '#1d9bf0';
            link.style.background = 'rgba(29, 155, 240, 0.1)';
        }
    });

    // Add click handlers to diagram cards
    document.querySelectorAll('.diagram-card').forEach(card => {
        card.addEventListener('click', function() {
            const name = this.querySelector('.diagram-name').textContent;
            alert('Diagram: ' + name + '\\n\\nFull viewer coming soon!');
        });
    });

    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
});
"""
        path.write_text(js, encoding='utf-8')
