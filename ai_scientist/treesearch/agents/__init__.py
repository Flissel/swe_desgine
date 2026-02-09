"""
Magentic-One inspired specialized research agents for AI-Scientist.

This package contains specialized agents that decompose the monolithic
ParallelAgent into focused, reusable components following the Magentic-One
pattern of agent specialization.

Agents:
- BaseResearchAgent: Abstract base class for all research agents
- CoderAgent: Code generation and implementation
- DebuggerAgent: Error analysis and fixing
- AnalystAgent: VLM analysis and metrics interpretation
- TunerAgent: Hyperparameter optimization
- AblationAgent: Ablation study execution
- ReviewerAgent: Stage completion evaluation
"""

from .base_agent import (
    BaseResearchAgent,
    AgentContext,
    AgentResult,
    AgentCapability,
    TaskType,
    ProgressUpdate,
)
from .coder_agent import CoderAgent
from .debugger_agent import DebuggerAgent
from .analyst_agent import AnalystAgent
from .tuner_agent import TunerAgent
from .ablation_agent import AblationAgent
from .reviewer_agent import ReviewerAgent

__all__ = [
    # Base classes
    "BaseResearchAgent",
    "AgentContext",
    "AgentResult",
    "AgentCapability",
    "TaskType",
    "ProgressUpdate",
    # Specialized agents
    "CoderAgent",
    "DebuggerAgent",
    "AnalystAgent",
    "TunerAgent",
    "AblationAgent",
    "ReviewerAgent",
]
