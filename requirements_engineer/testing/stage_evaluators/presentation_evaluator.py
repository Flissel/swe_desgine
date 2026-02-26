"""
Presentation Stage Evaluator (Stage 5).

Evaluates the presentation/HTML generation stage:
- HTML page generation
- Content quality
- Navigation structure
- Accessibility
- Mermaid diagram rendering
"""

from typing import Dict, List, Any
import logging
from pathlib import Path

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig

logger = logging.getLogger(__name__)


class PresentationEvaluator(BaseStageEvaluator):
    """Evaluator for Stage 5: Presentation."""

    def __init__(self, config: EvaluatorConfig):
        """Initialize presentation evaluator."""
        super().__init__(config)
        self.stage_number = 5
        self.stage_name = "presentation"

        # Expected pages
        self.expected_pages = [
            "index.html",
            "requirements.html",
            "diagrams.html",
            "test_cases.html"
        ]

    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """Setup for presentation evaluation."""
        self._project_input = project_input
        self._journal = journal

        if not self.config.use_real_llm:
            self._setup_mocks()

        self._log("Setup complete")

    def execute(self) -> Any:
        """Execute presentation stage."""
        self._log("Executing presentation stage...")

        if self.config.use_real_llm:
            return self._execute_real()
        else:
            return self._execute_mock()

    def _execute_real(self) -> Dict[str, Any]:
        """Execute with real LLM calls."""
        try:
            from requirements_engineer.stages.presentation_stage import PresentationStage
            from omegaconf import OmegaConf

            config = OmegaConf.load(str(Path(__file__).parent.parent.parent / "re_config.yaml"))
            config_dict = OmegaConf.to_container(config, resolve=True)

            project_id = self._project_input.get("id", "test_project")
            project_dir = Path(config.get("workspace_dir", "enterprise_output")) / project_id
            output_dir = project_dir / "presentation"

            stage = PresentationStage(
                project_id=project_id,
                project_dir=project_dir,
                output_dir=output_dir,
                config=config_dict
            )

            import asyncio
            result = asyncio.run(stage.run())

            return result

        except Exception as e:
            logger.error(f"Presentation execution failed: {e}")
            raise

    def _execute_mock(self) -> Dict[str, Any]:
        """Execute with mock responses."""
        mock_result = {
            "pages": [
                {
                    "name": "index.html",
                    "title": "Project Overview",
                    "content_length": 5000,
                    "has_navigation": True,
                    "has_mermaid": True,
                    "accessibility_score": 0.85
                },
                {
                    "name": "requirements.html",
                    "title": "Requirements Documentation",
                    "content_length": 8000,
                    "has_navigation": True,
                    "has_mermaid": False,
                    "accessibility_score": 0.82
                },
                {
                    "name": "diagrams.html",
                    "title": "System Diagrams",
                    "content_length": 4000,
                    "has_navigation": True,
                    "has_mermaid": True,
                    "accessibility_score": 0.78
                },
                {
                    "name": "test_cases.html",
                    "title": "Test Cases",
                    "content_length": 6000,
                    "has_navigation": True,
                    "has_mermaid": False,
                    "accessibility_score": 0.80
                }
            ],
            "total_pages": 4,
            "quality_score": 0.85,
            "iterations": 2,
            "success": True
        }
        return mock_result

    def validate_output(self, output: Any) -> Dict[str, float]:
        """Validate presentation output."""
        if not output:
            return {"completeness": 0.0, "quality": 0.0}

        pages = output.get("pages", [])
        num_pages = len(pages)

        if num_pages == 0:
            return {"completeness": 0.0, "quality": 0.0}

        # Check page coverage
        page_names = {p.get("name", "") for p in pages}
        expected_coverage = len(page_names.intersection(set(self.expected_pages))) / len(self.expected_pages)

        # Check navigation
        has_navigation = sum(1 for p in pages if p.get("has_navigation", False)) / num_pages

        # Check content quality
        avg_content_length = sum(p.get("content_length", 0) for p in pages) / num_pages
        content_quality = min(avg_content_length / 3000, 1.0)  # Expect ~3000 chars per page

        # Check mermaid integration
        has_mermaid = sum(1 for p in pages if p.get("has_mermaid", False)) / num_pages

        # Check accessibility
        accessibility_scores = [p.get("accessibility_score", 0.0) for p in pages]
        avg_accessibility = sum(accessibility_scores) / len(accessibility_scores) if accessibility_scores else 0.0

        # Overall quality from output
        reported_quality = output.get("quality_score", 0.0)

        return {
            "page_coverage": expected_coverage,
            "navigation": has_navigation,
            "content_quality": content_quality,
            "mermaid_integration": has_mermaid,
            "accessibility": avg_accessibility,
            "reported_quality": reported_quality,
            "completeness": (expected_coverage + has_navigation + content_quality) / 3
        }

    def get_expected_artifacts(self) -> List[str]:
        """Get expected artifacts for presentation stage."""
        return self.expected_pages + [
            "styles.css",
            "navigation.json",
            "assets/"
        ]
