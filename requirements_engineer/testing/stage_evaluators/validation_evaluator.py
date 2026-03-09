"""
Validation Stage Evaluator (Stage 4).

Evaluates the requirements validation stage:
- Consistency checks
- Feasibility analysis
- Completeness verification
- Quality scoring
"""

from typing import Dict, List, Any
from pathlib import Path
import logging

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig

logger = logging.getLogger(__name__)


class ValidationEvaluator(BaseStageEvaluator):
    """Evaluator for Stage 4: Validation."""

    def __init__(self, config: EvaluatorConfig):
        """Initialize validation evaluator."""
        super().__init__(config)
        self.stage_number = 4
        self.stage_name = "validation"

        # Quality metrics to check
        self.quality_metrics = [
            "completeness_score",
            "consistency_score",
            "testability_score",
            "clarity_score",
            "feasibility_score",
            "traceability_score"
        ]

    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """Setup for validation evaluation."""
        self._project_input = project_input
        self._journal = journal

        if not self.config.use_real_llm:
            self._setup_mocks()

        self._log("Setup complete")

    def execute(self) -> Any:
        """Execute validation stage."""
        self._log("Executing validation stage...")

        if self.config.use_real_llm:
            return self._execute_real()
        else:
            return self._execute_mock()

    def _execute_real(self) -> List[Any]:
        """Execute with real LLM calls."""
        try:
            from omegaconf import OmegaConf
            from requirements_engineer.core.re_agent_manager import REAgentManager

            config = OmegaConf.load(str(Path(__file__).parent.parent.parent / "re_config.yaml"))

            manager = REAgentManager(
                config=config,
                project_input=self._project_input,
                journal=self._journal
            )

            # Run stage 4
            manager._run_stage(4)

            return manager.journal.get_nodes_by_stage(4)

        except Exception as e:
            logger.error(f"Validation execution failed: {e}")
            raise

    def _execute_mock(self) -> List[Any]:
        """Execute with mock responses."""
        mock_validated = [
            {
                "requirement_id": "REQ-001",
                "validation_status": "validated",
                "completeness_score": 0.92,
                "consistency_score": 0.88,
                "testability_score": 0.95,
                "clarity_score": 0.90,
                "feasibility_score": 0.85,
                "traceability_score": 0.87,
                "quality_issues": [],
                "is_valid": True
            },
            {
                "requirement_id": "REQ-002",
                "validation_status": "validated",
                "completeness_score": 0.88,
                "consistency_score": 0.92,
                "testability_score": 0.85,
                "clarity_score": 0.88,
                "feasibility_score": 0.90,
                "traceability_score": 0.82,
                "quality_issues": ["Could improve traceability"],
                "is_valid": True
            },
            {
                "requirement_id": "REQ-003",
                "validation_status": "needs_improvement",
                "completeness_score": 0.75,
                "consistency_score": 0.80,
                "testability_score": 0.70,
                "clarity_score": 0.78,
                "feasibility_score": 0.65,
                "traceability_score": 0.72,
                "quality_issues": ["Low feasibility score", "Needs better testability"],
                "is_valid": False
            }
        ]
        return mock_validated

    def validate_output(self, output: Any) -> Dict[str, float]:
        """Validate validation output."""
        if not output:
            return {"completeness": 0.0, "consistency": 0.0}

        num_requirements = len(output)

        # Aggregate quality scores
        scores = {metric: [] for metric in self.quality_metrics}
        validated_count = 0
        has_issues_documented = 0

        for req in output:
            # Check validation status
            status = req.get("validation_status", "") if isinstance(req, dict) else getattr(req, "validation_status", "")
            if status in ("validated", "needs_improvement"):
                validated_count += 1

            # Collect quality scores
            for metric in self.quality_metrics:
                score = req.get(metric, 0.0) if isinstance(req, dict) else getattr(req, metric, 0.0)
                if score > 0:
                    scores[metric].append(score)

            # Check for documented issues
            issues = req.get("quality_issues", []) if isinstance(req, dict) else getattr(req, "quality_issues", [])
            is_valid = req.get("is_valid", True) if isinstance(req, dict) else getattr(req, "is_valid", True)
            if issues or not is_valid:
                has_issues_documented += 1

        # Calculate averages
        avg_scores = {}
        for metric, values in scores.items():
            if values:
                avg_scores[metric.replace("_score", "")] = sum(values) / len(values)
            else:
                avg_scores[metric.replace("_score", "")] = 0.0

        validation_coverage = validated_count / num_requirements if num_requirements > 0 else 0.0
        issue_documentation = has_issues_documented / num_requirements if num_requirements > 0 else 0.0

        result = {
            "validation_coverage": validation_coverage,
            "issue_documentation": issue_documentation
        }
        result.update(avg_scores)

        return result

    def get_expected_artifacts(self) -> List[str]:
        """Get expected artifacts for validation stage."""
        return [
            "validation_report",
            "quality_scores",
            "consistency_check_results",
            "feasibility_analysis"
        ]
