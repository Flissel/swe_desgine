"""
Requirements Engineering System

A system for automated requirements elicitation, analysis, specification,
and validation using LLM-powered agents and Mermaid diagram generation.

Based on the AI-Scientist-v2 architecture.
"""

__version__ = "0.1.0"
__author__ = "Requirements Engineering System"

from .core.re_journal import RequirementNode, RequirementJournal
from .core.re_metrics import RequirementMetrics
from .core.re_agent_manager import REAgentManager

__all__ = [
    "RequirementNode",
    "RequirementJournal",
    "RequirementMetrics",
    "REAgentManager",
]
