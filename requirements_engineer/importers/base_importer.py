"""
Base Importer Interface for Universal Requirements Import.

Defines the abstract interface that all importers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from requirements_engineer.core.re_journal import RequirementNode


@dataclass
class ImportResult:
    """
    Normalized import result from any importer.

    This is the standard format that all importers produce,
    regardless of their input format.
    """
    project_name: str
    project_title: str
    domain: str
    context: Dict[str, str] = field(default_factory=dict)
    stakeholders: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[RequirementNode] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    import_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source_format: str = "unknown"

    def to_standard_format(self) -> Dict[str, Any]:
        """Convert to standard RE-System project format."""
        return {
            "Name": self.project_name,
            "Title": self.project_title,
            "Domain": self.domain,
            "Context": self.context if isinstance(self.context, dict) else {"description": self.context},
            "Stakeholders": self.stakeholders,
            "Initial Requirements": [
                req.description for req in self.requirements
            ],
            "Constraints": self.constraints,
            "Enterprise Options": {
                "generate_user_stories": True,
                "generate_api_spec": True,
                "generate_data_dictionary": True,
                "generate_gherkin": True,
            },
            "_imported_requirements": [req.to_dict() for req in self.requirements],
            "_metadata": {
                **self.metadata,
                "source_format": self.source_format,
                "import_timestamp": self.import_timestamp
            }
        }

    def get_requirement_count(self) -> int:
        """Get total number of imported requirements."""
        return len(self.requirements)

    def get_requirements_by_type(self) -> Dict[str, List[RequirementNode]]:
        """Group requirements by type."""
        result = {}
        for req in self.requirements:
            req_type = req.type or "unknown"
            if req_type not in result:
                result[req_type] = []
            result[req_type].append(req)
        return result


class BaseImporter(ABC):
    """
    Abstract base class for all requirement importers.

    Subclasses must implement:
    - can_import(): Check if this importer can handle a file
    - import_requirements(): Actually import the requirements
    """

    # Human-readable name for the importer
    name: str = "Base Importer"

    # Supported file extensions
    supported_extensions: List[str] = []

    @classmethod
    @abstractmethod
    def can_import(cls, file_path: str) -> bool:
        """
        Check if this importer can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this importer can handle the file, False otherwise
        """
        pass

    @abstractmethod
    async def import_requirements(self, file_path: str) -> ImportResult:
        """
        Import requirements from the given file.

        Args:
            file_path: Path to the file to import

        Returns:
            ImportResult with normalized requirements
        """
        pass

    def _create_requirement_node(
        self,
        req_id: str,
        title: str,
        description: str,
        req_type: str = "functional",
        priority: str = "should",
        source: str = "import",
        **kwargs
    ) -> RequirementNode:
        """
        Helper method to create a RequirementNode.

        Args:
            req_id: Requirement ID
            title: Requirement title
            description: Requirement description
            req_type: Type (functional, non_functional, constraint)
            priority: Priority (must, should, could, wont)
            source: Source of the requirement
            **kwargs: Additional fields

        Returns:
            RequirementNode instance
        """
        return RequirementNode(
            requirement_id=req_id,
            title=title,
            description=description,
            type=req_type,
            priority=priority,
            source=source,
            **kwargs
        )
