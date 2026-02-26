"""
User Story Generator - Converts Requirements to User Stories and Epics.

Generates structured User Stories in the format:
    As a [persona]
    I want to [action]
    So that [benefit]

With acceptance criteria in Given-When-Then format.

Uses token management to chunk large requirement sets.
"""

import os
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from datetime import datetime

# Try to import OpenAI, fall back gracefully
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Import token management
from requirements_engineer.core.token_manager import (
    TokenBudget, TokenEstimator, RequirementChunker
)

# Import LLM logger for cost tracking
try:
    from requirements_engineer.core.llm_logger import log_llm_call
    HAS_LLM_LOGGER = True
except ImportError:
    HAS_LLM_LOGGER = False
    def log_llm_call(*args, **kwargs): pass

# Import Supermemory client for deduplication
try:
    from requirements_engineer.memory.supermemory_client import (
        SupermemoryClient, DeduplicationResult
    )
    HAS_SUPERMEMORY = True
except ImportError:
    HAS_SUPERMEMORY = False
    SupermemoryClient = None
    DeduplicationResult = None


@dataclass_json
@dataclass
class AcceptanceCriterion:
    """A single acceptance criterion in Given-When-Then format."""
    given: str
    when: str
    then: str

    def to_gherkin(self) -> str:
        """Convert to Gherkin format."""
        return f"Given {self.given}\nWhen {self.when}\nThen {self.then}"

    def to_markdown(self) -> str:
        """Convert to markdown bullet point."""
        return f"- **Given** {self.given}, **When** {self.when}, **Then** {self.then}"


@dataclass_json
@dataclass
class SubStory:
    """A sub-story (task) decomposing a complex User Story."""
    id: str  # US-001.1, US-001.2, etc.
    title: str
    description: str
    acceptance_criteria: List[AcceptanceCriterion] = field(default_factory=list)
    estimated_hours: Optional[int] = None

    def to_markdown(self) -> str:
        md = f"#### {self.id}: {self.title}\n\n"
        md += f"{self.description}\n\n"
        if self.estimated_hours:
            md += f"*Estimated: {self.estimated_hours}h*\n\n"
        if self.acceptance_criteria:
            md += "**Acceptance:**\n"
            for ac in self.acceptance_criteria:
                md += f"- Given {ac.given}, When {ac.when}, Then {ac.then}\n"
        return md


@dataclass_json
@dataclass
class UserStory:
    """A User Story with acceptance criteria and optional sub-stories."""
    id: str  # US-001, US-002, etc.
    title: str
    persona: str
    action: str
    benefit: str
    acceptance_criteria: List[AcceptanceCriterion] = field(default_factory=list)
    sub_stories: List[SubStory] = field(default_factory=list)  # Decomposition for complex stories
    priority: str = "should"  # must, should, could, wont
    story_points: Optional[int] = None
    parent_requirement_id: str = ""
    parent_epic_id: str = ""
    complexity: str = "simple"  # simple, medium, complex
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # Multi-Requirement Support for deduplicated stories
    linked_requirement_ids: List[str] = field(default_factory=list)  # Alle verlinkten REQs
    is_merged: bool = False  # Flag für deduplizierte Stories
    merge_count: int = 1  # Anzahl gemergter Requirements

    def to_standard_format(self) -> str:
        """Return the standard User Story format."""
        return f"As a {self.persona}\nI want to {self.action}\nSo that {self.benefit}"

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        md = f"## {self.id}: {self.title}\n\n"
        md += f"**Priority:** {self.priority.upper()}\n"
        if self.story_points:
            md += f"**Story Points:** {self.story_points}\n"
        # Show all linked requirements for merged stories
        if self.is_merged and self.linked_requirement_ids:
            md += f"**Linked Requirements:** {', '.join(self.linked_requirement_ids)}\n"
            md += f"*(Merged from {self.merge_count} requirements)*\n"
        else:
            md += f"**Linked Requirement:** {self.parent_requirement_id}\n"
        md += "\n"

        md += "### User Story\n\n"
        md += f"> As a **{self.persona}**\n"
        md += f"> I want to **{self.action}**\n"
        md += f"> So that **{self.benefit}**\n\n"

        if self.acceptance_criteria:
            md += "### Acceptance Criteria\n\n"
            for i, ac in enumerate(self.acceptance_criteria, 1):
                md += f"**AC-{i}:**\n"
                md += f"- Given: {ac.given}\n"
                md += f"- When: {ac.when}\n"
                md += f"- Then: {ac.then}\n\n"

        # Include sub-stories for decomposed complex stories
        if self.sub_stories:
            md += f"### Sub-Stories ({len(self.sub_stories)} tasks)\n\n"
            for sub in self.sub_stories:
                md += sub.to_markdown()
                md += "\n"

        return md

    def get_decomposition_depth(self) -> int:
        """Return decomposition depth (1 = simple, 2+ = has sub-stories)."""
        return 2 if self.sub_stories else 1


@dataclass_json
@dataclass
class Epic:
    """An Epic grouping related User Stories."""
    id: str  # EPIC-001, EPIC-002, etc.
    title: str
    description: str
    user_stories: List[str] = field(default_factory=list)  # List of US IDs
    parent_requirements: List[str] = field(default_factory=list)  # List of REQ IDs
    status: str = "draft"  # draft, in_progress, done
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        md = f"# {self.id}: {self.title}\n\n"
        md += f"**Status:** {self.status}\n\n"
        md += f"## Description\n\n{self.description}\n\n"

        if self.parent_requirements:
            md += f"## Linked Requirements\n\n"
            for req_id in self.parent_requirements:
                md += f"- {req_id}\n"
            md += "\n"

        if self.user_stories:
            md += f"## User Stories\n\n"
            for us_id in self.user_stories:
                md += f"- {us_id}\n"
            md += "\n"

        return md


class UserStoryGenerator:
    """
    Generates User Stories and Epics from Requirements using LLM.

    The generator:
    1. Analyzes requirements to identify personas and actions
    2. Groups related requirements into Epics
    3. Breaks down requirements into User Stories
    4. Generates acceptance criteria in Given-When-Then format
    """

    USER_STORY_PROMPT = """You are a Business Analyst expert in writing User Stories.

Given this requirement:
- ID: {req_id}
- Title: {title}
- Description: {description}
- Type: {type}
- Priority: {priority}

Stakeholder Context:
{stakeholders}

Generate a User Story in the following JSON format:
{{
    "persona": "the user role/persona (e.g., 'registered customer', 'shop admin')",
    "action": "what the user wants to do (verb phrase)",
    "benefit": "why the user wants this (business value)",
    "acceptance_criteria": [
        {{
            "given": "initial context/precondition",
            "when": "action taken",
            "then": "expected result"
        }}
    ]
}}

Guidelines:
- Choose the most appropriate persona from the stakeholders
- Action should be specific and testable
- Benefit should express business value
- Include 2-4 acceptance criteria that cover:
  - Happy path (success scenario)
  - Edge cases
  - Error handling if applicable

Return ONLY valid JSON, no other text."""

    EPIC_PROMPT = """You are a Business Analyst expert in organizing User Stories into Epics.

Given these requirements:
{requirements}

Domain Context: {domain}

Group these requirements into logical Epics. An Epic is a large body of work that can be broken down into smaller User Stories.

Return JSON format:
{{
    "epics": [
        {{
            "title": "Epic title",
            "description": "What this epic covers and its business value",
            "requirement_ids": ["REQ-001", "REQ-002"]
        }}
    ]
}}

Guidelines:
- Group by business capability (e.g., "User Authentication", "Shopping Cart", "Order Management")
- Each epic should have a clear scope
- Requirements can belong to multiple epics if they span capabilities
- Aim for 3-7 epics depending on scope

Return ONLY valid JSON, no other text."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        # Deduplication settings
        enable_deduplication: bool = True,
        similarity_threshold: float = 0.85,
        supermemory_api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        # Config-based settings
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the User Story Generator.

        Args:
            model_name: LLM model to use (OpenRouter format) - overrides config
            base_url: API base URL
            api_key: API key (defaults to OPENROUTER_API_KEY env var)
            enable_deduplication: Enable Supermemory-based deduplication
            similarity_threshold: Threshold for duplicate detection (0-1)
            supermemory_api_key: Supermemory API key (or SUPERMEMORY_API_KEY env var)
            project_id: Project ID for Supermemory user isolation
            config: Configuration dict with generators.user_story section
        """
        # Load from config if available
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("user_story", {})

        # Model settings (config < explicit parameter)
        self.model_name = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.7)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None

        # Counters for ID generation
        self._us_counter = 0
        self._epic_counter = 0

        # Storage
        self.user_stories: Dict[str, UserStory] = {}
        self.epics: Dict[str, Epic] = {}

        # Supermemory Deduplication
        self.enable_deduplication = enable_deduplication and HAS_SUPERMEMORY
        self.supermemory: Optional[SupermemoryClient] = None
        self.project_id = project_id
        self.merged_stories: Dict[str, List[str]] = {}  # story_id -> [req_ids]

        if self.enable_deduplication:
            self.supermemory = SupermemoryClient(
                api_key=supermemory_api_key,
                similarity_threshold=similarity_threshold
            )

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required. Install with: pip install openai")

        if not self.api_key:
            raise ValueError("API key not set. Set OPENROUTER_API_KEY environment variable.")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def create_new_user(self, project_id: Optional[str] = None, user_id: Optional[str] = None) -> Optional[str]:
        """
        Create a new User/Agent in Supermemory for fresh generation.

        Call this at the start of a new generation session to ensure
        stories are stored in a fresh memory space.

        Args:
            project_id: Optional project identifier
            user_id: Optional user identifier

        Returns:
            The new containerTag for this user, or None if deduplication disabled
        """
        if not self.supermemory or not self.enable_deduplication:
            return None

        project = project_id or self.project_id
        new_tag = await self.supermemory.create_user(
            project_id=project,
            user_id=user_id,
            metadata={"generator": "UserStoryGenerator"}
        )
        print(f"    [SUPERMEMORY] Neuer User erstellt: {new_tag}")
        return new_tag

    def switch_user(self, container_tag: str) -> None:
        """
        Switch to an existing Supermemory user/space.

        Use this to continue working with stories from a previous session.

        Args:
            container_tag: The containerTag of the target user
        """
        if self.supermemory:
            self.supermemory.switch_user(container_tag)
            print(f"    [SUPERMEMORY] Gewechselt zu User: {container_tag}")

    def _generate_us_id(self) -> str:
        """Generate a new User Story ID."""
        self._us_counter += 1
        return f"US-{str(self._us_counter).zfill(3)}"

    def _generate_epic_id(self) -> str:
        """Generate a new Epic ID."""
        self._epic_counter += 1
        return f"EPIC-{str(self._epic_counter).zfill(3)}"

    async def _call_llm(self, prompt: str, max_tokens_override: int = None) -> str:
        """Call the LLM and return the response."""
        import time
        start_time = time.time()

        if not self.client:
            await self.initialize()

        # Use config values or defaults
        temperature = getattr(self, 'temperature', 0.7)
        max_tokens = max_tokens_override or getattr(self, 'max_tokens', 8000)

        # Detect language from prompt content for consistent output
        lang = self._detect_language(prompt)
        system_msg = f"You are an expert Business Analyst. Write ALL output (titles, descriptions, acceptance criteria) in {lang}. Always respond with valid JSON only."

        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )

        response_text = response.choices[0].message.content.strip()

        # Log the LLM call for cost tracking
        latency_ms = int((time.time() - start_time) * 1000)
        if HAS_LLM_LOGGER:
            log_llm_call(
                component="user_story_generator",
                model=self.model_name,
                response=response,
                latency_ms=latency_ms,
                system_message=system_msg,
                user_message=prompt,
                response_text=response_text,
            )

        return response_text

    @staticmethod
    def _detect_language(text: str) -> str:
        """Detect whether input text is German or English based on common markers."""
        german_markers = {
            "und", "oder", "der", "die", "das", "ist", "ein", "eine",
            "für", "mit", "auf", "als", "nach", "bei", "soll", "muss",
            "kann", "wird", "von", "des", "den", "dem", "nicht", "werden",
        }
        words = set(text.lower().split())
        if len(words & german_markers) >= 3:
            return "German"
        return "English"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response with robust error handling."""
        errors = []

        # Try to parse directly
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            errors.append(f"Direct parse: {e}")

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                errors.append(f"Code block parse: {e}")

        # Try to find JSON object (greedy match for last closing brace)
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                errors.append(f"Object parse: {e}")
                # Try to fix truncated JSON by closing open brackets
                try:
                    fixed = self._fix_truncated_json(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError as e2:
                    errors.append(f"Fixed parse: {e2}")

        # Return empty result with warning instead of raising exception
        print(f"    [WARN] Could not parse JSON response. Returning empty result.")
        print(f"    Errors: {'; '.join(errors)}")
        return {"user_story": {}, "acceptance_criteria": []}

    def _fix_truncated_json(self, text: str) -> str:
        """Try to fix truncated JSON by adding missing closing brackets."""
        # Count open/close brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')

        # Add missing closing brackets
        fixed = text
        for _ in range(open_brackets):
            fixed += ']'
        for _ in range(open_braces):
            fixed += '}'

        return fixed

    async def generate_user_story(
        self,
        requirement,
        stakeholders: List[Dict[str, Any]] = None
    ) -> UserStory:
        """
        Generate a User Story from a RequirementNode.

        With deduplication enabled, checks Supermemory for similar stories
        and links to existing instead of creating duplicates.

        Args:
            requirement: RequirementNode instance
            stakeholders: List of stakeholder definitions

        Returns:
            UserStory instance (new or existing if duplicate)
        """
        # =====================================================================
        # DEDUPLICATION CHECK - Search Supermemory for similar stories
        # =====================================================================
        if self.supermemory and self.enable_deduplication:
            preview_text = f"{requirement.title}. {requirement.description}"
            dedup_result = await self.supermemory.search_similar_story(preview_text)

            if dedup_result.is_duplicate:
                existing_id = dedup_result.existing_story_id

                # Update links in Supermemory
                await self.supermemory.update_story_links(
                    existing_id,
                    requirement.requirement_id,
                    dedup_result.linked_requirements
                )

                # Update local tracking
                if existing_id not in self.merged_stories:
                    self.merged_stories[existing_id] = dedup_result.linked_requirements.copy()
                if requirement.requirement_id not in self.merged_stories[existing_id]:
                    self.merged_stories[existing_id].append(requirement.requirement_id)

                print(f"    [DEDUP] {requirement.requirement_id} → {existing_id} "
                      f"(similarity: {dedup_result.similarity_score:.0%})")

                # Update existing story if in local storage
                if existing_id in self.user_stories:
                    story = self.user_stories[existing_id]
                    story.linked_requirement_ids = self.merged_stories[existing_id]
                    story.is_merged = True
                    story.merge_count = len(self.merged_stories[existing_id])
                    return story

                # Story not in local storage - create reference
                return UserStory(
                    id=existing_id,
                    title=f"[Merged] See {existing_id}",
                    persona="",
                    action="",
                    benefit="",
                    parent_requirement_id=requirement.requirement_id,
                    linked_requirement_ids=self.merged_stories.get(existing_id, []),
                    is_merged=True,
                    merge_count=len(self.merged_stories.get(existing_id, []))
                )

        # =====================================================================
        # NORMAL STORY GENERATION
        # =====================================================================
        stakeholder_text = ""
        if stakeholders:
            for sh in stakeholders:
                stakeholder_text += f"- {sh.get('role', 'Unknown')}"
                if sh.get('persona'):
                    stakeholder_text += f" ({sh['persona']})"
                if sh.get('concerns'):
                    stakeholder_text += f": {', '.join(sh['concerns'])}"
                stakeholder_text += "\n"

        prompt = self.USER_STORY_PROMPT.format(
            req_id=requirement.requirement_id,
            title=requirement.title,
            description=requirement.description,
            type=requirement.type,
            priority=requirement.priority,
            stakeholders=stakeholder_text or "Not specified"
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        # Build acceptance criteria
        criteria = []
        for ac_data in data.get("acceptance_criteria", []):
            criteria.append(AcceptanceCriterion(
                given=ac_data.get("given", ""),
                when=ac_data.get("when", ""),
                then=ac_data.get("then", "")
            ))

        us_id = self._generate_us_id()

        # Determine complexity
        is_complex = self._is_complex_requirement(requirement)
        complexity = "complex" if is_complex else "simple"

        user_story = UserStory(
            id=us_id,
            title=requirement.title,
            persona=data.get("persona", "user"),
            action=data.get("action", requirement.description),
            benefit=data.get("benefit", "achieve their goal"),
            acceptance_criteria=criteria,
            priority=requirement.priority,
            parent_requirement_id=requirement.requirement_id,
            complexity=complexity,
            # Initialize linked requirements with the parent
            linked_requirement_ids=[requirement.requirement_id]
        )

        # Generate sub-stories for complex requirements
        if is_complex:
            sub_stories = await self._generate_sub_stories(user_story, requirement)
            user_story.sub_stories = sub_stories

        self.user_stories[us_id] = user_story

        # =====================================================================
        # STORE IN SUPERMEMORY for future deduplication
        # =====================================================================
        if self.supermemory and self.enable_deduplication:
            story_text = f"{user_story.persona} wants to {user_story.action} so that {user_story.benefit}"
            await self.supermemory.add_story(
                us_id,
                story_text,
                requirement.requirement_id,
                metadata={
                    "title": user_story.title,
                    "priority": user_story.priority,
                    "complexity": complexity
                }
            )
            self.merged_stories[us_id] = [requirement.requirement_id]

        return user_story

    def _is_complex_requirement(self, requirement) -> bool:
        """
        Determine if a requirement is complex and needs decomposition.

        Complex requirements have:
        - Long descriptions (>150 chars)
        - Multiple actions (contains 'and' or ',' listing actions)
        - Multiple conditions
        """
        desc = requirement.description.lower()

        # Check length
        if len(desc) > 150:
            return True

        # Check for multiple actions
        action_indicators = [" and ", " sowie ", " oder ", " additionally ", " also "]
        if any(ind in desc for ind in action_indicators):
            return True

        # Check for lists
        if desc.count(",") >= 2:
            return True

        return False

    async def _generate_sub_stories(self, parent_story: UserStory, requirement) -> List[SubStory]:
        """
        Generate sub-stories (tasks) to decompose a complex user story.
        """
        SUB_STORY_PROMPT = """Decompose this complex User Story into 2-4 smaller sub-tasks:

USER STORY:
- ID: {us_id}
- Title: {title}
- As a {persona}, I want to {action}, so that {benefit}

REQUIREMENT DESCRIPTION:
{description}

Return JSON with sub-tasks:
{{
    "sub_stories": [
        {{
            "title": "Brief task title",
            "description": "What needs to be done",
            "acceptance": {{
                "given": "context",
                "when": "action",
                "then": "result"
            }},
            "hours": 4
        }}
    ]
}}

Keep each sub-task focused and testable. Return ONLY valid JSON."""

        prompt = SUB_STORY_PROMPT.format(
            us_id=parent_story.id,
            title=parent_story.title,
            persona=parent_story.persona,
            action=parent_story.action,
            benefit=parent_story.benefit,
            description=requirement.description[:500]
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        sub_stories = []
        for i, sub_data in enumerate(data.get("sub_stories", []), 1):
            sub_id = f"{parent_story.id}.{i}"

            # Build acceptance criteria
            ac_data = sub_data.get("acceptance", {})
            criteria = []
            if ac_data:
                criteria.append(AcceptanceCriterion(
                    given=ac_data.get("given", ""),
                    when=ac_data.get("when", ""),
                    then=ac_data.get("then", "")
                ))

            sub_story = SubStory(
                id=sub_id,
                title=sub_data.get("title", f"Task {i}"),
                description=sub_data.get("description", ""),
                acceptance_criteria=criteria,
                estimated_hours=sub_data.get("hours")
            )
            sub_stories.append(sub_story)

        return sub_stories

    async def generate_user_stories(
        self,
        requirements: List,
        stakeholders: List[Dict[str, Any]] = None,
        max_context_tokens: int = 100000
    ) -> List[UserStory]:
        """
        Generate User Stories for multiple requirements.

        Uses token-aware batching for progress tracking.

        Args:
            requirements: List of RequirementNode instances
            stakeholders: List of stakeholder definitions
            max_context_tokens: Maximum tokens per LLM call

        Returns:
            List of UserStory instances
        """
        # Filter functional requirements
        functional_reqs = [r for r in requirements if r.type == "functional"]

        if not functional_reqs:
            print("  [WARN] No functional requirements for user story generation")
            return []

        # Set up chunking for progress tracking
        budget = TokenBudget(max_context=max_context_tokens)
        chunker = RequirementChunker(budget)
        template_tokens = TokenEstimator.estimate_tokens(self.USER_STORY_PROMPT)
        batch_info = chunker.get_batch_info(functional_reqs)

        print(f"  Processing {batch_info['total_requirements']} functional requirements in {batch_info['num_batches']} batch(es)")

        stories = []
        batch_num = 0

        for batch in chunker.chunk_requirements(functional_reqs, template_tokens):
            batch_num += 1
            print(f"  [Batch {batch_num}/{batch_info['num_batches']}] Processing {len(batch)} requirements...")

            for req in batch:
                story = await self.generate_user_story(req, stakeholders)
                stories.append(story)
                print(f"    Generated {story.id}: {story.title}")

        print(f"  Total user stories generated: {len(stories)}")
        return stories

    async def generate_nfr_story(
        self,
        requirement,
        stakeholders: List[Dict[str, Any]] = None
    ) -> UserStory:
        """
        Generate a verification story for a Non-Functional Requirement.

        NFR stories focus on how to verify/measure the requirement.
        """
        NFR_STORY_PROMPT = """Create a verification story for this Non-Functional Requirement:

REQUIREMENT:
- ID: {req_id}
- Title: {title}
- Description: {description}
- Type: {type}
- Priority: {priority}

STAKEHOLDERS:
{stakeholders}

Return JSON:
{{
    "persona": "role responsible for verifying (e.g., QA Engineer, DevOps, Security Team)",
    "action": "verification action (e.g., validate performance meets SLA)",
    "benefit": "why this verification matters",
    "verification_criteria": [
        {{
            "metric": "what to measure",
            "target": "threshold value",
            "method": "how to measure"
        }}
    ]
}}

Return ONLY valid JSON."""

        stakeholder_text = ""
        if stakeholders:
            for sh in stakeholders:
                stakeholder_text += f"- {sh.get('role', 'Unknown')}\n"

        prompt = NFR_STORY_PROMPT.format(
            req_id=requirement.requirement_id,
            title=requirement.title,
            description=requirement.description,
            type=requirement.type,
            priority=requirement.priority,
            stakeholders=stakeholder_text or "Not specified"
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        # Build acceptance criteria from verification criteria
        criteria = []
        for vc in data.get("verification_criteria", []):
            criteria.append(AcceptanceCriterion(
                given=f"the system is under {vc.get('method', 'test')} conditions",
                when=f"measuring {vc.get('metric', 'the metric')}",
                then=f"the result meets target: {vc.get('target', 'defined threshold')}"
            ))

        us_id = self._generate_us_id()
        user_story = UserStory(
            id=us_id,
            title=f"Verify: {requirement.title}",
            persona=data.get("persona", "QA Engineer"),
            action=data.get("action", f"verify {requirement.title}"),
            benefit=data.get("benefit", "ensure quality requirements are met"),
            acceptance_criteria=criteria,
            priority=requirement.priority,
            parent_requirement_id=requirement.requirement_id,
            complexity="simple"
        )

        self.user_stories[us_id] = user_story
        return user_story

    async def generate_nfr_stories(
        self,
        requirements: List,
        stakeholders: List[Dict[str, Any]] = None
    ) -> List[UserStory]:
        """
        Generate verification stories for Non-Functional Requirements.

        Args:
            requirements: List of RequirementNode instances
            stakeholders: List of stakeholder definitions

        Returns:
            List of UserStory instances for NFR verification
        """
        # Filter non-functional requirements
        nfr_reqs = [r for r in requirements if r.type != "functional"]

        if not nfr_reqs:
            print("  [INFO] No non-functional requirements found")
            return []

        print(f"  Generating verification stories for {len(nfr_reqs)} NFR requirements...")

        stories = []
        for req in nfr_reqs:
            story = await self.generate_nfr_story(req, stakeholders)
            stories.append(story)
            print(f"    Generated {story.id}: {story.title}")

        print(f"  Total NFR stories generated: {len(stories)}")
        return stories

    async def generate_all_stories(
        self,
        requirements: List,
        stakeholders: List[Dict[str, Any]] = None,
        include_nfr: bool = True
    ) -> List[UserStory]:
        """
        Generate stories for all requirements (functional + non-functional).

        Args:
            requirements: List of all RequirementNode instances
            stakeholders: List of stakeholder definitions
            include_nfr: Whether to include NFR verification stories

        Returns:
            Combined list of UserStory instances
        """
        all_stories = []

        # Generate functional user stories
        functional_stories = await self.generate_user_stories(requirements, stakeholders)
        all_stories.extend(functional_stories)

        # Generate NFR verification stories
        if include_nfr:
            nfr_stories = await self.generate_nfr_stories(requirements, stakeholders)
            all_stories.extend(nfr_stories)

        return all_stories

    async def generate_epics(
        self,
        requirements: List,
        domain: str = "",
        max_context_tokens: int = 100000
    ) -> List[Epic]:
        """
        Generate Epics by grouping related requirements.

        Uses token-aware chunking for large requirement sets.

        Args:
            requirements: List of RequirementNode instances
            domain: Domain context string
            max_context_tokens: Maximum tokens per LLM call

        Returns:
            List of Epic instances
        """
        if not requirements:
            print("  [WARN] No requirements provided for epic generation")
            return []

        # Set up chunking
        budget = TokenBudget(max_context=max_context_tokens)
        chunker = RequirementChunker(budget)

        # Estimate prompt template tokens
        template_tokens = TokenEstimator.estimate_tokens(self.EPIC_PROMPT)

        # Get batch info
        batch_info = chunker.get_batch_info(requirements)

        # If everything fits in one batch, process normally
        if batch_info['num_batches'] <= 1:
            # Build requirements summary
            req_summary = ""
            for req in requirements:
                req_summary += f"- {req.requirement_id}: {req.title} ({req.type})\n"
                req_summary += f"  {req.description[:100]}...\n"

            prompt = self.EPIC_PROMPT.format(
                requirements=req_summary,
                domain=domain or "Software System"
            )

            response = await self._call_llm(prompt)
            data = self._extract_json(response)

            epics = []
            for epic_data in data.get("epics", []):
                epic_id = self._generate_epic_id()
                epic = Epic(
                    id=epic_id,
                    title=epic_data.get("title", "Unnamed Epic"),
                    description=epic_data.get("description", ""),
                    parent_requirements=epic_data.get("requirement_ids", [])
                )
                self.epics[epic_id] = epic
                epics.append(epic)
                print(f"  Generated {epic_id}: {epic.title}")

            return epics

        # For large sets, process in batches and merge epics
        print(f"  Processing {batch_info['total_requirements']} requirements in {batch_info['num_batches']} batch(es)")

        all_epics = []
        batch_num = 0

        for batch in chunker.chunk_requirements(requirements, template_tokens):
            batch_num += 1
            print(f"  [Batch {batch_num}/{batch_info['num_batches']}] Processing {len(batch)} requirements...")

            # Build requirements summary for this batch
            req_summary = ""
            for req in batch:
                req_summary += f"- {req.requirement_id}: {req.title} ({req.type})\n"
                req_summary += f"  {req.description[:100]}...\n"

            prompt = self.EPIC_PROMPT.format(
                requirements=req_summary,
                domain=domain or "Software System"
            )

            response = await self._call_llm(prompt)
            data = self._extract_json(response)

            for epic_data in data.get("epics", []):
                # Check if similar epic already exists
                existing = self._find_similar_epic(epic_data.get("title", ""), all_epics)
                if existing:
                    # Merge requirements into existing epic
                    for req_id in epic_data.get("requirement_ids", []):
                        if req_id not in existing.parent_requirements:
                            existing.parent_requirements.append(req_id)
                    print(f"    Merged into existing epic: {existing.title}")
                else:
                    # Create new epic
                    epic_id = self._generate_epic_id()
                    epic = Epic(
                        id=epic_id,
                        title=epic_data.get("title", "Unnamed Epic"),
                        description=epic_data.get("description", ""),
                        parent_requirements=epic_data.get("requirement_ids", [])
                    )
                    self.epics[epic_id] = epic
                    all_epics.append(epic)
                    print(f"    Generated {epic_id}: {epic.title}")

        print(f"  Total epics generated: {len(all_epics)}")
        return all_epics

    def _find_similar_epic(self, title: str, epics: List[Epic]) -> Optional[Epic]:
        """Find an epic with a similar title (for merging across batches)."""
        title_lower = title.lower()
        for epic in epics:
            # Simple similarity check - contains key words
            epic_words = set(epic.title.lower().split())
            title_words = set(title_lower.split())
            common = epic_words & title_words
            # If > 50% words match, consider it similar
            if len(common) >= len(title_words) * 0.5:
                return epic
        return None

    def link_stories_to_epics(self):
        """Link User Stories to their parent Epics based on requirements."""
        for epic in self.epics.values():
            for story in self.user_stories.values():
                if story.parent_requirement_id in epic.parent_requirements:
                    if story.id not in epic.user_stories:
                        epic.user_stories.append(story.id)
                    story.parent_epic_id = epic.id

    def to_markdown(self) -> str:
        """Export all User Stories and Epics to markdown."""
        md = "# User Stories and Epics\n\n"
        md += f"Generated: {datetime.now().isoformat()}\n\n"

        md += "## Summary\n\n"
        md += f"- Total Epics: {len(self.epics)}\n"
        md += f"- Total User Stories: {len(self.user_stories)}\n\n"

        md += "---\n\n"
        md += "# Epics\n\n"
        for epic in sorted(self.epics.values(), key=lambda x: x.id):
            md += epic.to_markdown()
            md += "---\n\n"

        md += "# User Stories\n\n"
        for story in sorted(self.user_stories.values(), key=lambda x: x.id):
            md += story.to_markdown()
            md += "---\n\n"

        return md

    def to_dict(self) -> Dict[str, Any]:
        """Export to dictionary format."""
        return {
            "epics": {k: v.to_dict() for k, v in self.epics.items()},
            "user_stories": {k: v.to_dict() for k, v in self.user_stories.items()},
            "generated_at": datetime.now().isoformat()
        }


# Test function
async def test_user_story_generator():
    """Test the UserStoryGenerator with sample data."""
    from requirements_engineer.core.re_journal import RequirementNode

    # Create sample requirements
    requirements = [
        RequirementNode(
            requirement_id="REQ-001",
            title="User Registration",
            description="Users should be able to register with email and password",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-002",
            title="User Login",
            description="Users should be able to login with their credentials",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-003",
            title="Product Search",
            description="Users should be able to search for products with filters",
            type="functional",
            priority="should"
        )
    ]

    stakeholders = [
        {"role": "End User (Customer)", "persona": "Online Shopper", "concerns": ["usability", "speed"]},
        {"role": "Admin", "persona": "Shop Manager", "concerns": ["efficiency", "reporting"]}
    ]

    generator = UserStoryGenerator()
    await generator.initialize()

    print("=== Generating User Stories ===\n")
    stories = await generator.generate_user_stories(requirements, stakeholders)

    print("\n=== Generating Epics ===\n")
    epics = await generator.generate_epics(requirements, "E-Commerce Platform")

    print("\n=== Linking Stories to Epics ===\n")
    generator.link_stories_to_epics()

    print("\n=== Markdown Output ===\n")
    print(generator.to_markdown())

    return generator


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_user_story_generator())
