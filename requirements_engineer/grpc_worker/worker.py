"""
PropagationWorker - gRPC Service Implementation

Handles change propagation through dependency graph and Kilo Agent integration.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

# Import proto modules (may not exist yet)
try:
    from requirements_engineer.grpc_worker.proto import propagation_pb2
    from requirements_engineer.grpc_worker.proto import propagation_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    propagation_pb2 = None
    propagation_pb2_grpc = None

logger = logging.getLogger(__name__)


# ============================================
# Data Classes
# ============================================

@dataclass
class ChangeInfo:
    """Information about a change."""
    id: str
    project_id: str
    node_id: str
    node_type: str
    change_type: str
    old_content: str
    new_content: str
    kilo_prompt: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Suggestion:
    """A change suggestion for an affected node."""
    id: str
    change_id: str
    source_node_id: str
    target_node_id: str
    target_node_type: str
    link_type: str
    current_content: str
    suggested_content: str
    reasoning: str
    confidence: float
    kilo_session_id: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected


# ============================================
# PropagationWorker
# ============================================

class PropagationWorker:
    """
    gRPC Servicer for change propagation.

    Integrates with:
    - LinkGraph for finding affected nodes
    - PropagationEngine for change analysis
    - KilocodeCliTool for Kilo Agent integration
    """

    def __init__(self, config: dict):
        self.config = config
        self.propagation_config = config.get("propagation", {})
        self.kilo_config = config.get("kilo", {})

        # State
        self.pending_changes: Dict[str, ChangeInfo] = {}
        self.pending_suggestions: Dict[str, Suggestion] = {}
        self.engines: Dict[str, Any] = {}  # project_id -> PropagationEngine

        # Kilo integration (lazy loaded)
        self._kilo_tool = None
        self._conversation_manager = None

    async def initialize(self):
        """Initialize the worker."""
        logger.info("Initializing PropagationWorker...")

        # Try to import Kilo tools
        if self.kilo_config.get("enabled", True):
            try:
                from requirements_engineer.tools.kilocli_tool import KilocodeCliTool
                from requirements_engineer.tools.kilo_conversation import KiloConversationManager

                self._kilo_tool = KilocodeCliTool()
                self._conversation_manager = KiloConversationManager()
                logger.info("Kilo Agent integration enabled")
            except ImportError as e:
                logger.warning(f"Kilo tools not available: {e}")

        logger.info("PropagationWorker initialized")

    async def cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up PropagationWorker...")
        self.pending_changes.clear()
        self.pending_suggestions.clear()
        self.engines.clear()

    # ============================================
    # gRPC Methods
    # ============================================

    async def ProcessChange(self, request, context):
        """
        Process a change and find affected nodes.

        Flow:
        1. Create ChangeInfo from request
        2. Get or create PropagationEngine for project
        3. Find affected nodes via LinkGraph
        4. If kilo_prompt provided, use Kilo Agent for analysis
        5. Generate suggestions for affected nodes
        6. Return summary with affected node IDs
        """
        logger.info(f"ProcessChange: node={request.node_id}, type={request.node_type}")

        # Create change info
        change = ChangeInfo(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            node_id=request.node_id,
            node_type=request.node_type,
            change_type=request.change_type or "content_edit",
            old_content=request.old_content,
            new_content=request.new_content,
            kilo_prompt=request.kilo_prompt if request.kilo_prompt else None,
        )

        self.pending_changes[change.id] = change

        try:
            # Get affected nodes
            max_depth = request.max_propagation_depth or self.propagation_config.get("max_depth", 2)
            affected_nodes = await self._get_affected_nodes(
                change.project_id,
                change.node_id,
                max_depth
            )

            logger.info(f"Found {len(affected_nodes)} affected nodes")

            # Process with Kilo Agent if prompt provided
            kilo_response = ""
            if change.kilo_prompt and self._kilo_tool:
                kilo_response = await self._process_with_kilo(change, affected_nodes)

            # Generate suggestions for affected nodes
            suggestions = await self._generate_suggestions(change, affected_nodes)

            # Store suggestions
            for s in suggestions:
                self.pending_suggestions[s.id] = s

            # Build response
            if PROTO_AVAILABLE:
                return propagation_pb2.ChangeResponse(
                    change_id=change.id,
                    success=True,
                    affected_node_ids=[n["node_id"] for n in affected_nodes],
                    suggestion_count=len(suggestions),
                    kilo_response=kilo_response,
                )
            else:
                return {
                    "change_id": change.id,
                    "success": True,
                    "affected_node_ids": [n["node_id"] for n in affected_nodes],
                    "suggestion_count": len(suggestions),
                    "kilo_response": kilo_response,
                }

        except Exception as e:
            logger.error(f"ProcessChange error: {e}", exc_info=True)
            if PROTO_AVAILABLE:
                return propagation_pb2.ChangeResponse(
                    change_id=change.id,
                    success=False,
                    error=str(e),
                )
            else:
                return {"change_id": change.id, "success": False, "error": str(e)}

    async def EvaluateImpact(self, request, context):
        """
        Evaluate impact on linked nodes without applying changes.
        Returns affected nodes with their details.
        """
        logger.info(f"EvaluateImpact: node={request.node_id}")

        depth = request.depth or self.propagation_config.get("max_depth", 2)
        include_types = list(request.include_types) if request.include_types else None

        affected_nodes = await self._get_affected_nodes(
            request.project_id,
            request.node_id,
            depth,
            include_types
        )

        # Build response
        if PROTO_AVAILABLE:
            affected_list = [
                propagation_pb2.AffectedNode(
                    node_id=n["node_id"],
                    node_type=n.get("node_type", ""),
                    title=n.get("title", ""),
                    link_type=n.get("link_type", ""),
                    distance=n.get("distance", 0),
                    current_content=n.get("content", "")[:500],  # Truncate
                )
                for n in affected_nodes
            ]

            # Generate impact visualization
            mermaid_viz = self._generate_impact_diagram(request.node_id, affected_nodes)

            return propagation_pb2.ImpactResponse(
                affected_nodes=affected_list,
                total_count=len(affected_nodes),
                graph_visualization=mermaid_viz,
            )
        else:
            return {
                "affected_nodes": affected_nodes,
                "total_count": len(affected_nodes),
            }

    async def GetSuggestions(self, request, context):
        """
        Stream suggestions for affected nodes.
        """
        change_id = request.change_id
        target_node_id = request.target_node_id if request.target_node_id else None

        for suggestion_id, suggestion in self.pending_suggestions.items():
            if suggestion.change_id != change_id:
                continue
            if target_node_id and suggestion.target_node_id != target_node_id:
                continue

            if PROTO_AVAILABLE:
                yield propagation_pb2.SuggestionResponse(
                    suggestion_id=suggestion.id,
                    source_node_id=suggestion.source_node_id,
                    target_node_id=suggestion.target_node_id,
                    target_node_type=suggestion.target_node_type,
                    link_type=suggestion.link_type,
                    current_content=suggestion.current_content,
                    suggested_content=suggestion.suggested_content,
                    reasoning=suggestion.reasoning,
                    confidence=suggestion.confidence,
                    kilo_session_id=suggestion.kilo_session_id or "",
                )
            else:
                yield {
                    "suggestion_id": suggestion.id,
                    "source_node_id": suggestion.source_node_id,
                    "target_node_id": suggestion.target_node_id,
                    "target_node_type": suggestion.target_node_type,
                    "link_type": suggestion.link_type,
                    "current_content": suggestion.current_content,
                    "suggested_content": suggestion.suggested_content,
                    "reasoning": suggestion.reasoning,
                    "confidence": suggestion.confidence,
                }

    async def ApplySuggestion(self, request, context):
        """Apply an approved suggestion."""
        suggestion_id = request.suggestion_id
        suggestion = self.pending_suggestions.get(suggestion_id)

        if not suggestion:
            if PROTO_AVAILABLE:
                return propagation_pb2.ApplyResponse(
                    success=False,
                    error=f"Suggestion not found: {suggestion_id}"
                )
            return {"success": False, "error": f"Suggestion not found: {suggestion_id}"}

        try:
            # Get content to apply (user may have modified)
            content = request.modified_content if request.modified_content else suggestion.suggested_content

            # Apply the change (implementation depends on node type)
            file_path, backup_path = await self._apply_suggestion(suggestion, content)

            # Update status
            suggestion.status = "approved"

            if PROTO_AVAILABLE:
                return propagation_pb2.ApplyResponse(
                    success=True,
                    updated_file_path=str(file_path) if file_path else "",
                    backup_path=str(backup_path) if backup_path else "",
                )
            return {"success": True, "updated_file_path": str(file_path)}

        except Exception as e:
            logger.error(f"ApplySuggestion error: {e}", exc_info=True)
            if PROTO_AVAILABLE:
                return propagation_pb2.ApplyResponse(success=False, error=str(e))
            return {"success": False, "error": str(e)}

    async def RejectSuggestion(self, request, context):
        """Reject a suggestion."""
        suggestion_id = request.suggestion_id
        suggestion = self.pending_suggestions.get(suggestion_id)

        if suggestion:
            suggestion.status = "rejected"
            logger.info(f"Suggestion rejected: {suggestion_id}, reason: {request.reason}")

        if PROTO_AVAILABLE:
            return propagation_pb2.RejectResponse(success=True)
        return {"success": True}

    async def HealthCheck(self, request, context):
        """Health check endpoint."""
        pending = sum(1 for s in self.pending_suggestions.values() if s.status == "pending")

        if PROTO_AVAILABLE:
            return propagation_pb2.HealthResponse(
                healthy=True,
                status="running",
                pending_suggestions=pending,
                active_sessions=len(self.pending_changes),
            )
        return {
            "healthy": True,
            "status": "running",
            "pending_suggestions": pending,
            "active_sessions": len(self.pending_changes),
        }

    # ============================================
    # Internal Methods
    # ============================================

    async def _get_affected_nodes(
        self,
        project_id: str,
        node_id: str,
        depth: int,
        include_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get affected nodes using LinkGraph.

        Tries to use existing PropagationEngine/LinkGraph infrastructure.
        Falls back to config-based traversal if not available.
        """
        try:
            # Try to use existing LinkGraph
            from requirements_engineer.propagation.link_graph import LinkGraph

            # Get project path from engines or use default
            project_path = self._get_project_path(project_id)
            if project_path:
                graph = LinkGraph(project_path)
                await asyncio.to_thread(graph.build)

                linked = graph.get_linked_nodes(node_id, depth=depth, include_types=include_types)

                return [
                    {
                        "node_id": nid,
                        "node_type": graph.nodes.get(nid, {}).get("type", "unknown"),
                        "title": graph.nodes.get(nid, {}).get("title", ""),
                        "link_type": self._get_link_type(graph, node_id, nid),
                        "distance": 1,  # Simplified
                        "content": graph.nodes.get(nid, {}).get("content", ""),
                    }
                    for nid in linked
                ]

        except ImportError:
            logger.warning("LinkGraph not available, using config-based traversal")
        except Exception as e:
            logger.warning(f"LinkGraph error: {e}")

        # Fallback: Use connection_types from config
        return self._get_affected_from_config(node_id)

    def _get_affected_from_config(self, node_id: str) -> List[Dict]:
        """
        Get affected nodes based on connection_types config.
        This is a simplified fallback when LinkGraph is not available.
        """
        # Parse node type from ID (e.g., EPIC-001 -> epic)
        node_type = self._parse_node_type(node_id)

        connection_types = self.config.get("connection_types", {})
        connected_types = connection_types.get(node_type, [])

        # Return placeholder - actual implementation would query the project data
        return [
            {
                "node_id": f"{t.upper()}-AFFECTED",
                "node_type": t,
                "title": f"Affected {t}",
                "link_type": f"{node_type}_{t}",
                "distance": 1,
                "content": "",
            }
            for t in connected_types
        ]

    def _parse_node_type(self, node_id: str) -> str:
        """Parse node type from ID."""
        prefixes = {
            "EPIC": "epic",
            "REQ": "requirement",
            "US": "user_story",
            "TASK": "task",
            "DIAG": "diagram",
            "TEST": "test",
        }

        for prefix, node_type in prefixes.items():
            if node_id.upper().startswith(prefix):
                return node_type

        return "unknown"

    def _get_project_path(self, project_id: str) -> Optional[Path]:
        """Get project path from ID or environment."""
        import os

        # Check environment variable
        env_path = os.getenv("RE_PROJECT_PATH")
        if env_path:
            return Path(env_path)

        # Check if it's a path
        if project_id and Path(project_id).exists():
            return Path(project_id)

        return None

    def _get_link_type(self, graph, source_id: str, target_id: str) -> str:
        """Get link type between two nodes."""
        try:
            return graph._edge_types.get((source_id, target_id), "related")
        except:
            return "related"

    async def _process_with_kilo(
        self,
        change: ChangeInfo,
        affected_nodes: List[Dict]
    ) -> str:
        """
        Process change with Kilo Agent.

        Sends the change and affected nodes to Kilo for analysis.
        """
        if not self._kilo_tool:
            return ""

        # Build context for Kilo
        context = self._build_kilo_context(change, affected_nodes)

        try:
            # Execute via Kilo CLI
            result = self._kilo_tool.run_autonomous(
                prompt=f"{change.kilo_prompt}\n\nKontext:\n{context}",
                mode=self.kilo_config.get("mode", "code"),
                timeout=self.kilo_config.get("timeout_seconds", 60),
                json_output=True,
                yolo=self.kilo_config.get("yolo_mode", True),
            )

            if result.get("success"):
                return result.get("stdout", "")
            else:
                logger.warning(f"Kilo execution failed: {result.get('stderr', '')}")
                return ""

        except Exception as e:
            logger.error(f"Kilo processing error: {e}")
            return ""

    def _build_kilo_context(
        self,
        change: ChangeInfo,
        affected_nodes: List[Dict]
    ) -> str:
        """Build context string for Kilo Agent."""
        lines = [
            f"## Geänderte Node",
            f"- ID: {change.node_id}",
            f"- Typ: {change.node_type}",
            f"- Änderung: {change.change_type}",
            "",
            f"## Alter Inhalt",
            f"```",
            change.old_content[:1000],  # Truncate
            "```",
            "",
            f"## Neuer Inhalt",
            f"```",
            change.new_content[:1000],
            "```",
            "",
            f"## Betroffene Nodes ({len(affected_nodes)})",
        ]

        for node in affected_nodes[:10]:  # Limit
            lines.append(f"- {node['node_id']} ({node['node_type']}): {node.get('title', '')}")

        return "\n".join(lines)

    async def _generate_suggestions(
        self,
        change: ChangeInfo,
        affected_nodes: List[Dict]
    ) -> List[Suggestion]:
        """
        Generate suggestions for affected nodes.

        Uses LLM or heuristics to determine what changes are needed.
        """
        suggestions = []
        min_confidence = self.propagation_config.get("min_confidence", 0.5)

        for node in affected_nodes:
            # Simple heuristic: suggest update based on link type
            confidence = self._calculate_confidence(change, node)

            if confidence < min_confidence:
                continue

            suggestion = Suggestion(
                id=str(uuid.uuid4()),
                change_id=change.id,
                source_node_id=change.node_id,
                target_node_id=node["node_id"],
                target_node_type=node["node_type"],
                link_type=node.get("link_type", "related"),
                current_content=node.get("content", ""),
                suggested_content="",  # Will be filled by Kilo or LLM
                reasoning=f"Node {node['node_id']} ist mit {change.node_id} über '{node.get('link_type', 'related')}' verbunden und sollte überprüft werden.",
                confidence=confidence,
            )

            suggestions.append(suggestion)

        return suggestions

    def _calculate_confidence(self, change: ChangeInfo, node: Dict) -> float:
        """Calculate confidence score for a suggestion."""
        link_type = node.get("link_type", "")

        # Higher confidence for direct relationships
        direct_relationships = ["epic_story", "requirement_diagram", "story_test"]
        if link_type in direct_relationships:
            return 0.85

        # Medium confidence for related
        if "requirement" in link_type or "story" in link_type:
            return 0.7

        return 0.5

    async def _apply_suggestion(
        self,
        suggestion: Suggestion,
        content: str
    ) -> tuple:
        """
        Apply a suggestion to the target node.

        Returns (file_path, backup_path)
        """
        # TODO: Implement actual file modification
        # This would need to know the file structure of the project
        logger.info(f"Applying suggestion to {suggestion.target_node_id}")

        # For now, just log
        return (None, None)

    def _generate_impact_diagram(
        self,
        source_id: str,
        affected_nodes: List[Dict]
    ) -> str:
        """Generate a Mermaid diagram showing impact."""
        lines = ["graph LR"]
        lines.append(f'    {source_id.replace("-", "_")}["{source_id}"]')

        for node in affected_nodes[:20]:  # Limit for readability
            node_id = node["node_id"].replace("-", "_")
            lines.append(f'    {node_id}["{node["node_id"]}"]')
            lines.append(f'    {source_id.replace("-", "_")} --> {node_id}')

        return "\n".join(lines)
