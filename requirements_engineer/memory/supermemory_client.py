"""Supermemory Client für User Story Deduplizierung.

Dieser Client verbindet sich mit Supermemory (https://supermemory.ai) um
User Stories semantisch zu deduplizieren. Bei ähnlichen Stories wird
nur ein Link hinzugefügt statt eine neue Story zu erstellen.

Features:
- User/Agent Management via containerTag
- Semantische Duplikat-Erkennung
- Automatisches Link-Tracking

Usage:
    # Mit automatischem User-Management
    client = SupermemoryClient()

    # Neuen User für neue Generierung anlegen
    user_tag = await client.create_user(project_id="my_project")

    # Oder existierenden User verwenden
    client = SupermemoryClient(container_tag="sw_eng_my_project_user123")

    # Prüfe auf Duplikate
    result = await client.search_similar_story("Als Benutzer möchte ich...")
    if result.is_duplicate:
        await client.update_story_links(result.existing_story_id, "REQ-002", result.linked_requirements)
    else:
        await client.add_story("US-001", story_text, "REQ-001")
"""

import os
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SUPERMEMORY_API = "https://v2.api.supermemory.ai"


@dataclass
class DeduplicationResult:
    """Result of a duplicate check against Supermemory."""
    is_duplicate: bool
    existing_story_id: Optional[str] = None
    similarity_score: float = 0.0
    linked_requirements: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.is_duplicate:
            return f"Duplicate found: {self.existing_story_id} (score: {self.similarity_score:.2%})"
        return f"No duplicate (best score: {self.similarity_score:.2%})"


class SupermemoryClient:
    """Client für Supermemory User Story Memory.

    Verwendet Supermemory als externe Memory für den Software Engineering Agent.
    Speichert User Stories mit ihren Requirement-Links und ermöglicht
    semantische Suche nach Duplikaten.

    Attributes:
        CONTAINER_TAG: Isolierter Memory-Space für User Stories
        SIMILARITY_THRESHOLD: Schwellwert für Duplikat-Erkennung (default: 0.85)
    """

    CONTAINER_TAG = "sw_engineer_user_stories"
    SIMILARITY_THRESHOLD = 0.85

    def __init__(
        self,
        api_key: Optional[str] = None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        container_tag: Optional[str] = None
    ):
        """Initialisiert den Supermemory Client.

        Args:
            api_key: Supermemory API Key (oder aus SUPERMEMORY_API_KEY env var)
            similarity_threshold: Schwellwert für Duplikat-Erkennung (0-1)
            container_tag: Custom Container Tag für Projekt-Isolation
        """
        self.api_key = api_key or os.environ.get("SUPERMEMORY_API_KEY")
        self.similarity_threshold = similarity_threshold
        self.container_tag = container_tag or self.CONTAINER_TAG

        if not self.api_key:
            logger.warning(
                "SUPERMEMORY_API_KEY nicht gesetzt. "
                "Hole einen Key von https://console.supermemory.ai"
            )

        self.headers = {
            "x-api-key": self.api_key or "",
            "Content-Type": "application/json"
        }

        # Import httpx nur wenn benötigt
        self._client = None

    def _get_client(self):
        """Lazy-load httpx client."""
        if self._client is None:
            try:
                import httpx
                self._client = httpx.AsyncClient(timeout=30.0)
            except ImportError:
                raise ImportError(
                    "httpx ist erforderlich für Supermemory. "
                    "Installiere mit: pip install httpx"
                )
        return self._client

    async def search_similar_story(
        self,
        story_text: str,
        top_k: int = 5
    ) -> DeduplicationResult:
        """Suche nach semantisch ähnlicher User Story in Supermemory.

        Args:
            story_text: Der Text der User Story (Persona + Action + Benefit)
            top_k: Anzahl der zu prüfenden Kandidaten

        Returns:
            DeduplicationResult mit Match-Informationen
        """
        if not self.api_key:
            logger.debug("Keine API Key - überspringe Duplikat-Check")
            return DeduplicationResult(is_duplicate=False)

        try:
            client = self._get_client()
            response = await client.post(
                f"{SUPERMEMORY_API}/search",
                headers=self.headers,
                json={
                    "q": story_text,
                    "searchMode": "memories",
                    "containerTag": self.container_tag,
                    "limit": top_k
                }
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                return DeduplicationResult(is_duplicate=False)

            best_match = results[0]
            score = best_match.get("similarity_score", 0) or best_match.get("score", 0)

            if score >= self.similarity_threshold:
                metadata = best_match.get("metadata", {})
                return DeduplicationResult(
                    is_duplicate=True,
                    existing_story_id=metadata.get("story_id"),
                    similarity_score=score,
                    linked_requirements=metadata.get("linked_requirements", [])
                )

            return DeduplicationResult(
                is_duplicate=False,
                existing_story_id=None,
                similarity_score=score,
                linked_requirements=[]
            )

        except Exception as e:
            logger.error(f"Supermemory search error: {e}")
            return DeduplicationResult(is_duplicate=False)

    async def add_story(
        self,
        story_id: str,
        story_text: str,
        requirement_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Speichere eine neue User Story in Supermemory.

        Args:
            story_id: Die ID der User Story (z.B. "US-001")
            story_text: Der vollständige Story-Text
            requirement_id: Die ID des zugehörigen Requirements
            metadata: Zusätzliche Metadaten (optional)

        Returns:
            Die Supermemory Memory-ID oder None bei Fehler
        """
        if not self.api_key:
            logger.debug("Keine API Key - überspringe Story-Speicherung")
            return None

        try:
            client = self._get_client()

            story_metadata = {
                "story_id": story_id,
                "linked_requirements": [requirement_id],
                "type": "user_story",
                **(metadata or {})
            }

            response = await client.post(
                f"{SUPERMEMORY_API}/add",
                headers=self.headers,
                json={
                    "content": story_text,
                    "customId": story_id,  # Ermöglicht idempotente Updates
                    "containerTag": self.container_tag,
                    "metadata": story_metadata
                }
            )
            response.raise_for_status()
            data = response.json()

            memory_id = data.get("id")
            logger.info(f"Story {story_id} in Supermemory gespeichert: {memory_id}")
            return memory_id

        except Exception as e:
            logger.error(f"Supermemory add error: {e}")
            return None

    async def update_story_links(
        self,
        story_id: str,
        new_requirement_id: str,
        existing_links: List[str]
    ) -> bool:
        """Füge einen neuen Requirement-Link zu einer existierenden Story hinzu.

        Args:
            story_id: Die ID der existierenden User Story
            new_requirement_id: Die ID des neuen Requirements
            existing_links: Liste der bereits verlinkten Requirement-IDs

        Returns:
            True wenn erfolgreich, False sonst
        """
        if not self.api_key:
            logger.debug("Keine API Key - überspringe Link-Update")
            return False

        if new_requirement_id in existing_links:
            logger.debug(f"{new_requirement_id} bereits verlinkt mit {story_id}")
            return True

        try:
            client = self._get_client()
            updated_links = existing_links + [new_requirement_id]

            # Mit gleicher customId wird die Memory aktualisiert
            response = await client.post(
                f"{SUPERMEMORY_API}/add",
                headers=self.headers,
                json={
                    "customId": story_id,
                    "containerTag": self.container_tag,
                    "metadata": {
                        "story_id": story_id,
                        "linked_requirements": updated_links,
                        "type": "user_story"
                    }
                }
            )
            response.raise_for_status()

            logger.info(
                f"Link hinzugefügt: {new_requirement_id} → {story_id} "
                f"(total: {len(updated_links)} requirements)"
            )
            return True

        except Exception as e:
            logger.error(f"Supermemory update error: {e}")
            return False

    async def get_story_requirements(self, story_id: str) -> List[str]:
        """Hole alle Requirement-IDs die zu einer User Story verlinkt sind.

        Args:
            story_id: Die ID der User Story

        Returns:
            Liste der verlinkten Requirement-IDs
        """
        result = await self.search_similar_story(story_id, top_k=1)
        return result.linked_requirements if result.existing_story_id == story_id else []

    async def close(self):
        """Schließe den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # User/Agent Management
    # =========================================================================

    @staticmethod
    def generate_user_tag(project_id: Optional[str] = None, user_id: Optional[str] = None) -> str:
        """Generiere einen eindeutigen containerTag für einen neuen User/Agent.

        In Supermemory ist containerTag der isolierte Memory-Space.
        Jeder User/Agent bekommt seinen eigenen Tag.

        Args:
            project_id: Optionale Projekt-ID für Gruppierung
            user_id: Optionale User-ID (wird generiert wenn nicht angegeben)

        Returns:
            Eindeutiger containerTag im Format: sw_eng_{project}_{user}_{timestamp}
        """
        project = project_id or "default"
        user = user_id or str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"sw_eng_{project}_{user}_{timestamp}"

    async def create_user(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Erstelle einen neuen User/Agent mit eigenem Memory-Space.

        Bei neuer Generierung sollte ein neuer User angelegt werden,
        damit die Stories in einem frischen Space gespeichert werden.

        Args:
            project_id: Optionale Projekt-ID
            user_id: Optionale User-ID
            metadata: Zusätzliche User-Metadaten

        Returns:
            Der neue containerTag für diesen User
        """
        new_tag = self.generate_user_tag(project_id, user_id)

        # Registriere den User in Supermemory mit einer Marker-Memory
        if self.api_key:
            try:
                client = self._get_client()
                user_metadata = {
                    "type": "user_registration",
                    "created_at": datetime.now().isoformat(),
                    "project_id": project_id,
                    "user_id": user_id,
                    **(metadata or {})
                }

                await client.post(
                    f"{SUPERMEMORY_API}/add",
                    headers=self.headers,
                    json={
                        "content": f"Software Engineering Agent initialized for project: {project_id or 'default'}",
                        "customId": f"_user_registration_{new_tag}",
                        "containerTag": new_tag,
                        "metadata": user_metadata
                    }
                )
                logger.info(f"Neuer User erstellt: {new_tag}")

            except Exception as e:
                logger.error(f"User creation error: {e}")

        # Update den Client mit dem neuen Tag
        self.container_tag = new_tag
        return new_tag

    def switch_user(self, container_tag: str) -> None:
        """Wechsle zu einem anderen User/Memory-Space.

        Args:
            container_tag: Der containerTag des Ziel-Users
        """
        self.container_tag = container_tag
        logger.info(f"Gewechselt zu User: {container_tag}")

    async def list_user_stories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Liste alle User Stories im aktuellen User-Space.

        Args:
            limit: Maximale Anzahl der Stories

        Returns:
            Liste der Stories mit Metadaten
        """
        if not self.api_key:
            return []

        try:
            client = self._get_client()
            response = await client.post(
                f"{SUPERMEMORY_API}/search",
                headers=self.headers,
                json={
                    "q": "user_story",  # Suche nach allen User Stories
                    "searchMode": "memories",
                    "containerTag": self.container_tag,
                    "limit": limit,
                    "filters": {
                        "type": "user_story"
                    }
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except Exception as e:
            logger.error(f"List stories error: {e}")
            return []
