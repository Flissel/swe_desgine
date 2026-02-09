"""Mermaid diagram generators for Requirements Engineering System."""

# Kilo-based generator (primary method)
from .kilo_diagram_generator import KiloDiagramGenerator, DIAGRAM_PROMPTS

# Legacy generators (optional, may not be implemented yet)
try:
    from .flowchart_generator import FlowchartGenerator
    from .sequence_generator import SequenceGenerator
    from .class_generator import ClassGenerator
    from .er_generator import ERGenerator
    from .state_generator import StateGenerator
    from .c4_generator import C4Generator
    from .diagram_manager import DiagramManager
    _LEGACY_AVAILABLE = True
except ImportError:
    # Legacy generators not yet implemented
    FlowchartGenerator = None
    SequenceGenerator = None
    ClassGenerator = None
    ERGenerator = None
    StateGenerator = None
    C4Generator = None
    DiagramManager = None
    _LEGACY_AVAILABLE = False

__all__ = [
    "KiloDiagramGenerator",
    "DIAGRAM_PROMPTS",
]

# Add legacy exports if available
if _LEGACY_AVAILABLE:
    __all__.extend([
        "FlowchartGenerator",
        "SequenceGenerator",
        "ClassGenerator",
        "ERGenerator",
        "StateGenerator",
        "C4Generator",
        "DiagramManager",
    ])
