"""
Analysis Stage Evaluator (Stage 2).

Evaluates the requirements analysis stage:
- Decomposition of requirements
- Classification (functional, non-functional, constraint)
- MoSCoW prioritization
- Dependency identification
"""

from typing import Dict, List, Any
from pathlib import Path
import logging

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig

logger = logging.getLogger(__name__)


class AnalysisEvaluator(BaseStageEvaluator):
    """Evaluator for Stage 2: Analysis."""

    def __init__(self, config: EvaluatorConfig):
        """Initialize analysis evaluator."""
        super().__init__(config)
        self.stage_number = 2
        self.stage_name = "analysis"

    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """Setup for analysis evaluation."""
        self._project_input = project_input
        self._journal = journal

        if not self.config.use_real_llm:
            self._setup_mocks()

        self._log("Setup complete")

    def execute(self) -> Any:
        """Execute analysis stage."""
        self._log("Executing analysis stage...")

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

            # Run stage 2 (assumes stage 1 completed)
            manager._run_stage(2)

            return manager.journal.get_nodes_by_stage(2)

        except Exception as e:
            logger.error(f"Analysis execution failed: {e}")
            raise

    def _execute_mock(self) -> List[Any]:
        """Execute with mock responses."""
        # Return mock analyzed requirements
        mock_analyzed = [
            {
                "requirement_id": "REQ-001",
                "title": "User Authentication",
                "type": "functional",
                "priority": "must",
                "dependencies": [],
                "parent_requirement": None,
                "classification_confidence": 0.95
            },
            {
                "requirement_id": "REQ-002",
                "title": "Product Catalog",
                "type": "functional",
                "priority": "must",
                "dependencies": ["REQ-001"],
                "parent_requirement": None,
                "classification_confidence": 0.92
            },
            {
                "requirement_id": "REQ-003",
                "title": "Performance - Page Load",
                "type": "non_functional",
                "priority": "should",
                "dependencies": [],
                "parent_requirement": None,
                "classification_confidence": 0.88
            }
        ]
        return mock_analyzed

    def validate_output(self, output: Any) -> Dict[str, float]:
        """Validate analysis output."""
        if not output:
            return {"completeness": 0.0, "classification": 0.0}

        num_requirements = len(output)

        # Check classification
        classified = 0
        prioritized = 0
        has_dependencies = 0
        valid_types = {"functional", "non_functional", "constraint", "assumption", "dependency"}
        valid_priorities = {"must", "should", "could", "wont"}

        for req in output:
            req_type = req.get("type", "") if isinstance(req, dict) else getattr(req, "type", "")
            priority = req.get("priority", "") if isinstance(req, dict) else getattr(req, "priority", "")
            deps = req.get("dependencies", []) if isinstance(req, dict) else getattr(req, "dependencies", [])

            if req_type in valid_types:
                classified += 1
            if priority in valid_priorities:
                prioritized += 1
            if deps:
                has_dependencies += 1

        classification = classified / num_requirements if num_requirements > 0 else 0.0
        prioritization = prioritized / num_requirements if num_requirements > 0 else 0.0
        dependency_analysis = has_dependencies / num_requirements if num_requirements > 0 else 0.0

        return {
            "classification": classification,
            "prioritization": prioritization,
            "dependency_analysis": dependency_analysis,
            "completeness": (classification + prioritization) / 2
        }

    def get_expected_artifacts(self) -> List[str]:
        """Get expected artifacts for analysis stage."""
        return ["classified_requirements", "dependency_matrix", "priority_list"]
