"""Stage implementations for Requirements Engineering System."""

# Only import stages that actually exist
from .presentation_stage import PresentationStage, run_presentation_stage

# Placeholder imports for stages that may be implemented later
# from .discovery import DiscoveryStage
# from .analysis import AnalysisStage
# from .specification import SpecificationStage
# from .validation import ValidationStage

__all__ = [
    "PresentationStage",
    "run_presentation_stage",
]
