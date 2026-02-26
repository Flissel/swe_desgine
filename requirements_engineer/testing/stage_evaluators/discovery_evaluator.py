"""
Discovery Stage Evaluator (Stage 1).

Evaluates the requirements discovery/elicitation stage:
- Requirements extraction from project input
- Field completeness (title, description, type, priority)
- Quality of extracted requirements
"""

from typing import Dict, List, Any
from pathlib import Path
import logging

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig

logger = logging.getLogger(__name__)


class DiscoveryEvaluator(BaseStageEvaluator):
    """Evaluator for Stage 1: Discovery."""

    def __init__(self, config: EvaluatorConfig):
        """Initialize discovery evaluator."""
        super().__init__(config)
        self.stage_number = 1
        self.stage_name = "discovery"

    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """Setup for discovery evaluation."""
        self._project_input = project_input
        self._journal = journal

        if not self.config.use_real_llm:
            self._setup_mocks()

        self._log("Setup complete")

    def execute(self) -> Any:
        """Execute discovery stage."""
        self._log("Executing discovery stage...")

        if self.config.use_real_llm:
            # Real execution
            return self._execute_real()
        else:
            # Mock execution for testing
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

            # Run only stage 1
            manager._run_stage(1)

            # Update stats
            self._llm_calls = manager.journal.stats.get("llm_calls", 0)
            self._tokens_used = manager.journal.stats.get("tokens_used", 0)
            self._cost_usd = manager.journal.stats.get("cost_usd", 0.0)

            return manager.journal.get_nodes_by_stage(1)

        except Exception as e:
            logger.error(f"Discovery execution failed: {e}")
            raise

    def _execute_mock(self) -> List[Any]:
        """Execute with mock responses."""
        # Return mock requirements for testing
        mock_requirements = [
            {
                "title": "User Authentication",
                "description": "Users must be able to register, login, and manage accounts",
                "type": "functional",
                "priority": "must",
                "rationale": "Core security requirement",
                "source": "Project description",
                "acceptance_criteria": ["User can register", "User can login", "User can logout"]
            },
            {
                "title": "Product Catalog",
                "description": "System must display products with details",
                "type": "functional",
                "priority": "must",
                "rationale": "Core e-commerce functionality",
                "source": "Project features",
                "acceptance_criteria": ["Products are displayed", "Details are visible"]
            },
            {
                "title": "Shopping Cart",
                "description": "Users can add products to cart and manage quantity",
                "type": "functional",
                "priority": "must",
                "rationale": "Core shopping functionality",
                "source": "Project features",
                "acceptance_criteria": ["Add to cart works", "Quantity can be changed"]
            }
        ]
        return mock_requirements

    def validate_output(self, output: Any) -> Dict[str, float]:
        """Validate discovery output."""
        if not output:
            return {"completeness": 0.0, "consistency": 0.0}

        # Count requirements
        num_requirements = len(output)

        # Check for required fields
        required_fields = ["title", "description", "type", "priority"]
        field_scores = []

        for req in output:
            if isinstance(req, dict):
                present = sum(1 for f in required_fields if f in req and req[f])
                field_scores.append(present / len(required_fields))
            else:
                # Object with attributes
                present = sum(1 for f in required_fields if hasattr(req, f) and getattr(req, f))
                field_scores.append(present / len(required_fields))

        # Calculate metrics
        completeness = min(num_requirements / 5, 1.0)  # Expect at least 5
        field_coverage = sum(field_scores) / len(field_scores) if field_scores else 0.0

        # Check for unique types and priorities
        types = set()
        priorities = set()
        for req in output:
            if isinstance(req, dict):
                types.add(req.get("type", ""))
                priorities.add(req.get("priority", ""))
            else:
                types.add(getattr(req, "type", ""))
                priorities.add(getattr(req, "priority", ""))

        diversity = (len(types) + len(priorities)) / 8  # Expect 4 types + 4 priorities max

        return {
            "completeness": completeness,
            "field_coverage": field_coverage,
            "diversity": min(diversity, 1.0),
            "requirement_count": float(num_requirements)
        }

    def get_expected_artifacts(self) -> List[str]:
        """Get expected artifacts for discovery stage."""
        return ["requirements_draft", "stakeholder_list", "initial_scope"]
