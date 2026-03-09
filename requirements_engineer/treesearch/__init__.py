"""
Tree Search for Requirements Engineering Pipeline.

Applies the AI-Scientist's iterative tree-search approach to documentation
generation. Each epic's trace tree (Epic → Requirement → UserStory → TestCase)
is walked depth-first, with parent-relative evaluation and iterative refinement.
"""

from .trace_node import TraceNode, TraceWalkResult
from .trace_evaluator import TraceEvaluator
from .trace_expander import TraceExpander
from .trace_walker import TraceWalker

__all__ = [
    "TraceNode",
    "TraceWalkResult",
    "TraceEvaluator",
    "TraceExpander",
    "TraceWalker",
]
