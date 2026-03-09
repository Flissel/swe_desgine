"""
KiloConversation - Gesprächshistorie für Kilo Agent Sessions.

Ermöglicht Multi-Turn Konversationen für iterative Änderungen
an Mermaid-Diagrammen und anderen Artefakten.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import json


@dataclass
class KiloMessage:
    """Eine einzelne Nachricht in der Konversation."""

    role: str  # "user" oder "agent"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    mermaid_id: Optional[str] = None  # Link zu gespeichertem Mermaid
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Nachricht in ein Dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "mermaid_id": self.mermaid_id,
            "metadata": self.metadata,
        }


@dataclass
class KiloConversation:
    """Verwaltet Gesprächshistorie für Kilo Agent Sessions."""

    session_id: str
    messages: List[KiloMessage] = field(default_factory=list)
    current_mermaid_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Fügt eine Benutzer-Nachricht hinzu."""
        msg = KiloMessage(
            role="user",
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)

    def add_agent_response(
        self,
        content: str,
        mermaid_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Fügt eine Agent-Antwort hinzu."""
        msg = KiloMessage(
            role="agent",
            content=content,
            mermaid_id=mermaid_id,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        if mermaid_id:
            self.current_mermaid_id = mermaid_id

    def get_context(self, max_messages: int = 10) -> str:
        """
        Baut Kontext-String für den Agent aus den letzten Nachrichten.

        Args:
            max_messages: Maximale Anzahl der Nachrichten im Kontext

        Returns:
            Formatierter Kontext-String
        """
        if not self.messages:
            return ""

        context_parts = []
        for msg in self.messages[-max_messages:]:
            prefix = "Benutzer: " if msg.role == "user" else "Agent: "
            # Kürze sehr lange Nachrichten
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            context_parts.append(f"{prefix}{content}")

        return "\n---\n".join(context_parts)

    def get_last_mermaid_id(self) -> Optional[str]:
        """Gibt die ID des letzten Mermaid-Diagramms zurück."""
        for msg in reversed(self.messages):
            if msg.mermaid_id:
                return msg.mermaid_id
        return self.current_mermaid_id

    def get_message_count(self) -> int:
        """Gibt die Anzahl der Nachrichten zurück."""
        return len(self.messages)

    def clear(self):
        """Löscht alle Nachrichten."""
        self.messages.clear()
        self.current_mermaid_id = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert die Konversation in ein Dictionary."""
        return {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "current_mermaid_id": self.current_mermaid_id,
            "created_at": self.created_at.isoformat(),
            "message_count": len(self.messages),
        }

    def to_json(self) -> str:
        """Serialisiert die Konversation als JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KiloConversation":
        """Erstellt eine Konversation aus einem Dictionary."""
        conv = cls(session_id=data["session_id"])
        conv.current_mermaid_id = data.get("current_mermaid_id")

        if "created_at" in data:
            conv.created_at = datetime.fromisoformat(data["created_at"])

        for msg_data in data.get("messages", []):
            msg = KiloMessage(
                role=msg_data["role"],
                content=msg_data["content"],
                timestamp=datetime.fromisoformat(msg_data.get("timestamp", datetime.now().isoformat())),
                mermaid_id=msg_data.get("mermaid_id"),
                metadata=msg_data.get("metadata", {}),
            )
            conv.messages.append(msg)

        return conv


class KiloConversationManager:
    """Verwaltet aktive Kilo Sessions."""

    def __init__(self):
        self.sessions: Dict[str, KiloConversation] = {}

    def get_or_create(self, session_id: str) -> KiloConversation:
        """
        Gibt eine bestehende Session zurück oder erstellt eine neue.

        Args:
            session_id: ID der Session

        Returns:
            KiloConversation Instanz
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = KiloConversation(session_id=session_id)
        return self.sessions[session_id]

    def get(self, session_id: str) -> Optional[KiloConversation]:
        """Gibt eine Session zurück, falls vorhanden."""
        return self.sessions.get(session_id)

    def get_current_mermaid(self, session_id: str) -> Optional[str]:
        """Gibt die aktuelle Mermaid-ID einer Session zurück."""
        if session_id in self.sessions:
            return self.sessions[session_id].current_mermaid_id
        return None

    def delete(self, session_id: str) -> bool:
        """Löscht eine Session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[str]:
        """Gibt alle aktiven Session-IDs zurück."""
        return list(self.sessions.keys())

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Gibt Informationen über eine Session zurück."""
        conv = self.sessions.get(session_id)
        if conv:
            return {
                "session_id": session_id,
                "message_count": conv.get_message_count(),
                "current_mermaid_id": conv.current_mermaid_id,
                "created_at": conv.created_at.isoformat(),
            }
        return None

    def clear_all(self):
        """Löscht alle Sessions."""
        self.sessions.clear()

    def export_session(self, session_id: str) -> Optional[str]:
        """Exportiert eine Session als JSON."""
        conv = self.sessions.get(session_id)
        if conv:
            return conv.to_json()
        return None

    def import_session(self, json_data: str) -> Optional[str]:
        """
        Importiert eine Session aus JSON.

        Returns:
            Session-ID oder None bei Fehler
        """
        try:
            data = json.loads(json_data)
            conv = KiloConversation.from_dict(data)
            self.sessions[conv.session_id] = conv
            return conv.session_id
        except (json.JSONDecodeError, KeyError):
            return None
