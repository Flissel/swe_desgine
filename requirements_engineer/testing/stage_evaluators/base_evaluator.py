"""
Base Stage Evaluator for Requirements Engineering Testing.

Abstract base class for all stage evaluators with:
- Configuration handling
- Timing measurement
- Quality validation
- Error collection

Usage:
    class DiscoveryEvaluator(BaseStageEvaluator):
        def __init__(self, config):
            super().__init__(config)
            self.stage_number = 1
            self.stage_name = "discovery"

        def setup(self, project_input, journal):
            # Setup stage...

        def execute(self):
            # Run stage...

        def validate_output(self, output):
            # Validate and return metrics...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
import time
import logging

from requirements_engineer.training.schemas import StageEvaluationResult, ErrorContext

logger = logging.getLogger(__name__)


@dataclass
class EvaluatorConfig:
    """Configuration for stage evaluators."""

    # LLM mode
    use_real_llm: bool = False               # True = real LLM calls, False = mocks
    mock_responses_path: Optional[str] = None  # Path to mock response files

    # Quality thresholds
    quality_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "min_completeness": 0.8,
        "min_consistency": 0.9,
        "min_testability": 0.75,
        "min_clarity": 0.8,
        "min_feasibility": 0.75,
        "min_traceability": 0.8,
    })

    # Timing
    timeout_seconds: int = 300               # Stage timeout

    # Training data
    collect_training_data: bool = True       # Collect training data during evaluation

    # Output
    output_dir: Optional[str] = None         # Output directory for artifacts

    # Logging
    verbose: bool = False                    # Verbose output


class BaseStageEvaluator(ABC):
    """
    Abstract base class for stage evaluators.

    Each stage (1-5) implements a concrete evaluator.
    """

    def __init__(self, config: EvaluatorConfig):
        """
        Initialize evaluator.

        Args:
            config: Evaluator configuration
        """
        self.config = config
        self.stage_number: int = 0
        self.stage_name: str = ""

        # Internal state
        self._project_input: Optional[Dict[str, Any]] = None
        self._journal: Any = None
        self._errors: List[ErrorContext] = []
        self._start_time: float = 0.0
        self._end_time: float = 0.0

        # Stats
        self._llm_calls: int = 0
        self._tokens_used: int = 0
        self._cost_usd: float = 0.0

    @property
    def duration_ms(self) -> int:
        """Get duration in milliseconds."""
        if self._start_time and self._end_time:
            return int((self._end_time - self._start_time) * 1000)
        return 0

    @abstractmethod
    def setup(self, project_input: Dict[str, Any], journal: Any) -> None:
        """
        Setup before evaluation.

        Args:
            project_input: Project input data
            journal: RequirementJournal instance
        """
        pass

    @abstractmethod
    def execute(self) -> Any:
        """
        Execute the stage.

        Returns:
            Stage output (varies by stage)
        """
        pass

    @abstractmethod
    def validate_output(self, output: Any) -> Dict[str, float]:
        """
        Validate output and return metrics.

        Args:
            output: Stage output

        Returns:
            Dict of metric name to value (0.0 - 1.0)
        """
        pass

    @abstractmethod
    def get_expected_artifacts(self) -> List[str]:
        """
        Get list of expected artifacts.

        Returns:
            List of artifact names
        """
        pass

    def evaluate(
        self,
        project_input: Dict[str, Any],
        journal: Any
    ) -> StageEvaluationResult:
        """
        Main evaluation method.

        Measures time, executes stage, validates output.

        Args:
            project_input: Project input data
            journal: RequirementJournal instance

        Returns:
            StageEvaluationResult with all metrics
        """
        self._start_time = time.time()
        self._errors.clear()

        # Setup
        try:
            self.setup(project_input, journal)
        except Exception as e:
            self._record_error("setup", e)
            return self._create_failed_result(str(e))

        # Execute
        output = None
        success = True
        error_msg = None

        try:
            output = self.execute()
        except Exception as e:
            success = False
            error_msg = str(e)
            self._record_error("execution", e)

        self._end_time = time.time()

        # Validate
        if success and output is not None:
            try:
                metrics = self.validate_output(output)
                passed = self._check_thresholds(metrics)
                quality_score = sum(metrics.values()) / len(metrics) if metrics else 0.0
            except Exception as e:
                success = False
                error_msg = f"Validation error: {e}"
                self._record_error("validation", e)
                metrics = {}
                passed = False
                quality_score = 0.0
        else:
            metrics = {}
            passed = False
            quality_score = 0.0

        # Get artifacts
        try:
            artifacts = self.get_expected_artifacts() if success else []
        except Exception:
            artifacts = []

        # Collect issues
        issues = self._collect_issues(metrics, error_msg)

        return StageEvaluationResult(
            stage_number=self.stage_number,
            stage_name=self.stage_name,
            duration_ms=self.duration_ms,
            metrics=metrics,
            passed=passed,
            quality_score=quality_score,
            issues_found=issues,
            improvements_suggested=[],
            artifacts_generated=artifacts,
            llm_calls=self._llm_calls,
            tokens_used=self._tokens_used,
            cost_usd=self._cost_usd,
            errors=self._errors.copy()
        )

    def _check_thresholds(self, metrics: Dict[str, float]) -> bool:
        """Check if metrics meet thresholds."""
        for metric, value in metrics.items():
            threshold_key = f"min_{metric}"
            threshold = self.config.quality_thresholds.get(threshold_key, 0)
            if value < threshold:
                return False
        return True

    def _collect_issues(
        self,
        metrics: Dict[str, float],
        error_msg: Optional[str]
    ) -> List[str]:
        """Collect issues from metrics and errors."""
        issues = []

        if error_msg:
            issues.append(f"Execution error: {error_msg}")

        for metric, value in metrics.items():
            threshold_key = f"min_{metric}"
            threshold = self.config.quality_thresholds.get(threshold_key, 0)
            if value < threshold:
                issues.append(f"{metric}: {value:.2f} < {threshold:.2f} (threshold)")

        for error in self._errors:
            issues.append(f"[{error.error_type}] {error.exception_message}")

        return issues

    def _record_error(self, step: str, exception: Exception):
        """Record an error."""
        error = ErrorContext.from_exception(
            exception=exception,
            error_type="evaluation",
            stage=self.stage_name,
            step=step,
            component=f"{self.stage_name}_evaluator"
        )
        self._errors.append(error)

    def _create_failed_result(self, error_msg: str) -> StageEvaluationResult:
        """Create a failed evaluation result."""
        self._end_time = time.time()
        return StageEvaluationResult(
            stage_number=self.stage_number,
            stage_name=self.stage_name,
            duration_ms=self.duration_ms,
            metrics={},
            passed=False,
            quality_score=0.0,
            issues_found=[f"Stage failed: {error_msg}"],
            improvements_suggested=[],
            artifacts_generated=[],
            llm_calls=self._llm_calls,
            tokens_used=self._tokens_used,
            cost_usd=self._cost_usd,
            errors=self._errors.copy()
        )

    def _setup_mocks(self):
        """Setup LLM mocks if configured."""
        if not self.config.use_real_llm and self.config.mock_responses_path:
            try:
                from requirements_engineer.testing.mocks.llm_mock import setup_llm_mock
                setup_llm_mock(self.config.mock_responses_path)
            except ImportError:
                logger.warning("LLM mock module not available")

    def _log(self, message: str):
        """Log a message if verbose mode is enabled."""
        if self.config.verbose:
            logger.info(f"[{self.stage_name}] {message}")
