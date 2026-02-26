"""
Specification Stage Evaluator (Stage 3).

Evaluates the requirements specification stage:
- Acceptance criteria formalization
- Mermaid diagram generation
- Work breakdown structure
- Traceability
"""

from typing import Dict, List, Any
from pathlib import Path
import logging

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig

logger = logging.getLogger(__name__)


class SpecificationEvaluator(BaseStageEvaluator):
    """Evaluator for Stage 3: Specification."""

    def __init__(self, config: EvaluatorConfig):
        """Initialize specification evaluator."""
        super().__init__(config)
        self.stage_number = 3
        self.stage_name = "specification"

        # Expected diagram types
        self.expected_diagram_types = [
            "flowchart",
            "sequenceDiagram",
            "classDiagram",
            "erDiagram",
            "stateDiagram",
            "C4Context"
        ]

    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """Setup for specification evaluation."""
        self._project_input = project_input
        self._journal = journal

        if not self.config.use_real_llm:
            self._setup_mocks()

        self._log("Setup complete")

    def execute(self) -> Any:
        """Execute specification stage."""
        self._log("Executing specification stage...")

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

            # Run stage 3
            manager._run_stage(3)

            return manager.journal.get_nodes_by_stage(3)

        except Exception as e:
            logger.error(f"Specification execution failed: {e}")
            raise

    def _execute_mock(self) -> List[Any]:
        """Execute with mock responses."""
        mock_specified = [
            {
                "requirement_id": "REQ-001",
                "title": "User Authentication",
                "acceptance_criteria": [
                    "Given a new user, when they submit registration form, then account is created",
                    "Given a registered user, when they submit valid credentials, then they are logged in"
                ],
                "mermaid_diagrams": {
                    "flowchart": "graph TD\n    A[User] --> B{Has Account?}\n    B -->|No| C[Register]\n    B -->|Yes| D[Login]",
                    "sequenceDiagram": "sequenceDiagram\n    User->>System: Submit credentials\n    System->>Database: Validate\n    Database-->>System: Result\n    System-->>User: Response"
                },
                "work_package": "Authentication",
                "estimated_effort": "Medium"
            },
            {
                "requirement_id": "REQ-002",
                "title": "Product Catalog",
                "acceptance_criteria": [
                    "Given products exist, when user views catalog, then all products are displayed",
                    "Given a product, when user clicks details, then full product info is shown"
                ],
                "mermaid_diagrams": {
                    "erDiagram": "erDiagram\n    PRODUCT ||--o{ CATEGORY : belongs_to\n    PRODUCT {\n        int id\n        string name\n        float price\n    }"
                },
                "work_package": "Catalog",
                "estimated_effort": "Large"
            }
        ]
        return mock_specified

    def validate_output(self, output: Any) -> Dict[str, float]:
        """Validate specification output."""
        if not output:
            return {"completeness": 0.0, "testability": 0.0}

        num_requirements = len(output)

        has_acceptance_criteria = 0
        has_diagrams = 0
        diagram_types_found = set()
        has_work_package = 0

        for req in output:
            # Check acceptance criteria
            criteria = req.get("acceptance_criteria", []) if isinstance(req, dict) else getattr(req, "acceptance_criteria", [])
            if criteria and len(criteria) > 0:
                has_acceptance_criteria += 1

            # Check diagrams
            diagrams = req.get("mermaid_diagrams", {}) if isinstance(req, dict) else getattr(req, "mermaid_diagrams", {})
            if diagrams:
                has_diagrams += 1
                diagram_types_found.update(diagrams.keys())

            # Check work package
            work_package = req.get("work_package", "") if isinstance(req, dict) else getattr(req, "work_package", "")
            if work_package:
                has_work_package += 1

        testability = has_acceptance_criteria / num_requirements if num_requirements > 0 else 0.0
        diagram_coverage = has_diagrams / num_requirements if num_requirements > 0 else 0.0
        diagram_variety = len(diagram_types_found) / len(self.expected_diagram_types)
        work_breakdown = has_work_package / num_requirements if num_requirements > 0 else 0.0

        return {
            "testability": testability,
            "diagram_coverage": diagram_coverage,
            "diagram_variety": min(diagram_variety, 1.0),
            "work_breakdown": work_breakdown,
            "completeness": (testability + diagram_coverage + work_breakdown) / 3
        }

    def get_expected_artifacts(self) -> List[str]:
        """Get expected artifacts for specification stage."""
        return [
            "acceptance_criteria",
            "mermaid_diagrams",
            "work_breakdown_structure",
            "traceability_matrix"
        ]
