"""
Change Detector - Identifies what changed in a file and extracts affected node IDs.

Supports JSON and Markdown formats used in the RE System.
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
import difflib

from .models import ChangeInfo


class ChangeDetector:
    """
    Detects and classifies changes in RE System files.

    Identifies which nodes were affected by a file change.
    """

    def __init__(self, project_path: Path):
        """
        Initialize the change detector.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self._file_cache: Dict[str, str] = {}  # file_path -> content

    def cache_file(self, file_path: str):
        """
        Cache the current content of a file for later comparison.

        Args:
            file_path: Path to the file to cache
        """
        path = Path(file_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._file_cache[str(path)] = f.read()
            except IOError:
                pass

    def get_cached_content(self, file_path: str) -> Optional[str]:
        """Get cached content for a file."""
        return self._file_cache.get(str(file_path))

    def detect_change(self, file_path: str, old_content: Optional[str] = None) -> ChangeInfo:
        """
        Detect what changed in a file.

        Args:
            file_path: Path to the changed file
            old_content: Previous content (if None, uses cached content)

        Returns:
            ChangeInfo with details about the change
        """
        path = Path(file_path)
        file_type = self._get_file_type(path)

        # Get old content from cache if not provided
        if old_content is None:
            old_content = self._file_cache.get(str(path))

        # Read new content
        new_content = ""
        change_type = "modified"

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    new_content = f.read()
            except IOError:
                pass

            if old_content is None:
                change_type = "created"
        else:
            change_type = "deleted"

        # Generate diff summary
        diff_summary = self._generate_diff_summary(old_content, new_content)

        # Detect affected nodes based on file type
        affected_nodes = self._detect_affected_nodes(
            file_path, file_type, old_content, new_content
        )

        # Update cache with new content
        if new_content:
            self._file_cache[str(path)] = new_content
        elif str(path) in self._file_cache:
            del self._file_cache[str(path)]

        return ChangeInfo(
            file_path=str(file_path),
            file_type=file_type,
            change_type=change_type,
            affected_node_ids=affected_nodes,
            old_content=old_content,
            new_content=new_content,
            diff_summary=diff_summary,
            timestamp=datetime.now().isoformat()
        )

    def _get_file_type(self, path: Path) -> str:
        """Determine the file type based on path and name."""
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name == "journal.json":
            return "journal"
        elif name == "user_stories.md":
            return "user_stories"
        elif name == "task_list.json":
            return "tasks"
        elif name == "data_dictionary.md":
            return "data_dictionary"
        elif name == "feature_breakdown.md":
            return "feature_breakdown"
        elif name == "api_documentation.md":
            return "api"
        elif suffix == ".mmd":
            return "diagram"
        elif suffix == ".feature":
            return "test"
        elif suffix == ".json":
            return "json"
        elif suffix == ".md":
            return "markdown"
        else:
            return "unknown"

    def _generate_diff_summary(self, old_content: Optional[str], new_content: str) -> str:
        """Generate a human-readable diff summary."""
        if old_content is None:
            return "Neue Datei erstellt"

        if not new_content:
            return "Datei gelöscht"

        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=''))

        # Count changes
        added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        if added == 0 and removed == 0:
            return "Keine Änderungen erkannt"

        return f"{added} Zeilen hinzugefügt, {removed} Zeilen entfernt"

    def _detect_affected_nodes(
        self,
        file_path: str,
        file_type: str,
        old_content: Optional[str],
        new_content: str
    ) -> List[str]:
        """Detect which nodes were affected by the change."""
        if file_type == "journal":
            return self._detect_journal_changes(old_content, new_content)
        elif file_type == "user_stories":
            return self._detect_user_story_changes(old_content, new_content)
        elif file_type == "tasks":
            return self._detect_task_changes(old_content, new_content)
        elif file_type == "diagram":
            return self._detect_diagram_node(file_path)
        elif file_type == "test":
            return self._detect_test_changes(old_content, new_content)
        else:
            return []

    def _detect_journal_changes(self, old_content: Optional[str], new_content: str) -> List[str]:
        """Find changed node IDs in journal.json."""
        affected = []

        try:
            old_data = json.loads(old_content) if old_content else {"nodes": {}}
            new_data = json.loads(new_content) if new_content else {"nodes": {}}
        except json.JSONDecodeError:
            return []

        old_nodes = old_data.get("nodes", {})
        new_nodes = new_data.get("nodes", {})

        # Find added nodes
        for node_id in new_nodes:
            if node_id not in old_nodes:
                affected.append(node_id)

        # Find removed nodes
        for node_id in old_nodes:
            if node_id not in new_nodes:
                affected.append(node_id)

        # Find modified nodes
        for node_id in new_nodes:
            if node_id in old_nodes:
                if json.dumps(old_nodes[node_id], sort_keys=True) != json.dumps(new_nodes[node_id], sort_keys=True):
                    affected.append(node_id)

        return list(set(affected))

    def _detect_user_story_changes(self, old_content: Optional[str], new_content: str) -> List[str]:
        """Find changed Epic/UserStory IDs in user_stories.md."""
        affected = []

        # Extract IDs from old content
        old_ids = set()
        if old_content:
            old_ids.update(re.findall(r'(EPIC-\d+|US-\d+)', old_content))

        # Extract IDs from new content
        new_ids = set()
        if new_content:
            new_ids.update(re.findall(r'(EPIC-\d+|US-\d+)', new_content))

        # Added or removed IDs are affected
        affected.extend(old_ids.symmetric_difference(new_ids))

        # For modified content, we need to compare sections
        if old_content and new_content:
            old_sections = self._extract_markdown_sections(old_content)
            new_sections = self._extract_markdown_sections(new_content)

            for section_id, new_section in new_sections.items():
                if section_id in old_sections:
                    if old_sections[section_id] != new_section:
                        affected.append(section_id)

        return list(set(affected))

    def _extract_markdown_sections(self, content: str) -> Dict[str, str]:
        """Extract sections from markdown content by heading ID."""
        sections = {}
        current_id = None
        current_content = []

        for line in content.split('\n'):
            # Check for Epic or User Story heading
            match = re.match(r'^##\s+(EPIC-\d+):', line)
            if match:
                if current_id:
                    sections[current_id] = '\n'.join(current_content)
                current_id = match.group(1)
                current_content = [line]
                continue

            match = re.match(r'^###\s+(US-\d+):', line)
            if match:
                if current_id:
                    sections[current_id] = '\n'.join(current_content)
                current_id = match.group(1)
                current_content = [line]
                continue

            if current_id:
                current_content.append(line)

        if current_id:
            sections[current_id] = '\n'.join(current_content)

        return sections

    def _detect_task_changes(self, old_content: Optional[str], new_content: str) -> List[str]:
        """Find changed task IDs in task_list.json."""
        affected = []

        try:
            old_data = json.loads(old_content) if old_content else {"tasks": []}
            new_data = json.loads(new_content) if new_content else {"tasks": []}
        except json.JSONDecodeError:
            return []

        old_tasks = {t.get("id"): t for t in old_data.get("tasks", [])}
        new_tasks = {t.get("id"): t for t in new_data.get("tasks", [])}

        # Find added tasks
        for task_id in new_tasks:
            if task_id and task_id not in old_tasks:
                affected.append(task_id)

        # Find removed tasks
        for task_id in old_tasks:
            if task_id and task_id not in new_tasks:
                affected.append(task_id)

        # Find modified tasks
        for task_id in new_tasks:
            if task_id and task_id in old_tasks:
                if json.dumps(old_tasks[task_id], sort_keys=True) != json.dumps(new_tasks[task_id], sort_keys=True):
                    affected.append(task_id)

        return list(set(affected))

    def _detect_diagram_node(self, file_path: str) -> List[str]:
        """Extract node ID from diagram filename."""
        path = Path(file_path)
        stem = path.stem

        # Filename format: REQ-001_flowchart.mmd or EPIC-001_sequence.mmd
        parts = stem.split('_')
        if parts:
            node_id = parts[0]
            # Check if it looks like a valid ID
            if re.match(r'^(REQ|AUTO|EPIC|US|TASK|FR|NFR)-', node_id):
                return [node_id]

        return []

    def _detect_test_changes(self, old_content: Optional[str], new_content: str) -> List[str]:
        """Find affected requirements from test feature files."""
        affected = []

        # Look for requirement references in tags or comments
        # @REQ-001 or # Requirement: REQ-001
        if new_content:
            req_refs = re.findall(r'@?(REQ-\d+|AUTO-\d+)', new_content)
            affected.extend(req_refs)

        return list(set(affected))

    def get_detailed_diff(self, old_content: Optional[str], new_content: str) -> List[str]:
        """Get detailed unified diff."""
        if old_content is None:
            return [f"+{line}" for line in new_content.splitlines()]

        if not new_content:
            return [f"-{line}" for line in old_content.splitlines()]

        return list(difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            lineterm='',
            fromfile='original',
            tofile='modified'
        ))
