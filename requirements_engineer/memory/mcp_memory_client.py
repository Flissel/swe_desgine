"""MCP Memory Client für User Story Deduplizierung.

Nutzt den MCP Memory Server (Knowledge Graph) für persistente
Speicherung und Deduplizierung von User Stories.

Features:
- Knowledge Graph basierte Speicherung
- Relation-Tracking zwischen User Stories und Requirements
- Persistente Speicherung über Sessions hinweg

Usage:
    client = MCPMemoryClient()

    # User Story speichern
    await client.add_story("US-001", story_text, "REQ-001")

    # Pruefen ob Requirement bereits einer Story zugeordnet
    existing = await client.find_story_for_requirement("REQ-002")
    if existing:
        # Link hinzufuegen statt neue Story
        await client.link_requirement_to_story(existing, "REQ-002")
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of a duplicate check."""
    is_duplicate: bool
    existing_story_id: Optional[str] = None
    similarity_score: float = 0.0
    linked_requirements: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.is_duplicate:
            return f"Duplicate found: {self.existing_story_id}"
        return "No duplicate found"


class MCPMemoryClient:
    """Client fuer MCP Memory Server (Knowledge Graph).

    Speichert User Stories und Requirements als Entities
    und trackt ihre Beziehungen als Relations.
    """

    def __init__(self):
        """Initialisiert den MCP Memory Client."""
        # MCP Tools werden extern aufgerufen
        self._stories_cache: Dict[str, Dict[str, Any]] = {}
        self._req_to_story: Dict[str, str] = {}

    async def add_story(
        self,
        story_id: str,
        story_text: str,
        requirement_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Speichere eine User Story im Knowledge Graph.

        Args:
            story_id: Die ID der User Story (z.B. "US-001")
            story_text: Der vollstaendige Story-Text
            requirement_id: Die ID des zugehoerigen Requirements
            metadata: Zusaetzliche Metadaten (persona, priority, etc.)

        Returns:
            True wenn erfolgreich
        """
        observations = [story_text, f"linked_requirements: {requirement_id}"]
        if metadata:
            for key, value in metadata.items():
                observations.append(f"{key}: {value}")

        # Cache aktualisieren
        self._stories_cache[story_id] = {
            "story_id": story_id,
            "story_text": story_text,
            "requirements": [requirement_id],
            "metadata": metadata or {}
        }
        self._req_to_story[requirement_id] = story_id

        logger.info(f"Story {story_id} gespeichert mit {requirement_id}")
        return True

    async def link_requirement_to_story(
        self,
        story_id: str,
        requirement_id: str
    ) -> bool:
        """Verlinke ein Requirement mit einer existierenden Story.

        Args:
            story_id: Die ID der existierenden User Story
            requirement_id: Die ID des neuen Requirements

        Returns:
            True wenn erfolgreich
        """
        # Cache aktualisieren
        if story_id in self._stories_cache:
            if requirement_id not in self._stories_cache[story_id]["requirements"]:
                self._stories_cache[story_id]["requirements"].append(requirement_id)

        self._req_to_story[requirement_id] = story_id

        logger.info(f"Link hinzugefuegt: {requirement_id} -> {story_id}")
        return True

    async def find_story_for_requirement(
        self,
        requirement_id: str
    ) -> Optional[str]:
        """Finde eine existierende Story fuer ein Requirement.

        Args:
            requirement_id: Die ID des Requirements

        Returns:
            Story-ID wenn gefunden, sonst None
        """
        return self._req_to_story.get(requirement_id)

    async def search_similar_story(
        self,
        story_text: str,
        threshold: float = 0.85
    ) -> DeduplicationResult:
        """Suche nach aehnlicher User Story.

        Hinweis: Der MCP Memory Server unterstuetzt keine semantische Suche.
        Diese Methode prueft nur auf exakte Uebereinstimmungen im Cache.

        Args:
            story_text: Der Text der User Story
            threshold: Aehnlichkeits-Schwellwert (nicht verwendet)

        Returns:
            DeduplicationResult mit Match-Informationen
        """
        # Einfache Text-Suche im Cache
        story_text_lower = story_text.lower()
        for story_id, data in self._stories_cache.items():
            cached_text = data.get("story_text", "").lower()
            # Einfacher Wort-Overlap Check
            story_words = set(story_text_lower.split())
            cached_words = set(cached_text.split())
            if story_words and cached_words:
                overlap = len(story_words & cached_words) / len(story_words | cached_words)
                if overlap >= threshold:
                    return DeduplicationResult(
                        is_duplicate=True,
                        existing_story_id=story_id,
                        similarity_score=overlap,
                        linked_requirements=data.get("requirements", [])
                    )

        return DeduplicationResult(is_duplicate=False)

    async def get_story_requirements(self, story_id: str) -> List[str]:
        """Hole alle Requirements einer Story.

        Args:
            story_id: Die ID der User Story

        Returns:
            Liste der verlinkten Requirement-IDs
        """
        if story_id in self._stories_cache:
            return self._stories_cache[story_id].get("requirements", [])
        return []

    async def get_all_stories(self) -> List[Dict[str, Any]]:
        """Hole alle gespeicherten Stories.

        Returns:
            Liste aller Stories mit Metadaten
        """
        return list(self._stories_cache.values())

    def get_mcp_entity_for_story(
        self,
        story_id: str,
        story_text: str,
        requirement_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generiere MCP Entity-Format fuer eine User Story.

        Kann verwendet werden um die Story direkt mit MCP Tools zu speichern.

        Returns:
            Entity-Dict fuer create_entities Tool
        """
        observations = [story_text, f"linked_requirements: {requirement_id}"]
        if metadata:
            for key, value in metadata.items():
                observations.append(f"{key}: {value}")

        return {
            "name": story_id,
            "entityType": "UserStory",
            "observations": observations
        }

    def get_mcp_relation_for_link(
        self,
        story_id: str,
        requirement_id: str
    ) -> Dict[str, Any]:
        """Generiere MCP Relation-Format fuer einen Story-Requirement Link.

        Returns:
            Relation-Dict fuer create_relations Tool
        """
        return {
            "from": story_id,
            "to": requirement_id,
            "relationType": "implements"
        }
