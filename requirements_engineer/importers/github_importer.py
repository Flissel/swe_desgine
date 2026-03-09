"""
GitHub Repository Importer

Imports requirements from a public GitHub repository.

Resolution order:
  1. re_ideas/*.json   — pre-extracted project input files in the repo
  2. README.md         — LLM-free heuristic extraction from README text

Usage:
    python run_re_system.py --project https://github.com/owner/repo
    python run_re_system.py --project https://github.com/owner/repo --mode enterprise
"""

import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_importer import BaseImporter, ImportResult
from requirements_engineer.core.re_journal import RequirementNode


_GITHUB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\s?#]+)"
)

# Priority keywords → RE priority
_PRIO_MAP = {
    "must": "must", "required": "must", "shall": "must",
    "should": "should", "recommended": "should",
    "could": "could", "optional": "could", "nice": "could",
}

# Requirement-sentence indicators
_REQ_PATTERNS = [
    re.compile(r"\b(must|shall|should|will|needs? to|has? to|is required to)\b", re.I),
    re.compile(r"\b(support|provide|enable|allow|handle|process|manage|generate)\b", re.I),
]


class GitHubImporter(BaseImporter):
    """
    Importer that reads requirements directly from a GitHub repository.

    Accepts URLs of the form:
        https://github.com/<owner>/<repo>
        https://github.com/<owner>/<repo>/tree/<branch>
    """

    name = "GitHub Repository"
    supported_extensions = []   # URL-based, no extension matching

    # ── Detection ────────────────────────────────────────────────────

    @classmethod
    def can_import(cls, path: str) -> bool:
        return bool(_GITHUB_RE.match(path))

    # ── Entry point ──────────────────────────────────────────────────

    async def import_requirements(self, url: str) -> ImportResult:
        m = _GITHUB_RE.match(url)
        owner, repo_name = m.group("owner"), m.group("repo")
        repo_slug = f"{owner}/{repo_name}"

        print(f"   [GitHub] Importing from {repo_slug}…")

        # Try re_ideas/*.json files first
        json_result = self._try_re_ideas(owner, repo_name)
        if json_result:
            json_result.metadata["git_repo"] = url
            return json_result

        # Fallback: parse README
        readme_result = self._try_readme(owner, repo_name)
        readme_result.metadata["git_repo"] = url
        return readme_result

    # ── Strategy 1: re_ideas/*.json ──────────────────────────────────

    def _try_re_ideas(self, owner: str, repo: str) -> Optional[ImportResult]:
        contents = _gh_api(f"repos/{owner}/{repo}/contents/re_ideas") or []
        if not isinstance(contents, list):
            return None

        json_files = [
            f for f in contents
            if isinstance(f, dict)
            and f.get("name", "").endswith(".json")
            and f.get("name") not in ("index.json",)
        ]
        if not json_files:
            return None

        # Prefer the first (often only) JSON file
        chosen = json_files[0]
        print(f"   [GitHub] Found re_ideas/{chosen['name']} — downloading…")
        raw = _fetch_raw(chosen.get("download_url", ""))
        if not raw:
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        return self._parse_project_json(data, owner, repo, chosen["name"])

    def _parse_project_json(
        self, data: dict, owner: str, repo: str, filename: str
    ) -> ImportResult:
        """Parse a project input JSON (billing-spec or standard format)."""
        project = data.get("project", {})
        raw_reqs = data.get("requirements", [])
        req_nodes: List[RequirementNode] = []

        for i, r in enumerate(raw_reqs):
            if not isinstance(r, dict):
                continue
            rid = r.get("id") or f"REQ-{i+1:03d}"
            title = r.get("title", r.get("description", f"Requirement {i+1}"))
            desc = r.get("description", title)
            cat = r.get("category", "functional")
            prio = _norm_priority(r.get("priority", "should"))

            node = RequirementNode(
                requirement_id=rid,
                title=title[:200],
                description=desc,
                type="functional" if "non" not in cat else "non_functional",
                priority=prio,
                source="github_import",
                acceptance_criteria=r.get("acceptance_criteria", []),
            )
            req_nodes.append(node)

        project_name = (
            project.get("name")
            or project.get("title")
            or repo
        ).replace(" ", "-").lower()

        print(f"   [GitHub] Loaded {len(req_nodes)} requirements from {filename}")
        return ImportResult(
            project_name=project_name,
            project_title=project.get("name") or project.get("title") or repo,
            domain=project.get("domain", "software"),
            context={"description": project.get("description", ""), "source": f"https://github.com/{owner}/{repo}"},
            requirements=req_nodes,
            constraints=data.get("constraints", {}),
            metadata={
                "source_file": filename,
                "github_owner": owner,
                "github_repo": repo,
                "total_requirements": len(req_nodes),
            },
            source_format="github_re_ideas",
        )

    # ── Strategy 2: README extraction ────────────────────────────────

    def _try_readme(self, owner: str, repo: str) -> ImportResult:
        readme_raw = _fetch_raw(
            f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
        ) or _fetch_raw(
            f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
        ) or ""

        req_nodes = _extract_from_readme(readme_raw, owner, repo)

        # Try to get a project name from the first heading
        project_name = repo
        m = re.search(r"^#\s+(.+)", readme_raw, re.M)
        if m:
            project_name = m.group(1).strip()

        print(f"   [GitHub] Extracted {len(req_nodes)} requirements from README")
        return ImportResult(
            project_name=project_name.replace(" ", "-").lower(),
            project_title=project_name,
            domain="software",
            context={"description": f"Imported from GitHub: {owner}/{repo}", "source": f"https://github.com/{owner}/{repo}"},
            requirements=req_nodes,
            constraints={},
            metadata={
                "source_file": "README.md",
                "github_owner": owner,
                "github_repo": repo,
                "total_requirements": len(req_nodes),
            },
            source_format="github_readme",
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gh_api(endpoint: str) -> Any:
    """Call GitHub API via `gh api` CLI (respects auth token)."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def _fetch_raw(url: str) -> Optional[str]:
    """Fetch a raw URL; returns None on any error."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _norm_priority(raw: str) -> str:
    raw_l = raw.lower()
    for kw, prio in _PRIO_MAP.items():
        if kw in raw_l:
            return prio
    return "should"


def _extract_from_readme(text: str, owner: str, repo: str) -> List[RequirementNode]:
    """Heuristic extraction: sentences that look like requirements."""
    nodes: List[RequirementNode] = []
    counter = 1

    for line in text.splitlines():
        line = line.strip().lstrip("- *•").strip()
        if len(line) < 20 or len(line) > 400:
            continue
        if any(p.search(line) for p in _REQ_PATTERNS):
            rid = f"REQ-{owner[:4].upper()}-{counter:03d}"
            nodes.append(RequirementNode(
                requirement_id=rid,
                title=line[:200],
                description=line,
                type="functional",
                priority="should",
                source="github_readme",
                acceptance_criteria=[],
            ))
            counter += 1

    return nodes
