"""
Stage Evaluators for Requirements Engineering.

Each stage (1-5) has a dedicated evaluator that:
- Runs the stage logic
- Validates output quality
- Measures timing
- Reports metrics

Available Evaluators:
- DiscoveryEvaluator (Stage 1)
- AnalysisEvaluator (Stage 2)
- SpecificationEvaluator (Stage 3)
- ValidationEvaluator (Stage 4)
- PresentationEvaluator (Stage 5)
"""

from .base_evaluator import BaseStageEvaluator, EvaluatorConfig
from .discovery_evaluator import DiscoveryEvaluator
from .analysis_evaluator import AnalysisEvaluator
from .specification_evaluator import SpecificationEvaluator
from .validation_evaluator import ValidationEvaluator
from .presentation_evaluator import PresentationEvaluator

__all__ = [
    "BaseStageEvaluator",
    "EvaluatorConfig",
    "DiscoveryEvaluator",
    "AnalysisEvaluator",
    "SpecificationEvaluator",
    "ValidationEvaluator",
    "PresentationEvaluator",
]
