"""
HTML Improver Agent for Multi-Agent HTML Generation.

This agent applies actual improvements to generated HTML pages based on
the reviewer's feedback. Uses Claude/OpenRouter for intelligent content
enhancement and structural fixes.
"""

import logging
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
    ImprovementItem,
    ImprovementType,
)

log = logging.getLogger(__name__)


@dataclass
class AppliedImprovement:
    """Record of an applied improvement."""
    improvement_type: ImprovementType
    target_file: str
    description: str
    success: bool
    changes_made: str
    error: Optional[str] = None


# System prompt for content enhancement
CONTENT_ENHANCER_SYSTEM_PROMPT = """You are an HTML Content Enhancer Agent specialized in improving
software requirements documentation. Your role is to:

1. Enhance text content for clarity and completeness
2. Add missing sections and descriptions
3. Improve formatting and structure
4. Generate additional explanatory content

When asked to enhance content, provide the improved HTML snippet directly.
Do not include explanations, just return the improved HTML code."""


# System prompt for structure fixing
STRUCTURE_FIXER_SYSTEM_PROMPT = """You are an HTML Structure Fixer Agent specialized in fixing
HTML markup issues. Your role is to:

1. Fix heading hierarchy issues
2. Add missing semantic elements
3. Correct HTML validation errors
4. Improve document structure

Return only the fixed HTML snippet, no explanations."""


class HTMLImproverAgent(BasePresentationAgent):
    """
    Agent that applies improvements to HTML pages.

    Capabilities:
    - Apply structural fixes (semantic elements, heading hierarchy)
    - Enhance content quality (descriptions, explanations)
    - Add missing sections (navigation, accessibility)
    - Fix styling issues
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="HTMLImprover",
            role=AgentRole.HTML_IMPROVER,
            description="Applies improvements to HTML pages based on review feedback",
            capabilities=[
                AgentCapability.HTML_GENERATION,
                AgentCapability.CONTENT_ENHANCEMENT,
                AgentCapability.STRUCTURE_FIXING,
            ],
            config=config
        )

        # Improvement handlers
        self._handlers = {
            ImprovementType.ADD_SECTION: self._add_section,
            ImprovementType.ENHANCE_CONTENT: self._enhance_content,
            ImprovementType.FIX_STRUCTURE: self._fix_structure,
            ImprovementType.ADD_STYLING: self._add_styling,
            ImprovementType.ADD_NAVIGATION: self._add_navigation,
            ImprovementType.FIX_ACCESSIBILITY: self._fix_accessibility,
            ImprovementType.MERGE_CONTENT: self._merge_content,
            ImprovementType.GENERATE_DIAGRAM: self._generate_diagram,
        }

        # Applied improvements history
        self._applied_improvements: List[AppliedImprovement] = []

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Execute HTML improvements based on review feedback.

        Args:
            context: The presentation context with quality issues

        Returns:
            AgentResult with applied improvements
        """
        self._is_running = True
        self._current_context = context

        try:
            self._log_progress(f"Starting HTML improvements for project: {context.project_id}")

            # Load review report
            review_data = await self._load_review_report(context)

            if not review_data:
                return AgentResult(
                    success=False,
                    error_message="No review report found. Run HTMLReviewerAgent first.",
                    action_type="IMPROVE_HTML",
                    should_replan=True
                )

            # Get prioritized improvements
            improvements = self._prioritize_improvements(context.quality_issues)

            if not improvements:
                self._log_progress("No improvements to apply")
                return AgentResult(
                    success=True,
                    action_type="IMPROVE_HTML",
                    notes="No improvements needed",
                    stage_complete=True
                )

            # Apply improvements
            applied = []
            modified_files = []

            max_improvements = self.config.get("max_per_iteration", 5)

            for improvement in improvements[:max_improvements]:
                result = await self._apply_improvement(context, improvement)
                applied.append(result)
                self._applied_improvements.append(result)

                if result.success:
                    modified_files.append(result.target_file)

            # Calculate success rate
            success_count = sum(1 for a in applied if a.success)
            success_rate = success_count / len(applied) if applied else 0

            self._log_progress(f"Applied {success_count}/{len(applied)} improvements")

            return AgentResult(
                success=success_count > 0,
                modified_files=list(set(modified_files)),
                improvements_applied=[
                    {
                        "type": a.improvement_type.value,
                        "target": a.target_file,
                        "description": a.description,
                        "success": a.success
                    }
                    for a in applied
                ],
                action_type="IMPROVE_HTML",
                notes=f"Applied {success_count}/{len(applied)} improvements (success rate: {success_rate:.1%})",
                recommendations=[
                    "Re-run review to verify improvements",
                    f"Remaining improvements: {len(improvements) - len(applied)}"
                ],
                suggested_next_agent="HTMLReviewer",
                confidence=success_rate,
                needs_review=True,
                stage_complete=False
            )

        except Exception as e:
            self._log_error(f"HTML improvement failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="IMPROVE_HTML",
                notes=f"Improvement failed: {e}",
                should_replan=True
            )

        finally:
            self._is_running = False

    async def _load_review_report(self, context: PresentationContext) -> Optional[Dict[str, Any]]:
        """Load the review report."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        report_path = output_dir / "html_review_report.json"

        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        return None

    def _prioritize_improvements(
        self,
        quality_issues: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prioritize improvements by severity and type."""
        severity_order = {"critical": 0, "major": 1, "minor": 2}

        # Sort by severity
        sorted_issues = sorted(
            quality_issues,
            key=lambda x: severity_order.get(x.get("severity", "minor"), 3)
        )

        return sorted_issues

    async def _apply_improvement(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> AppliedImprovement:
        """Apply a single improvement."""
        improvement_type_str = improvement.get("type", "enhance_content")

        try:
            improvement_type = ImprovementType(improvement_type_str)
        except ValueError:
            improvement_type = ImprovementType.ENHANCE_CONTENT

        target_file = improvement.get("location", improvement.get("target", ""))
        description = improvement.get("description", "")

        self._log_progress(f"Applying {improvement_type.value}: {description[:50]}...")

        # Get the handler
        handler = self._handlers.get(improvement_type)

        if not handler:
            return AppliedImprovement(
                improvement_type=improvement_type,
                target_file=target_file,
                description=description,
                success=False,
                changes_made="",
                error=f"No handler for improvement type: {improvement_type}"
            )

        try:
            success, changes = await handler(context, improvement)
            return AppliedImprovement(
                improvement_type=improvement_type,
                target_file=target_file,
                description=description,
                success=success,
                changes_made=changes
            )
        except Exception as e:
            log.error(f"Improvement handler failed: {e}")
            return AppliedImprovement(
                improvement_type=improvement_type,
                target_file=target_file,
                description=description,
                success=False,
                changes_made="",
                error=str(e)
            )

    async def _add_section(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Add a new section to the HTML."""
        target_file = Path(improvement.get("location", ""))
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Use LLM to generate the new section
        user_prompt = f"""Add a new section to this HTML document based on the following suggestion:

Suggestion: {suggestion}

Current HTML (excerpt):
{content[:2000]}...

Generate ONLY the new section HTML (a complete <section> element) that should be added.
The section should fit the existing style and structure."""

        try:
            new_section = await self._call_llm(
                system_prompt=CONTENT_ENHANCER_SYSTEM_PROMPT,
                user_prompt=user_prompt
            )

            # Clean up response
            new_section = self._extract_html(new_section)

            if not new_section:
                return False, "Failed to generate new section"

            # Insert before </main> or </body>
            if '</main>' in content:
                content = content.replace('</main>', f'{new_section}\n</main>')
            elif '</body>' in content:
                content = content.replace('</body>', f'{new_section}\n</body>')
            else:
                return False, "Could not find insertion point"

            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(content)

            return True, f"Added new section: {new_section[:100]}..."

        except Exception as e:
            return False, str(e)

    async def _enhance_content(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Enhance existing content quality."""
        target_file = Path(improvement.get("location", ""))
        description = improvement.get("description", "")
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Use LLM to enhance content
        user_prompt = f"""Enhance the content in this HTML document.

Issue: {description}
Suggestion: {suggestion}

Current HTML:
{content[:4000]}

Return the COMPLETE enhanced HTML document with improved content.
Focus on: better descriptions, clearer explanations, more detail where needed."""

        try:
            enhanced_content = await self._call_llm(
                system_prompt=CONTENT_ENHANCER_SYSTEM_PROMPT,
                user_prompt=user_prompt
            )

            # Validate response is HTML
            if '<html' not in enhanced_content.lower() and '<!doctype' not in enhanced_content.lower():
                # Partial response - try to apply as patch
                return await self._apply_content_patch(target_file, content, enhanced_content)

            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(enhanced_content)

            return True, "Enhanced content quality"

        except Exception as e:
            return False, str(e)

    async def _apply_content_patch(
        self,
        target_file: Path,
        original: str,
        patch: str
    ) -> Tuple[bool, str]:
        """Apply a partial content patch."""
        # Simple approach: find and replace similar content
        # This is a fallback when LLM returns only a snippet
        patch_clean = self._extract_html(patch)
        if not patch_clean:
            return False, "Could not extract HTML from response"

        # Try to identify what to replace
        # Look for a section/div with similar content
        return False, "Partial patch not applied (full HTML expected)"

    async def _fix_structure(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Fix HTML structure issues."""
        target_file = Path(improvement.get("location", ""))
        description = improvement.get("description", "")
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        changes_made = []

        # Apply specific structure fixes based on suggestion
        if "DOCTYPE" in suggestion:
            if not content.strip().startswith('<!DOCTYPE'):
                content = '<!DOCTYPE html>\n' + content
                changes_made.append("Added DOCTYPE")

        if "viewport" in suggestion.lower():
            if 'viewport' not in content.lower():
                # Add viewport meta tag
                viewport_tag = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                if '<head>' in content:
                    content = content.replace('<head>', f'<head>\n    {viewport_tag}')
                    changes_made.append("Added viewport meta tag")

        if "semantic" in suggestion.lower():
            # Add basic semantic structure if missing
            if '<main>' not in content and '<main ' not in content:
                # Wrap content in main tag
                if '<body>' in content:
                    content = self._add_semantic_structure(content)
                    changes_made.append("Added semantic structure")

        if "h1" in suggestion.lower():
            # Check and fix heading hierarchy
            if '<h2' in content and '<h1' not in content:
                # Find first h2 and consider promoting it
                content = content.replace('<h2', '<h1', 1)
                content = content.replace('</h2>', '</h1>', 1)
                changes_made.append("Fixed heading hierarchy")

        if changes_made:
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "; ".join(changes_made)

        return False, "No automatic fix available"

    def _add_semantic_structure(self, content: str) -> str:
        """Add semantic HTML structure to content."""
        # Find body content and wrap in main
        body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_content = body_match.group(1)

            # Check if content already has main
            if '<main>' not in body_content and '<main ' not in body_content:
                # Wrap in main (preserving header/nav/footer if present)
                new_body = body_content

                # Don't wrap header, nav, footer in main
                if '<header' not in body_content:
                    new_body = f'<main>\n{body_content}\n</main>'

                content = content[:body_match.start(1)] + new_body + content[body_match.end(1):]

        return content

    async def _add_styling(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Add or improve CSS styling."""
        target_file = Path(improvement.get("location", ""))
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if there's already a style tag
        if '<style>' in content:
            # Add responsive CSS if missing
            if "responsive" in suggestion.lower() and '@media' not in content:
                responsive_css = """
        @media (max-width: 768px) {
            .container { padding: 0 10px; }
            nav ul { flex-direction: column; }
            .stats-grid { grid-template-columns: 1fr; }
        }
"""
                content = content.replace('</style>', f'{responsive_css}\n</style>')

                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write(content)

                return True, "Added responsive CSS"

        return False, "Styling improvement requires manual review"

    async def _add_navigation(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Add navigation elements."""
        target_file = Path(improvement.get("location", ""))
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if '<nav' in content:
            return False, "Navigation already exists"

        # Find other HTML files for navigation
        output_dir = target_file.parent
        html_files = list(output_dir.glob("*.html"))

        if len(html_files) < 2:
            return False, "Not enough pages for navigation"

        # Build navigation HTML
        nav_items = []
        for html_file in html_files:
            page_name = html_file.stem
            title = page_name.replace("_", " ").title()
            is_current = html_file == target_file
            active_class = 'class="active"' if is_current else ''
            nav_items.append(f'<li><a href="{html_file.name}" {active_class}>{title}</a></li>')

        nav_html = f'''
    <nav>
        <div class="container">
            <ul>
                {chr(10).join(nav_items)}
            </ul>
        </div>
    </nav>
'''

        # Insert after header or at beginning of body
        if '</header>' in content:
            content = content.replace('</header>', f'</header>\n{nav_html}')
        elif '<body>' in content:
            content = content.replace('<body>', f'<body>\n{nav_html}')
        else:
            return False, "Could not find insertion point for navigation"

        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return True, f"Added navigation with {len(html_files)} items"

    async def _fix_accessibility(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Fix accessibility issues."""
        target_file = Path(improvement.get("location", ""))
        description = improvement.get("description", "")
        suggestion = improvement.get("suggestion", "")

        if not target_file.exists():
            return False, f"File not found: {target_file}"

        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()

        changes_made = []

        # Add lang attribute
        if "lang" in suggestion.lower():
            if 'lang=' not in content:
                content = content.replace('<html>', '<html lang="en">')
                content = content.replace('<html ', '<html lang="en" ')
                changes_made.append("Added lang attribute")

        # Add skip link
        if "skip" in suggestion.lower():
            if 'skip' not in content.lower():
                skip_link = '<a href="#main-content" class="skip-link" style="position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;">Skip to main content</a>'

                if '<body>' in content:
                    content = content.replace('<body>', f'<body>\n{skip_link}')
                    changes_made.append("Added skip navigation link")

                # Add id to main content
                if '<main>' in content and 'id=' not in content[content.find('<main>'):content.find('<main>')+50]:
                    content = content.replace('<main>', '<main id="main-content">')

        # Add ARIA landmarks
        if "aria" in suggestion.lower() or "landmark" in suggestion.lower():
            if '<header>' in content and 'role=' not in content[content.find('<header>'):content.find('<header>')+50]:
                content = content.replace('<header>', '<header role="banner">')
                changes_made.append("Added banner role to header")

            if '<nav>' in content and 'role=' not in content[content.find('<nav>'):content.find('<nav>')+50]:
                content = content.replace('<nav>', '<nav role="navigation">')
                changes_made.append("Added navigation role")

            if '<main>' in content and 'role=' not in content[content.find('<main>'):content.find('<main>')+50]:
                content = content.replace('<main', '<main role="main"')
                changes_made.append("Added main role")

            if '<footer>' in content and 'role=' not in content[content.find('<footer>'):content.find('<footer>')+50]:
                content = content.replace('<footer>', '<footer role="contentinfo">')
                changes_made.append("Added contentinfo role to footer")

        if changes_made:
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "; ".join(changes_made)

        return False, "No automatic accessibility fix available"

    async def _merge_content(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Merge duplicate or related content."""
        # This is a complex operation that would typically require
        # analyzing multiple files and making decisions about consolidation
        return False, "Content merging requires manual review"

    async def _generate_diagram(
        self,
        context: PresentationContext,
        improvement: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Generate a missing diagram."""
        # This would delegate to the KiloIntegrationAgent
        return False, "Diagram generation delegated to KiloIntegrationAgent"

    def _extract_html(self, response: str) -> str:
        """Extract HTML from LLM response."""
        # Try to extract HTML code block
        code_match = re.search(r'```html?\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()

        # Try to find HTML tags
        html_match = re.search(r'(<(?:section|div|article|nav|main|header|footer)[^>]*>.*?</(?:section|div|article|nav|main|header|footer)>)', response, re.DOTALL | re.IGNORECASE)
        if html_match:
            return html_match.group(1).strip()

        # Return cleaned response if it looks like HTML
        if '<' in response and '>' in response:
            return response.strip()

        return ""

    def get_applied_improvements(self) -> List[AppliedImprovement]:
        """Get list of applied improvements."""
        return self._applied_improvements
