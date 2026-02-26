"""
Self-Critique Engine - LLM reviews and improves its own outputs.

Performs automated quality review of generated artifacts:
- Consistency: Checks for contradictions between requirements
- Completeness: Identifies missing aspects or gaps
- Testability: Validates acceptance criteria are measurable
- Traceability: Verifies links between requirements, stories, and tests
"""

import os
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

# Try to import OpenAI, fall back gracefully
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Import LLM logger
import time
from pathlib import Path
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call

# Import generator data structures for auto-fix
try:
    from requirements_engineer.generators.user_story_generator import AcceptanceCriterion
    from requirements_engineer.generators.test_case_generator import TestCase, TestStep
    HAS_GENERATORS = True
except ImportError:
    HAS_GENERATORS = False


class IssueSeverity(Enum):
    """Severity levels for critique issues."""
    CRITICAL = "critical"  # Must fix before proceeding
    HIGH = "high"          # Should fix, impacts quality
    MEDIUM = "medium"      # Recommended to fix
    LOW = "low"            # Nice to have improvement
    INFO = "info"          # Informational note


class IssueCategory(Enum):
    """Categories of critique issues."""
    CONSISTENCY = "consistency"
    COMPLETENESS = "completeness"
    TESTABILITY = "testability"
    TRACEABILITY = "traceability"
    CLARITY = "clarity"
    FEASIBILITY = "feasibility"


@dataclass
class CritiqueIssue:
    """A single issue found during critique."""
    id: str
    category: IssueCategory
    severity: IssueSeverity
    title: str
    description: str
    affected_artifacts: List[str] = field(default_factory=list)
    suggestion: str = ""
    auto_fixable: bool = False
    fixed: bool = False
    fix_strategy: str = "manual"  # programmatic, llm_assisted, manual
    fix_details: str = ""         # Description of what was done to fix

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "affected_artifacts": self.affected_artifacts,
            "suggestion": self.suggestion,
            "auto_fixable": self.auto_fixable,
            "fixed": self.fixed,
            "fix_strategy": self.fix_strategy,
            "fix_details": self.fix_details,
        }

    def to_markdown(self) -> str:
        severity_emoji = {
            IssueSeverity.CRITICAL: "🔴",
            IssueSeverity.HIGH: "🟠",
            IssueSeverity.MEDIUM: "🟡",
            IssueSeverity.LOW: "🟢",
            IssueSeverity.INFO: "ℹ️"
        }
        emoji = severity_emoji.get(self.severity, "")
        md = f"### {emoji} {self.id}: {self.title}\n\n"
        md += f"**Category:** {self.category.value}\n"
        md += f"**Severity:** {self.severity.value}\n"
        md += f"**Affected:** {', '.join(self.affected_artifacts)}\n\n"
        md += f"{self.description}\n\n"
        if self.suggestion:
            md += f"**Suggestion:** {self.suggestion}\n\n"
        if self.fixed:
            md += f"**Status:** ✅ Auto-fixed\n\n"
        return md


@dataclass
class CritiqueResult:
    """Complete result of a self-critique pass."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    issues: List[CritiqueIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def count_by_severity(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in IssueSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts

    def count_by_category(self) -> Dict[str, int]:
        counts = {c.value: 0 for c in IssueCategory}
        for issue in self.issues:
            counts[issue.category.value] += 1
        return counts

    def to_markdown(self) -> str:
        md = "# Self-Critique Report\n\n"
        md += f"**Generated:** {self.timestamp}\n\n"

        # Summary
        md += "## Summary\n\n"
        md += f"- **Quality Score:** {self.quality_score:.1f}/10\n"
        md += f"- **Total Issues:** {len(self.issues)}\n\n"

        # By severity
        md += "### Issues by Severity\n\n"
        for severity, count in self.count_by_severity().items():
            if count > 0:
                md += f"- {severity}: {count}\n"
        md += "\n"

        # By category
        md += "### Issues by Category\n\n"
        for category, count in self.count_by_category().items():
            if count > 0:
                md += f"- {category}: {count}\n"
        md += "\n"

        # Recommendations
        if self.recommendations:
            md += "## Key Recommendations\n\n"
            for i, rec in enumerate(self.recommendations, 1):
                md += f"{i}. {rec}\n"
            md += "\n"

        # Detailed issues
        md += "---\n\n## Detailed Issues\n\n"

        # Group by category
        for category in IssueCategory:
            category_issues = [i for i in self.issues if i.category == category]
            if category_issues:
                md += f"### {category.value.title()}\n\n"
                for issue in category_issues:
                    md += issue.to_markdown()

        return md

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "quality_score": self.quality_score,
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
            "recommendations": self.recommendations
        }, indent=2)


class SelfCritiqueEngine:
    """
    LLM-based self-critique engine for requirements artifacts.

    Reviews generated outputs for:
    - Consistency: No contradictions between requirements
    - Completeness: All necessary aspects covered
    - Testability: Acceptance criteria are measurable
    - Traceability: Links between artifacts are valid
    """

    CONSISTENCY_PROMPT = """You are a Requirements Engineering expert reviewing for CONSISTENCY.

Analyze these requirements and user stories for contradictions or conflicts:

REQUIREMENTS:
{requirements}

USER STORIES:
{user_stories}

Find any:
1. Contradictory statements (A says X, B says not X)
2. Conflicting priorities or timelines
3. Incompatible technical constraints
4. Overlapping responsibilities without clear boundaries

Return JSON:
{{
    "issues": [
        {{
            "title": "Brief issue title",
            "description": "What is contradictory",
            "affected": ["REQ-001", "US-002"],
            "severity": "high|medium|low",
            "suggestion": "How to resolve"
        }}
    ]
}}

If no issues found, return {{"issues": []}}
Return ONLY valid JSON."""

    COMPLETENESS_PROMPT = """You are a Requirements Engineering expert reviewing for COMPLETENESS.

Analyze these requirements for missing aspects:

REQUIREMENTS:
{requirements}

DOMAIN: {domain}

Check for:
1. Missing error handling scenarios
2. Missing edge cases
3. Unclear or undefined terms
4. Missing non-functional requirements (security, performance, etc.)
5. Incomplete user journeys
6. Missing integration points

Return JSON:
{{
    "issues": [
        {{
            "title": "What is missing",
            "description": "Why it should be added",
            "affected": ["REQ-001"],
            "severity": "high|medium|low",
            "suggestion": "What to add"
        }}
    ],
    "missing_areas": ["list of topics not covered"]
}}

Return ONLY valid JSON."""

    TESTABILITY_PROMPT = """You are a QA Engineering expert reviewing for TESTABILITY.

Analyze these user stories and acceptance criteria:

USER STORIES:
{user_stories}

TEST CASES:
{test_cases}

Check for:
1. Vague acceptance criteria (not measurable)
2. Missing boundary conditions
3. Untestable requirements (subjective terms like "fast", "easy")
4. Missing negative test scenarios
5. Gaps in test coverage

Return JSON:
{{
    "issues": [
        {{
            "title": "Testability problem",
            "description": "Why it's hard to test",
            "affected": ["US-001", "TC-002"],
            "severity": "high|medium|low",
            "suggestion": "How to make testable"
        }}
    ],
    "coverage_gaps": ["areas without sufficient tests"]
}}

Return ONLY valid JSON."""

    TRACEABILITY_PROMPT = """You are a Requirements Engineering expert reviewing for TRACEABILITY.

Analyze the links between artifacts:

REQUIREMENTS:
{requirements}

USER STORIES:
{user_stories}

TEST CASES:
{test_cases}

Check for:
1. Requirements without user stories (orphans)
2. User stories without test cases
3. Test cases referencing non-existent requirements
4. Broken or unclear links
5. Missing bi-directional traceability

Return JSON:
{{
    "issues": [
        {{
            "title": "Traceability gap",
            "description": "What link is missing or broken",
            "affected": ["REQ-001"],
            "severity": "high|medium|low",
            "suggestion": "How to fix tracing"
        }}
    ],
    "orphan_requirements": ["REQ-IDs without stories"],
    "orphan_stories": ["US-IDs without tests"]
}}

Return ONLY valid JSON."""

    ACCEPTANCE_CRITERIA_PROMPT = """You are a Requirements Engineering expert.

Generate acceptance criteria in Given-When-Then format for these user stories:

{stories_text}

For EACH story, return 2-3 specific, measurable acceptance criteria.

Return JSON:
{{
    "stories": [
        {{
            "id": "US-001",
            "acceptance_criteria": [
                {{
                    "given": "a specific precondition",
                    "when": "the user performs an action",
                    "then": "a specific observable result"
                }}
            ]
        }}
    ]
}}

Return ONLY valid JSON."""

    SUBJECTIVE_TERMS_PROMPT = """You are a QA expert. These user stories contain subjective/untestable terms.
For each affected story, add ONE measurable acceptance criterion that quantifies the vague term.

{stories_text}

Return JSON:
{{
    "stories": [
        {{
            "id": "US-001",
            "vague_term": "quickly",
            "acceptance_criteria": {{
                "given": "the system is under normal load",
                "when": "the user performs the action",
                "then": "response time is less than 200ms"
            }}
        }}
    ]
}}

Return ONLY valid JSON."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Self-Critique Engine.

        Args:
            model_name: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with critique section
        """
        self.config = config or {}
        critique_config = self.config.get("critique", {})

        self.model_name = model_name or critique_config.get("model", "google/gemini-2.0-flash-exp:free")
        self.temperature = critique_config.get("temperature", 0.3)
        self.max_tokens = critique_config.get("max_tokens", 8000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None
        self.issue_counter = 0

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def _call_llm(self, prompt: str, max_tokens: int = None) -> str:
        """Call the LLM and return the response."""
        if not self.client:
            await self.initialize()

        # Use config max_tokens if not specified
        if max_tokens is None:
            max_tokens = self.max_tokens

        start_time = time.time()
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are a senior Requirements Engineering expert. Analyze artifacts critically and return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=max_tokens
        )
        latency_ms = int((time.time() - start_time) * 1000)

        response_text = response.choices[0].message.content.strip()

        # Log the LLM call
        log_llm_call(
            component="self_critique",
            model=self.model_name,
            response=response,
            latency_ms=latency_ms,
            system_message="You are a senior Requirements Engineering expert. Analyze artifacts critically and return valid JSON.",
            user_message=prompt,
            response_text=response_text,
        )

        return response_text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return {"issues": []}

    def _create_issue(
        self,
        category: IssueCategory,
        data: Dict[str, Any]
    ) -> CritiqueIssue:
        """Create a CritiqueIssue from parsed data."""
        self.issue_counter += 1

        severity_map = {
            "critical": IssueSeverity.CRITICAL,
            "high": IssueSeverity.HIGH,
            "medium": IssueSeverity.MEDIUM,
            "low": IssueSeverity.LOW,
            "info": IssueSeverity.INFO
        }

        return CritiqueIssue(
            id=f"CI-{self.issue_counter:03d}",
            category=category,
            severity=severity_map.get(data.get("severity", "medium"), IssueSeverity.MEDIUM),
            title=data.get("title", "Untitled Issue"),
            description=data.get("description", ""),
            affected_artifacts=data.get("affected", []),
            suggestion=data.get("suggestion", "")
        )

    def _format_requirements(self, requirements: List) -> str:
        """Format requirements for prompt."""
        lines = []
        for req in requirements[:30]:  # Limit to prevent token overflow
            lines.append(f"- {req.requirement_id}: {req.title}")
            if req.description:
                lines.append(f"  {req.description[:200]}")
        return "\n".join(lines)

    def _format_user_stories(self, user_stories: List) -> str:
        """Format user stories for prompt."""
        lines = []
        for us in user_stories[:20]:
            lines.append(f"- {us.id}: {us.title}")
            lines.append(f"  As a {us.persona}, I want to {us.action}, so that {us.benefit}")
            if us.parent_requirement_id:
                lines.append(f"  [Links to: {us.parent_requirement_id}]")
        return "\n".join(lines)

    def _format_test_cases(self, test_cases: List) -> str:
        """Format test cases for prompt."""
        lines = []
        for tc in test_cases[:30]:
            lines.append(f"- {tc.id}: {tc.title}")
            if hasattr(tc, 'parent_user_story_id') and tc.parent_user_story_id:
                lines.append(f"  [Links to: {tc.parent_user_story_id}]")
        return "\n".join(lines)

    async def check_consistency(
        self,
        requirements: List,
        user_stories: List
    ) -> List[CritiqueIssue]:
        """Check for consistency issues."""
        print("    Checking consistency...")

        prompt = self.CONSISTENCY_PROMPT.format(
            requirements=self._format_requirements(requirements),
            user_stories=self._format_user_stories(user_stories)
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(self._create_issue(IssueCategory.CONSISTENCY, issue_data))

        return issues

    async def check_completeness(
        self,
        requirements: List,
        domain: str = ""
    ) -> List[CritiqueIssue]:
        """Check for completeness issues."""
        print("    Checking completeness...")

        prompt = self.COMPLETENESS_PROMPT.format(
            requirements=self._format_requirements(requirements),
            domain=domain or "Software System"
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(self._create_issue(IssueCategory.COMPLETENESS, issue_data))

        return issues

    async def check_testability(
        self,
        user_stories: List,
        test_cases: List
    ) -> List[CritiqueIssue]:
        """Check for testability issues."""
        print("    Checking testability...")

        prompt = self.TESTABILITY_PROMPT.format(
            user_stories=self._format_user_stories(user_stories),
            test_cases=self._format_test_cases(test_cases)
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(self._create_issue(IssueCategory.TESTABILITY, issue_data))

        return issues

    async def check_traceability(
        self,
        requirements: List,
        user_stories: List,
        test_cases: List
    ) -> List[CritiqueIssue]:
        """Check for traceability issues."""
        print("    Checking traceability...")

        prompt = self.TRACEABILITY_PROMPT.format(
            requirements=self._format_requirements(requirements),
            user_stories=self._format_user_stories(user_stories),
            test_cases=self._format_test_cases(test_cases)
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        issues = []
        for issue_data in data.get("issues", []):
            issues.append(self._create_issue(IssueCategory.TRACEABILITY, issue_data))

        return issues

    def _calculate_quality_score(self, issues: List[CritiqueIssue]) -> float:
        """Calculate overall quality score based on issues found."""
        if not issues:
            return 10.0

        # Deduct points based on severity
        deductions = {
            IssueSeverity.CRITICAL: 2.0,
            IssueSeverity.HIGH: 1.0,
            IssueSeverity.MEDIUM: 0.5,
            IssueSeverity.LOW: 0.2,
            IssueSeverity.INFO: 0.0
        }

        total_deduction = sum(deductions.get(i.severity, 0.5) for i in issues)
        score = max(0.0, 10.0 - total_deduction)

        return round(score, 1)

    def _generate_recommendations(self, issues: List[CritiqueIssue]) -> List[str]:
        """Generate top recommendations based on issues."""
        recommendations = []

        # Count by category
        by_category = {}
        for issue in issues:
            cat = issue.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        # Generate recommendations based on most common issues
        if by_category.get("consistency", 0) > 2:
            recommendations.append("Review requirements for conflicting statements and resolve contradictions")

        if by_category.get("completeness", 0) > 3:
            recommendations.append("Conduct additional requirement elicitation to fill identified gaps")

        if by_category.get("testability", 0) > 2:
            recommendations.append("Refine acceptance criteria to be more specific and measurable")

        if by_category.get("traceability", 0) > 2:
            recommendations.append("Establish clear links between requirements, user stories, and test cases")

        # Add critical issue recommendations
        critical_issues = [i for i in issues if i.severity == IssueSeverity.CRITICAL]
        if critical_issues:
            recommendations.insert(0, f"URGENT: Address {len(critical_issues)} critical issues before proceeding")

        return recommendations[:5]  # Top 5 recommendations

    # ================================================================
    # Auto-Fix Methods
    # ================================================================

    def _classify_fixability(self, issues: List[CritiqueIssue]) -> None:
        """Classify each issue as auto-fixable or manual.

        Modifies issues in-place, setting auto_fixable and fix_strategy.
        """
        for issue in issues:
            title_lower = issue.title.lower()
            cat = issue.category

            if cat == IssueCategory.TRACEABILITY and "orphan" in title_lower:
                issue.auto_fixable = True
                issue.fix_strategy = "programmatic"
            elif cat == IssueCategory.TRACEABILITY and (
                "without test" in title_lower or "test coverage" in title_lower
            ):
                issue.auto_fixable = True
                issue.fix_strategy = "programmatic"
            elif cat == IssueCategory.TESTABILITY and "acceptance criteria" in title_lower:
                issue.auto_fixable = True
                issue.fix_strategy = "llm_assisted"
            elif cat == IssueCategory.TESTABILITY and (
                "subjective" in title_lower or "untestable" in title_lower
            ):
                issue.auto_fixable = True
                issue.fix_strategy = "llm_assisted"

    async def apply_auto_fixes(
        self,
        issues: List[CritiqueIssue],
        requirements: List,
        user_stories: List,
        test_cases: List,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply auto-fixes to all fixable issues.

        Returns:
            Dict with fixed_count, skipped_count, fix_log, modified_artifacts.
        """
        fix_log: List[str] = []
        fixed_count = 0
        skipped_count = 0
        modified_artifacts: set = set()

        for issue in issues:
            if not issue.auto_fixable or issue.fixed:
                continue

            try:
                if issue.fix_strategy == "programmatic":
                    fixes = self._dispatch_programmatic_fix(
                        issue, requirements, user_stories, test_cases
                    )
                elif issue.fix_strategy == "llm_assisted":
                    fixes = await self._dispatch_llm_fix(issue, user_stories)
                else:
                    skipped_count += 1
                    continue

                if fixes:
                    issue.fixed = True
                    issue.fix_details = "; ".join(fixes)
                    fix_log.extend(fixes)
                    fixed_count += 1
                    modified_artifacts.update(issue.affected_artifacts)
                else:
                    skipped_count += 1

            except Exception as e:
                fix_log.append(f"Failed to fix {issue.id}: {e}")
                skipped_count += 1

        return {
            "fixed_count": fixed_count,
            "skipped_count": skipped_count,
            "fix_log": fix_log,
            "modified_artifacts": modified_artifacts,
        }

    def _dispatch_programmatic_fix(
        self,
        issue: CritiqueIssue,
        requirements: List,
        user_stories: List,
        test_cases: List,
    ) -> List[str]:
        """Route a programmatic fix to the appropriate fixer."""
        title_lower = issue.title.lower()
        if "orphan" in title_lower:
            return self._fix_orphan_requirements(issue, requirements, user_stories)
        elif "without test" in title_lower or "test coverage" in title_lower:
            return self._fix_stories_without_tests(issue, user_stories, test_cases)
        return []

    async def _dispatch_llm_fix(
        self,
        issue: CritiqueIssue,
        user_stories: List,
    ) -> List[str]:
        """Route an LLM-assisted fix to the appropriate fixer."""
        title_lower = issue.title.lower()
        if "acceptance criteria" in title_lower:
            return await self._fix_missing_acceptance_criteria(issue, user_stories)
        elif "subjective" in title_lower or "untestable" in title_lower:
            return await self._fix_subjective_terms(issue, user_stories)
        return []

    def _fix_orphan_requirements(
        self,
        issue: CritiqueIssue,
        requirements: List,
        user_stories: List,
    ) -> List[str]:
        """Link orphan requirements to matching user stories via keyword overlap."""
        if not user_stories:
            return []

        fixes = []
        # Build requirement lookup
        req_map = {}
        for req in requirements:
            rid = getattr(req, "requirement_id", None) or getattr(req, "id", "")
            if rid:
                req_map[rid] = req

        # Stopwords for keyword matching
        stopwords = {"the", "a", "an", "is", "are", "to", "of", "in", "for", "and", "or", "as", "i", "want", "so", "that"}

        for orphan_id in issue.affected_artifacts:
            req = req_map.get(orphan_id)
            if not req:
                continue

            # Tokenize requirement title
            req_title = getattr(req, "title", "") or ""
            req_words = {w.lower() for w in re.split(r'\W+', req_title) if w.lower() not in stopwords and len(w) > 2}

            if not req_words:
                continue

            # Find best-matching user story
            best_story = None
            best_score = 0
            for story in user_stories:
                story_title = getattr(story, "title", "") or ""
                story_action = getattr(story, "action", "") or ""
                story_text = f"{story_title} {story_action}"
                story_words = {w.lower() for w in re.split(r'\W+', story_text) if w.lower() not in stopwords and len(w) > 2}
                overlap = len(req_words & story_words)
                if overlap > best_score:
                    best_score = overlap
                    best_story = story

            if best_story and best_score > 0:
                # Link the story to the requirement
                story_id = getattr(best_story, "id", "")
                if hasattr(best_story, "linked_requirement_ids"):
                    if orphan_id not in best_story.linked_requirement_ids:
                        best_story.linked_requirement_ids.append(orphan_id)
                if not getattr(best_story, "parent_requirement_id", ""):
                    best_story.parent_requirement_id = orphan_id
                fixes.append(f"Linked {orphan_id} to {story_id} (keyword overlap: {best_score})")

        return fixes

    def _fix_stories_without_tests(
        self,
        issue: CritiqueIssue,
        user_stories: List,
        test_cases: List,
    ) -> List[str]:
        """Create stub test cases for user stories without test coverage."""
        if not HAS_GENERATORS:
            return []

        fixes = []
        # Find existing TC IDs to avoid collisions
        existing_ids = {getattr(tc, "id", "") for tc in test_cases}
        tc_counter = len(test_cases) + 1

        # Build story lookup
        story_map = {}
        for story in user_stories:
            sid = getattr(story, "id", "")
            if sid:
                story_map[sid] = story

        for story_id in issue.affected_artifacts:
            story = story_map.get(story_id)
            if not story:
                continue

            # Generate unique TC ID
            while f"TC-{tc_counter:03d}" in existing_ids:
                tc_counter += 1
            tc_id = f"TC-{tc_counter:03d}"
            existing_ids.add(tc_id)
            tc_counter += 1

            persona = getattr(story, "persona", "user")
            action = getattr(story, "action", "perform action")
            benefit = getattr(story, "benefit", "achieve goal")
            title = getattr(story, "title", story_id)
            parent_req = getattr(story, "parent_requirement_id", "")

            # Build meaningful steps from acceptance criteria
            ac_list = getattr(story, "acceptance_criteria", None) or []
            if ac_list and isinstance(ac_list, list) and len(ac_list) > 0:
                steps = [
                    TestStep(step_type="Given", description=f"{persona} is authenticated and on the relevant page"),
                    TestStep(step_type="When", description=f"{persona} performs: {action}"),
                ]
                for ac in ac_list[:5]:
                    ac_text = ac if isinstance(ac, str) else str(ac)
                    steps.append(TestStep(step_type="Then", description=ac_text))
            else:
                steps = [
                    TestStep(step_type="Given", description=f"{persona} is authenticated"),
                    TestStep(step_type="When", description=f"{persona} {action}"),
                    TestStep(step_type="Then", description=f"System confirms: {benefit}"),
                ]

            stub_tc = TestCase(
                id=tc_id,
                title=f"Verify {title}",
                description=f"Test case for {story_id} - verifies acceptance criteria",
                preconditions=[f"{persona} is authenticated", "System is in a valid state"],
                steps=steps,
                expected_result=benefit,
                priority="medium",
                test_type="functional",
                parent_user_story_id=story_id,
                parent_requirement_id=parent_req,
            )
            test_cases.append(stub_tc)
            fixes.append(f"Created stub {tc_id} for {story_id}")

        return fixes

    async def _fix_missing_acceptance_criteria(
        self,
        issue: CritiqueIssue,
        user_stories: List,
    ) -> List[str]:
        """Generate acceptance criteria for stories that lack them (LLM-assisted)."""
        if not HAS_GENERATORS:
            return []

        fixes = []
        # Build story lookup
        story_map = {}
        for story in user_stories:
            sid = getattr(story, "id", "")
            if sid:
                story_map[sid] = story

        # Collect stories that need acceptance criteria
        stories_to_fix = []
        for story_id in issue.affected_artifacts:
            story = story_map.get(story_id)
            if story and not getattr(story, "acceptance_criteria", None):
                stories_to_fix.append(story)

        if not stories_to_fix:
            return []

        # Batch up to 5 stories per LLM call
        batch_size = 5
        for batch_start in range(0, len(stories_to_fix), batch_size):
            batch = stories_to_fix[batch_start:batch_start + batch_size]

            stories_text = ""
            for s in batch:
                stories_text += (
                    f"- {s.id}: {getattr(s, 'title', '')}\n"
                    f"  As a {getattr(s, 'persona', 'user')}, "
                    f"I want to {getattr(s, 'action', 'do something')}, "
                    f"so that {getattr(s, 'benefit', 'I benefit')}\n"
                )

            try:
                response = await self._call_llm(
                    self.ACCEPTANCE_CRITERIA_PROMPT.format(stories_text=stories_text)
                )
                data = self._extract_json(response)

                for story_data in data.get("stories", []):
                    sid = story_data.get("id", "")
                    story = story_map.get(sid)
                    if not story:
                        continue
                    for ac_data in story_data.get("acceptance_criteria", []):
                        ac = AcceptanceCriterion(
                            given=ac_data.get("given", ""),
                            when=ac_data.get("when", ""),
                            then=ac_data.get("then", ""),
                        )
                        if not hasattr(story, "acceptance_criteria") or story.acceptance_criteria is None:
                            story.acceptance_criteria = []
                        story.acceptance_criteria.append(ac)
                    if story_data.get("acceptance_criteria"):
                        fixes.append(
                            f"Added {len(story_data['acceptance_criteria'])} acceptance criteria to {sid}"
                        )
            except Exception as e:
                fixes.append(f"LLM call failed for batch starting at {batch[0].id}: {e}")

        return fixes

    async def _fix_subjective_terms(
        self,
        issue: CritiqueIssue,
        user_stories: List,
    ) -> List[str]:
        """Add measurable acceptance criteria for subjective terms (LLM-assisted)."""
        if not HAS_GENERATORS:
            return []

        fixes = []
        story_map = {}
        for story in user_stories:
            sid = getattr(story, "id", "")
            if sid:
                story_map[sid] = story

        stories_to_fix = []
        for story_id in issue.affected_artifacts:
            story = story_map.get(story_id)
            if story:
                stories_to_fix.append(story)

        if not stories_to_fix:
            return []

        # Build text for LLM
        stories_text = ""
        for s in stories_to_fix[:10]:  # Limit to 10
            stories_text += (
                f"- {s.id}: As a {getattr(s, 'persona', 'user')}, "
                f"I want to {getattr(s, 'action', 'do something')}, "
                f"so that {getattr(s, 'benefit', 'I benefit')}\n"
            )

        try:
            response = await self._call_llm(
                self.SUBJECTIVE_TERMS_PROMPT.format(stories_text=stories_text)
            )
            data = self._extract_json(response)

            for story_data in data.get("stories", []):
                sid = story_data.get("id", "")
                story = story_map.get(sid)
                if not story:
                    continue
                ac_data = story_data.get("acceptance_criteria", {})
                if isinstance(ac_data, dict) and ac_data.get("given"):
                    ac = AcceptanceCriterion(
                        given=ac_data.get("given", ""),
                        when=ac_data.get("when", ""),
                        then=ac_data.get("then", ""),
                    )
                    if not hasattr(story, "acceptance_criteria") or story.acceptance_criteria is None:
                        story.acceptance_criteria = []
                    story.acceptance_criteria.append(ac)
                    vague = story_data.get("vague_term", "")
                    fixes.append(f"Added measurable criterion for '{vague}' in {sid}")
        except Exception as e:
            fixes.append(f"LLM call failed for subjective terms: {e}")

        return fixes

    def _save_fixed_artifacts(
        self,
        output_dir: str,
        user_stories: List,
        test_cases: List,
    ) -> List[str]:
        """Re-save modified artifacts to disk after auto-fixes."""
        saved_files = []
        out = Path(output_dir)

        # Re-save user_stories/user_stories.md
        us_md_path = out / "user_stories" / "user_stories.md"
        if us_md_path.parent.exists():
            md_content = "# User Stories\n\n"
            for story in user_stories:
                if hasattr(story, "to_markdown"):
                    md_content += story.to_markdown() + "\n---\n\n"
            us_md_path.write_text(md_content, encoding="utf-8")
            saved_files.append(str(us_md_path))

        # Append new stub test cases to testing/test_documentation.md
        test_doc_path = out / "testing" / "test_documentation.md"
        if test_doc_path.parent.exists():
            new_tcs = [tc for tc in test_cases if getattr(tc, "description", "").startswith("Stub test case")]
            if new_tcs:
                append_content = "\n\n## Auto-Generated Stub Test Cases\n\n"
                for tc in new_tcs:
                    if hasattr(tc, "to_markdown"):
                        append_content += tc.to_markdown() + "\n"
                with open(test_doc_path, "a", encoding="utf-8") as f:
                    f.write(append_content)
                saved_files.append(str(test_doc_path))

        return saved_files

    # ================================================================
    # Per-Stage Critique
    # ================================================================

    async def run_stage_critique(
        self,
        stage: str,
        requirements: List,
        user_stories: List = None,
        test_cases: List = None,
        domain: str = "",
        auto_fix: bool = True,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run targeted critique for a specific pipeline stage.

        Only runs the analyses relevant to the given stage, enabling
        earlier detection and fixing of issues so downstream stages
        benefit from cleaner data.

        Args:
            stage: One of "discovery", "analysis", "validation"
            requirements: List of RequirementNode instances
            user_stories: List of UserStory instances (needed for analysis/validation)
            test_cases: List of TestCase instances (needed for validation)
            domain: Domain context string
            auto_fix: If True, apply auto-fixes for fixable issues
            output_dir: Project output directory (for re-saving fixed artifacts)

        Returns:
            Dict with stage, issues_found, issues_fixed, fix_log.
        """
        if user_stories is None:
            user_stories = []
        if test_cases is None:
            test_cases = []
        all_issues: List[CritiqueIssue] = []
        self.issue_counter = getattr(self, 'issue_counter', 0)

        print(f"  [{stage.title()}] Running per-stage critique...")

        try:
            if stage == "discovery":
                # Only completeness check — just needs requirements + domain
                issues = await self.check_completeness(requirements, domain)
                all_issues.extend(issues)
                print(f"      Found {len(issues)} completeness issues")

            elif stage == "analysis":
                # Consistency + orphan detection (traceability with empty test_cases)
                consistency_issues = await self.check_consistency(requirements, user_stories)
                all_issues.extend(consistency_issues)
                print(f"      Found {len(consistency_issues)} consistency issues")

                traceability_issues = await self.check_traceability(requirements, user_stories, [])
                all_issues.extend(traceability_issues)
                print(f"      Found {len(traceability_issues)} traceability issues (orphans)")

            elif stage == "validation":
                # Testability + full traceability
                testability_issues = await self.check_testability(user_stories, test_cases)
                all_issues.extend(testability_issues)
                print(f"      Found {len(testability_issues)} testability issues")

                traceability_issues = await self.check_traceability(requirements, user_stories, test_cases)
                all_issues.extend(traceability_issues)
                print(f"      Found {len(traceability_issues)} traceability issues")

            else:
                print(f"      Unknown stage '{stage}', skipping critique")
                return {
                    "stage": stage,
                    "issues_found": 0,
                    "issues_fixed": 0,
                    "fix_log": [],
                }

        except Exception as e:
            print(f"      [WARN] Stage critique failed: {e}")
            return {
                "stage": stage,
                "issues_found": len(all_issues),
                "issues_fixed": 0,
                "fix_log": [f"Critique error: {e}"],
            }

        # Auto-fix phase
        fix_log: List[str] = []
        fixed_count = 0

        if auto_fix and all_issues and HAS_GENERATORS:
            self._classify_fixability(all_issues)
            fixable = [i for i in all_issues if i.auto_fixable]

            if fixable:
                print(f"      {len(fixable)} issues classified as auto-fixable")
                fix_result = await self.apply_auto_fixes(
                    all_issues, requirements, user_stories, test_cases, output_dir
                )
                fixed_count = fix_result["fixed_count"]
                fix_log = fix_result["fix_log"]
                print(f"      Fixed {fixed_count} issues")

                # Re-save modified artifacts if we fixed anything
                if output_dir and fixed_count > 0:
                    saved = self._save_fixed_artifacts(output_dir, user_stories, test_cases)
                    if saved:
                        print(f"      Re-saved {len(saved)} artifact files")

        return {
            "stage": stage,
            "issues_found": len(all_issues),
            "issues_fixed": fixed_count,
            "fix_log": fix_log,
        }

    # ================================================================
    # Main Orchestration
    # ================================================================

    async def critique_and_improve(
        self,
        requirements: List,
        user_stories: List,
        test_cases: List,
        domain: str = "",
        auto_fix: bool = False,
        output_dir: Optional[str] = None,
    ) -> CritiqueResult:
        """
        Perform comprehensive self-critique of all artifacts.

        Args:
            requirements: List of RequirementNode instances
            user_stories: List of UserStory instances
            test_cases: List of TestCase instances
            domain: Domain context string
            auto_fix: If True, attempt to auto-fix detected issues
            output_dir: Project output directory (for re-saving fixed artifacts)

        Returns:
            CritiqueResult with all issues and recommendations
        """
        print("  Running Self-Critique Analysis...")
        self.issue_counter = 0
        all_issues = []

        # Run all checks
        consistency_issues = await self.check_consistency(requirements, user_stories)
        all_issues.extend(consistency_issues)
        print(f"      Found {len(consistency_issues)} consistency issues")

        completeness_issues = await self.check_completeness(requirements, domain)
        all_issues.extend(completeness_issues)
        print(f"      Found {len(completeness_issues)} completeness issues")

        testability_issues = await self.check_testability(user_stories, test_cases)
        all_issues.extend(testability_issues)
        print(f"      Found {len(testability_issues)} testability issues")

        traceability_issues = await self.check_traceability(requirements, user_stories, test_cases)
        all_issues.extend(traceability_issues)
        print(f"      Found {len(traceability_issues)} traceability issues")

        # Calculate quality score
        quality_score = self._calculate_quality_score(all_issues)

        # Generate recommendations
        recommendations = self._generate_recommendations(all_issues)

        # Auto-fix phase
        fix_summary = {}
        if auto_fix and HAS_GENERATORS:
            print("  Applying Auto-Fixes...")
            self._classify_fixability(all_issues)

            fixable_count = sum(1 for i in all_issues if i.auto_fixable)
            print(f"      {fixable_count} issues classified as auto-fixable")

            fix_result = await self.apply_auto_fixes(
                all_issues, requirements, user_stories, test_cases, output_dir
            )
            print(f"      Fixed {fix_result['fixed_count']} issues, skipped {fix_result['skipped_count']}")

            # Recalculate quality score excluding fixed issues
            unfixed_issues = [i for i in all_issues if not i.fixed]
            quality_score = self._calculate_quality_score(unfixed_issues)

            fix_summary = {
                "auto_fixed": fix_result["fixed_count"],
                "auto_fix_skipped": fix_result["skipped_count"],
                "fix_log": fix_result["fix_log"],
            }

            # Re-save modified artifacts
            if output_dir:
                saved = self._save_fixed_artifacts(output_dir, user_stories, test_cases)
                fix_summary["resaved_files"] = saved
                print(f"      Re-saved {len(saved)} artifact files")

            print(f"  Updated Quality Score: {quality_score}/10")
        elif auto_fix and not HAS_GENERATORS:
            print("  [WARN] Auto-fix requested but generator classes not available")

        # Build result
        result = CritiqueResult(
            issues=all_issues,
            quality_score=quality_score,
            recommendations=recommendations,
            summary={
                "total_issues": len(all_issues),
                "requirements_reviewed": len(requirements),
                "user_stories_reviewed": len(user_stories),
                "test_cases_reviewed": len(test_cases),
                "by_severity": {s.value: sum(1 for i in all_issues if i.severity == s) for s in IssueSeverity},
                "by_category": {c.value: sum(1 for i in all_issues if i.category == c) for c in IssueCategory},
                **fix_summary,
            }
        )

        print(f"  Self-Critique Complete: {len(all_issues)} issues, Quality Score: {quality_score}/10")

        return result


# Test function
async def test_self_critique():
    """Test the SelfCritiqueEngine with sample data."""
    from dataclasses import dataclass

    @dataclass
    class MockReq:
        requirement_id: str
        title: str
        description: str

    @dataclass
    class MockUS:
        id: str
        title: str
        persona: str
        action: str
        benefit: str
        parent_requirement_id: str

    @dataclass
    class MockTC:
        id: str
        title: str
        parent_user_story_id: str

    # Sample data
    requirements = [
        MockReq("REQ-001", "User Registration", "Users can register with email"),
        MockReq("REQ-002", "Fast Response", "System must respond quickly"),
    ]

    user_stories = [
        MockUS("US-001", "Register Account", "new user", "register", "access system", "REQ-001"),
    ]

    test_cases = [
        MockTC("TC-001", "Valid Registration", "US-001"),
    ]

    engine = SelfCritiqueEngine()
    await engine.initialize()

    result = await engine.critique_and_improve(
        requirements, user_stories, test_cases, domain="E-Commerce"
    )

    print("\n=== Critique Report ===\n")
    print(result.to_markdown())

    return result


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_self_critique())
