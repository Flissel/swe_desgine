"""
Change Propagation & Auto-Link Discovery System

This module provides:
1. Change Propagation: When a node is modified, linked nodes are automatically suggested for updates
2. Auto-Link Discovery: Orphan nodes (without links) get automatic link suggestions

Components:
- FileWatcher: Monitors project files for changes
- ChangeDetector: Detects what changed in a file
- LinkGraph: Graph of all node relationships
- PropagationEngine: Orchestrates change propagation workflow
- AutoLinker: Finds orphans and suggests links
- LLMAnalyzer: LLM integration for semantic analysis
- BackupManager: Creates backups before modifications
"""

from .models import (
    ChangeInfo,
    PropagationSuggestion,
    LinkSuggestion,
    Edge,
)
from .backup_manager import BackupManager
from .link_graph import LinkGraph
from .file_watcher import FileWatcher
from .change_detector import ChangeDetector
from .llm_analyzer import LLMAnalyzer
from .propagation_engine import PropagationEngine
from .auto_linker import AutoLinker

__all__ = [
    "ChangeInfo",
    "PropagationSuggestion",
    "LinkSuggestion",
    "Edge",
    "BackupManager",
    "LinkGraph",
    "FileWatcher",
    "ChangeDetector",
    "LLMAnalyzer",
    "PropagationEngine",
    "AutoLinker",
]
