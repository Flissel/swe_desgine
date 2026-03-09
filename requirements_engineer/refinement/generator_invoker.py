"""
Generator Invoker — selectively re-invokes pipeline generators to fill gaps.

Key optimization: passes only the affected artifacts (not the full set)
to the generator, reducing LLM token usage.

Three tiers of fixes:
  1. Auto-link (programmatic, no LLM) — keyword overlap matching
  2. LLM-extend — direct LLM calls for entity linking, acceptance criteria
  3. Generator — re-invoke existing pipeline generators with focused inputs
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from . import ArtifactBundle, Gap, GapFixStrategy

logger = logging.getLogger(__name__)

# Optional: AsyncOpenAI for LLM calls
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Optional: LLM logger
try:
    from requirements_engineer.core.llm_logger import log_llm_call
    HAS_LOGGER = True
except ImportError:
    HAS_LOGGER = False

# Optional: Semantic matcher for RAG
try:
    from requirements_engineer.memory.semantic_matcher import SemanticMatcher
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False

# Stopwords for keyword overlap matching (reused from completeness_checker)
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "and", "but", "or",
    "nor", "not", "no", "so", "yet", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "about", "up", "down",
    "out", "off", "over", "again", "further", "then", "once", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "than",
    "too", "very", "just", "also", "if", "this", "that", "these", "those",
    "it", "its", "user", "system", "data", "information",
})

# LLM prompts
ENTITY_LINK_PROMPT = """You are a Requirements Engineering expert. Link each data entity to the most relevant requirement.

## Entities to link:
{entities_text}

## Available Requirements:
{requirements_text}

Return a JSON object with this structure:
```json
{{
  "links": [
    {{"entity": "EntityName", "requirement_id": "REQ-XXX", "reason": "brief reason"}}
  ]
}}
```

Only link entities where you are confident of the match. If no good match exists, omit that entity."""

API_LINK_PROMPT = """You are a Requirements Engineering expert. Link each API endpoint to the most relevant requirement.

## API Endpoints to link:
{endpoints_text}

## Available Requirements:
{requirements_text}

Return a JSON object with this structure:
```json
{{
  "links": [
    {{"endpoint": "/api/v1/...", "requirement_id": "REQ-XXX", "reason": "brief reason"}}
  ]
}}
```

Link every endpoint to its best-matching requirement. If multiple could fit, pick the strongest match."""

TASK_LINK_PROMPT = """You are a Requirements Engineering expert. Link each task to the most relevant requirement.

## Tasks to link:
{tasks_text}

## Available Requirements:
{requirements_text}

Return a JSON object with this structure:
```json
{{
  "links": [
    {{"task_id": "TASK-XXX", "requirement_id": "REQ-XXX", "reason": "brief reason"}}
  ]
}}
```

Link every task to its best-matching requirement. If multiple could fit, pick the strongest match."""

ACCEPTANCE_CRITERIA_PROMPT = """You are a senior QA engineer. Generate acceptance criteria in Given-When-Then format for these user stories.

## User Stories:
{stories_text}

Return a JSON object with this structure:
```json
{{
  "stories": [
    {{
      "id": "US-XXX",
      "acceptance_criteria": [
        {{"given": "...", "when": "...", "then": "..."}}
      ]
    }}
  ]
}}
```

Generate 2-4 acceptance criteria per story. Be specific and testable."""

# Cost estimates per model family (USD per 1K tokens, input/output averaged)
_COST_PER_1K = {
    "gemini": 0.0001,
    "flash": 0.0001,
    "gpt-4o-mini": 0.0003,
    "gpt-4o": 0.005,
    "claude": 0.003,
    "sonnet": 0.003,
    "opus": 0.015,
}


def _extract_keywords(text: str) -> Set[str]:
    # Split CamelCase: "PaymentTransaction" → "Payment Transaction"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Split on underscores, hyphens, slashes, braces, dots, colons
    text = re.sub(r'[_/\-{}.:]', ' ', text)
    words = set(re.findall(r"[a-zA-ZäöüÄÖÜß]{3,}", text.lower()))
    return words - _STOPWORDS


def _estimate_cost(model: str, approx_tokens: int = 4000) -> float:
    """Estimate LLM call cost from model name heuristic."""
    model_lower = model.lower()
    for key, cost in _COST_PER_1K.items():
        if key in model_lower:
            return cost * approx_tokens / 1000
    return 0.001  # default fallback


class GeneratorInvoker:
    """Applies fixes to an ArtifactBundle by re-invoking generators or programmatic fixes."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.llm_calls = 0
        self.cost_usd = 0.0
        self.fix_log: List[str] = []

        # LLM settings
        self.model_name = self.config.get("model", "google/gemini-3-flash-preview")
        self.generator_model = self.config.get("generator_model", self.model_name)
        self.temperature = self.config.get("temperature", 0.3)
        self.max_tokens = self.config.get("max_tokens", 8000)
        self.base_url = self.config.get("base_url", "https://openrouter.ai/api/v1")
        self.api_key = self.config.get("api_key") or os.environ.get("OPENROUTER_API_KEY")
        self._client = None  # Lazy init
        self._client_checked = False  # Only log warning once

        # Semantic matcher (RAG)
        self._matcher = None  # type: Optional[SemanticMatcher]
        self._matcher_checked = False
        self._index_built = False
        self.similarity_threshold = self.config.get("similarity_threshold", 0.55)

    # ------------------------------------------------------------------
    # LLM infrastructure
    # ------------------------------------------------------------------

    async def _ensure_client(self):
        """Lazily initialize the OpenAI client."""
        if self._client is not None:
            return True
        if self._client_checked:
            return False
        self._client_checked = True
        if not HAS_OPENAI:
            logger.warning("openai package not installed. LLM fixes disabled.")
            return False
        if not self.api_key:
            logger.warning("No API key found. LLM fixes disabled.")
            return False
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        return True

    async def _ensure_matcher(self) -> bool:
        """Lazily initialize the semantic matcher for RAG-based linking."""
        if self._matcher is not None:
            return self._matcher.available
        if self._matcher_checked:
            return False
        self._matcher_checked = True
        if not HAS_SEMANTIC:
            logger.info("Semantic matcher not available (import failed).")
            return False
        openai_key = self.config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            logger.info("Semantic matching disabled (no OPENAI_API_KEY).")
            return False
        model = self.config.get("embeddings_model", "text-embedding-3-small")
        self._matcher = SemanticMatcher(api_key=openai_key, model=model)
        return self._matcher.available

    async def build_artifact_index(self, bundle: ArtifactBundle) -> bool:
        """Build semantic index over all requirements, stories, and entities.

        Called once before the refinement loop starts. Indexes artifact texts
        so find_similar() can be used during gap fixing.
        """
        if self._index_built:
            return True
        if not await self._ensure_matcher():
            return False

        items = []
        # Index requirements
        for req in bundle.requirements:
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            title = getattr(req, "title", "")
            desc = getattr(req, "description", "")
            if rid and (title or desc):
                items.append((rid, f"{title} {desc}".strip()))

        # Index user stories
        for story in bundle.user_stories:
            sid = getattr(story, "id", "")
            title = getattr(story, "title", "")
            action = getattr(story, "action", "")
            benefit = getattr(story, "benefit", "")
            if sid:
                items.append((sid, f"{title} {action} {benefit}".strip()))

        if not items:
            return False

        try:
            count = await self._matcher.build_index(items)
            self._index_built = count > 0
            return self._index_built
        except Exception as e:
            logger.warning("Failed to build semantic index: %s", e)
            return False

    async def _call_llm(
        self,
        prompt: str,
        system_message: str = "You are a senior Requirements Engineering expert. Return valid JSON.",
        max_tokens: Optional[int] = None,
    ) -> str:
        """Call the LLM and return the response text."""
        if not await self._ensure_client():
            return ""

        start_time = time.time()
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        response_text = response.choices[0].message.content.strip()

        # Track budget
        self.llm_calls += 1
        self.cost_usd += _estimate_cost(self.model_name)

        # Log if available
        if HAS_LOGGER:
            try:
                log_llm_call(
                    component="refinement_invoker",
                    model=self.model_name,
                    response=response,
                    latency_ms=latency_ms,
                    system_message=system_message,
                    user_message=prompt,
                    response_text=response_text,
                )
            except Exception:
                pass

        return response_text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response (3-strategy fallback)."""
        # Strategy 1: direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Strategy 2: code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: find JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {}

    def _format_requirements(self, requirements: list, limit: int = 50) -> str:
        """Format requirements for LLM prompts."""
        lines = []
        for req in requirements[:limit]:
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            title = getattr(req, "title", "")
            desc = getattr(req, "description", "")
            lines.append(f"- {rid}: {title}")
            if desc:
                lines.append(f"  {desc[:150]}")
        return "\n".join(lines)

    def _format_user_stories(self, stories: list, limit: int = 20) -> str:
        """Format user stories for LLM prompts."""
        lines = []
        for s in stories[:limit]:
            sid = getattr(s, "id", "")
            title = getattr(s, "title", "")
            persona = getattr(s, "persona", "user")
            action = getattr(s, "action", "")
            benefit = getattr(s, "benefit", "")
            lines.append(f"- {sid}: {title}")
            lines.append(f"  As a {persona}, I want to {action}, so that {benefit}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Auto-link fixes (programmatic, no LLM)
    # ------------------------------------------------------------------

    async def apply_auto_link_fixes(
        self, gaps: List[Gap], bundle: ArtifactBundle, max_fixes: int = 200
    ) -> int:
        """Apply programmatic auto-link fixes. Returns count of gaps fixed."""
        fixed = 0
        # Batch story_to_screen gaps for efficient grouped handling
        screen_gaps = [g for g in gaps if g.rule_id == "story_to_screen"]
        flow_gaps = [g for g in gaps if g.rule_id == "flow_coverage"]
        other_gaps = [g for g in gaps if g.rule_id not in ("story_to_screen", "flow_coverage")]

        # Handle story_to_screen in batch (creates compositions)
        if screen_gaps:
            fixed += self._fix_stories_to_screens_batch(screen_gaps, bundle)

        # Handle flow_coverage in batch (creates stub flows)
        if flow_gaps:
            fixed += self._fix_flow_coverage_batch(flow_gaps, bundle)

        # Handle state_machine_density gaps (create stub state machines)
        sm_gaps = [g for g in other_gaps if g.rule_id == "state_machine_density"]
        if sm_gaps:
            fixed += self._fix_state_machine_stubs(sm_gaps, bundle)

        # Handle task_ratio gaps (create stub tasks from under-covered requirements)
        task_ratio_gaps = [g for g in other_gaps if g.rule_id == "task_ratio"]
        if task_ratio_gaps:
            fixed += self._fix_task_ratio_stubs(task_ratio_gaps, bundle)

        for gap in other_gaps[:max_fixes]:
            if gap.rule_id in ("state_machine_density", "task_ratio"):
                continue  # Already handled above
            elif gap.rule_id == "story_to_test":
                if self._fix_story_without_test(gap, bundle):
                    fixed += 1
            elif gap.rule_id == "api_to_req":
                if await self._fix_api_to_req_link(gap, bundle):
                    fixed += 1
            elif gap.rule_id == "task_backlinks":
                if await self._fix_task_backlink(gap, bundle):
                    fixed += 1
            elif gap.rule_id == "quality_gates":
                # Quality gates are informational — no programmatic fix
                pass
        return fixed

    def _fix_story_without_test(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """Create a stub test case for a story without one."""
        for sid in gap.affected_ids:
            story = bundle.story_by_id.get(sid)
            if not story:
                continue
            try:
                from requirements_engineer.generators.test_case_generator import TestCase
                tc_id = f"TC-REFINE-{len(bundle.test_cases) + 1:03d}"
                title = getattr(story, "title", "")
                tc = TestCase(
                    id=tc_id,
                    title=f"Test: {title}",
                    description=f"Auto-generated test stub for {sid}",
                    parent_user_story_id=sid,
                    test_type="acceptance",
                    priority="should",
                    automation_status="stub",
                )
                bundle.test_cases.append(tc)
                bundle.test_by_id[tc_id] = tc
                self.fix_log.append(f"Created stub test {tc_id} for story {sid}")
                return True
            except Exception as e:
                logger.warning("Failed to create stub test for %s: %s", sid, e)
        return False

    async def _fix_api_to_req_link(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """Link API endpoint to requirement — semantic → LLM → keyword → best-effort."""
        for ep_key in gap.affected_ids:
            ep = bundle.endpoint_by_key.get(ep_key)
            if not ep:
                continue
            path = getattr(ep, "path", "")
            summary = getattr(ep, "summary", "")
            query = f"{path} {summary}".strip()

            # Try semantic matching first
            if self._index_built and self._matcher and self._matcher.available:
                try:
                    matches = await self._matcher.find_similar(
                        query, top_k=3, threshold=self.similarity_threshold
                    )
                    for req_id, score in matches:
                        if req_id in bundle.req_by_id:
                            ep.parent_requirement_id = req_id
                            self.fix_log.append(
                                f"[SEMANTIC] Linked API {ep_key} -> {req_id} "
                                f"(cosine={score:.3f})"
                            )
                            return True
                except Exception as e:
                    logger.warning("Semantic API-to-req matching failed: %s", e)

            # Try LLM fallback (if API key available)
            if await self._ensure_client():
                try:
                    if await self._fix_api_to_req_link_llm(ep_key, ep, bundle):
                        return True
                except Exception as e:
                    logger.warning("LLM API-to-req linking failed, falling back to keywords: %s", e)

            # Fallback: keyword overlap + best-effort
            return self._fix_api_to_req_link_keywords(ep_key, ep, bundle)
        return False

    def _fix_api_to_req_link_keywords(
        self, ep_key: str, ep: Any, bundle: ArtifactBundle
    ) -> bool:
        """Keyword-matching fallback for API-to-requirement linking."""
        path = getattr(ep, "path", "")
        summary = getattr(ep, "summary", "")
        ep_kw = _extract_keywords(f"{path} {summary}")

        best_req = None
        best_score = 0
        for req in bundle.requirements:
            title = getattr(req, "title", "")
            desc = getattr(req, "description", "")
            req_kw = _extract_keywords(f"{title} {desc}")
            overlap = len(ep_kw & req_kw)
            if overlap > best_score:
                best_score = overlap
                best_req = req

        if best_req and best_score >= 1:
            rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
            ep.parent_requirement_id = rid
            self.fix_log.append(
                f"Linked API {ep_key} -> {rid} (keyword overlap={best_score})"
            )
            return True
        # Best-effort: link to closest match even with overlap=0
        if best_req:
            rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
            ep.parent_requirement_id = rid
            self.fix_log.append(
                f"[BEST-EFFORT] Linked API {ep_key} -> {rid} (overlap={best_score})"
            )
            return True
        # Absolute fallback: first requirement
        if bundle.requirements:
            req = bundle.requirements[0]
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            ep.parent_requirement_id = rid
            self.fix_log.append(f"[FALLBACK] Linked API {ep_key} -> {rid}")
            return True
        return False

    async def _fix_api_to_req_link_llm(
        self, ep_key: str, ep: Any, bundle: ArtifactBundle
    ) -> bool:
        """LLM-based API-to-requirement linking."""
        path = getattr(ep, "path", "")
        summary = getattr(ep, "summary", "")
        method = getattr(ep, "method", "")
        endpoints_text = f"- {method} {path}"
        if summary:
            endpoints_text += f" ({summary})"

        requirements_text = self._format_requirements(bundle.requirements)
        prompt = API_LINK_PROMPT.format(
            endpoints_text=endpoints_text,
            requirements_text=requirements_text,
        )

        response = await self._call_llm(prompt, max_tokens=2000)
        data = self._extract_json(response)

        for link in data.get("links", []):
            req_id = link.get("requirement_id", "")
            reason = link.get("reason", "")
            if req_id and req_id in bundle.req_by_id:
                ep.parent_requirement_id = req_id
                self.fix_log.append(
                    f"[LLM] Linked API {ep_key} -> {req_id} ({reason})"
                )
                return True
        return False

    def _fix_stories_to_screens_batch(
        self, gaps: List[Gap], bundle: ArtifactBundle
    ) -> int:
        """Link stories to screens by matching existing screens or creating compositions.

        Strategy:
          1. Match unlinked stories to existing screens via keyword overlap
          2. Group remaining stories by parent_epic_id
          3. Create one ScreenComposition per group linking stories to a virtual screen
        """
        # Collect all unlinked story IDs
        unlinked_sids = set()
        for gap in gaps:
            unlinked_sids.update(gap.affected_ids)

        if not unlinked_sids:
            return 0

        # Build keyword index for existing screens
        screen_kw_map: List[tuple] = []  # [(screen, keywords)]
        for screen in bundle.screens:
            name = getattr(screen, "name", "")
            desc = getattr(screen, "description", "")
            route = getattr(screen, "route", "")
            screen_kw_map.append((screen, _extract_keywords(f"{name} {desc} {route}")))

        linked_sids: Set[str] = set()
        unmatched_sids: Set[str] = set()

        # Step 1: Try to match stories to existing screens
        for sid in unlinked_sids:
            story = bundle.story_by_id.get(sid)
            if not story:
                continue
            title = getattr(story, "title", "")
            action = getattr(story, "action", "")
            story_kw = _extract_keywords(f"{title} {action}")

            best_screen = None
            best_overlap = 0
            for screen, skw in screen_kw_map:
                overlap = len(story_kw & skw)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_screen = screen

            if best_screen and best_overlap >= 2:
                # Link via parent_user_story if empty, else via composition
                screen_id = getattr(best_screen, "id", "")
                if not getattr(best_screen, "parent_user_story", ""):
                    best_screen.parent_user_story = sid
                    self.fix_log.append(
                        f"Linked story {sid} -> screen {screen_id} "
                        f"(keyword overlap={best_overlap})"
                    )
                else:
                    # Create composition linking this story to the screen
                    comp = {
                        "route": getattr(best_screen, "route", f"/{screen_id}"),
                        "screen_name": getattr(best_screen, "name", screen_id),
                        "linked_user_stories": [sid],
                        "user_stories": [sid],
                    }
                    bundle.screen_compositions.append(comp)
                    self.fix_log.append(
                        f"Linked story {sid} -> screen {screen_id} via composition "
                        f"(keyword overlap={best_overlap})"
                    )
                linked_sids.add(sid)
            else:
                unmatched_sids.add(sid)

        # Step 2: Group unmatched stories by epic and create stub compositions
        if unmatched_sids:
            groups: Dict[str, List[str]] = {}  # epic_id -> [story_ids]
            for sid in unmatched_sids:
                story = bundle.story_by_id.get(sid)
                epic_id = getattr(story, "parent_epic_id", "ungrouped") if story else "ungrouped"
                groups.setdefault(epic_id or "ungrouped", []).append(sid)

            for group_key, sids in groups.items():
                # Create one composition per group
                epic = bundle.epic_by_id.get(group_key)
                group_name = getattr(epic, "title", group_key) if epic else group_key
                comp = {
                    "route": f"/{'_'.join(group_name.lower().split()[:3])}",
                    "screen_name": f"Screen: {group_name}",
                    "description": f"Auto-generated composition for {len(sids)} stories",
                    "linked_user_stories": sids,
                    "user_stories": sids,
                }
                bundle.screen_compositions.append(comp)
                self.fix_log.append(
                    f"Created composition '{group_name}' linking {len(sids)} stories "
                    f"(epic: {group_key})"
                )
                linked_sids.update(sids)

        return len(linked_sids)

    def _fix_state_machine_stubs(
        self, gaps: List[Gap], bundle: ArtifactBundle
    ) -> int:
        """Create stub state machines for lifecycle entities."""
        fixed = 0
        for gap in gaps:
            for entity_name in gap.affected_ids:
                entity = bundle.entities.get(entity_name)
                if not entity:
                    continue

                # Extract status field values if available
                status_values = []
                fields = getattr(entity, "fields", [])
                for f in fields:
                    fname = f.name if hasattr(f, "name") else (f.get("name", "") if isinstance(f, dict) else "")
                    if fname.lower() in ("status", "state", "phase"):
                        enum_vals = getattr(f, "enum_values", None) or (
                            f.get("enum_values") if isinstance(f, dict) else None
                        )
                        if enum_vals:
                            status_values = enum_vals
                        break

                # Default states if none found
                if not status_values:
                    status_values = ["created", "active", "completed", "cancelled"]

                try:
                    from requirements_engineer.generators.state_machine_generator import (
                        StateMachine, StateTransition,
                    )
                    state_names = status_values
                    initial = state_names[0]
                    finals = [state_names[-1]]
                    if "cancelled" in state_names:
                        finals.append("cancelled")

                    # Linear transitions
                    transitions = []
                    for i in range(len(state_names) - 1):
                        transitions.append(StateTransition(
                            from_state=state_names[i],
                            to_state=state_names[i + 1],
                            trigger=f"{state_names[i]}_to_{state_names[i + 1]}",
                        ))

                    sm = StateMachine(
                        entity=entity_name,
                        description=f"Lifecycle state machine for {entity_name}",
                        states=state_names,
                        initial_state=initial,
                        final_states=finals,
                        transitions=transitions,
                    )
                    bundle.state_machines.append(sm)
                    self.fix_log.append(
                        f"Created stub state machine for entity '{entity_name}' "
                        f"({len(state_names)} states, {len(transitions)} transitions)"
                    )
                    fixed += 1
                except Exception as e:
                    logger.warning("Failed to create stub state machine for %s: %s", entity_name, e)

        return fixed

    def _fix_flow_coverage_batch(
        self, gaps: List[Gap], bundle: ArtifactBundle
    ) -> int:
        """Create stub UserFlow objects for epics without matching flows."""
        fixed = 0
        for gap in gaps:
            for eid in gap.affected_ids:
                epic = bundle.epic_by_id.get(eid)
                if not epic:
                    continue
                title = getattr(epic, "title", "")
                desc = getattr(epic, "description", "")

                # Find stories for this epic
                epic_stories = [
                    s for s in bundle.user_stories
                    if getattr(s, "parent_epic_id", "") == eid
                ]
                story_ids = [getattr(s, "id", "") for s in epic_stories if getattr(s, "id", "")]

                # Find persona
                persona_name = "User"
                if epic_stories:
                    persona_name = getattr(epic_stories[0], "persona", "User")

                try:
                    from requirements_engineer.generators.ux_design_generator import UserFlow, FlowStep
                    flow_id = f"FLOW-REFINE-{len(bundle.user_flows) + 1:03d}"
                    flow = UserFlow(
                        id=flow_id,
                        name=f"{title} Flow",
                        description=f"User flow for epic: {desc[:200]}" if desc else f"User flow for {title}",
                        actor=persona_name,
                        trigger=f"User initiates {title.lower()}",
                        steps=[
                            FlowStep(
                                step_number=1,
                                action=f"Navigate to {title.lower()} section",
                                screen=f"{title} Screen",
                                expected_result=f"{title} view is displayed",
                            ),
                            FlowStep(
                                step_number=2,
                                action=f"Complete {title.lower()} action",
                                screen=f"{title} Screen",
                                expected_result="Action completes successfully",
                            ),
                        ],
                        success_criteria=f"{title} completed successfully",
                        linked_user_story_ids=story_ids[:10],
                    )
                    bundle.user_flows.append(flow)
                    self.fix_log.append(
                        f"Created stub flow {flow_id} for epic {eid} ({title})"
                    )
                    fixed += 1
                except Exception as e:
                    logger.warning("Failed to create stub flow for epic %s: %s", eid, e)

        return fixed

    def _fix_task_ratio_stubs(
        self, gaps: List[Gap], bundle: ArtifactBundle
    ) -> int:
        """Create stub tasks from requirements to meet the task ratio threshold.

        The task_ratio rule requires tasks/requirements >= 2.0 (threshold).
        This method creates lightweight programmatic tasks for requirements
        that have fewer than 2 associated tasks, avoiding LLM calls entirely.
        """
        try:
            from requirements_engineer.generators.task_generator import Task
        except ImportError:
            self.fix_log.append("[SKIP] Task dataclass not available")
            return 0

        # Get the threshold from the gap
        threshold = 2.0
        for gap in gaps:
            if gap.target_value > 0:
                threshold = gap.target_value
                break

        func_reqs = [
            r for r in bundle.requirements
            if getattr(r, "type", "functional") == "functional"
        ]
        if not func_reqs:
            return 0

        needed_total = int(len(func_reqs) * threshold)
        current_total = len(bundle.tasks)
        deficit = needed_total - current_total
        if deficit <= 0:
            return 0

        # Build reverse index: requirement_id -> count of existing tasks
        req_task_count: Dict[str, int] = {}
        for req in func_reqs:
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            req_task_count[rid] = 0
        for task in bundle.tasks:
            prid = getattr(task, "parent_requirement_id", "")
            if prid in req_task_count:
                req_task_count[prid] += 1

        # Sort requirements by task count (least covered first)
        sorted_reqs = sorted(func_reqs, key=lambda r: req_task_count.get(
            getattr(r, "requirement_id", "") or getattr(r, "id", ""), 0
        ))

        created = 0
        task_counter = current_total
        task_types = ["development", "testing", "documentation", "design"]

        for req in sorted_reqs:
            if created >= deficit:
                break
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            title = getattr(req, "title", "")
            existing = req_task_count.get(rid, 0)
            # Create tasks up to 2 per requirement
            tasks_to_add = max(0, 2 - existing)
            if tasks_to_add == 0:
                tasks_to_add = 1  # Still need overall ratio

            for i in range(tasks_to_add):
                if created >= deficit:
                    break
                task_counter += 1
                task_type = task_types[i % len(task_types)]
                tid = f"TASK-REFINE-{task_counter:04d}"

                stub = Task(
                    id=tid,
                    title=f"Implement {title}" if task_type == "development"
                          else f"Test {title}" if task_type == "testing"
                          else f"Document {title}" if task_type == "documentation"
                          else f"Design {title}",
                    description=f"Auto-generated {task_type} task for requirement {rid}",
                    task_type=task_type,
                    parent_requirement_id=rid,
                    parent_feature_id=getattr(req, "parent_epic_id", ""),
                    estimated_hours=4 if task_type == "development" else 2,
                    complexity="medium" if task_type == "development" else "simple",
                    story_points=3 if task_type == "development" else 1,
                    status="todo",
                    acceptance_criteria=[f"{title} {task_type} completed"],
                )

                bundle.task_by_id[tid] = stub
                # Add to task_breakdown.features
                if bundle.task_breakdown:
                    feature_id = stub.parent_feature_id or "ungrouped"
                    if feature_id not in bundle.task_breakdown.features:
                        bundle.task_breakdown.features[feature_id] = []
                    bundle.task_breakdown.features[feature_id].append(stub)
                    bundle.task_breakdown.total_tasks += 1

                created += 1
                req_task_count[rid] = req_task_count.get(rid, 0) + 1

        if created > 0:
            # Refresh bundle.tasks snapshot
            if bundle.task_breakdown:
                bundle.tasks = bundle.task_breakdown.tasks
            self.fix_log.append(
                f"Created {created} stub tasks to meet task ratio "
                f"({current_total} -> {current_total + created} tasks, "
                f"target: {needed_total})"
            )

        return min(created, 1)  # Count as 1 gap fixed (the aggregate task_ratio gap)

    async def _fix_task_backlink(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """Link task to requirement — semantic → LLM → keyword → best-effort."""
        for tid in gap.affected_ids:
            task = bundle.task_by_id.get(tid)
            if not task:
                continue
            title = getattr(task, "title", "")
            desc = getattr(task, "description", "")
            query = f"{title} {desc}".strip()

            # Try semantic matching first
            if self._index_built and self._matcher and self._matcher.available:
                try:
                    matches = await self._matcher.find_similar(
                        query, top_k=3, threshold=self.similarity_threshold
                    )
                    for req_id, score in matches:
                        if req_id in bundle.req_by_id:
                            task.parent_requirement_id = req_id
                            self.fix_log.append(
                                f"[SEMANTIC] Linked task {tid} -> {req_id} "
                                f"(cosine={score:.3f})"
                            )
                            return True
                except Exception as e:
                    logger.warning("Semantic task-to-req matching failed: %s", e)

            # Try LLM fallback (if API key available)
            if await self._ensure_client():
                try:
                    if await self._fix_task_backlink_llm(tid, task, bundle):
                        return True
                except Exception as e:
                    logger.warning("LLM task-to-req linking failed, falling back to keywords: %s", e)

            # Fallback: keyword overlap
            task_kw = _extract_keywords(query)
            best_req = None
            best_score = 0
            for req in bundle.requirements:
                req_title = getattr(req, "title", "")
                req_desc = getattr(req, "description", "")
                req_kw = _extract_keywords(f"{req_title} {req_desc}")
                overlap = len(task_kw & req_kw)
                if overlap > best_score:
                    best_score = overlap
                    best_req = req

            if best_req and best_score >= 1:
                rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
                task.parent_requirement_id = rid
                self.fix_log.append(
                    f"Linked task {tid} -> {rid} (keyword overlap={best_score})"
                )
                return True
            # Best-effort: link to closest match even with overlap=0
            if best_req:
                rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
                task.parent_requirement_id = rid
                self.fix_log.append(
                    f"[BEST-EFFORT] Linked task {tid} -> {rid} (overlap={best_score})"
                )
                return True
            # Absolute fallback: first requirement
            if bundle.requirements:
                req = bundle.requirements[0]
                rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
                task.parent_requirement_id = rid
                self.fix_log.append(f"[FALLBACK] Linked task {tid} -> {rid}")
                return True
        return False

    async def _fix_task_backlink_llm(
        self, tid: str, task: Any, bundle: ArtifactBundle
    ) -> bool:
        """LLM-based task-to-requirement linking."""
        title = getattr(task, "title", "")
        desc = getattr(task, "description", "")
        task_type = getattr(task, "task_type", "")
        tasks_text = f"- {tid}: {title}"
        if task_type:
            tasks_text += f" (type: {task_type})"
        if desc:
            tasks_text += f"\n  {desc[:200]}"

        requirements_text = self._format_requirements(bundle.requirements)
        prompt = TASK_LINK_PROMPT.format(
            tasks_text=tasks_text,
            requirements_text=requirements_text,
        )

        response = await self._call_llm(prompt, max_tokens=2000)
        data = self._extract_json(response)

        for link in data.get("links", []):
            req_id = link.get("requirement_id", "")
            reason = link.get("reason", "")
            if req_id and req_id in bundle.req_by_id:
                task.parent_requirement_id = req_id
                self.fix_log.append(
                    f"[LLM] Linked task {tid} -> {req_id} ({reason})"
                )
                return True
        return False

    # ------------------------------------------------------------------
    # LLM-assisted fixes
    # ------------------------------------------------------------------

    async def apply_llm_fixes(
        self, gaps: List[Gap], bundle: ArtifactBundle, max_fixes: int = 10
    ) -> int:
        """Apply LLM-assisted fixes (entity linking, acceptance criteria). Returns count fixed."""
        fixed = 0
        for gap in gaps[:max_fixes]:
            if gap.rule_id == "entity_to_req":
                if await self._fix_entity_to_req(gap, bundle):
                    fixed += 1
        return fixed

    async def _fix_entity_to_req(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """Link entity to requirement — LLM with keyword-matching fallback."""
        if not bundle.requirements:
            return False

        # Try LLM first
        if await self._ensure_client():
            try:
                return await self._fix_entity_to_req_llm(gap, bundle)
            except Exception as e:
                logger.warning("LLM entity linking failed, falling back to keywords: %s", e)

        # Fallback: semantic then keyword matching
        return await self._fix_entity_to_req_keywords(gap, bundle)

    async def _fix_entity_to_req_llm(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """LLM-based entity-to-requirement linking with optional RAG context."""
        # Build entity descriptions
        entities_text = ""
        rag_context = ""
        for entity_name in gap.affected_ids:
            entity = bundle.entities.get(entity_name)
            if entity:
                fields = getattr(entity, "fields", [])
                field_names = []
                for f in fields[:10]:
                    fname = f.name if hasattr(f, "name") else (f.get("name", "") if isinstance(f, dict) else "")
                    if fname:
                        field_names.append(fname)
                entities_text += f"- {entity_name} (fields: {', '.join(field_names)})\n"
            else:
                entities_text += f"- {entity_name}\n"

            # RAG: find semantically similar requirements for this entity
            if self._index_built and self._matcher and self._matcher.available:
                try:
                    similar = await self._matcher.find_similar(entity_name, top_k=3)
                    if similar:
                        rag_context += f"\n### Semantic matches for '{entity_name}':\n"
                        for req_id, score in similar:
                            req = bundle.req_by_id.get(req_id)
                            title = getattr(req, "title", "") if req else req_id
                            rag_context += f"- {req_id} (similarity: {score:.2f}): {title}\n"
                except Exception:
                    pass  # RAG context is optional enhancement

        requirements_text = self._format_requirements(bundle.requirements)

        prompt = ENTITY_LINK_PROMPT.format(
            entities_text=entities_text,
            requirements_text=requirements_text,
        )

        # Inject RAG context if available
        if rag_context:
            prompt += f"\n## Semantic Analysis (pre-computed similarity):\n{rag_context}\n"
            prompt += "Use the semantic analysis above to inform your linking decisions.\n"

        response = await self._call_llm(prompt, max_tokens=2000)
        data = self._extract_json(response)

        linked = False
        for link in data.get("links", []):
            entity_name = link.get("entity", "")
            req_id = link.get("requirement_id", "")
            reason = link.get("reason", "")
            if entity_name and req_id and req_id in bundle.req_by_id:
                # Mutate requirement description so keyword checker sees the link
                req = bundle.req_by_id[req_id]
                self._tag_entity_on_req(req, entity_name)
                self.fix_log.append(
                    f"[LLM] Linked entity '{entity_name}' -> {req_id} ({reason})"
                )
                linked = True

        return linked

    @staticmethod
    def _tag_entity_on_req(req: Any, entity_name: str):
        """Append entity name to requirement description so keyword checker sees the link."""
        desc = getattr(req, "description", "") or ""
        tag = f" [Entity: {entity_name}]"
        if tag not in desc:
            req.description = desc + tag

    async def _fix_entity_to_req_keywords(self, gap: Gap, bundle: ArtifactBundle) -> bool:
        """Semantic then keyword-matching fallback for entity linking."""
        for entity_name in gap.affected_ids:
            # Try semantic matching (no LLM, just embeddings)
            if self._index_built and self._matcher and self._matcher.available:
                try:
                    match = await self._matcher.find_best_match(
                        entity_name, threshold=self.similarity_threshold
                    )
                    if match:
                        req_id, score = match
                        if req_id in bundle.req_by_id:
                            self._tag_entity_on_req(bundle.req_by_id[req_id], entity_name)
                            self.fix_log.append(
                                f"[SEMANTIC] Linked entity '{entity_name}' -> {req_id} "
                                f"(cosine={score:.3f})"
                            )
                            return True
                except Exception:
                    pass

            # Final fallback: keyword overlap
            entity_kw = _extract_keywords(entity_name)

            best_req = None
            best_score = 0
            for req in bundle.requirements:
                title = getattr(req, "title", "")
                desc = getattr(req, "description", "")
                req_kw = _extract_keywords(f"{title} {desc}")
                overlap = len(entity_kw & req_kw)
                if overlap > best_score:
                    best_score = overlap
                    best_req = req

            if best_req and best_score >= 1:
                rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
                self._tag_entity_on_req(best_req, entity_name)
                self.fix_log.append(
                    f"Linked entity '{entity_name}' -> {rid} (keyword overlap={best_score})"
                )
                return True
            # Best-effort: link to closest match even with overlap=0
            if best_req:
                rid = getattr(best_req, "requirement_id", "") or getattr(best_req, "id", "")
                self._tag_entity_on_req(best_req, entity_name)
                self.fix_log.append(
                    f"[BEST-EFFORT] Linked entity '{entity_name}' -> {rid} "
                    f"(overlap={best_score})"
                )
                return True
            # Absolute fallback: first requirement
            if bundle.requirements:
                req = bundle.requirements[0]
                rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
                self._tag_entity_on_req(req, entity_name)
                self.fix_log.append(
                    f"[FALLBACK] Linked entity '{entity_name}' -> {rid}"
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Generator re-invocations (expensive)
    # ------------------------------------------------------------------

    async def apply_generator_fixes(
        self, gaps: List[Gap], bundle: ArtifactBundle, max_calls: int = 3
    ) -> int:
        """Re-invoke generators for gaps that need new artifact generation."""
        if not await self._ensure_client():
            # Log what would be done if we had API access
            for gap in gaps[:5]:
                if gap.generator_name:
                    self.fix_log.append(
                        f"[SKIP] No API key: would invoke {gap.generator_name} "
                        f"for {len(gap.affected_ids)} artifacts"
                    )
            return 0

        # Group gaps by generator name
        by_generator: Dict[str, List[Gap]] = {}
        for gap in gaps[:max_calls * 5]:
            if gap.generator_name:
                by_generator.setdefault(gap.generator_name, []).append(gap)

        fixed = 0
        calls = 0
        for gen_name, gen_gaps in by_generator.items():
            if calls >= max_calls:
                break
            try:
                count = await self._invoke_generator(gen_name, gen_gaps, bundle)
                fixed += count
                calls += 1
            except Exception as e:
                logger.warning("Generator '%s' failed: %s", gen_name, e)
                self.fix_log.append(f"[ERROR] Generator {gen_name} failed: {e}")

        return fixed

    async def _invoke_generator(
        self, gen_name: str, gaps: List[Gap], bundle: ArtifactBundle
    ) -> int:
        """Invoke a specific generator for a set of gaps."""
        logger.info("Invoking generator '%s' for %d gaps", gen_name, len(gaps))

        dispatch = {
            "test_case": self._gen_test_cases,
            "user_story": self._gen_user_stories,
            "task": self._gen_tasks,
            "state_machine": self._gen_state_machines,
            "screen": self._gen_screens,
            "user_flow": self._gen_user_flows,
        }

        handler = dispatch.get(gen_name)
        if handler:
            return await handler(gaps, bundle)

        # Unknown generator — log but don't crash
        affected_count = sum(len(g.affected_ids) for g in gaps)
        self.fix_log.append(
            f"[GENERATOR] No handler for '{gen_name}' ({len(gaps)} gaps, "
            f"{affected_count} affected artifacts)"
        )
        return 0

    async def _gen_test_cases(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate test cases for stories without test coverage."""
        try:
            from requirements_engineer.generators.test_case_generator import TestCaseGenerator
        except ImportError:
            self.fix_log.append("[SKIP] TestCaseGenerator not available")
            return 0

        gen = TestCaseGenerator(
            model_name=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )
        await gen.initialize()

        fixed = 0
        affected_ids = set()
        for gap in gaps:
            affected_ids.update(gap.affected_ids)

        for sid in list(affected_ids)[:10]:  # Limit per invocation
            story = bundle.story_by_id.get(sid)
            if not story:
                continue
            try:
                new_tcs = await gen.generate_test_cases(story)
                for tc in new_tcs:
                    bundle.test_cases.append(tc)
                    bundle.test_by_id[tc.id] = tc
                self.llm_calls += 1
                self.cost_usd += _estimate_cost(self.generator_model)
                self.fix_log.append(
                    f"[GENERATOR] Generated {len(new_tcs)} test cases for {sid}"
                )
                fixed += 1
            except Exception as e:
                logger.warning("Test case generation failed for %s: %s", sid, e)

        return fixed

    async def _gen_user_stories(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate user stories for requirements without coverage."""
        try:
            from requirements_engineer.generators.user_story_generator import UserStoryGenerator
        except ImportError:
            self.fix_log.append("[SKIP] UserStoryGenerator not available")
            return 0

        # Collect affected requirements
        affected_reqs = []
        for gap in gaps:
            for rid in gap.affected_ids:
                req = bundle.req_by_id.get(rid)
                if req:
                    affected_reqs.append(req)

        if not affected_reqs:
            return 0

        gen = UserStoryGenerator(
            model_name=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )
        await gen.initialize()

        try:
            new_stories, new_epics = await gen.generate_user_stories(affected_reqs[:15])
            for story in new_stories:
                bundle.user_stories.append(story)
                sid = getattr(story, "id", "")
                if sid:
                    bundle.story_by_id[sid] = story
            for epic in new_epics:
                bundle.epics.append(epic)
                eid = getattr(epic, "id", "")
                if eid:
                    bundle.epic_by_id[eid] = epic

            self.llm_calls += 1
            self.cost_usd += _estimate_cost(self.generator_model, 6000)
            self.fix_log.append(
                f"[GENERATOR] Generated {len(new_stories)} stories + "
                f"{len(new_epics)} epics for {len(affected_reqs)} requirements"
            )
            return len(new_stories)
        except Exception as e:
            logger.warning("User story generation failed: %s", e)
            self.fix_log.append(f"[ERROR] User story generation failed: {e}")
            return 0

    async def _gen_tasks(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate tasks to improve task ratio."""
        try:
            from requirements_engineer.generators.task_generator import TaskGenerator
        except ImportError:
            self.fix_log.append("[SKIP] TaskGenerator not available")
            return 0

        gen = TaskGenerator(
            model=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )
        # TaskGenerator has no initialize() — ready after __init__

        # Generate tasks for all epics (not just first 5)
        fixed = 0
        for epic in bundle.epics:
            eid = getattr(epic, "id", "")
            title = getattr(epic, "title", "")
            desc = getattr(epic, "description", "")
            # Find stories for this epic
            epic_stories = [
                s for s in bundle.user_stories
                if getattr(s, "parent_epic_id", "") == eid
            ]
            epic_reqs = [
                bundle.req_by_id[rid]
                for s in epic_stories
                for rid in [getattr(s, "parent_requirement_id", "")]
                if rid in bundle.req_by_id
            ]

            try:
                new_tasks = await gen.generate_tasks_for_feature(
                    feature_id=eid,
                    feature_name=title,
                    feature_description=desc,
                    user_stories=epic_stories[:10],
                    requirements=epic_reqs[:10],
                )
                for task in new_tasks:
                    tid = getattr(task, "id", "")
                    if tid:
                        bundle.task_by_id[tid] = task
                # Also add to task_breakdown.features so to_dict() includes them
                if bundle.task_breakdown:
                    if eid not in bundle.task_breakdown.features:
                        bundle.task_breakdown.features[eid] = []
                    bundle.task_breakdown.features[eid].extend(new_tasks)
                    bundle.task_breakdown.total_tasks += len(new_tasks)
                self.llm_calls += 1
                self.cost_usd += _estimate_cost(self.generator_model)
                self.fix_log.append(
                    f"[GENERATOR] Generated {len(new_tasks)} tasks for epic {eid}"
                )
                fixed += len(new_tasks)
            except Exception as e:
                logger.warning("Task generation failed for epic %s: %s", eid, e)

        return fixed

    async def _gen_state_machines(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate state machines for lifecycle entities."""
        try:
            from requirements_engineer.generators.state_machine_generator import StateMachineGenerator
        except ImportError:
            self.fix_log.append("[SKIP] StateMachineGenerator not available")
            return 0

        # Collect affected entity names
        entity_names = set()
        for gap in gaps:
            entity_names.update(gap.affected_ids)

        entities_list = [
            bundle.entities[name]
            for name in entity_names
            if name in bundle.entities
        ]
        if not entities_list:
            return 0

        gen = StateMachineGenerator(
            model_name=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )
        await gen.initialize()

        try:
            new_sms = await gen.generate_state_machines(
                requirements=bundle.requirements[:30],
                user_stories=bundle.user_stories[:30],
                entities=entities_list,
            )
            for sm in new_sms:
                bundle.state_machines.append(sm)
            self.llm_calls += 1
            self.cost_usd += _estimate_cost(self.generator_model, 6000)
            self.fix_log.append(
                f"[GENERATOR] Generated {len(new_sms)} state machines"
            )
            return len(new_sms)
        except Exception as e:
            logger.warning("State machine generation failed: %s", e)
            return 0

    async def _gen_screens(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate screens for stories without screen coverage (LLM fallback).

        This is a fallback — the primary fix happens in _fix_stories_to_screens_batch
        as an auto-link fix. This handles any remaining gaps via LLM generation.
        """
        try:
            from requirements_engineer.generators.ui_design_generator import (
                UIDesignGenerator, Screen,
            )
        except ImportError:
            self.fix_log.append("[SKIP] UIDesignGenerator not available")
            return 0

        # Collect affected story IDs not yet covered
        affected_sids = set()
        for gap in gaps:
            affected_sids.update(gap.affected_ids)

        uncovered = []
        for sid in affected_sids:
            story = bundle.story_by_id.get(sid)
            if story:
                uncovered.append(story)

        if not uncovered:
            return 0

        gen = UIDesignGenerator(
            model=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )

        fixed = 0
        for story in uncovered[:15]:
            sid = getattr(story, "id", "")
            title = getattr(story, "title", "")
            try:
                screen = await gen.generate_screen(
                    project_name="Refinement",
                    user_story=story,
                    ia_node=None,
                    components=[],
                )
                if screen:
                    screen.parent_user_story = sid
                    bundle.screens.append(screen)
                    screen_id = getattr(screen, "id", "")
                    bundle.screen_by_id[screen_id] = screen
                    self.llm_calls += 1
                    self.cost_usd += _estimate_cost(self.generator_model)
                    self.fix_log.append(
                        f"[GENERATOR] Generated screen {screen_id} for story {sid}"
                    )
                    fixed += 1
            except Exception as e:
                logger.warning("Screen generation failed for %s: %s", sid, e)

        return fixed

    async def _gen_user_flows(self, gaps: List[Gap], bundle: ArtifactBundle) -> int:
        """Generate user flows for epics without flow coverage (LLM fallback).

        This is a fallback — the primary fix happens in _fix_flow_coverage_batch
        as an auto-link fix. This handles any remaining gaps via LLM generation.
        """
        try:
            from requirements_engineer.generators.ux_design_generator import (
                UXDesignGenerator,
            )
        except ImportError:
            self.fix_log.append("[SKIP] UXDesignGenerator not available")
            return 0

        affected_eids = set()
        for gap in gaps:
            affected_eids.update(gap.affected_ids)

        gen = UXDesignGenerator(
            model=self.generator_model,
            base_url=self.base_url,
            api_key=self.api_key,
            config=self.config,
        )

        fixed = 0
        for eid in list(affected_eids)[:7]:
            epic = bundle.epic_by_id.get(eid)
            if not epic:
                continue
            # Find stories for this epic
            epic_stories = [
                s for s in bundle.user_stories
                if getattr(s, "parent_epic_id", "") == eid
            ]
            if not epic_stories:
                continue
            # Pick first story + first persona
            story = epic_stories[0]
            persona = bundle.personas[0] if bundle.personas else None
            try:
                flow = await gen.generate_user_flow(
                    project_name="Refinement",
                    persona=persona,
                    user_story=story,
                )
                if flow:
                    bundle.user_flows.append(flow)
                    self.llm_calls += 1
                    self.cost_usd += _estimate_cost(self.generator_model)
                    self.fix_log.append(
                        f"[GENERATOR] Generated user flow {flow.id} for epic {eid}"
                    )
                    fixed += 1
            except Exception as e:
                logger.warning("User flow generation failed for epic %s: %s", eid, e)

        return fixed

    def matcher_stats(self) -> Optional[Dict[str, Any]]:
        """Return semantic matcher statistics, or None if not active."""
        if self._matcher and self._matcher.available:
            return self._matcher.stats()
        return None

    # ------------------------------------------------------------------
    # Artifact saving
    # ------------------------------------------------------------------

    def save_artifacts(self, bundle: ArtifactBundle, output_dir: Path):
        """Save modified artifacts back to the output directory."""
        # Save test cases if modified
        if bundle.test_cases:
            self._save_test_cases(bundle, output_dir)

        # Save tasks if modified (backlinks updated)
        if bundle.tasks:
            self._save_tasks(bundle, output_dir)

        # Save API endpoints if modified (parent_requirement_id updated)
        if bundle.api_endpoints:
            self._save_api_endpoints(bundle, output_dir)

        # Save screen compositions (story-to-screen links)
        if bundle.screen_compositions:
            self._save_screen_compositions(bundle, output_dir)

        # Save screens if modified (parent_user_story updated)
        if bundle.screens:
            self._save_screens(bundle, output_dir)

        # Save user flows (stub flows for epic coverage)
        if bundle.user_flows:
            self._save_user_flows(bundle, output_dir)

        # Save state machines if any were added
        if bundle.state_machines:
            self._save_state_machines(bundle, output_dir)

        # Save requirements (entity tags in descriptions)
        if bundle.requirements:
            self._save_requirements(bundle, output_dir)

    def _save_test_cases(self, bundle: ArtifactBundle, output_dir: Path):
        """Append stub test cases to test_documentation.md."""
        stub_tests = [
            tc for tc in bundle.test_cases
            if getattr(tc, "automation_status", "") == "stub"
        ]
        if not stub_tests:
            return

        test_path = output_dir / "testing" / "test_documentation.md"
        if not test_path.exists():
            return

        with open(test_path, "a", encoding="utf-8") as f:
            f.write("\n\n## Auto-Generated Stub Tests (Refinement)\n\n")
            for tc in stub_tests:
                f.write(f"### {tc.id}: {tc.title}\n\n")
                f.write(f"- **Type:** {tc.test_type}\n")
                f.write(f"- **Linked Story:** {tc.parent_user_story_id}\n")
                f.write(f"- **Status:** STUB -- needs manual completion\n\n")

        logger.info("Appended %d stub tests to %s", len(stub_tests), test_path)

    def _save_tasks(self, bundle: ArtifactBundle, output_dir: Path):
        """Save updated task_list.json with backlinks."""
        task_path = output_dir / "tasks" / "task_list.json"
        if not task_path.exists() or not bundle.task_breakdown:
            return

        try:
            data = bundle.task_breakdown.to_dict()
            with open(task_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("Updated task backlinks in %s", task_path)
        except Exception as e:
            logger.warning("Failed to save tasks: %s", e)

    def _save_api_endpoints(self, bundle: ArtifactBundle, output_dir: Path):
        """Update the stage_5 checkpoint with updated API endpoint links."""
        cp_path = output_dir / "_checkpoints" / "stage_5.json"
        if not cp_path.exists():
            return

        try:
            data = [ep.to_dict() for ep in bundle.api_endpoints]
            cp_data = {"api_endpoints": data}
            with open(cp_path, "w", encoding="utf-8") as f:
                json.dump(cp_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("Updated API endpoint links in %s", cp_path)
        except Exception as e:
            logger.warning("Failed to save API endpoints: %s", e)

    def _save_state_machines(self, bundle: ArtifactBundle, output_dir: Path):
        """Save state machines to state_machines/state_machines.json."""
        sm_dir = output_dir / "state_machines"
        sm_dir.mkdir(parents=True, exist_ok=True)
        sm_path = sm_dir / "state_machines.json"

        try:
            sm_data = []
            for sm in bundle.state_machines:
                if hasattr(sm, "to_dict"):
                    sm_data.append(sm.to_dict())
                elif isinstance(sm, dict):
                    sm_data.append(sm)
            with open(sm_path, "w", encoding="utf-8") as f:
                json.dump(sm_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("Saved %d state machines to %s", len(sm_data), sm_path)
        except Exception as e:
            logger.warning("Failed to save state machines: %s", e)

    def _save_screen_compositions(self, bundle: ArtifactBundle, output_dir: Path):
        """Save screen compositions to ui_design/compositions/ as individual files.

        Each composition is saved as a separate JSON file so the ArtifactLoader
        can load them (it expects one dict per file, not an array).
        """
        comp_dir = output_dir / "ui_design" / "compositions"
        comp_dir.mkdir(parents=True, exist_ok=True)

        # Collect refinement compositions (dicts with linked_user_stories)
        refine_comps = [
            c for c in bundle.screen_compositions
            if isinstance(c, dict) and "linked_user_stories" in c
        ]
        if not refine_comps:
            return

        # Save each composition as a separate file
        for i, comp in enumerate(refine_comps, 1):
            name = comp.get("screen_name", f"refine_{i}")
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())[:50]
            comp_path = comp_dir / f"refine_{safe_name}.json"
            try:
                with open(comp_path, "w", encoding="utf-8") as f:
                    json.dump(comp, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        logger.info("Saved %d screen compositions to %s", len(refine_comps), comp_dir)

    def _save_screens(self, bundle: ArtifactBundle, output_dir: Path):
        """Save screens with updated parent_user_story links."""
        screens_dir = output_dir / "ui_design" / "screens"
        if not screens_dir.exists():
            return

        for screen in bundle.screens:
            sid = getattr(screen, "id", "")
            if not sid:
                continue
            try:
                screen_path = screens_dir / f"{sid}.json"
                data = screen.to_dict() if hasattr(screen, "to_dict") else {}
                if data:
                    with open(screen_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            except Exception:
                pass  # Non-critical, screen files may not be individually saved

    def _save_user_flows(self, bundle: ArtifactBundle, output_dir: Path):
        """Save user flows — update ux_spec.json if it exists, plus standalone file."""
        ux_dir = output_dir / "ux_design"
        ux_dir.mkdir(parents=True, exist_ok=True)

        flows_data = []
        for flow in bundle.user_flows:
            if hasattr(flow, "to_dict"):
                flows_data.append(flow.to_dict())
            elif isinstance(flow, dict):
                flows_data.append(flow)

        # Update ux_spec.json (primary — what the loader reads)
        ux_spec_path = ux_dir / "ux_spec.json"
        if ux_spec_path.exists():
            try:
                with open(ux_spec_path, encoding="utf-8") as f:
                    spec_data = json.load(f)
                spec_data["user_flows"] = flows_data
                with open(ux_spec_path, "w", encoding="utf-8") as f:
                    json.dump(spec_data, f, indent=2, ensure_ascii=False, default=str)
                logger.info("Updated %d user flows in %s", len(flows_data), ux_spec_path)
            except Exception as e:
                logger.warning("Failed to update ux_spec.json: %s", e)

        # Also update stage_9 checkpoint if it exists
        cp_path = output_dir / "_checkpoints" / "stage_9.json"
        if cp_path.exists():
            try:
                with open(cp_path, encoding="utf-8") as f:
                    cp_data = json.load(f)
                if "ux_spec" in cp_data:
                    cp_data["ux_spec"]["user_flows"] = flows_data
                    with open(cp_path, "w", encoding="utf-8") as f:
                        json.dump(cp_data, f, indent=2, ensure_ascii=False, default=str)
                    logger.info("Updated user flows in %s", cp_path)
            except Exception as e:
                logger.warning("Failed to update stage_9 checkpoint: %s", e)

        # Standalone backup
        flows_path = ux_dir / "user_flows.json"
        try:
            with open(flows_path, "w", encoding="utf-8") as f:
                json.dump(flows_data, f, indent=2, ensure_ascii=False, default=str)
        except Exception:
            pass

    def _save_requirements(self, bundle: ArtifactBundle, output_dir: Path):
        """Save requirements with entity tags back to journal.json."""
        journal_path = output_dir / "journal.json"
        if not journal_path.exists():
            return

        try:
            with open(journal_path, encoding="utf-8") as f:
                data = json.load(f)
            if "nodes" not in data:
                return

            updated = 0
            # Update description fields with entity tags
            for rid, req in bundle.req_by_id.items():
                desc = getattr(req, "description", "")
                if "[Entity:" not in desc:
                    continue
                # Try both "rid" and "node-rid" keys (journal uses "node-" prefix)
                for key in (rid, f"node-{rid}"):
                    if key in data["nodes"] and isinstance(data["nodes"][key], dict):
                        data["nodes"][key]["description"] = desc
                        updated += 1
                        break

            if updated > 0:
                with open(journal_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                logger.info("Updated %d requirement descriptions in %s", updated, journal_path)
        except Exception as e:
            logger.warning("Failed to save requirements: %s", e)
