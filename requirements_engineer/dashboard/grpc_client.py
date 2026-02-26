"""
gRPC Client for Change Propagation Worker

Provides async interface to communicate with the gRPC PropagationService.
"""

import asyncio
import logging
from typing import Dict, List, Optional, AsyncIterator, Any

logger = logging.getLogger(__name__)

# Try to import gRPC
try:
    import grpc
    from grpc import aio
    HAS_GRPC = True
except ImportError:
    HAS_GRPC = False
    grpc = None
    aio = None

# Try to import generated proto modules
try:
    from requirements_engineer.grpc_worker.proto import propagation_pb2
    from requirements_engineer.grpc_worker.proto import propagation_pb2_grpc
    HAS_PROTO = True
except ImportError:
    HAS_PROTO = False
    propagation_pb2 = None
    propagation_pb2_grpc = None


class PropagationClient:
    """
    Async client for the gRPC Change Propagation Worker.

    Usage:
        client = PropagationClient("localhost:50051")
        await client.connect()

        response = await client.process_change(
            project_id="my-project",
            node_id="EPIC-001",
            node_type="epic",
            old_content="...",
            new_content="...",
            kilo_prompt="Füge Fehlerbehandlung hinzu"
        )

        async for suggestion in client.get_suggestions(response.change_id):
            print(suggestion)

        await client.close()
    """

    def __init__(self, address: str = "localhost:50051", timeout: int = 30):
        """
        Initialize the client.

        Args:
            address: gRPC server address (host:port)
            timeout: Default timeout for RPC calls in seconds
        """
        if not HAS_GRPC:
            raise ImportError("grpcio required. Install with: pip install grpcio")

        self.address = address
        self.timeout = timeout
        self._channel: Optional[aio.Channel] = None
        self._stub = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Connect to the gRPC server.

        Returns:
            True if connection successful
        """
        if self._connected:
            return True

        try:
            self._channel = aio.insecure_channel(
                self.address,
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                ]
            )

            if HAS_PROTO:
                self._stub = propagation_pb2_grpc.PropagationServiceStub(self._channel)

            # Test connection with health check
            healthy = await self.health_check()
            self._connected = healthy

            if healthy:
                logger.info(f"Connected to gRPC server at {self.address}")
            else:
                logger.warning(f"gRPC server at {self.address} not healthy")

            return healthy

        except Exception as e:
            logger.error(f"Failed to connect to gRPC server: {e}")
            return False

    async def close(self):
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            self._connected = False
            logger.info("Disconnected from gRPC server")

    async def health_check(self) -> bool:
        """
        Check if the server is healthy.

        Returns:
            True if server is healthy
        """
        if not self._stub or not HAS_PROTO:
            return False

        try:
            response = await self._stub.HealthCheck(
                propagation_pb2.HealthRequest(),
                timeout=5
            )
            return response.healthy
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    async def process_change(
        self,
        project_id: str,
        node_id: str,
        node_type: str,
        old_content: str,
        new_content: str,
        kilo_prompt: Optional[str] = None,
        change_type: str = "content_edit",
        max_depth: int = 2,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a change and get affected nodes.

        Args:
            project_id: Project identifier
            node_id: ID of the changed node
            node_type: Type of node (epic, requirement, user_story, etc.)
            old_content: Previous content
            new_content: New content after change
            kilo_prompt: Optional Kilo Agent instruction
            change_type: Type of change (content_edit, structure_change, diagram_update)
            max_depth: Maximum propagation depth
            session_id: Session ID for tracking

        Returns:
            Response dict with change_id, affected_node_ids, etc.
        """
        if not self._connected:
            await self.connect()

        if not self._stub or not HAS_PROTO:
            return {"success": False, "error": "Not connected to gRPC server"}

        try:
            request = propagation_pb2.ChangeRequest(
                project_id=project_id,
                node_id=node_id,
                node_type=node_type,
                change_type=change_type,
                old_content=old_content,
                new_content=new_content,
                kilo_prompt=kilo_prompt or "",
                max_propagation_depth=max_depth,
                session_id=session_id or "",
            )

            response = await self._stub.ProcessChange(
                request,
                timeout=self.timeout
            )

            return {
                "success": response.success,
                "change_id": response.change_id,
                "error": response.error if response.error else None,
                "affected_node_ids": list(response.affected_node_ids),
                "suggestion_count": response.suggestion_count,
                "kilo_response": response.kilo_response if response.kilo_response else None,
            }

        except grpc.RpcError as e:
            logger.error(f"ProcessChange RPC error: {e}")
            return {"success": False, "error": str(e)}

    async def evaluate_impact(
        self,
        project_id: str,
        node_id: str,
        depth: int = 2,
        include_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate impact on linked nodes without applying changes.

        Args:
            project_id: Project identifier
            node_id: ID of the node to analyze
            depth: Traversal depth
            include_types: Filter by node types

        Returns:
            Response with affected nodes and optional graph visualization
        """
        if not self._connected:
            await self.connect()

        if not self._stub or not HAS_PROTO:
            return {"success": False, "error": "Not connected to gRPC server"}

        try:
            request = propagation_pb2.ImpactRequest(
                project_id=project_id,
                node_id=node_id,
                depth=depth,
                include_types=include_types or [],
            )

            response = await self._stub.EvaluateImpact(
                request,
                timeout=self.timeout
            )

            affected = [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "title": n.title,
                    "link_type": n.link_type,
                    "distance": n.distance,
                    "current_content": n.current_content,
                }
                for n in response.affected_nodes
            ]

            return {
                "success": True,
                "affected_nodes": affected,
                "total_count": response.total_count,
                "graph_visualization": response.graph_visualization if response.graph_visualization else None,
            }

        except grpc.RpcError as e:
            logger.error(f"EvaluateImpact RPC error: {e}")
            return {"success": False, "error": str(e)}

    async def get_suggestions(
        self,
        change_id: str,
        target_node_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream suggestions for affected nodes.

        Args:
            change_id: ID of the change to get suggestions for
            target_node_id: Optional: get suggestions for specific node only

        Yields:
            Suggestion dicts
        """
        if not self._connected:
            await self.connect()

        if not self._stub or not HAS_PROTO:
            return

        try:
            request = propagation_pb2.SuggestionRequest(
                change_id=change_id,
                target_node_id=target_node_id or "",
            )

            async for response in self._stub.GetSuggestions(request, timeout=self.timeout):
                yield {
                    "suggestion_id": response.suggestion_id,
                    "source_node_id": response.source_node_id,
                    "target_node_id": response.target_node_id,
                    "target_node_type": response.target_node_type,
                    "link_type": response.link_type,
                    "current_content": response.current_content,
                    "suggested_content": response.suggested_content,
                    "reasoning": response.reasoning,
                    "confidence": response.confidence,
                    "kilo_session_id": response.kilo_session_id if response.kilo_session_id else None,
                }

        except grpc.RpcError as e:
            logger.error(f"GetSuggestions RPC error: {e}")

    async def apply_suggestion(
        self,
        suggestion_id: str,
        modified_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply an approved suggestion.

        Args:
            suggestion_id: ID of the suggestion to apply
            modified_content: Optional modified content (user can edit before applying)

        Returns:
            Response with success status and file paths
        """
        if not self._connected:
            await self.connect()

        if not self._stub or not HAS_PROTO:
            return {"success": False, "error": "Not connected to gRPC server"}

        try:
            request = propagation_pb2.ApplyRequest(
                suggestion_id=suggestion_id,
                modified_content=modified_content or "",
            )

            response = await self._stub.ApplySuggestion(
                request,
                timeout=self.timeout
            )

            return {
                "success": response.success,
                "error": response.error if response.error else None,
                "updated_file_path": response.updated_file_path if response.updated_file_path else None,
                "backup_path": response.backup_path if response.backup_path else None,
            }

        except grpc.RpcError as e:
            logger.error(f"ApplySuggestion RPC error: {e}")
            return {"success": False, "error": str(e)}

    async def reject_suggestion(
        self,
        suggestion_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reject a suggestion.

        Args:
            suggestion_id: ID of the suggestion to reject
            reason: Optional reason for rejection

        Returns:
            Response with success status
        """
        if not self._connected:
            await self.connect()

        if not self._stub or not HAS_PROTO:
            return {"success": False, "error": "Not connected to gRPC server"}

        try:
            request = propagation_pb2.RejectRequest(
                suggestion_id=suggestion_id,
                reason=reason or "",
            )

            response = await self._stub.RejectSuggestion(
                request,
                timeout=self.timeout
            )

            return {"success": response.success}

        except grpc.RpcError as e:
            logger.error(f"RejectSuggestion RPC error: {e}")
            return {"success": False, "error": str(e)}


# ============================================
# Singleton for global access
# ============================================

_client_instance: Optional[PropagationClient] = None


def get_propagation_client(address: str = "localhost:50051") -> PropagationClient:
    """
    Get or create a global PropagationClient instance.

    Args:
        address: gRPC server address

    Returns:
        PropagationClient instance
    """
    global _client_instance

    if _client_instance is None:
        _client_instance = PropagationClient(address)

    return _client_instance


async def close_propagation_client():
    """Close the global PropagationClient instance."""
    global _client_instance

    if _client_instance is not None:
        await _client_instance.close()
        _client_instance = None
