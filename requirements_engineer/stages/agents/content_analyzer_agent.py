"""
Content Analyzer Agent for Multi-Agent HTML Generation.

This agent analyzes artifacts from Stages 1-4 (Discovery, Analysis,
Specification, Validation) and prepares structured content summaries
for the HTML generation process.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
)

log = logging.getLogger(__name__)


@dataclass
class ArtifactSummary:
    """Summary of an analyzed artifact."""
    artifact_type: str
    count: int
    items: List[Dict[str, Any]]
    key_themes: List[str]
    complexity_score: float  # 0-1
    completeness_score: float  # 0-1


@dataclass
class ContentAnalysis:
    """Complete content analysis result."""
    project_name: str
    total_artifacts: int
    artifact_summaries: Dict[str, ArtifactSummary]

    # High-level insights
    key_themes: List[str]
    main_requirements: List[str]
    epics_overview: List[Dict[str, str]]

    # Recommendations for HTML structure
    recommended_pages: List[Dict[str, Any]]
    navigation_structure: Dict[str, Any]

    # Statistics
    diagram_count: int
    test_count: int
    stakeholder_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project_name": self.project_name,
            "total_artifacts": self.total_artifacts,
            "artifact_summaries": {
                k: {
                    "type": v.artifact_type,
                    "count": v.count,
                    "items": v.items,
                    "key_themes": v.key_themes,
                    "complexity_score": v.complexity_score,
                    "completeness_score": v.completeness_score
                }
                for k, v in self.artifact_summaries.items()
            },
            "key_themes": self.key_themes,
            "main_requirements": self.main_requirements,
            "epics_overview": self.epics_overview,
            "recommended_pages": self.recommended_pages,
            "navigation_structure": self.navigation_structure,
            "diagram_count": self.diagram_count,
            "test_count": self.test_count,
            "stakeholder_count": self.stakeholder_count
        }


# System prompt for content analysis
CONTENT_ANALYZER_SYSTEM_PROMPT = """You are a Content Analyzer Agent specialized in analyzing
software requirements engineering artifacts. Your role is to:

1. Parse and understand various artifact types (requirements, user stories, epics, diagrams, tests)
2. Identify key themes, patterns, and relationships
3. Assess completeness and complexity
4. Recommend optimal HTML page structure for presentation

You should provide structured analysis that helps the HTML Generator Agent create
well-organized, navigable presentation pages.

Always respond with valid JSON matching the requested schema."""


class ContentAnalyzerAgent(BasePresentationAgent):
    """
    Agent that analyzes artifacts from RE stages 1-4.

    Capabilities:
    - Parse requirements, user stories, epics from JSON/Markdown
    - Extract key themes and relationships
    - Assess artifact completeness and complexity
    - Recommend HTML page structure
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="ContentAnalyzer",
            role=AgentRole.CONTENT_ANALYZER,
            description="Analyzes artifacts from Stages 1-4 for HTML generation",
            capabilities=[
                AgentCapability.ARTIFACT_PARSING,
                AgentCapability.QUALITY_EVALUATION,
            ],
            config=config
        )

        # Analysis cache
        self._analysis_cache: Dict[str, ContentAnalysis] = {}

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Execute content analysis on project artifacts.

        Args:
            context: The presentation context with artifact paths

        Returns:
            AgentResult with analysis data and recommendations
        """
        self._is_running = True
        self._current_context = context

        try:
            self._log_progress(f"Starting content analysis for project: {context.project_id}")

            # Load and parse artifacts
            artifacts = await self._load_artifacts(context)

            # Analyze each artifact type
            summaries = await self._analyze_artifacts(artifacts)

            # Generate recommendations via LLM
            analysis = await self._generate_analysis(context, summaries)

            # Cache the analysis
            self._analysis_cache[context.project_id] = analysis

            # Save analysis to file
            output_path = await self._save_analysis(context, analysis)

            self._log_progress(f"Content analysis complete: {analysis.total_artifacts} artifacts analyzed")

            return AgentResult(
                success=True,
                generated_files=[str(output_path)],
                generated_content=json.dumps(analysis.to_dict(), indent=2),
                action_type="ANALYZE_CONTENT",
                notes=f"Analyzed {analysis.total_artifacts} artifacts, identified {len(analysis.key_themes)} themes",
                recommendations=[
                    f"Recommended {len(analysis.recommended_pages)} pages for HTML generation",
                    f"Found {analysis.diagram_count} diagrams for embedding",
                ],
                suggested_next_agent="HTMLGenerator",
                confidence=0.85,
                needs_review=False,
                stage_complete=False
            )

        except Exception as e:
            self._log_error(f"Content analysis failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="ANALYZE_CONTENT",
                notes=f"Analysis failed: {e}",
                should_replan=True
            )

        finally:
            self._is_running = False

    async def _load_artifacts(self, context: PresentationContext) -> Dict[str, Any]:
        """Load all artifacts from the output directory."""
        artifacts = {
            "requirements": [],
            "user_stories": [],
            "epics": [],
            "diagrams": [],
            "tests": [],
            "personas": [],
            "screens": [],
            "components": [],
            "api_specs": [],
            "tasks": [],
            "validation_reports": []
        }

        output_dir = Path(context.output_dir) if context.output_dir else Path(".")

        # Try to load from standard locations
        artifact_files = {
            "requirements": ["requirements.json", "requirements.md"],
            "user_stories": ["user_stories.json", "stories.json"],
            "epics": ["epics.json"],
            "diagrams": ["diagrams/*.mmd", "diagrams.json"],
            "tests": ["test_cases.json", "tests.json"],
            "personas": ["personas.json", "ux_design.json"],
            "screens": ["screens.json", "ui_design.json"],
            "api_specs": ["api_spec.json", "openapi.json"],
            "tasks": ["tasks.json", "task_breakdown.json"],
            "validation_reports": ["validation_report.json", "validation.json"]
        }

        for artifact_type, file_patterns in artifact_files.items():
            for pattern in file_patterns:
                if "*" in pattern:
                    # Glob pattern
                    for file_path in output_dir.glob(pattern):
                        content = self._load_file(file_path)
                        if content:
                            artifacts[artifact_type].append({
                                "path": str(file_path),
                                "content": content
                            })
                else:
                    file_path = output_dir / pattern
                    if file_path.exists():
                        content = self._load_file(file_path)
                        if content:
                            artifacts[artifact_type].append({
                                "path": str(file_path),
                                "content": content
                            })

        self._log_progress(f"Loaded artifacts: {sum(len(v) for v in artifacts.values())} files")
        return artifacts

    def _load_file(self, file_path: Path) -> Optional[Any]:
        """Load a file and parse if JSON."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if file_path.suffix == '.json':
                return json.loads(content)
            else:
                return content

        except Exception as e:
            log.warning(f"Failed to load {file_path}: {e}")
            return None

    async def _analyze_artifacts(self, artifacts: Dict[str, Any]) -> Dict[str, ArtifactSummary]:
        """Analyze each artifact type and create summaries."""
        summaries = {}

        for artifact_type, items in artifacts.items():
            if not items:
                continue

            # Extract items list
            all_items = []
            for item in items:
                content = item.get("content", {})
                if isinstance(content, list):
                    all_items.extend(content)
                elif isinstance(content, dict):
                    # Handle dict structures (e.g., {"requirements": [...]})
                    for key, value in content.items():
                        if isinstance(value, list):
                            all_items.extend(value)
                        else:
                            all_items.append(value)
                else:
                    all_items.append(content)

            # Calculate basic metrics
            count = len(all_items)
            complexity = self._calculate_complexity(all_items)
            completeness = self._calculate_completeness(all_items, artifact_type)

            # Extract key themes (simple heuristic)
            themes = self._extract_themes(all_items)

            summaries[artifact_type] = ArtifactSummary(
                artifact_type=artifact_type,
                count=count,
                items=all_items[:50],  # Limit to 50 items for memory
                key_themes=themes,
                complexity_score=complexity,
                completeness_score=completeness
            )

        return summaries

    def _calculate_complexity(self, items: List[Any]) -> float:
        """Calculate complexity score based on item structure."""
        if not items:
            return 0.0

        # Simple heuristic: more nested structure = more complex
        total_depth = 0
        for item in items:
            total_depth += self._get_dict_depth(item)

        avg_depth = total_depth / len(items)
        # Normalize to 0-1 scale (assuming max depth of 10)
        return min(avg_depth / 10, 1.0)

    def _get_dict_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate the depth of a nested dictionary."""
        if not isinstance(obj, dict):
            return current_depth
        if not obj:
            return current_depth
        return max(self._get_dict_depth(v, current_depth + 1) for v in obj.values())

    def _calculate_completeness(self, items: List[Any], artifact_type: str) -> float:
        """Calculate completeness score based on required fields."""
        required_fields = {
            "requirements": ["id", "description", "priority"],
            "user_stories": ["id", "title", "acceptance_criteria"],
            "epics": ["id", "name", "description"],
            "tests": ["id", "name", "steps"],
            "personas": ["name", "goals"],
            "screens": ["name", "components"],
            "api_specs": ["endpoint", "method"],
            "tasks": ["id", "name", "status"]
        }

        expected_fields = required_fields.get(artifact_type, ["id"])

        if not items:
            return 0.0

        completeness_scores = []
        for item in items:
            if isinstance(item, dict):
                present = sum(1 for f in expected_fields if f in item)
                completeness_scores.append(present / len(expected_fields))
            else:
                completeness_scores.append(0.5)  # Non-dict items get 50%

        return sum(completeness_scores) / len(completeness_scores)

    def _extract_themes(self, items: List[Any]) -> List[str]:
        """Extract key themes from items using simple keyword analysis."""
        # Simple keyword extraction from text fields
        text_content = []
        for item in items:
            if isinstance(item, dict):
                for key in ["description", "title", "name", "content"]:
                    if key in item and isinstance(item[key], str):
                        text_content.append(item[key])
            elif isinstance(item, str):
                text_content.append(item)

        # Count word frequency (simple approach)
        word_count: Dict[str, int] = {}
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
                      "as", "by", "from", "up", "about", "into", "through", "during",
                      "should", "must", "can", "will", "would", "could", "shall"}

        for text in text_content:
            words = text.lower().split()
            for word in words:
                word = ''.join(c for c in word if c.isalnum())
                if word and len(word) > 3 and word not in stop_words:
                    word_count[word] = word_count.get(word, 0) + 1

        # Get top themes
        sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:10]]

    async def _generate_analysis(
        self,
        context: PresentationContext,
        summaries: Dict[str, ArtifactSummary]
    ) -> ContentAnalysis:
        """Generate complete analysis with LLM assistance."""

        # Build summary for LLM
        summary_text = self._build_summary_text(summaries)

        # Generate page recommendations via LLM
        user_prompt = f"""Analyze the following project artifacts and recommend HTML page structure:

Project: {context.project_id}

{summary_text}

Based on this content, provide:
1. 3-5 key themes for this project
2. Top 5 main requirements (summarized)
3. Recommended pages for HTML presentation (with page name, content type, and priority)
4. Navigation structure

Respond in JSON format:
{{
    "key_themes": ["theme1", "theme2", ...],
    "main_requirements": ["req1", "req2", ...],
    "recommended_pages": [
        {{"name": "page_name", "title": "Page Title", "content_types": ["requirements", "diagrams"], "priority": "high"}},
        ...
    ],
    "navigation_structure": {{
        "main_sections": ["section1", "section2"],
        "sidebar_items": ["item1", "item2"]
    }}
}}"""

        try:
            response = await self._call_llm(
                system_prompt=CONTENT_ANALYZER_SYSTEM_PROMPT,
                user_prompt=user_prompt
            )

            # Parse JSON response
            llm_analysis = json.loads(response)

        except Exception as e:
            log.warning(f"LLM analysis failed, using defaults: {e}")
            llm_analysis = {
                "key_themes": list(set(t for s in summaries.values() for t in s.key_themes[:3])),
                "main_requirements": [],
                "recommended_pages": [
                    {"name": "index", "title": "Overview", "content_types": ["summary"], "priority": "high"},
                    {"name": "requirements", "title": "Requirements", "content_types": ["requirements"], "priority": "high"},
                    {"name": "user_stories", "title": "User Stories", "content_types": ["user_stories"], "priority": "medium"},
                    {"name": "diagrams", "title": "Diagrams", "content_types": ["diagrams"], "priority": "medium"},
                ],
                "navigation_structure": {
                    "main_sections": ["Overview", "Requirements", "User Stories"],
                    "sidebar_items": []
                }
            }

        # Build epics overview
        epics_overview = []
        if "epics" in summaries:
            for epic in summaries["epics"].items[:10]:
                if isinstance(epic, dict):
                    epics_overview.append({
                        "id": epic.get("id", ""),
                        "name": epic.get("name", epic.get("title", "")),
                        "description": epic.get("description", "")[:200]
                    })

        return ContentAnalysis(
            project_name=context.project_id,
            total_artifacts=sum(s.count for s in summaries.values()),
            artifact_summaries=summaries,
            key_themes=llm_analysis.get("key_themes", []),
            main_requirements=llm_analysis.get("main_requirements", []),
            epics_overview=epics_overview,
            recommended_pages=llm_analysis.get("recommended_pages", []),
            navigation_structure=llm_analysis.get("navigation_structure", {}),
            diagram_count=summaries.get("diagrams", ArtifactSummary("diagrams", 0, [], [], 0, 0)).count,
            test_count=summaries.get("tests", ArtifactSummary("tests", 0, [], [], 0, 0)).count,
            stakeholder_count=summaries.get("personas", ArtifactSummary("personas", 0, [], [], 0, 0)).count
        )

    def _build_summary_text(self, summaries: Dict[str, ArtifactSummary]) -> str:
        """Build human-readable summary text for LLM."""
        lines = ["## Artifact Summary\n"]

        for artifact_type, summary in summaries.items():
            lines.append(f"### {artifact_type.replace('_', ' ').title()}")
            lines.append(f"- Count: {summary.count}")
            lines.append(f"- Complexity: {summary.complexity_score:.2f}")
            lines.append(f"- Completeness: {summary.completeness_score:.2f}")
            if summary.key_themes:
                lines.append(f"- Themes: {', '.join(summary.key_themes[:5])}")

            # Sample items
            if summary.items:
                lines.append("- Sample items:")
                for item in summary.items[:3]:
                    if isinstance(item, dict):
                        item_str = item.get("title") or item.get("name") or item.get("id", str(item)[:50])
                        lines.append(f"  - {item_str}")
                    else:
                        lines.append(f"  - {str(item)[:50]}")
            lines.append("")

        return "\n".join(lines)

    async def _save_analysis(self, context: PresentationContext, analysis: ContentAnalysis) -> Path:
        """Save analysis result to JSON file."""
        output_dir = Path(context.output_dir) if context.output_dir else Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "content_analysis.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis.to_dict(), f, indent=2, ensure_ascii=False)

        self._log_progress(f"Saved analysis to {output_path}")
        return output_path

    def get_cached_analysis(self, project_id: str) -> Optional[ContentAnalysis]:
        """Get cached analysis for a project."""
        return self._analysis_cache.get(project_id)
