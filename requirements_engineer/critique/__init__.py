"""
Self-Critique Module for Requirements Engineering.

Provides automated LLM-based review of generated artifacts.
"""

from .self_critique import SelfCritiqueEngine, CritiqueResult, CritiqueIssue

__all__ = ["SelfCritiqueEngine", "CritiqueResult", "CritiqueIssue"]
