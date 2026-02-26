"""
Testing Framework for Requirements Engineering System.

Provides:
- Stage evaluators for each of the 5 stages
- Pytest fixtures for testing
- LLM mocking utilities
- Test fixtures with sample projects

Usage:
    from requirements_engineer.testing import (
        DiscoveryEvaluator,
        AnalysisEvaluator,
        SpecificationEvaluator,
        ValidationEvaluator,
        PresentationEvaluator,
        EvaluatorConfig,
    )

    config = EvaluatorConfig(use_real_llm=False)
    evaluator = DiscoveryEvaluator(config)
    result = evaluator.evaluate(project_input, journal)
"""

from .stage_evaluators.base_evaluator import (
    BaseStageEvaluator,
    EvaluatorConfig,
)

__all__ = [
    "BaseStageEvaluator",
    "EvaluatorConfig",
]

# Lazy imports for concrete evaluators
def __getattr__(name):
    if name == "DiscoveryEvaluator":
        from .stage_evaluators.discovery_evaluator import DiscoveryEvaluator
        return DiscoveryEvaluator
    elif name == "AnalysisEvaluator":
        from .stage_evaluators.analysis_evaluator import AnalysisEvaluator
        return AnalysisEvaluator
    elif name == "SpecificationEvaluator":
        from .stage_evaluators.specification_evaluator import SpecificationEvaluator
        return SpecificationEvaluator
    elif name == "ValidationEvaluator":
        from .stage_evaluators.validation_evaluator import ValidationEvaluator
        return ValidationEvaluator
    elif name == "PresentationEvaluator":
        from .stage_evaluators.presentation_evaluator import PresentationEvaluator
        return PresentationEvaluator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
