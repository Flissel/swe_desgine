"""Memory module for Requirements Engineer - User Story Deduplication."""

from .supermemory_client import SupermemoryClient
from .supermemory_client import DeduplicationResult
from .mcp_memory_client import MCPMemoryClient

__all__ = [
    "SupermemoryClient",
    "MCPMemoryClient",
    "DeduplicationResult"
]
