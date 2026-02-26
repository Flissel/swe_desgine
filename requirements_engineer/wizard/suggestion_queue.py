"""
Wizard Suggestion Queue - Confidence-based routing for agent suggestions.

High-confidence suggestions are auto-applied.
Low-confidence suggestions are queued for user review via WebSocket notifications.
"""

import asyncio
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional


class SuggestionType(Enum):
    """Types of wizard suggestions."""
    STAKEHOLDER = "stakeholder"
    REQUIREMENT = "requirement"
    CONSTRAINT = "constraint"
    CONTEXT = "context"


class SuggestionStatus(Enum):
    """Status of a suggestion."""
    PENDING = "pending"
    AUTO_APPLIED = "auto_applied"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISCARDED = "discarded"


@dataclass
class WizardSuggestion:
    """A single suggestion from an agent team."""
    id: str
    type: SuggestionType
    status: SuggestionStatus
    content: Dict[str, Any]
    confidence: float
    reasoning: str
    source_team: str
    wizard_step: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict for JSON/WebSocket."""
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "content": self.content,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "source_team": self.source_team,
            "wizard_step": self.wizard_step,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

    @staticmethod
    def create(
        suggestion_type: SuggestionType,
        content: Dict[str, Any],
        confidence: float,
        reasoning: str,
        source_team: str,
        wizard_step: int,
    ) -> "WizardSuggestion":
        """Factory method to create a new suggestion."""
        return WizardSuggestion(
            id=uuid.uuid4().hex[:8],
            type=suggestion_type,
            status=SuggestionStatus.PENDING,
            content=content,
            confidence=confidence,
            reasoning=reasoning,
            source_team=source_team,
            wizard_step=wizard_step,
        )


class WizardSuggestionQueue:
    """
    Thread-safe suggestion queue with confidence-based routing.

    Confidence thresholds:
        >= auto_apply_threshold (0.85): Auto-apply without user input
        >= user_review_threshold (0.50): Queue for user review
        < user_review_threshold: Discard silently
    """

    def __init__(self, emitter, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        thresholds = config.get("thresholds", {})
        self._pending: Dict[str, WizardSuggestion] = {}
        self._history: List[WizardSuggestion] = []
        self._lock = asyncio.Lock()
        self._emitter = emitter
        self._auto_apply_threshold = thresholds.get("auto_apply", 0.85)
        self._user_review_threshold = thresholds.get("user_review", 0.50)
        self._max_pending = config.get("queue", {}).get("max_pending", 50)

    async def submit(self, suggestion: WizardSuggestion) -> Dict[str, Any]:
        """
        Submit a suggestion for routing based on confidence.

        Returns dict with: action ("auto_applied"|"pending"|"discarded"), suggestion data
        """
        async with self._lock:
            if suggestion.confidence >= self._auto_apply_threshold:
                suggestion.status = SuggestionStatus.AUTO_APPLIED
                suggestion.resolved_at = datetime.now().isoformat()
                self._history.append(suggestion)

                if self._emitter:
                    await self._emitter.emit_raw(
                        "wizard_suggestion_auto_applied", suggestion.to_dict()
                    )

                return {"action": "auto_applied", "suggestion": suggestion.to_dict()}

            elif suggestion.confidence >= self._user_review_threshold:
                suggestion.status = SuggestionStatus.PENDING
                self._pending[suggestion.id] = suggestion

                # Enforce max pending limit
                if len(self._pending) > self._max_pending:
                    oldest_id = next(iter(self._pending))
                    removed = self._pending.pop(oldest_id)
                    removed.status = SuggestionStatus.DISCARDED
                    self._history.append(removed)

                if self._emitter:
                    await self._emitter.emit_raw(
                        "wizard_suggestion_pending", suggestion.to_dict()
                    )

                return {"action": "pending", "suggestion": suggestion.to_dict()}

            else:
                suggestion.status = SuggestionStatus.DISCARDED
                suggestion.resolved_at = datetime.now().isoformat()
                self._history.append(suggestion)
                return {"action": "discarded", "suggestion": suggestion.to_dict()}

    async def approve(self, suggestion_id: str) -> Optional[WizardSuggestion]:
        """Approve a pending suggestion."""
        async with self._lock:
            suggestion = self._pending.pop(suggestion_id, None)
            if not suggestion:
                return None

            suggestion.status = SuggestionStatus.APPROVED
            suggestion.resolved_at = datetime.now().isoformat()
            self._history.append(suggestion)

            if self._emitter:
                await self._emitter.emit_raw(
                    "wizard_suggestion_approved", suggestion.to_dict()
                )

            return suggestion

    async def reject(self, suggestion_id: str, reason: str = "") -> Optional[WizardSuggestion]:
        """Reject a pending suggestion."""
        async with self._lock:
            suggestion = self._pending.pop(suggestion_id, None)
            if not suggestion:
                return None

            suggestion.status = SuggestionStatus.REJECTED
            suggestion.resolved_at = datetime.now().isoformat()
            self._history.append(suggestion)

            if self._emitter:
                await self._emitter.emit_raw(
                    "wizard_suggestion_rejected",
                    {**suggestion.to_dict(), "reject_reason": reason},
                )

            return suggestion

    def get_pending(self, wizard_step: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all pending suggestions, optionally filtered by step."""
        suggestions = list(self._pending.values())
        if wizard_step is not None:
            suggestions = [s for s in suggestions if s.wizard_step == wizard_step]
        return [s.to_dict() for s in suggestions]

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get resolved suggestion history."""
        return [s.to_dict() for s in self._history[-limit:]]

    @property
    def pending_count(self) -> int:
        return len(self._pending)
