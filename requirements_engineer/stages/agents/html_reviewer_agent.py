"""
HTML Reviewer Agent for Multi-Agent HTML Generation.

This agent evaluates the quality of generated HTML pages and provides
structured feedback with improvement recommendations.
"""

import logging
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
    QualityEvaluation,
    ImprovementItem,
    ImprovementType,
)

log = logging.getLogger(__name__)


@dataclass
class HTMLQualityIssue:
    """Represents a quality issue found in HTML."""
    severity: str  # critical, major, minor
    category: str  # structure, content, styling, navigation, accessibility
    description: str
    location: str  # file path or selector
    suggestion: str
    improvement_type: ImprovementType


@dataclass
class PageReview:
    """Review result for a single page."""
    page_name: str
    file_path: str
    overall_score: float
    criteria_scores: Dict[str, float]
    issues: List[HTMLQualityIssue]
    recommendations: List[str]
    passed: bool


# System prompt for HTML review
HTML_REVIEWER_SYSTEM_PROMPT = """You are an HTML Quality Reviewer Agent specialized in evaluating
software requirements documentation pages. Your role is to:

1. Assess HTML structure and semantic correctness
2. Evaluate content completeness and clarity
3. Check styling consistency and professional appearance
4. Verify navigation and accessibility
5. Identify specific issues with improvement suggestions

Quality Criteria (0.0 - 1.0 scale):
- structure: Proper HTML5 semantic elements, heading hierarchy, valid markup
- content: Completeness, clarity, accuracy of displayed information
- styling: Visual consistency, professional appearance, responsive design
- navigation: Working links, clear navigation, breadcrumbs
- accessibility: ARIA labels, alt texts, keyboard navigation

Provide structured JSON feedback with specific, actionable improvements."""


class SimpleHTMLAnalyzer(HTMLParser):
    """Simple HTML parser for structure analysis."""

    def __init__(self):
        super().__init__()
        self.tags = []
        self.headings = []
        self.links = []
        self.images = []
        self.forms = []
        self.semantic_tags = []
        self.errors = []

        self.semantic_elements = {
            'header', 'nav', 'main', 'article', 'section', 'aside', 'footer',
            'figure', 'figcaption', 'details', 'summary', 'mark', 'time'
        }

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs_dict = dict(attrs)

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.headings.append({'tag': tag, 'attrs': attrs_dict})

        if tag == 'a':
            self.links.append(attrs_dict.get('href', ''))

        if tag == 'img':
            self.images.append({
                'src': attrs_dict.get('src', ''),
                'alt': attrs_dict.get('alt', '')
            })

        if tag == 'form':
            self.forms.append(attrs_dict)

        if tag in self.semantic_elements:
            self.semantic_tags.append(tag)

    def handle_error(self, message):
        self.errors.append(message)


class HTMLReviewerAgent(BasePresentationAgent):
    """
    Agent that reviews HTML quality and provides improvement feedback.

    Capabilities:
    - Analyze HTML structure and semantics
    - Evaluate content quality
    - Check styling consistency
    - Verify accessibility compliance
    - Generate improvement recommendations
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="HTMLReviewer",
            role=AgentRole.HTML_REVIEWER,
            description="Reviews HTML quality and provides structured feedback",
            capabilities=[
                AgentCapability.QUALITY_EVALUATION,
            ],
            config=config
        )

        # Quality aspects with weights
        self.quality_aspects = {
            "structure": 0.25,
            "content": 0.30,
            "styling": 0.15,
            "navigation": 0.15,
            "accessibility": 0.15
        }

        # Review cache
        self._review_cache: Dict[str, PageReview] = {}

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Execute HTML quality review.

        Args:
            context: The presentation context with generated HTML paths

        Returns:
            AgentResult with quality evaluation and improvements
        """
        self._is_running = True
        self._current_context = context

        try:
            self._log_progress(f"Starting HTML review for project: {context.project_id}")

            # Find HTML files to review
            html_files = await self._find_html_files(context)

            if not html_files:
                return AgentResult(
                    success=False,
                    error_message="No HTML files found to review",
                    action_type="REVIEW_HTML",
                    should_replan=True
                )

            # Review each page
            reviews: List[PageReview] = []
            all_issues: List[HTMLQualityIssue] = []

            for html_file in html_files:
                review = await self._review_page(html_file)
                reviews.append(review)
                all_issues.extend(review.issues)
                self._review_cache[review.page_name] = review

            # Calculate overall quality
            overall_score = sum(r.overall_score for r in reviews) / len(reviews)
            criteria_scores = self._aggregate_criteria_scores(reviews)

            # Build quality evaluation
            evaluation = QualityEvaluation(
                overall_score=overall_score,
                criteria_scores=criteria_scores,
                issues=[
                    ImprovementItem(
                        type=issue.improvement_type,
                        severity=issue.severity,
                        target_file=issue.location,
                        description=issue.description,
                        suggested_fix=issue.suggestion
                    )
                    for issue in all_issues
                ],
                recommendations=self._generate_recommendations(reviews),
                passed=overall_score >= context.quality_threshold,
                threshold=context.quality_threshold
            )

            # Save review report
            report_path = await self._save_review_report(context, reviews, evaluation)

            self._log_progress(f"Review complete: {overall_score:.1%} quality score")

            # Determine if improvement is needed
            needs_improvement = not evaluation.passed or len(all_issues) > 0

            return AgentResult(
                success=True,
                generated_files=[str(report_path)],
                quality_score=overall_score,
                quality_issues=[
                    {
                        "severity": issue.severity,
                        "category": issue.category,
                        "description": issue.description,
                        "location": issue.location
                    }
                    for issue in all_issues[:20]  # Limit to top 20
                ],
                improvements_pending=[
                    {
                        "type": issue.improvement_type.value,
                        "severity": issue.severity,
                        "description": issue.description,
                        "suggestion": issue.suggestion
                    }
                    for issue in sorted(all_issues, key=lambda x: {"critical": 0, "major": 1, "minor": 2}.get(x.severity, 3))[:10]
                ],
                action_type="REVIEW_HTML",
                notes=f"Reviewed {len(reviews)} pages, found {len(all_issues)} issues, score: {overall_score:.1%}",
                recommendations=evaluation.recommendations[:5],
                suggested_next_agent="HTMLImprover" if needs_improvement else None,
                confidence=0.85,
                needs_improvement=needs_improvement,
                needs_review=False,
                stage_complete=not needs_improvement
            )

        except Exception as e:
            self._log_error(f"HTML review failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="REVIEW_HTML",
                notes=f"Review failed: {e}",
                should_replan=True
            )

        finally:
            self._is_running = False

    async def _find_html_files(self, context: PresentationContext) -> List[Path]:
        """Find HTML files in the output directory."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        presentation_dir = output_dir / "presentation"

        html_files = []

        if presentation_dir.exists():
            html_files.extend(presentation_dir.glob("*.html"))
        else:
            html_files.extend(output_dir.glob("*.html"))

        return list(html_files)

    async def _review_page(self, html_file: Path) -> PageReview:
        """Review a single HTML page."""
        self._log_progress(f"Reviewing: {html_file.name}")

        # Read HTML content
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Analyze structure
        analyzer = SimpleHTMLAnalyzer()
        try:
            analyzer.feed(html_content)
        except Exception as e:
            log.warning(f"HTML parsing error: {e}")

        # Calculate scores and find issues
        issues = []

        # Structure analysis
        structure_score, structure_issues = self._evaluate_structure(analyzer, html_content, str(html_file))
        issues.extend(structure_issues)

        # Content analysis
        content_score, content_issues = self._evaluate_content(html_content, str(html_file))
        issues.extend(content_issues)

        # Styling analysis
        styling_score, styling_issues = self._evaluate_styling(html_content, str(html_file))
        issues.extend(styling_issues)

        # Navigation analysis
        nav_score, nav_issues = self._evaluate_navigation(analyzer, html_content, str(html_file))
        issues.extend(nav_issues)

        # Accessibility analysis
        access_score, access_issues = self._evaluate_accessibility(analyzer, html_content, str(html_file))
        issues.extend(access_issues)

        criteria_scores = {
            "structure": structure_score,
            "content": content_score,
            "styling": styling_score,
            "navigation": nav_score,
            "accessibility": access_score
        }

        # Calculate weighted overall score
        overall_score = sum(
            criteria_scores[aspect] * weight
            for aspect, weight in self.quality_aspects.items()
        )

        # Generate recommendations based on issues
        recommendations = self._generate_page_recommendations(issues)

        return PageReview(
            page_name=html_file.stem,
            file_path=str(html_file),
            overall_score=overall_score,
            criteria_scores=criteria_scores,
            issues=issues,
            recommendations=recommendations,
            passed=overall_score >= 0.75
        )

    def _evaluate_structure(
        self,
        analyzer: SimpleHTMLAnalyzer,
        html_content: str,
        file_path: str
    ) -> tuple[float, List[HTMLQualityIssue]]:
        """Evaluate HTML structure quality."""
        issues = []
        score = 1.0

        # Check for semantic elements
        semantic_count = len(analyzer.semantic_tags)
        if semantic_count < 3:
            score -= 0.15
            issues.append(HTMLQualityIssue(
                severity="major",
                category="structure",
                description="Insufficient semantic HTML elements",
                location=file_path,
                suggestion="Add semantic elements: header, main, nav, section, article, footer",
                improvement_type=ImprovementType.FIX_STRUCTURE
            ))

        # Check heading hierarchy
        if analyzer.headings:
            heading_levels = [int(h['tag'][1]) for h in analyzer.headings]
            if heading_levels and heading_levels[0] != 1:
                score -= 0.1
                issues.append(HTMLQualityIssue(
                    severity="minor",
                    category="structure",
                    description="Page should start with h1",
                    location=file_path,
                    suggestion="Ensure the page has an h1 heading at the top",
                    improvement_type=ImprovementType.FIX_STRUCTURE
                ))

            # Check for skipped heading levels
            for i in range(1, len(heading_levels)):
                if heading_levels[i] > heading_levels[i-1] + 1:
                    score -= 0.05
                    issues.append(HTMLQualityIssue(
                        severity="minor",
                        category="structure",
                        description=f"Skipped heading level: h{heading_levels[i-1]} to h{heading_levels[i]}",
                        location=file_path,
                        suggestion="Maintain proper heading hierarchy without skipping levels",
                        improvement_type=ImprovementType.FIX_STRUCTURE
                    ))
                    break

        # Check for DOCTYPE
        if not html_content.strip().lower().startswith('<!doctype'):
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="major",
                category="structure",
                description="Missing DOCTYPE declaration",
                location=file_path,
                suggestion="Add <!DOCTYPE html> at the beginning of the file",
                improvement_type=ImprovementType.FIX_STRUCTURE
            ))

        # Check for meta viewport
        if 'viewport' not in html_content.lower():
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="major",
                category="structure",
                description="Missing viewport meta tag",
                location=file_path,
                suggestion="Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
                improvement_type=ImprovementType.FIX_STRUCTURE
            ))

        return max(0.0, score), issues

    def _evaluate_content(
        self,
        html_content: str,
        file_path: str
    ) -> tuple[float, List[HTMLQualityIssue]]:
        """Evaluate content quality."""
        issues = []
        score = 1.0

        # Check for empty or placeholder content
        placeholder_patterns = [
            r'lorem ipsum',
            r'placeholder',
            r'TODO:?',
            r'\[INSERT\s+\w+\s+HERE\]',
            r'content\s+goes\s+here'
        ]

        for pattern in placeholder_patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                score -= 0.2
                issues.append(HTMLQualityIssue(
                    severity="major",
                    category="content",
                    description=f"Found placeholder content: {pattern}",
                    location=file_path,
                    suggestion="Replace placeholder content with actual information",
                    improvement_type=ImprovementType.ENHANCE_CONTENT
                ))

        # Check for title
        if '<title>' not in html_content.lower() or '<title></title>' in html_content.lower():
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="major",
                category="content",
                description="Missing or empty page title",
                location=file_path,
                suggestion="Add a descriptive title to the page",
                improvement_type=ImprovementType.ENHANCE_CONTENT
            ))

        # Check for meta description
        if 'meta name="description"' not in html_content.lower():
            score -= 0.05
            issues.append(HTMLQualityIssue(
                severity="minor",
                category="content",
                description="Missing meta description",
                location=file_path,
                suggestion="Add a meta description for better SEO and accessibility",
                improvement_type=ImprovementType.ENHANCE_CONTENT
            ))

        # Check content length
        # Remove HTML tags to estimate text content
        text_content = re.sub(r'<[^>]+>', '', html_content)
        text_content = re.sub(r'\s+', ' ', text_content).strip()

        if len(text_content) < 200:
            score -= 0.2
            issues.append(HTMLQualityIssue(
                severity="major",
                category="content",
                description="Very little text content on page",
                location=file_path,
                suggestion="Add more descriptive content to the page",
                improvement_type=ImprovementType.ADD_SECTION
            ))

        return max(0.0, score), issues

    def _evaluate_styling(
        self,
        html_content: str,
        file_path: str
    ) -> tuple[float, List[HTMLQualityIssue]]:
        """Evaluate styling quality."""
        issues = []
        score = 1.0

        # Check for CSS presence
        has_css = '<style' in html_content.lower() or 'stylesheet' in html_content.lower()
        if not has_css:
            score -= 0.3
            issues.append(HTMLQualityIssue(
                severity="major",
                category="styling",
                description="No CSS styling found",
                location=file_path,
                suggestion="Add CSS styling for professional appearance",
                improvement_type=ImprovementType.ADD_STYLING
            ))

        # Check for responsive design indicators
        responsive_indicators = ['@media', 'max-width', 'min-width', 'flex', 'grid']
        has_responsive = any(ind in html_content.lower() for ind in responsive_indicators)
        if not has_responsive and has_css:
            score -= 0.15
            issues.append(HTMLQualityIssue(
                severity="minor",
                category="styling",
                description="No responsive design detected",
                location=file_path,
                suggestion="Add media queries or responsive layout for mobile support",
                improvement_type=ImprovementType.ADD_STYLING
            ))

        # Check for inline styles (not recommended)
        inline_style_count = html_content.lower().count('style="')
        if inline_style_count > 10:
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="minor",
                category="styling",
                description=f"Found {inline_style_count} inline styles",
                location=file_path,
                suggestion="Move inline styles to CSS classes for maintainability",
                improvement_type=ImprovementType.ADD_STYLING
            ))

        return max(0.0, score), issues

    def _evaluate_navigation(
        self,
        analyzer: SimpleHTMLAnalyzer,
        html_content: str,
        file_path: str
    ) -> tuple[float, List[HTMLQualityIssue]]:
        """Evaluate navigation quality."""
        issues = []
        score = 1.0

        # Check for navigation element
        if 'nav' not in analyzer.semantic_tags:
            score -= 0.2
            issues.append(HTMLQualityIssue(
                severity="major",
                category="navigation",
                description="No <nav> element found",
                location=file_path,
                suggestion="Add a navigation section with links to other pages",
                improvement_type=ImprovementType.ADD_NAVIGATION
            ))

        # Check for links
        if len(analyzer.links) < 2:
            score -= 0.15
            issues.append(HTMLQualityIssue(
                severity="major",
                category="navigation",
                description="Very few navigation links",
                location=file_path,
                suggestion="Add navigation links to other sections/pages",
                improvement_type=ImprovementType.ADD_NAVIGATION
            ))

        # Check for broken internal links (basic check)
        for link in analyzer.links:
            if link and not link.startswith(('http', '#', 'mailto:', 'tel:')):
                # Internal link - check if it looks valid
                if link.endswith('.html') or link.endswith('/'):
                    pass  # Looks like a valid internal link
                elif not link:
                    score -= 0.05
                    issues.append(HTMLQualityIssue(
                        severity="minor",
                        category="navigation",
                        description=f"Empty href attribute",
                        location=file_path,
                        suggestion="Fix empty link href",
                        improvement_type=ImprovementType.FIX_STRUCTURE
                    ))

        return max(0.0, score), issues

    def _evaluate_accessibility(
        self,
        analyzer: SimpleHTMLAnalyzer,
        html_content: str,
        file_path: str
    ) -> tuple[float, List[HTMLQualityIssue]]:
        """Evaluate accessibility quality."""
        issues = []
        score = 1.0

        # Check for lang attribute
        if 'lang=' not in html_content.lower():
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="major",
                category="accessibility",
                description="Missing lang attribute on html element",
                location=file_path,
                suggestion="Add lang=\"en\" to the <html> tag",
                improvement_type=ImprovementType.FIX_ACCESSIBILITY
            ))

        # Check for image alt texts
        for img in analyzer.images:
            if not img.get('alt'):
                score -= 0.05
                issues.append(HTMLQualityIssue(
                    severity="minor",
                    category="accessibility",
                    description=f"Image missing alt text: {img.get('src', 'unknown')[:50]}",
                    location=file_path,
                    suggestion="Add descriptive alt text to all images",
                    improvement_type=ImprovementType.FIX_ACCESSIBILITY
                ))
                break  # Only report once

        # Check for ARIA landmarks
        has_aria = 'role=' in html_content.lower() or 'aria-' in html_content.lower()
        if not has_aria and len(html_content) > 5000:
            score -= 0.1
            issues.append(HTMLQualityIssue(
                severity="minor",
                category="accessibility",
                description="No ARIA attributes found",
                location=file_path,
                suggestion="Consider adding ARIA landmarks and labels for screen readers",
                improvement_type=ImprovementType.FIX_ACCESSIBILITY
            ))

        # Check for skip link
        if 'skip' not in html_content.lower():
            score -= 0.05
            issues.append(HTMLQualityIssue(
                severity="minor",
                category="accessibility",
                description="No skip navigation link",
                location=file_path,
                suggestion="Add a 'Skip to main content' link for keyboard users",
                improvement_type=ImprovementType.FIX_ACCESSIBILITY
            ))

        return max(0.0, score), issues

    def _aggregate_criteria_scores(self, reviews: List[PageReview]) -> Dict[str, float]:
        """Aggregate criteria scores across all pages."""
        if not reviews:
            return {aspect: 0.0 for aspect in self.quality_aspects}

        aggregated = {}
        for aspect in self.quality_aspects:
            scores = [r.criteria_scores.get(aspect, 0.0) for r in reviews]
            aggregated[aspect] = sum(scores) / len(scores)

        return aggregated

    def _generate_page_recommendations(self, issues: List[HTMLQualityIssue]) -> List[str]:
        """Generate recommendations based on issues."""
        recommendations = []

        # Group by category
        by_category = {}
        for issue in issues:
            if issue.category not in by_category:
                by_category[issue.category] = []
            by_category[issue.category].append(issue)

        # Generate recommendations
        for category, cat_issues in by_category.items():
            critical = [i for i in cat_issues if i.severity == "critical"]
            major = [i for i in cat_issues if i.severity == "major"]

            if critical:
                recommendations.append(f"CRITICAL: Fix {len(critical)} critical {category} issues immediately")
            if major:
                recommendations.append(f"Fix {len(major)} major {category} issues: {major[0].suggestion}")

        return recommendations[:5]

    def _generate_recommendations(self, reviews: List[PageReview]) -> List[str]:
        """Generate overall recommendations."""
        recommendations = []

        # Find lowest scoring aspects
        all_scores = {}
        for review in reviews:
            for aspect, score in review.criteria_scores.items():
                if aspect not in all_scores:
                    all_scores[aspect] = []
                all_scores[aspect].append(score)

        avg_scores = {aspect: sum(scores) / len(scores) for aspect, scores in all_scores.items()}
        sorted_aspects = sorted(avg_scores.items(), key=lambda x: x[1])

        for aspect, score in sorted_aspects[:3]:
            if score < 0.8:
                recommendations.append(f"Improve {aspect}: current score {score:.1%}")

        # Find pages needing most attention
        low_scoring_pages = [r for r in reviews if r.overall_score < 0.7]
        if low_scoring_pages:
            page_names = [r.page_name for r in low_scoring_pages[:3]]
            recommendations.append(f"Focus improvement on: {', '.join(page_names)}")

        return recommendations

    async def _save_review_report(
        self,
        context: PresentationContext,
        reviews: List[PageReview],
        evaluation: QualityEvaluation
    ) -> Path:
        """Save the review report to JSON."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "project_id": context.project_id,
            "reviewed_at": datetime.now().isoformat(),
            "overall_score": evaluation.overall_score,
            "passed": evaluation.passed,
            "threshold": evaluation.threshold,
            "criteria_scores": evaluation.criteria_scores,
            "page_reviews": [
                {
                    "page_name": r.page_name,
                    "file_path": r.file_path,
                    "overall_score": r.overall_score,
                    "criteria_scores": r.criteria_scores,
                    "passed": r.passed,
                    "issues": [
                        {
                            "severity": i.severity,
                            "category": i.category,
                            "description": i.description,
                            "location": i.location,
                            "suggestion": i.suggestion
                        }
                        for i in r.issues
                    ],
                    "recommendations": r.recommendations
                }
                for r in reviews
            ],
            "recommendations": evaluation.recommendations
        }

        report_path = output_dir / "html_review_report.json"

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self._log_progress(f"Saved review report to {report_path}")
        return report_path

    def get_page_review(self, page_name: str) -> Optional[PageReview]:
        """Get cached review for a page."""
        return self._review_cache.get(page_name)
