"""
HTML Generator Agent for Multi-Agent HTML Generation.

This agent generates HTML pages from analyzed content using Claude/OpenRouter
for intelligent content structuring and formatting.
"""

import html
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
)

log = logging.getLogger(__name__)


def _esc(text: Any) -> str:
    """Escape text for safe HTML embedding. Prevents XSS."""
    return html.escape(str(text)) if text else ""


@dataclass
class HTMLPage:
    """Represents a generated HTML page."""
    name: str
    title: str
    content: str
    file_path: str
    content_types: List[str]
    priority: str = "medium"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# System prompt for HTML generation
HTML_GENERATOR_SYSTEM_PROMPT = """You are an HTML Generator Agent specialized in creating
professional, accessible, and well-structured HTML pages for software requirements documentation.

Your pages should:
1. Use semantic HTML5 elements (header, main, nav, article, section, aside, footer)
2. Include proper meta tags and accessibility attributes
3. Have a clean, professional styling with CSS
4. Support responsive design
5. Include navigation for multi-page documents
6. Embed Mermaid diagrams correctly with the mermaid.js script
7. Use proper heading hierarchy (h1, h2, h3...)
8. Include a table of contents for longer pages

Always respond with complete, valid HTML that can be directly saved to a file."""


# Base HTML template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{description}">
    <title>{title} - {project_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true, theme:'neutral'}});</script>
    <style>
        :root {{
            --primary-color: #1a73e8;
            --secondary-color: #5f6368;
            --background-color: #ffffff;
            --surface-color: #f8f9fa;
            --text-color: #202124;
            --border-color: #dadce0;
            --success-color: #34a853;
            --warning-color: #fbbc04;
            --error-color: #ea4335;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background-color: var(--background-color);
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }}

        header {{
            background-color: var(--primary-color);
            color: white;
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        header h1 {{
            font-size: 1.5rem;
            font-weight: 500;
        }}

        nav {{
            background-color: var(--surface-color);
            border-bottom: 1px solid var(--border-color);
            padding: 0.5rem 0;
        }}

        nav ul {{
            list-style: none;
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        nav a {{
            color: var(--secondary-color);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: background-color 0.2s;
        }}

        nav a:hover, nav a.active {{
            background-color: var(--border-color);
            color: var(--primary-color);
        }}

        main {{
            padding: 2rem 0;
            min-height: calc(100vh - 200px);
        }}

        .page-header {{
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--primary-color);
        }}

        .page-header h2 {{
            color: var(--primary-color);
            margin-bottom: 0.5rem;
        }}

        .page-header .meta {{
            color: var(--secondary-color);
            font-size: 0.9rem;
        }}

        section {{
            margin-bottom: 2rem;
        }}

        section h3 {{
            color: var(--text-color);
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .card {{
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }}

        .card h4 {{
            color: var(--primary-color);
            margin-bottom: 0.5rem;
        }}

        .card .meta {{
            font-size: 0.85rem;
            color: var(--secondary-color);
            margin-bottom: 0.5rem;
        }}

        .requirement-card {{
            border-left: 4px solid var(--primary-color);
        }}

        .story-card {{
            border-left: 4px solid var(--success-color);
        }}

        .test-card {{
            border-left: 4px solid var(--warning-color);
        }}

        .priority-must {{
            border-left-color: var(--error-color);
        }}

        .priority-should {{
            border-left-color: var(--warning-color);
        }}

        .priority-could {{
            border-left-color: var(--success-color);
        }}

        .tag {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-right: 0.25rem;
            background-color: var(--border-color);
        }}

        .tag-must {{ background-color: #fce8e6; color: var(--error-color); }}
        .tag-should {{ background-color: #fef7e0; color: #e37400; }}
        .tag-could {{ background-color: #e6f4ea; color: #137333; }}
        .tag-wont {{ background-color: #f1f3f4; color: var(--secondary-color); }}

        .diagram-container {{
            background-color: white;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            margin: 1rem 0;
            overflow-x: auto;
        }}

        .mermaid {{
            text-align: center;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }}

        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}

        th {{
            background-color: var(--surface-color);
            font-weight: 600;
        }}

        tr:hover {{
            background-color: var(--surface-color);
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background-color: var(--surface-color);
            border-radius: 8px;
            padding: 1.5rem;
            text-align: center;
        }}

        .stat-card .value {{
            font-size: 2rem;
            font-weight: 600;
            color: var(--primary-color);
        }}

        .stat-card .label {{
            color: var(--secondary-color);
            font-size: 0.9rem;
        }}

        footer {{
            background-color: var(--surface-color);
            border-top: 1px solid var(--border-color);
            padding: 1rem 0;
            text-align: center;
            color: var(--secondary-color);
            font-size: 0.85rem;
        }}

        .toc {{
            background-color: var(--surface-color);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}

        .toc h4 {{
            margin-bottom: 1rem;
        }}

        .toc ul {{
            list-style: none;
            padding-left: 1rem;
        }}

        .toc li {{
            margin: 0.25rem 0;
        }}

        .toc a {{
            color: var(--primary-color);
            text-decoration: none;
        }}

        .toc a:hover {{
            text-decoration: underline;
        }}

        @media (max-width: 768px) {{
            nav ul {{
                flex-direction: column;
            }}

            .stats-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        @media print {{
            header, nav, footer {{
                display: none;
            }}

            main {{
                padding: 0;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>{project_name}</h1>
        </div>
    </header>

    <nav>
        <div class="container">
            <ul>
                {navigation}
            </ul>
        </div>
    </nav>

    <main>
        <div class="container">
            {content}
        </div>
    </main>

    <footer>
        <div class="container">
            <p>Generated by RE System - {generated_at}</p>
        </div>
    </footer>
</body>
</html>"""


class HTMLGeneratorAgent(BasePresentationAgent):
    """
    Agent that generates HTML pages from content analysis.

    Capabilities:
    - Generate complete HTML pages from templates
    - Create navigation structure
    - Embed Mermaid diagrams
    - Format requirements, user stories, and other artifacts
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="HTMLGenerator",
            role=AgentRole.HTML_GENERATOR,
            description="Generates HTML pages from analyzed content",
            capabilities=[
                AgentCapability.HTML_GENERATION,
                AgentCapability.CSS_STYLING,
            ],
            config=config
        )

        # Generated pages cache
        self._generated_pages: Dict[str, HTMLPage] = {}

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Execute HTML generation based on content analysis.

        Args:
            context: The presentation context with analysis data

        Returns:
            AgentResult with generated HTML pages
        """
        self._is_running = True
        self._current_context = context

        try:
            self._log_progress(f"Starting HTML generation for project: {context.project_id}")

            # Load content analysis
            analysis = await self._load_analysis(context)

            if not analysis:
                return AgentResult(
                    success=False,
                    error_message="No content analysis found. Run ContentAnalyzerAgent first.",
                    action_type="GENERATE_HTML",
                    should_replan=True
                )

            # Generate pages based on recommendations
            pages = await self._generate_pages(context, analysis)

            # Save pages
            generated_files = []
            for page in pages:
                file_path = await self._save_page(context, page)
                generated_files.append(str(file_path))
                self._generated_pages[page.name] = page

            self._log_progress(f"HTML generation complete: {len(pages)} pages generated")

            return AgentResult(
                success=True,
                generated_files=generated_files,
                action_type="GENERATE_HTML",
                notes=f"Generated {len(pages)} HTML pages",
                recommendations=[
                    "Review generated HTML for quality",
                    "Check diagram embedding",
                    "Verify navigation links"
                ],
                suggested_next_agent="HTMLReviewer",
                confidence=0.8,
                needs_review=True,
                stage_complete=False
            )

        except Exception as e:
            self._log_error(f"HTML generation failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="GENERATE_HTML",
                notes=f"Generation failed: {e}",
                should_replan=True
            )

        finally:
            self._is_running = False

    async def _load_analysis(self, context: PresentationContext) -> Optional[Dict[str, Any]]:
        """Load content analysis from file."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        analysis_path = output_dir / "content_analysis.json"

        if analysis_path.exists():
            with open(analysis_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        return None

    async def _generate_pages(
        self,
        context: PresentationContext,
        analysis: Dict[str, Any]
    ) -> List[HTMLPage]:
        """Generate HTML pages based on content analysis."""
        pages = []

        # Get recommended pages from analysis
        recommended = analysis.get("recommended_pages", [])

        # Always generate index page
        index_page = await self._generate_index_page(context, analysis)
        pages.append(index_page)

        # Generate additional pages
        for page_config in recommended:
            if page_config.get("name") == "index":
                continue  # Already generated

            page = await self._generate_content_page(context, analysis, page_config)
            if page:
                pages.append(page)

        return pages

    async def _generate_index_page(
        self,
        context: PresentationContext,
        analysis: Dict[str, Any]
    ) -> HTMLPage:
        """Generate the index/overview page."""
        project_name = analysis.get("project_name", context.project_id)
        artifact_summaries = analysis.get("artifact_summaries", {})

        # Build statistics section
        stats_html = '<div class="stats-grid">'
        for artifact_type, summary in artifact_summaries.items():
            count = summary.get("count", 0) if isinstance(summary, dict) else 0
            stats_html += f'''
                <div class="stat-card">
                    <div class="value">{_esc(count)}</div>
                    <div class="label">{_esc(artifact_type.replace('_', ' ').title())}</div>
                </div>
            '''
        stats_html += '</div>'

        # Build key themes section
        themes = analysis.get("key_themes", [])
        themes_html = '<section><h3>Key Themes</h3><ul>'
        for theme in themes:
            themes_html += f'<li>{_esc(theme)}</li>'
        themes_html += '</ul></section>'

        # Build epics overview
        epics = analysis.get("epics_overview", [])
        epics_html = ""
        if epics:
            epics_html = '<section><h3>Epics Overview</h3>'
            for epic in epics[:10]:
                epics_html += f'''
                    <div class="card">
                        <h4>{_esc(epic.get("name", epic.get("id", "")))}</h4>
                        <p>{_esc(epic.get("description", ""))}</p>
                    </div>
                '''
            epics_html += '</section>'

        # Build content
        content = f'''
            <div class="page-header">
                <h2>Project Overview</h2>
                <p class="meta">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
            </div>

            <section>
                <h3>Artifact Statistics</h3>
                {stats_html}
            </section>

            {themes_html}

            {epics_html}

            <section>
                <h3>Quick Navigation</h3>
                <p>Use the navigation menu above to explore requirements, user stories, diagrams, and more.</p>
            </section>
        '''

        # Build navigation
        navigation = await self._build_navigation(analysis, "index")

        # Generate final HTML
        html_content = HTML_TEMPLATE.format(
            title="Overview",
            project_name=_esc(project_name),
            description=_esc(f"Overview of {project_name} requirements"),
            navigation=navigation,
            content=content,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        return HTMLPage(
            name="index",
            title="Overview",
            content=html_content,
            file_path="index.html",
            content_types=["summary", "statistics"],
            priority="high"
        )

    async def _generate_content_page(
        self,
        context: PresentationContext,
        analysis: Dict[str, Any],
        page_config: Dict[str, Any]
    ) -> Optional[HTMLPage]:
        """Generate a content page based on configuration."""
        page_name = page_config.get("name", "")
        page_title = page_config.get("title", page_name.replace("_", " ").title())
        content_types = page_config.get("content_types", [])

        project_name = analysis.get("project_name", context.project_id)
        artifact_summaries = analysis.get("artifact_summaries", {})

        # Build content based on content types
        content_sections = []

        for content_type in content_types:
            summary = artifact_summaries.get(content_type)
            if summary:
                section_html = await self._render_artifact_section(content_type, summary)
                content_sections.append(section_html)

        if not content_sections:
            # Generate placeholder content via LLM
            section_html = await self._generate_placeholder_section(page_title, content_types)
            content_sections.append(section_html)

        # Build page header
        header = f'''
            <div class="page-header">
                <h2>{_esc(page_title)}</h2>
                <p class="meta">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
            </div>
        '''

        # Build navigation
        navigation = await self._build_navigation(analysis, page_name)

        # Generate final HTML
        html_content = HTML_TEMPLATE.format(
            title=_esc(page_title),
            project_name=_esc(project_name),
            description=_esc(f"{page_title} for {project_name}"),
            navigation=navigation,
            content=header + "\n".join(content_sections),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        return HTMLPage(
            name=page_name,
            title=page_title,
            content=html_content,
            file_path=f"{page_name}.html",
            content_types=content_types,
            priority=page_config.get("priority", "medium")
        )

    async def _render_artifact_section(
        self,
        artifact_type: str,
        summary: Dict[str, Any]
    ) -> str:
        """Render a section for a specific artifact type."""
        items = summary.get("items", [])
        count = summary.get("count", len(items))

        section_title = artifact_type.replace("_", " ").title()

        html = f'<section id="{_esc(artifact_type)}"><h3>{_esc(section_title)} ({_esc(count)})</h3>'

        if artifact_type == "requirements":
            html += self._render_requirements(items)
        elif artifact_type == "user_stories":
            html += self._render_user_stories(items)
        elif artifact_type == "diagrams":
            html += self._render_diagrams(items)
        elif artifact_type == "tests":
            html += self._render_tests(items)
        elif artifact_type == "epics":
            html += self._render_epics(items)
        else:
            html += self._render_generic_items(items)

        html += '</section>'
        return html

    def _render_requirements(self, items: List[Dict[str, Any]]) -> str:
        """Render requirements as cards."""
        html = ""
        for item in items[:50]:  # Limit to 50 items
            if not isinstance(item, dict):
                continue

            req_id = item.get("id", "")
            title = item.get("title", item.get("name", ""))
            description = item.get("description", "")
            priority = item.get("priority", "").lower()
            req_type = item.get("type", "functional")

            priority_class = f"priority-{priority}" if priority in ["must", "should", "could", "wont"] else ""
            tag_class = f"tag-{priority}" if priority else ""

            html += f'''
                <div class="card requirement-card {priority_class}">
                    <h4>{_esc(req_id)}: {_esc(title)}</h4>
                    <div class="meta">
                        <span class="tag {tag_class}">{_esc(priority.upper()) if priority else 'N/A'}</span>
                        <span class="tag">{_esc(req_type)}</span>
                    </div>
                    <p>{_esc(description)}</p>
                </div>
            '''
        return html

    def _render_user_stories(self, items: List[Dict[str, Any]]) -> str:
        """Render user stories as cards."""
        html = ""
        for item in items[:50]:
            if not isinstance(item, dict):
                continue

            story_id = item.get("id", "")
            title = item.get("title", "")
            as_a = item.get("as_a", item.get("role", ""))
            i_want = item.get("i_want", item.get("action", ""))
            so_that = item.get("so_that", item.get("benefit", ""))
            acceptance = item.get("acceptance_criteria", [])

            html += f'''
                <div class="card story-card">
                    <h4>{_esc(story_id)}: {_esc(title)}</h4>
                    <p><strong>As a</strong> {_esc(as_a)}</p>
                    <p><strong>I want</strong> {_esc(i_want)}</p>
                    <p><strong>So that</strong> {_esc(so_that)}</p>
            '''

            if acceptance:
                html += '<p><strong>Acceptance Criteria:</strong></p><ul>'
                for criterion in acceptance[:5]:
                    html += f'<li>{_esc(criterion)}</li>'
                html += '</ul>'

            html += '</div>'
        return html

    def _render_diagrams(self, items: List[Dict[str, Any]]) -> str:
        """Render diagrams with Mermaid embedding."""
        html = ""
        for item in items[:30]:
            if isinstance(item, str):
                # Direct Mermaid code - escape to prevent XSS
                html += f'''
                    <div class="diagram-container">
                        <pre class="mermaid">{_esc(item)}</pre>
                    </div>
                '''
            elif isinstance(item, dict):
                diagram_id = item.get("id", "")
                diagram_type = item.get("type", "")
                code = item.get("code", item.get("content", ""))
                title = item.get("title", item.get("name", diagram_id))

                html += f'''
                    <div class="diagram-container">
                        <h4>{_esc(title)} ({_esc(diagram_type)})</h4>
                        <pre class="mermaid">{_esc(code)}</pre>
                    </div>
                '''
        return html

    def _render_tests(self, items: List[Dict[str, Any]]) -> str:
        """Render test cases as cards."""
        html = ""
        for item in items[:50]:
            if not isinstance(item, dict):
                continue

            test_id = item.get("id", "")
            name = item.get("name", item.get("title", ""))
            description = item.get("description", "")
            status = item.get("status", "pending")
            steps = item.get("steps", [])

            status_color = {
                "passed": "success",
                "failed": "error",
                "pending": "warning"
            }.get(status.lower(), "secondary")

            html += f'''
                <div class="card test-card">
                    <h4>{_esc(test_id)}: {_esc(name)}</h4>
                    <div class="meta">
                        <span class="tag" style="background-color: var(--{status_color}-color); color: white;">{_esc(status)}</span>
                    </div>
                    <p>{_esc(description)}</p>
            '''

            if steps:
                html += '<p><strong>Steps:</strong></p><ol>'
                for step in steps[:10]:
                    html += f'<li>{_esc(step)}</li>'
                html += '</ol>'

            html += '</div>'
        return html

    def _render_epics(self, items: List[Dict[str, Any]]) -> str:
        """Render epics as cards."""
        html = ""
        for item in items[:20]:
            if not isinstance(item, dict):
                continue

            epic_id = item.get("id", "")
            name = item.get("name", item.get("title", ""))
            description = item.get("description", "")
            stories = item.get("stories", item.get("user_stories", []))

            html += f'''
                <div class="card">
                    <h4>{_esc(epic_id)}: {_esc(name)}</h4>
                    <p>{_esc(description)}</p>
            '''

            if stories:
                html += f'<p><strong>User Stories:</strong> {len(stories)}</p>'

            html += '</div>'
        return html

    def _render_generic_items(self, items: List[Any]) -> str:
        """Render generic items as a simple list."""
        html = '<ul>'
        for item in items[:50]:
            if isinstance(item, dict):
                name = item.get("name", item.get("title", item.get("id", str(item))))
                html += f'<li>{_esc(name)}</li>'
            else:
                html += f'<li>{_esc(str(item)[:200])}</li>'
        html += '</ul>'
        return html

    async def _generate_placeholder_section(
        self,
        page_title: str,
        content_types: List[str]
    ) -> str:
        """Generate placeholder content via LLM."""
        return f'''
            <section>
                <h3>{_esc(page_title)}</h3>
                <p class="meta">Content for: {_esc(', '.join(content_types))}</p>
                <div class="card">
                    <p>This section will be populated with {_esc(page_title.lower())} content.</p>
                </div>
            </section>
        '''

    async def _build_navigation(
        self,
        analysis: Dict[str, Any],
        current_page: str
    ) -> str:
        """Build navigation HTML."""
        nav_items = [
            {"name": "index", "title": "Overview", "file": "index.html"},
        ]

        # Add recommended pages
        for page in analysis.get("recommended_pages", []):
            if page.get("name") != "index":
                nav_items.append({
                    "name": page.get("name"),
                    "title": page.get("title"),
                    "file": f"{page.get('name')}.html"
                })

        html = ""
        for item in nav_items:
            active_class = "active" if item["name"] == current_page else ""
            html += f'<li><a href="{_esc(item["file"])}" class="{active_class}">{_esc(item["title"])}</a></li>'

        return html

    async def _save_page(self, context: PresentationContext, page: HTMLPage) -> Path:
        """Save an HTML page to file."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        presentation_dir = output_dir / "presentation"
        presentation_dir.mkdir(parents=True, exist_ok=True)

        file_path = presentation_dir / page.file_path

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(page.content)

        self._log_progress(f"Saved page: {file_path}")
        return file_path

    def get_generated_page(self, name: str) -> Optional[HTMLPage]:
        """Get a generated page by name."""
        return self._generated_pages.get(name)
