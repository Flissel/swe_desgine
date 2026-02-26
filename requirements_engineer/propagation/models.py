"""
Data models for the Change Propagation & Auto-Link Discovery System.
"""

from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import uuid


@dataclass_json
@dataclass
class Edge:
    """Represents a relationship between two nodes."""
    source: str
    target: str
    edge_type: str  # "parent", "dependency", "related", "conflict", "epic", "story", "task"
    bidirectional: bool = False

    def __hash__(self):
        return hash((self.source, self.target, self.edge_type))

    def __eq__(self, other):
        if not isinstance(other, Edge):
            return False
        return (self.source == other.source and
                self.target == other.target and
                self.edge_type == other.edge_type)


@dataclass_json
@dataclass
class ChangeInfo:
    """Information about a detected file change."""
    file_path: str
    file_type: str  # "journal", "user_stories", "tasks", "diagram", "test"
    change_type: str  # "modified", "created", "deleted"
    affected_node_ids: List[str] = field(default_factory=list)
    old_content: Optional[str] = None
    new_content: str = ""
    diff_summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def node_id(self) -> Optional[str]:
        """Returns the first affected node ID for convenience."""
        return self.affected_node_ids[0] if self.affected_node_ids else None


@dataclass_json
@dataclass
class PropagationSuggestion:
    """A suggestion to update a linked node after a change."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_node_id: str = ""  # The changed node
    target_node_id: str = ""  # The node to update
    target_file: str = ""  # Path to target file
    link_type: str = ""  # How the nodes are linked
    suggestion_type: str = ""  # "update_description", "update_link", "add_dependency"
    current_content: str = ""
    suggested_content: str = ""
    reasoning: str = ""  # LLM explanation (German)
    confidence: float = 0.0  # 0.0 - 1.0
    status: str = "pending"  # "pending", "approved", "rejected", "applied"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_event_dict(self) -> Dict[str, Any]:
        """Convert to dict for WebSocket event."""
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "link_type": self.link_type,
            "suggestion_type": self.suggestion_type,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "status": self.status,
            "current_content_preview": self.current_content[:200] if self.current_content else "",
            "suggested_content_preview": self.suggested_content[:200] if self.suggested_content else "",
        }


@dataclass_json
@dataclass
class LinkSuggestion:
    """A suggestion to create a link for an orphan node."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    orphan_node_id: str = ""
    orphan_node_title: str = ""
    orphan_node_type: str = ""
    target_node_id: str = ""
    target_node_title: str = ""
    target_node_type: str = ""
    link_type: str = ""  # "dependency", "related", "parent", "child"
    reasoning: str = ""  # LLM explanation
    confidence: float = 0.0  # 0.0 - 1.0
    status: str = "pending"  # "pending", "approved", "rejected", "applied"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_event_dict(self) -> Dict[str, Any]:
        """Convert to dict for WebSocket event."""
        return {
            "id": self.id,
            "orphan_node_id": self.orphan_node_id,
            "orphan_node_title": self.orphan_node_title,
            "orphan_node_type": self.orphan_node_type,
            "target_node_id": self.target_node_id,
            "target_node_title": self.target_node_title,
            "target_node_type": self.target_node_type,
            "link_type": self.link_type,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "status": self.status,
        }


@dataclass_json
@dataclass
class BackupInfo:
    """Information about a backup file."""
    original_path: str
    backup_path: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    size_bytes: int = 0


@dataclass_json
@dataclass
class PropagationAnalysis:
    """LLM analysis result for propagation need."""
    needs_update: bool = False
    reasoning: str = ""
    suggested_changes: str = ""
    confidence: float = 0.0


@dataclass_json
@dataclass
class LinkAnalysis:
    """LLM analysis result for link suggestion."""
    target_id: str = ""
    link_type: str = ""
    reasoning: str = ""
    confidence: float = 0.0
