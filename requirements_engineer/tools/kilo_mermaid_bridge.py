"""
KiloMermaidBridge - Verbindet Kilo Agent Output mit VibeMind DB.

Ermöglicht automatische Persistierung von Mermaid-Diagrammen aus
Kilo Agent Responses direkt in die vibemind.db Datenbank.
"""

import sys
import logging
from typing import Optional, Dict, Any, List

# VibeMind Python-Pfad hinzufügen
VIBEMIND_PATH = r"C:\Users\User\Desktop\Voice_dialog_vibemind\VibeMind-VoiceDialog\python"
if VIBEMIND_PATH not in sys.path:
    sys.path.insert(0, VIBEMIND_PATH)

from .mermaid_output_handler import MermaidOutputHandler

logger = logging.getLogger(__name__)


class KiloMermaidBridge:
    """Verbindet Kilo Agent Output mit VibeMind DB."""

    def __init__(self):
        """Initialisiert die Bridge mit Repository und Handler."""
        self._repo = None
        self.handler = MermaidOutputHandler()
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Stellt sicher, dass das Repository initialisiert ist."""
        if self._initialized:
            return True

        try:
            from data.repository import MermaidDiagramsRepository
            self._repo = MermaidDiagramsRepository()
            self._initialized = True
            return True
        except ImportError as e:
            logger.warning(f"VibeMind repository not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize MermaidDiagramsRepository: {e}")
            return False

    def save_from_kilo_output(
        self,
        response: str,
        title: str,
        source_idea_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Extrahiert Mermaid aus Kilo-Output und speichert in DB.

        Args:
            response: Die Kilo Agent Response
            title: Titel für das Diagramm
            source_idea_id: Optional - Link zur Quell-Idee
            session_id: Optional - Session-ID für Tracking

        Returns:
            diagram_id oder None wenn kein Mermaid gefunden
        """
        if not self._ensure_initialized():
            logger.warning("DB not initialized, skipping persistence")
            return None

        try:
            # 1. Unescape content
            content = self.handler.unescape_content(response)
            content = self.handler.fix_malformed_markdown(content)

            # 2. Extract mermaid block
            diagram_type, mermaid_code = self.handler.extract_mermaid_block(content)

            if not mermaid_code:
                logger.debug("No mermaid block found in response")
                return None

            # 3. Normalize
            mermaid_code = self.handler.normalize_mermaid(mermaid_code)

            # 4. Prepare metadata
            metadata = {
                "generated_by": "kilo_agent",
                "session_id": session_id,
            }

            # 5. Save to DB
            diagram = self._repo.create(
                title=title[:100],  # Titel kürzen falls nötig
                content=mermaid_code,
                diagram_type=diagram_type or "flowchart",
                source_idea_id=source_idea_id,
                metadata=metadata,
            )

            logger.info(f"Mermaid diagram saved with ID: {diagram.id}")
            return diagram.id

        except Exception as e:
            logger.error(f"Error saving mermaid from kilo output: {e}")
            return None

    def update_diagram(
        self,
        diagram_id: str,
        new_content: str,
    ) -> bool:
        """
        Aktualisiert bestehendes Diagram.

        Args:
            diagram_id: ID des zu aktualisierenden Diagramms
            new_content: Neuer Inhalt (kann Markdown oder reines Mermaid sein)

        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self._ensure_initialized():
            return False

        try:
            diagram = self._repo.get(diagram_id)
            if not diagram:
                logger.warning(f"Diagram not found: {diagram_id}")
                return False

            # Unescape if needed
            new_content = self.handler.unescape_content(new_content)
            _, mermaid_code = self.handler.extract_mermaid_block(new_content)

            if mermaid_code:
                diagram.content = self.handler.normalize_mermaid(mermaid_code)
            else:
                # Falls kein Mermaid-Block, verwende den Content direkt
                diagram.content = new_content

            self._repo.update(diagram)
            logger.info(f"Diagram updated: {diagram_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating diagram: {e}")
            return False

    def get_diagram(self, diagram_id: str) -> Optional[Dict[str, Any]]:
        """
        Holt ein Diagramm aus der DB.

        Args:
            diagram_id: ID des Diagramms

        Returns:
            Dictionary mit Diagramm-Daten oder None
        """
        if not self._ensure_initialized():
            return None

        try:
            diagram = self._repo.get(diagram_id)
            if diagram:
                return diagram.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting diagram: {e}")
            return None

    def delete_diagram(self, diagram_id: str) -> bool:
        """
        Löscht ein Diagramm aus der DB.

        Args:
            diagram_id: ID des Diagramms

        Returns:
            True bei Erfolg
        """
        if not self._ensure_initialized():
            return False

        try:
            return self._repo.delete(diagram_id)
        except Exception as e:
            logger.error(f"Error deleting diagram: {e}")
            return False

    def list_diagrams(
        self,
        source_idea_id: Optional[str] = None,
        diagram_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Listet Diagramme mit optionalen Filtern.

        Args:
            source_idea_id: Optional - Filter nach Quell-Idee
            diagram_type: Optional - Filter nach Typ
            limit: Maximale Anzahl der Ergebnisse

        Returns:
            Liste von Diagramm-Dictionaries
        """
        if not self._ensure_initialized():
            return []

        try:
            diagrams = self._repo.list(
                source_idea_id=source_idea_id,
                diagram_type=diagram_type,
                limit=limit,
            )
            return [d.to_dict() for d in diagrams]
        except Exception as e:
            logger.error(f"Error listing diagrams: {e}")
            return []

    def search_diagrams(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Sucht Diagramme nach Titel oder Inhalt.

        Args:
            query: Suchbegriff
            limit: Maximale Anzahl der Ergebnisse

        Returns:
            Liste von passenden Diagramm-Dictionaries
        """
        if not self._ensure_initialized():
            return []

        try:
            diagrams = self._repo.search(query, limit=limit)
            return [d.to_dict() for d in diagrams]
        except Exception as e:
            logger.error(f"Error searching diagrams: {e}")
            return []

    def get_diagram_markdown(self, diagram_id: str) -> Optional[str]:
        """
        Gibt das Diagramm als Markdown zurück.

        Args:
            diagram_id: ID des Diagramms

        Returns:
            Markdown-String oder None
        """
        if not self._ensure_initialized():
            return None

        try:
            diagram = self._repo.get(diagram_id)
            if diagram:
                return diagram.to_markdown()
            return None
        except Exception as e:
            logger.error(f"Error getting diagram markdown: {e}")
            return None

    def is_available(self) -> bool:
        """Prüft ob die Bridge verfügbar ist (DB erreichbar)."""
        return self._ensure_initialized()
