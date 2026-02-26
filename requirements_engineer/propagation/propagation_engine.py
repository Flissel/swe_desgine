"""
Propagation Engine - Orchestrates the change propagation workflow.

Main orchestrator that ties together file watching, change detection,
link graph traversal, LLM analysis, and suggestion management.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import uuid

from .models import ChangeInfo, PropagationSuggestion
from .link_graph import LinkGraph
from .change_detector import ChangeDetector
from .llm_analyzer import LLMAnalyzer
from .backup_manager import BackupManager
from .file_watcher import AsyncFileWatcher


class PropagationEngine:
    """
    Main orchestrator for change propagation.

    Workflow:
    1. FileWatcher detects file change
    2. ChangeDetector identifies affected nodes
    3. LinkGraph finds linked nodes
    4. LLMAnalyzer determines if updates are needed
    5. Suggestions are generated and stored
    6. User approves/rejects suggestions
    7. BackupManager creates backups before applying changes
    """

    def __init__(
        self,
        project_path: Path,
        event_callback: Optional[Callable[[str, dict], Any]] = None,
        llm_model: str = None
    ):
        """
        Initialize the propagation engine.

        Args:
            project_path: Path to the project directory
            event_callback: Async callback for emitting events (event_type, data)
            llm_model: LLM model to use (default: from env)
        """
        self.project_path = Path(project_path)
        self.event_callback = event_callback

        # Initialize components
        self.link_graph = LinkGraph()
        self.change_detector = ChangeDetector(project_path)
        self.llm_analyzer = LLMAnalyzer(model=llm_model)
        self.backup_manager = BackupManager(project_path)
        self.file_watcher: Optional[AsyncFileWatcher] = None

        # Suggestion storage
        self.pending_suggestions: Dict[str, PropagationSuggestion] = {}

        # Configuration
        self.max_propagation_depth = 2
        self.min_confidence_threshold = 0.3
        self.auto_approve_threshold = 0.9  # Not used currently, all require manual approval

        # Processing state
        self._is_processing = False
        self._processing_lock = asyncio.Lock()

    async def initialize(self):
        """
        Initialize the engine: build link graph, cache files, start watcher.
        """
        # Build link graph from project
        self.link_graph.build_from_project(self.project_path)

        # Cache all watched files
        await self._cache_watched_files()

        # Log statistics
        stats = self.link_graph.get_statistics()
        print(f"[PropagationEngine] Initialized with {stats['total_nodes']} nodes, {stats['total_edges']} edges")

        await self._emit_event("propagation_initialized", stats)

    async def _cache_watched_files(self):
        """Cache content of all watched files."""
        watched_files = [
            self.project_path / "journal.json",
            self.project_path / "user_stories" / "user_stories.md",
            self.project_path / "tasks" / "task_list.json",
        ]

        for file_path in watched_files:
            if file_path.exists():
                self.change_detector.cache_file(str(file_path))

        # Cache diagram files
        diagrams_path = self.project_path / "diagrams"
        if diagrams_path.exists():
            for diagram_file in diagrams_path.glob("*.mmd"):
                self.change_detector.cache_file(str(diagram_file))

    async def start_watching(self):
        """Start file watching."""
        if self.file_watcher:
            return

        self.file_watcher = AsyncFileWatcher(self.project_path)
        self.file_watcher.add_callback(self._on_file_change)
        await self.file_watcher.start()

        await self._emit_event("file_watching_started", {"project": str(self.project_path)})

    async def stop_watching(self):
        """Stop file watching."""
        if self.file_watcher:
            await self.file_watcher.stop()
            self.file_watcher = None

        await self._emit_event("file_watching_stopped", {})

    async def _on_file_change(self, event_type: str, file_path: str):
        """
        Handle a file change event.

        Args:
            event_type: Type of change (modified, created, deleted)
            file_path: Path to the changed file
        """
        async with self._processing_lock:
            if self._is_processing:
                return

            self._is_processing = True

        try:
            # Detect change
            change = self.change_detector.detect_change(file_path)

            if not change.affected_node_ids:
                return

            # Emit file changed event
            await self._emit_event("file_changed", {
                "file_path": change.file_path,
                "file_type": change.file_type,
                "change_type": change.change_type,
                "affected_nodes": change.affected_node_ids,
                "diff_summary": change.diff_summary
            })

            # Process change
            suggestions = await self.process_change(change)

            # Emit suggestions
            for suggestion in suggestions:
                await self._emit_event("propagation_suggestion", suggestion.to_event_dict())

        except Exception as e:
            print(f"[PropagationEngine] Error processing change: {e}")
            await self._emit_event("propagation_error", {"error": str(e)})

        finally:
            self._is_processing = False

    async def process_change(self, change: ChangeInfo) -> List[PropagationSuggestion]:
        """
        Process a file change and generate propagation suggestions.

        Args:
            change: Information about the change

        Returns:
            List of generated suggestions
        """
        suggestions = []

        # Rebuild link graph to include any new nodes
        self.link_graph.build_from_project(self.project_path)

        for node_id in change.affected_node_ids:
            # Find linked nodes
            linked_nodes = self.link_graph.get_linked_nodes(
                node_id,
                depth=self.max_propagation_depth
            )

            # Get changed node data
            changed_node = self.link_graph.get_node(node_id) or {"id": node_id}

            # Analyze each linked node
            for linked_id in linked_nodes:
                linked_node = self.link_graph.get_node(linked_id)
                if not linked_node:
                    continue

                link_type = self.link_graph.get_link_type(node_id, linked_id) or "unknown"

                # LLM analysis
                analysis = await self.llm_analyzer.analyze_propagation_need(
                    changed_node=changed_node,
                    linked_node=linked_node,
                    link_type=link_type,
                    change_summary=change.diff_summary
                )

                # Create suggestion if update needed
                if analysis.needs_update and analysis.confidence >= self.min_confidence_threshold:
                    suggestion = PropagationSuggestion(
                        id=uuid.uuid4().hex,
                        source_node_id=node_id,
                        target_node_id=linked_id,
                        target_file=self._get_node_file(linked_id),
                        link_type=link_type,
                        suggestion_type="update",
                        current_content=self._get_node_content(linked_node),
                        suggested_content=analysis.suggested_changes,
                        reasoning=analysis.reasoning,
                        confidence=analysis.confidence,
                        status="pending"
                    )

                    self.pending_suggestions[suggestion.id] = suggestion
                    suggestions.append(suggestion)

        return suggestions

    def _get_node_file(self, node_id: str) -> str:
        """Determine which file contains a node."""
        node = self.link_graph.get_node(node_id)
        if not node:
            return ""

        node_type = node.get("type", "")

        if node_type == "diagram":
            return node.get("file", "")
        elif node_type in ["epic", "user_story"]:
            return str(self.project_path / "user_stories" / "user_stories.md")
        elif node_type == "task":
            return str(self.project_path / "tasks" / "task_list.json")
        else:
            return str(self.project_path / "journal.json")

    def _get_node_content(self, node: dict) -> str:
        """Get human-readable content from a node."""
        content_parts = []

        if node.get("title"):
            content_parts.append(f"Titel: {node['title']}")

        if node.get("description"):
            content_parts.append(f"Beschreibung: {node['description'][:500]}")

        if node.get("acceptance_criteria"):
            criteria = node["acceptance_criteria"]
            if isinstance(criteria, list):
                content_parts.append("Akzeptanzkriterien: " + ", ".join(criteria[:5]))

        return "\n".join(content_parts)

    async def apply_suggestion(self, suggestion_id: str) -> bool:
        """
        Apply an approved suggestion.

        Args:
            suggestion_id: ID of the suggestion to apply

        Returns:
            True if successful
        """
        suggestion = self.pending_suggestions.get(suggestion_id)
        if not suggestion:
            return False

        if suggestion.status != "pending":
            return False

        try:
            # Create backup
            if suggestion.target_file:
                self.backup_manager.create_backup(Path(suggestion.target_file))

            # Apply the change based on file type
            success = await self._apply_change(suggestion)

            if success:
                suggestion.status = "applied"
                await self._emit_event("propagation_applied", {
                    "id": suggestion_id,
                    "target_node_id": suggestion.target_node_id
                })
            else:
                suggestion.status = "failed"

            return success

        except Exception as e:
            print(f"[PropagationEngine] Error applying suggestion: {e}")
            suggestion.status = "failed"
            return False

    async def _apply_change(self, suggestion: PropagationSuggestion) -> bool:
        """Apply a change to the target file."""
        # For now, we just mark it as applied
        # The actual file modification would depend on the file type
        # and would need careful implementation to avoid corruption

        # This is a placeholder - in production, you'd want to:
        # 1. For JSON files: Parse, update the specific node, write back
        # 2. For Markdown files: Find and replace the relevant section
        # 3. For diagrams: Update the Mermaid code

        print(f"[PropagationEngine] Would apply change to {suggestion.target_node_id}")
        print(f"  Suggested: {suggestion.suggested_changes[:200]}...")

        return True

    async def reject_suggestion(self, suggestion_id: str) -> bool:
        """
        Reject a suggestion.

        Args:
            suggestion_id: ID of the suggestion to reject

        Returns:
            True if successful
        """
        suggestion = self.pending_suggestions.get(suggestion_id)
        if not suggestion:
            return False

        suggestion.status = "rejected"

        await self._emit_event("propagation_rejected", {
            "id": suggestion_id,
            "target_node_id": suggestion.target_node_id
        })

        return True

    def get_pending_suggestions(self) -> List[PropagationSuggestion]:
        """Get all pending suggestions."""
        return [
            s for s in self.pending_suggestions.values()
            if s.status == "pending"
        ]

    def get_suggestion(self, suggestion_id: str) -> Optional[PropagationSuggestion]:
        """Get a specific suggestion by ID."""
        return self.pending_suggestions.get(suggestion_id)

    def clear_processed_suggestions(self):
        """Remove all non-pending suggestions."""
        self.pending_suggestions = {
            k: v for k, v in self.pending_suggestions.items()
            if v.status == "pending"
        }

    async def _emit_event(self, event_type: str, data: dict):
        """Emit an event via the callback."""
        if self.event_callback:
            try:
                if asyncio.iscoroutinefunction(self.event_callback):
                    await self.event_callback(event_type, data)
                else:
                    self.event_callback(event_type, data)
            except Exception as e:
                print(f"[PropagationEngine] Event callback error: {e}")

    async def manual_analyze(self, node_id: str) -> List[PropagationSuggestion]:
        """
        Manually trigger analysis for a specific node.

        Args:
            node_id: Node ID to analyze

        Returns:
            List of suggestions
        """
        # Create a synthetic change info
        node = self.link_graph.get_node(node_id)
        if not node:
            return []

        change = ChangeInfo(
            file_path=self._get_node_file(node_id),
            file_type="manual",
            change_type="analyzed",
            affected_node_ids=[node_id],
            diff_summary="Manuelle Analyse angefordert"
        )

        return await self.process_change(change)
