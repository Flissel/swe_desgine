"""Memory module for Requirements Engineer - User Story Deduplication + Semantic RAG."""

from .supermemory_client import SupermemoryClient
from .supermemory_client import DeduplicationResult
from .mcp_memory_client import MCPMemoryClient
from .semantic_matcher import SemanticMatcher

__all__ = [
    "SupermemoryClient",
    "MCPMemoryClient",
    "DeduplicationResult",
    "SemanticMatcher",
]
