"""
Auto Linker - Discovers orphan nodes and suggests appropriate links.

Finds nodes without meaningful connections and uses LLM to suggest
semantically appropriate links.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import uuid

from .models import LinkSuggestion
from .link_graph import LinkGraph
from .llm_analyzer import LLMAnalyzer


class AutoLinker:
    """
    Discovers orphan nodes and suggests appropriate links.

    Workflow:
    1. Find all nodes with no incoming or outgoing edges (orphans)
    2. For each orphan, find type-compatible candidate targets
    3. Use LLM to analyze semantic similarity
    4. Generate ranked link suggestions
    """

    def __init__(
        self,
        link_graph: LinkGraph,
        llm_analyzer: LLMAnalyzer,
        project_path: Optional[Path] = None,
        event_callback: Optional[Callable[[str, dict], Any]] = None
    ):
        """
        Initialize the auto linker.

        Args:
            link_graph: The link graph to use
            llm_analyzer: LLM analyzer for semantic analysis
            project_path: Path to the project directory for persisting links
            event_callback: Async callback for emitting events
        """
        self.link_graph = link_graph
        self.llm_analyzer = llm_analyzer
        self.project_path = Path(project_path) if project_path else None
        self.event_callback = event_callback

        # File for persisting discovered links
        self.links_file = self.project_path / "discovered_links.json" if self.project_path else None

        # Debug output
        print(f"[AutoLinker] Initialized with project_path: {self.project_path}")
        print(f"[AutoLinker] links_file: {self.links_file}")

        # Suggestion storage
        self.pending_suggestions: Dict[str, LinkSuggestion] = {}

        # Load any previously persisted links
        if self.links_file:
            self._load_persisted_links()

        # Configuration
        self.min_confidence_threshold = 0.4
        self.max_suggestions_per_orphan = 3

        # Type compatibility matrix
        # Maps node types to compatible link target types
        self.type_compatibility = {
            "requirement": ["requirement", "epic", "user_story", "user-story", "task", "feature", "test"],
            "epic": ["requirement", "user_story", "user-story", "feature", "persona"],
            "user_story": ["requirement", "epic", "task", "test", "screen", "persona", "feature"],
            "user-story": ["requirement", "epic", "task", "test", "screen", "persona", "feature"],
            "task": ["user_story", "user-story", "requirement", "task", "feature"],
            "diagram": ["requirement", "epic", "user_story", "user-story", "feature", "screen"],
            "test": ["requirement", "user_story", "user-story", "feature"],
            "entity": ["requirement", "entity", "api", "screen"],
            "feature": ["requirement", "task", "user_story", "user-story", "epic"],
            # New node types
            "persona": ["user_story", "user-story", "epic", "screen", "user-flow", "requirement"],
            "user-flow": ["screen", "user_story", "user-story", "persona", "feature"],
            "screen": ["user_story", "user-story", "component", "user-flow", "persona", "feature"],
            "component": ["screen", "user_story", "user-story", "feature"],
            "api": ["entity", "requirement", "feature", "screen"],
            "tech-stack": ["requirement", "feature", "task"],
        }

    async def find_orphans(self) -> List[str]:
        """
        Find all nodes without meaningful links.

        Returns:
            List of orphan node IDs
        """
        orphans = self.link_graph.get_orphan_nodes()

        # Emit event
        if orphans:
            await self._emit_event("orphans_detected", {
                "count": len(orphans),
                "orphan_ids": orphans[:10]  # First 10 for preview
            })

        return orphans

    async def suggest_links_for_orphan(self, orphan_id: str) -> List[LinkSuggestion]:
        """
        Generate link suggestions for a single orphan node.

        Args:
            orphan_id: ID of the orphan node

        Returns:
            List of link suggestions
        """
        orphan = self.link_graph.get_node(orphan_id)
        if not orphan:
            print(f"[AutoLinker] Orphan {orphan_id} not found in graph")
            return []

        # Get type-compatible candidates
        candidates = self._get_compatible_candidates(orphan_id, orphan)
        print(f"[AutoLinker] Orphan '{orphan_id}' (type={orphan.get('type', 'unknown')}) has {len(candidates)} candidates")

        if not candidates:
            print(f"[AutoLinker] No candidates found for orphan {orphan_id}")
            return []

        # Use LLM to analyze and suggest links
        print(f"[AutoLinker] Calling LLM for {orphan_id}...")
        analyses = await self.llm_analyzer.suggest_links(
            orphan_node=orphan,
            candidate_nodes=candidates,
            max_suggestions=self.max_suggestions_per_orphan
        )
        print(f"[AutoLinker] LLM returned {len(analyses)} analyses for {orphan_id}")

        # Convert to LinkSuggestion objects
        suggestions = []
        for analysis in analyses:
            if analysis.confidence < self.min_confidence_threshold:
                continue

            target = self.link_graph.get_node(analysis.target_id)
            if not target:
                continue

            suggestion = LinkSuggestion(
                id=uuid.uuid4().hex,
                orphan_node_id=orphan_id,
                orphan_node_title=orphan.get("title", orphan_id),
                orphan_node_type=orphan.get("type", "unknown"),
                target_node_id=analysis.target_id,
                target_node_title=target.get("title", analysis.target_id),
                target_node_type=target.get("type", "unknown"),
                link_type=analysis.link_type,
                reasoning=analysis.reasoning,
                confidence=analysis.confidence,
                status="pending"
            )

            self.pending_suggestions[suggestion.id] = suggestion
            suggestions.append(suggestion)

        return suggestions

    def _get_compatible_candidates(self, orphan_id: str, orphan: dict) -> List[dict]:
        """
        Get candidate nodes that are type-compatible with the orphan.

        Args:
            orphan_id: ID of the orphan node
            orphan: Data of the orphan node

        Returns:
            List of candidate node data dicts
        """
        orphan_type = orphan.get("type", "requirement")

        # Get compatible types
        compatible_types = self.type_compatibility.get(orphan_type, ["requirement"])

        # Collect candidates
        candidates = []
        for node_id, node_data in self.link_graph.nodes.items():
            if node_id == orphan_id:
                continue

            node_type = node_data.get("type", "")
            if node_type in compatible_types:
                candidates.append(node_data)

        return candidates

    async def discover_all(self) -> Dict[str, List[LinkSuggestion]]:
        """
        Run auto-discovery for all orphan nodes in parallel.

        Returns:
            Dict mapping orphan IDs to their suggestions
        """
        orphans = await self.find_orphans()
        if not orphans:
            return {}

        # Process all orphans in parallel via asyncio.gather
        tasks = [self.suggest_links_for_orphan(oid) for oid in orphans]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for orphan_id, result in zip(orphans, all_results):
            if isinstance(result, Exception):
                print(f"[AutoLinker] Error for {orphan_id}: {result}")
                continue
            if result:
                results[orphan_id] = result
                for suggestion in result:
                    await self._emit_event("link_suggestion", suggestion.to_event_dict())

        return results

    async def approve_link(self, suggestion_id: str) -> bool:
        """
        Approve a link suggestion and create the link.

        Args:
            suggestion_id: ID of the suggestion to approve

        Returns:
            True if successful
        """
        print(f"[AutoLinker] approve_link called with: {suggestion_id}")
        print(f"[AutoLinker] links_file: {self.links_file}")
        print(f"[AutoLinker] pending_suggestions keys: {list(self.pending_suggestions.keys())[:5]}...")

        suggestion = self.pending_suggestions.get(suggestion_id)
        if not suggestion:
            print(f"[AutoLinker] Suggestion {suggestion_id} not found in pending")
            return False

        if suggestion.status != "pending":
            return False

        try:
            # Add the link to the graph
            self.link_graph._add_edge(
                suggestion.orphan_node_id,
                suggestion.target_node_id,
                suggestion.link_type
            )

            # Persist the link to discovered_links.json
            self._save_persisted_link({
                "id": suggestion_id,
                "source_id": suggestion.orphan_node_id,
                "target_id": suggestion.target_node_id,
                "link_type": suggestion.link_type,
                "reasoning": suggestion.reasoning,
                "confidence": suggestion.confidence,
                "created_at": datetime.now().isoformat()
            })

            suggestion.status = "applied"

            await self._emit_event("link_created", {
                "id": suggestion_id,
                "orphan_node_id": suggestion.orphan_node_id,
                "target_node_id": suggestion.target_node_id,
                "link_type": suggestion.link_type
            })

            return True

        except Exception as e:
            print(f"[AutoLinker] Error approving link: {e}")
            suggestion.status = "failed"
            return False

    async def reject_link(self, suggestion_id: str) -> bool:
        """
        Reject a link suggestion.

        Args:
            suggestion_id: ID of the suggestion to reject

        Returns:
            True if successful
        """
        suggestion = self.pending_suggestions.get(suggestion_id)
        if not suggestion:
            return False

        suggestion.status = "rejected"

        await self._emit_event("link_rejected", {
            "id": suggestion_id,
            "orphan_node_id": suggestion.orphan_node_id
        })

        return True

    def get_pending_suggestions(self) -> List[LinkSuggestion]:
        """Get all pending link suggestions."""
        return [
            s for s in self.pending_suggestions.values()
            if s.status == "pending"
        ]

    def get_suggestions_for_orphan(self, orphan_id: str) -> List[LinkSuggestion]:
        """Get all suggestions for a specific orphan."""
        return [
            s for s in self.pending_suggestions.values()
            if s.orphan_node_id == orphan_id and s.status == "pending"
        ]

    def get_suggestion(self, suggestion_id: str) -> Optional[LinkSuggestion]:
        """Get a specific suggestion by ID."""
        return self.pending_suggestions.get(suggestion_id)

    def clear_processed_suggestions(self):
        """Remove all non-pending suggestions."""
        self.pending_suggestions = {
            k: v for k, v in self.pending_suggestions.items()
            if v.status == "pending"
        }

    def get_orphan_statistics(self) -> Dict[str, Any]:
        """Get statistics about orphan nodes."""
        orphans = self.link_graph.get_orphan_nodes()

        type_counts = {}
        for orphan_id in orphans:
            node = self.link_graph.get_node(orphan_id)
            if node:
                node_type = node.get("type", "unknown")
                type_counts[node_type] = type_counts.get(node_type, 0) + 1

        return {
            "total_orphans": len(orphans),
            "orphans_by_type": type_counts,
            "pending_suggestions": len(self.get_pending_suggestions())
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
                print(f"[AutoLinker] Event callback error: {e}")

    def _load_persisted_links(self):
        """Load previously approved links from discovered_links.json."""
        if not self.links_file or not self.links_file.exists():
            return

        try:
            with open(self.links_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            count = 0
            for link in data.get("links", []):
                source_id = link.get("source_id")
                target_id = link.get("target_id")
                link_type = link.get("link_type", "discovered")

                if source_id and target_id:
                    self.link_graph._add_edge(source_id, target_id, link_type)
                    count += 1

            print(f"[AutoLinker] Loaded {count} persisted links from {self.links_file.name}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[AutoLinker] Failed to load persisted links: {e}")

    def _save_persisted_link(self, link_data: dict):
        """Save an approved link to discovered_links.json."""
        if not self.links_file:
            print("[AutoLinker] No links file configured, link not persisted")
            return

        try:
            # Load existing links
            existing = {"links": []}
            if self.links_file.exists():
                with open(self.links_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            # Append new link
            existing["links"].append(link_data)

            # Save back
            with open(self.links_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            print(f"[AutoLinker] Persisted link: {link_data['source_id']} → {link_data['target_id']}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[AutoLinker] Failed to save link: {e}")
