"""
ArchTeam Importer - Extract requirements from documents using arch_team ChunkMinerAgent.

Supports: PDF, DOCX, DOC, MD, TXT files.

This importer uses the arch_team project's ChunkMinerAgent to extract
structured requirements from unstructured documents.

Integration modes:
1. Git Submodule: external/arch_team (preferred)
2. Path reference: C:/Users/User/Desktop/-req-orchestrator/arch_team
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base_importer import BaseImporter, ImportResult
from requirements_engineer.core.re_journal import RequirementNode


# Try to find arch_team in multiple locations
# Note: The submodule structure is: external/arch_team/arch_team/ (repo contains package)
# Path from this file: importers/arch_team_importer.py -> requirements_engineer -> AI-Scientist-v2
ARCH_TEAM_REPO_PATHS = [
    # Git submodule location (preferred) - contains arch_team package
    # __file__ -> importers -> requirements_engineer -> AI-Scientist-v2 -> external/arch_team
    Path(__file__).parent.parent.parent / "external" / "arch_team",
    # Direct path reference (fallback) - the -req-orchestrator repo
    Path("C:/Users/User/Desktop/-req-orchestrator"),
    # Relative from project root
    Path(__file__).parent.parent.parent / ".." / "-req-orchestrator",
]

def _find_arch_team_path() -> Optional[Path]:
    """Find the arch_team repository path (containing the arch_team package)."""
    for path in ARCH_TEAM_REPO_PATHS:
        # Check for arch_team package with chunk_miner inside
        chunk_miner = path / "arch_team" / "agents" / "chunk_miner.py"
        if path.exists() and chunk_miner.exists():
            return path.resolve()
    return None

def _ensure_arch_team_in_path() -> bool:
    """Add arch_team repository to sys.path if found."""
    repo_path = _find_arch_team_path()
    if repo_path:
        # Add the repo root so 'from arch_team.agents...' works
        path_str = str(repo_path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        return True
    return False


class ArchTeamImporter(BaseImporter):
    """
    Extracts requirements from documents using arch_team's ChunkMinerAgent.

    This importer leverages the arch_team project's advanced document mining
    capabilities to extract structured requirements from various document formats.

    Features:
    - Chunk-based document analysis
    - LLM-powered requirement extraction
    - Evidence linking and traceability
    - Support for PDF, DOCX, MD, TXT files

    Configuration:
    - Default model: anthropic/claude-haiku-4.5 via OpenRouter
    - Chunk size: 1200 tokens with 300 token overlap
    """

    name = "arch_team Document Miner"
    supported_extensions = [".pdf", ".docx", ".doc", ".md", ".txt"]

    # LLM configuration - fallback defaults
    DEFAULT_MODEL = "anthropic/claude-haiku-4.5"  # Via OpenRouter
    CHUNK_SIZE = 1200
    CHUNK_OVERLAP = 300

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the importer.

        Args:
            config: Configuration dict with importers.arch_team section
        """
        self._arch_team_available = _ensure_arch_team_in_path()
        self.config = config or {}
        importer_config = self.config.get("importers", {}).get("arch_team", {})
        self.model = importer_config.get("model", self.DEFAULT_MODEL)
        self.temperature = importer_config.get("temperature", 0.3)
        self.max_tokens = importer_config.get("max_tokens", 4000)

    @classmethod
    def can_import(cls, file_path: str) -> bool:
        """
        Check if this importer can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file extension is supported and arch_team is available
        """
        path = Path(file_path)

        # Check extension
        if path.suffix.lower() not in cls.supported_extensions:
            return False

        # Check if arch_team is available
        if not _find_arch_team_path():
            print(f"  [ArchTeamImporter] arch_team not found in expected locations")
            return False

        return True

    async def import_requirements(self, file_path: str) -> ImportResult:
        """
        Import requirements from a document using arch_team ChunkMinerAgent.

        Args:
            file_path: Path to the document file

        Returns:
            ImportResult with extracted requirements
        """
        if not self._arch_team_available:
            raise ImportError(
                "arch_team is not available. Please install it as a git submodule "
                "in external/arch_team or ensure it's available at the expected path."
            )

        # Import ChunkMinerAgent
        try:
            from arch_team.agents.chunk_miner import ChunkMinerAgent
        except ImportError as e:
            raise ImportError(f"Failed to import arch_team ChunkMinerAgent: {e}")

        path = Path(file_path)
        print(f"  [ArchTeamImporter] Extracting requirements from: {path.name}")

        # Initialize ChunkMiner
        agent = ChunkMinerAgent(
            source="re-system",
            default_model=self.model
        )

        # Read file content
        with open(path, 'rb') as f:
            file_bytes = f.read()

        # Extract requirements using ChunkMiner
        print(f"  [ArchTeamImporter] Mining document with {self.model}...")
        items = agent.mine_files_or_texts_collect(
            files_or_texts=[file_bytes],
            neighbor_refs=True,
            chunk_options={
                "max_tokens": self.CHUNK_SIZE,
                "overlap_tokens": self.CHUNK_OVERLAP
            }
        )

        print(f"  [ArchTeamImporter] Extracted {len(items)} requirements")

        # Convert arch_team DTOs to RequirementNode format
        requirements = self._convert_dtos_to_nodes(items)

        # Build context from evidence
        context = self._build_context(path, items)

        return ImportResult(
            project_name=path.stem,
            project_title=f"Requirements from {path.name}",
            domain="extracted",
            context=context,
            stakeholders=[],
            requirements=requirements,
            constraints={},
            metadata={
                "source_file": str(path),
                "extraction_method": "arch_team_chunk_miner",
                "model_used": self.DEFAULT_MODEL,
                "raw_item_count": len(items),
                "chunk_size": self.CHUNK_SIZE,
                "chunk_overlap": self.CHUNK_OVERLAP
            },
            import_timestamp=datetime.now().isoformat(),
            source_format="arch_team_extraction"
        )

    def _convert_dtos_to_nodes(self, items: List[Dict[str, Any]]) -> List[RequirementNode]:
        """
        Convert arch_team requirement DTOs to RequirementNode format.

        Args:
            items: List of arch_team requirement DTOs

        Returns:
            List of RequirementNode instances
        """
        # Tag to requirement type mapping
        TAG_TO_TYPE = {
            "functional": "functional",
            "security": "non_functional",
            "performance": "non_functional",
            "usability": "functional",
            "reliability": "non_functional",
            "compliance": "constraint",
            "interface": "functional",
            "data": "functional",
            "constraint": "constraint"
        }

        nodes = []
        for idx, item in enumerate(items):
            # Extract fields from arch_team DTO
            req_id = item.get("req_id", f"REQ-{idx+1:03d}")
            title = item.get("title", "")
            tag = item.get("tag", "functional")
            priority = item.get("priority", "should")
            measurable_criteria = item.get("measurable_criteria", "")
            evidence = item.get("evidence", "")
            evidence_refs = item.get("evidence_refs", [])

            # Map tag to requirement type
            req_type = TAG_TO_TYPE.get(tag, "functional")

            # Build acceptance criteria
            acceptance_criteria = []
            if measurable_criteria:
                acceptance_criteria.append(measurable_criteria)

            # Build rationale from evidence
            rationale = ""
            if evidence:
                rationale = f"Evidence: {evidence}"
            if evidence_refs:
                ref_strs = [
                    f"{ref.get('sourceFile', 'unknown')}:chunk{ref.get('chunkIndex', '?')}"
                    for ref in evidence_refs
                ]
                rationale += f"\nSource references: {', '.join(ref_strs)}"

            # Create RequirementNode
            node = RequirementNode(
                requirement_id=req_id,
                title=title,
                description=title,  # arch_team uses title as the full requirement statement
                type=req_type,
                priority=priority,
                rationale=rationale.strip(),
                source="arch_team_extraction",
                acceptance_criteria=acceptance_criteria,
                testable=bool(measurable_criteria)
            )
            nodes.append(node)

        return nodes

    def _build_context(self, path: Path, items: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Build context dictionary from extraction results.

        Args:
            path: Source file path
            items: Extracted requirement items

        Returns:
            Context dictionary for the project
        """
        # Count requirements by tag
        tag_counts = {}
        for item in items:
            tag = item.get("tag", "unknown")
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Build summary
        tag_summary = ", ".join(f"{count} {tag}" for tag, count in sorted(tag_counts.items()))

        return {
            "summary": f"Requirements extracted from {path.name}",
            "source": f"Document: {path.name}",
            "extraction_summary": f"Found {len(items)} requirements: {tag_summary}",
            "technical": "Requirements extracted via LLM-based document analysis",
            "domain": "Extracted from document - domain to be determined"
        }


# Helper function for standalone usage
async def extract_requirements_from_file(file_path: str) -> ImportResult:
    """
    Convenience function to extract requirements from a file.

    Args:
        file_path: Path to the document

    Returns:
        ImportResult with extracted requirements
    """
    importer = ArchTeamImporter()
    return await importer.import_requirements(file_path)
