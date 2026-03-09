"""
Wizard Agent Module - AutoGen-powered enrichment for the Requirements Wizard.

Provides agent teams for auto-generating stakeholders, context, requirements,
and constraints with a notification queue for user-in-the-loop decisions.
"""

from .suggestion_queue import (
    WizardSuggestionQueue,
    WizardSuggestion,
    SuggestionType,
    SuggestionStatus,
)

__all__ = [
    "WizardSuggestionQueue",
    "WizardSuggestion",
    "SuggestionType",
    "SuggestionStatus",
]
