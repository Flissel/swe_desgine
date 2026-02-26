"""
Standard Importer - Imports the standard RE-System JSON format.

This importer handles the native format used by sample_project.json
and other standard RE-System project files.
"""

import json
import os
from typing import Dict, Any, List

from .base_importer import BaseImporter, ImportResult
from requirements_engineer.core.re_journal import RequirementNode


class StandardImporter(BaseImporter):
    """
    Importer for standard RE-System JSON format.

    Expected format:
    {
        "Name": "project_id",
        "Title": "Project Title",
        "Domain": "e-commerce",
        "Context": "Description" or {"business": "...", "domain": "..."},
        "Stakeholders": [...],
        "Initial Requirements": ["req1", "req2"],
        "Constraints": {...}
    }
    """

    name = "Standard RE-System"
    supported_extensions = [".json"]

    @classmethod
    def can_import(cls, file_path: str) -> bool:
        """Check if file is standard RE-System format."""
        if not file_path.endswith('.json'):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Standard format has "Name" and "Initial Requirements"
            has_name = "Name" in data
            has_requirements = "Initial Requirements" in data
            # Should NOT have "project" with "autonomy_level" (that's billing format)
            is_billing = "project" in data and "autonomy_level" in data.get("project", {})

            return has_name and has_requirements and not is_billing
        except Exception:
            return False

    async def import_requirements(self, file_path: str) -> ImportResult:
        """Import requirements from standard format."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract context (can be string or dict)
        context = data.get("Context", {})
        if isinstance(context, str):
            context = {"description": context}

        # Create requirements from "Initial Requirements" list
        requirements = []
        initial_reqs = data.get("Initial Requirements", [])

        for idx, req_text in enumerate(initial_reqs, start=1):
            req_id = f"REQ-{str(idx).zfill(3)}"

            # Try to determine type from text
            req_type = self._infer_type(req_text)
            priority = self._infer_priority(req_text)

            node = self._create_requirement_node(
                req_id=req_id,
                title=self._extract_title(req_text),
                description=req_text,
                req_type=req_type,
                priority=priority,
                source="standard_import"
            )
            requirements.append(node)

        # Also import pre-imported requirements if they exist
        imported_reqs = data.get("_imported_requirements", [])
        for req_data in imported_reqs:
            node = RequirementNode(
                requirement_id=req_data.get("requirement_id", f"IMP-{len(requirements)+1}"),
                title=req_data.get("title", ""),
                description=req_data.get("description", ""),
                type=req_data.get("type", "functional"),
                priority=req_data.get("priority", "should"),
                source=req_data.get("source", "imported")
            )
            requirements.append(node)

        return ImportResult(
            project_name=data.get("Name", "unnamed_project"),
            project_title=data.get("Title", data.get("Name", "Unnamed Project")),
            domain=data.get("Domain", "general"),
            context=context,
            stakeholders=data.get("Stakeholders", []),
            requirements=requirements,
            constraints=data.get("Constraints", {}),
            metadata=data.get("Enterprise Options", {}),
            source_format="standard"
        )

    def _infer_type(self, text: str) -> str:
        """Infer requirement type from text content."""
        text_lower = text.lower()

        # Non-functional indicators
        nfr_keywords = [
            "performance", "security", "scalability", "availability",
            "reliability", "usability", "maintainability", "portability",
            "response time", "throughput", "concurrent", "latency"
        ]

        if any(kw in text_lower for kw in nfr_keywords):
            return "non_functional"

        # Constraint indicators
        constraint_keywords = [
            "must use", "required to", "constraint", "limitation",
            "compliance", "regulation", "legal", "budget"
        ]

        if any(kw in text_lower for kw in constraint_keywords):
            return "constraint"

        return "functional"

    def _infer_priority(self, text: str) -> str:
        """Infer priority from text content."""
        text_lower = text.lower()

        if "must" in text_lower or "critical" in text_lower or "essential" in text_lower:
            return "must"
        elif "should" in text_lower or "important" in text_lower:
            return "should"
        elif "could" in text_lower or "nice to have" in text_lower:
            return "could"
        elif "won't" in text_lower or "future" in text_lower:
            return "wont"

        return "should"  # Default

    def _extract_title(self, text: str) -> str:
        """Extract a title from requirement text."""
        # Take first sentence or first 50 chars
        if "." in text:
            title = text.split(".")[0]
        else:
            title = text[:50]

        # Clean up
        title = title.strip()
        if len(title) > 60:
            title = title[:57] + "..."

        return title
