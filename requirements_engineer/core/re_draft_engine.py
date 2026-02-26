"""
Requirements Draft Engine - Parallel draft generation for requirements.

Based on ai_scientist/treesearch/parallel_agent.py draft patterns.
Generates multiple requirement variants from different perspectives.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
import logging
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from .re_journal import RequirementNode, RequirementJournal, NodeStageType

logger = logging.getLogger("re-draft-engine")


@dataclass
class DraftPerspective:
    """A perspective for generating requirement drafts."""
    name: str
    description: str
    focus_areas: List[str]
    prompt_modifier: str


# Default perspectives for parallel drafting
DEFAULT_PERSPECTIVES = [
    DraftPerspective(
        name="technical",
        description="Technical implementation perspective",
        focus_areas=["architecture", "APIs", "data models", "performance", "security"],
        prompt_modifier="""Focus on TECHNICAL aspects:
- Implementation feasibility and architecture
- API contracts and data structures
- Performance requirements and constraints
- Security considerations
- Integration points with existing systems"""
    ),
    DraftPerspective(
        name="business",
        description="Business and stakeholder perspective",
        focus_areas=["ROI", "workflows", "compliance", "KPIs", "user segments"],
        prompt_modifier="""Focus on BUSINESS aspects:
- Business value and ROI
- Workflow improvements
- Compliance and regulatory requirements
- Key performance indicators (KPIs)
- Stakeholder priorities and concerns"""
    ),
    DraftPerspective(
        name="user",
        description="End-user experience perspective",
        focus_areas=["usability", "accessibility", "error handling", "feedback", "onboarding"],
        prompt_modifier="""Focus on USER EXPERIENCE aspects:
- Usability and intuitive design
- Accessibility requirements
- Error handling and user feedback
- User journeys and scenarios
- Onboarding and learning curve"""
    ),
]


@dataclass
class DraftResult:
    """Result of a draft generation attempt."""
    node: RequirementNode
    perspective: str
    success: bool
    error: Optional[str] = None


class RequirementDraftEngine:
    """
    Generates parallel requirement drafts from different perspectives.

    Similar to AI-Scientist's parallel draft generation, but adapted
    for requirements engineering instead of code generation.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        journal: RequirementJournal,
        query_func: Any = None  # LLM query function
    ):
        """
        Initialize the draft engine.

        Args:
            config: Configuration dict with search.num_drafts, etc.
            journal: RequirementJournal to add nodes to
            query_func: Function to query LLM (from backend)
        """
        self.config = config
        self.journal = journal
        self.query_func = query_func

        # Extract search config
        search_config = config.get("agent", {}).get("search", {})
        self.num_drafts = search_config.get("num_drafts", 3)
        self.max_debug_depth = search_config.get("max_debug_depth", 2)

        # Validation thresholds
        self.thresholds = config.get("validation", {})

        # Metric weights
        self.metric_weights = config.get("metric_weights", {})

        # Perspectives to use
        self.perspectives = DEFAULT_PERSPECTIVES[:self.num_drafts]

        # PERFORMANCE: Evaluation cache to avoid redundant LLM calls
        self._eval_cache: Dict[str, Dict[str, float]] = {}

    def generate_drafts(
        self,
        context: Dict[str, Any],
        stage: int,
        base_prompt: str,
        existing_requirements: List[RequirementNode] = None
    ) -> List[DraftResult]:
        """
        Generate multiple requirement drafts in parallel.

        Uses ThreadPoolExecutor for ~3x speedup with 3 perspectives.

        Args:
            context: Project context (name, description, domain, etc.)
            stage: Current stage number (1-4)
            base_prompt: Base prompt for requirement generation
            existing_requirements: Existing requirements to consider

        Returns:
            List of DraftResult objects with generated nodes
        """
        results = []

        # PERFORMANCE: Generate drafts in parallel using ThreadPoolExecutor
        max_workers = min(3, len(self.perspectives))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all draft generation tasks
            futures = {
                executor.submit(
                    self._generate_single_draft,
                    context,
                    stage,
                    base_prompt,
                    perspective,
                    existing_requirements
                ): perspective
                for perspective in self.perspectives
            }

            # Collect results as they complete
            for future in as_completed(futures):
                perspective = futures[future]
                try:
                    node = future.result()
                    results.append(DraftResult(
                        node=node,
                        perspective=perspective.name,
                        success=True
                    ))
                except Exception as e:
                    logger.error(f"Failed to generate draft for {perspective.name}: {e}")
                    results.append(DraftResult(
                        node=None,
                        perspective=perspective.name,
                        success=False,
                        error=str(e)
                    ))

        return results

    def _generate_single_draft(
        self,
        context: Dict[str, Any],
        stage: int,
        base_prompt: str,
        perspective: DraftPerspective,
        existing_requirements: List[RequirementNode] = None
    ) -> RequirementNode:
        """
        Generate a single requirement draft for a given perspective.

        Args:
            context: Project context
            stage: Current stage number
            base_prompt: Base prompt
            perspective: DraftPerspective to use
            existing_requirements: Existing requirements

        Returns:
            RequirementNode with generated requirement
        """
        # Build the perspective-enhanced prompt
        enhanced_prompt = self._build_perspective_prompt(
            base_prompt=base_prompt,
            perspective=perspective,
            context=context,
            existing_requirements=existing_requirements
        )

        # Create a new node
        node = RequirementNode(
            stage=stage,
            stage_name="draft",
            draft_perspective=perspective.name
        )

        # If we have a query function, use it
        if self.query_func:
            try:
                response = self._query_llm(enhanced_prompt)
                node = self._parse_response_to_node(response, node)
            except Exception as e:
                logger.error(f"LLM query failed: {e}")
                node.is_buggy = True
                node.quality_issues.append(f"LLM query failed: {e}")
        else:
            # Placeholder for testing without LLM
            node.title = f"Draft from {perspective.name} perspective"
            node.description = f"Generated with focus on: {', '.join(perspective.focus_areas)}"

        return node

    def _build_perspective_prompt(
        self,
        base_prompt: str,
        perspective: DraftPerspective,
        context: Dict[str, Any],
        existing_requirements: List[RequirementNode] = None
    ) -> str:
        """Build the full prompt with perspective modifier."""
        prompt_parts = [
            f"# Project Context",
            f"Project: {context.get('name', 'Unknown')}",
            f"Domain: {context.get('domain', 'Unknown')}",
            f"Description: {context.get('description', '')}",
            "",
            f"# Perspective: {perspective.name.upper()}",
            perspective.prompt_modifier,
            "",
            "# Task",
            base_prompt,
        ]

        if existing_requirements:
            prompt_parts.extend([
                "",
                "# Existing Requirements (for reference)",
                self._format_existing_requirements(existing_requirements)
            ])

        return "\n".join(prompt_parts)

    def _format_existing_requirements(self, requirements: List[RequirementNode]) -> str:
        """Format existing requirements for inclusion in prompt."""
        if not requirements:
            return "No existing requirements."

        lines = []
        for req in requirements[:10]:  # Limit to avoid token overflow
            lines.append(f"- {req.requirement_id}: {req.title} ({req.priority})")

        if len(requirements) > 10:
            lines.append(f"... and {len(requirements) - 10} more")

        return "\n".join(lines)

    def _query_llm(self, prompt: str) -> str:
        """Query the LLM with the given prompt."""
        if self.query_func is None:
            raise ValueError("No query function provided")

        # Get model settings from config - check core.draft_engine first, then agent.code
        core_config = self.config.get("core", {}).get("draft_engine", {})
        code_config = self.config.get("agent", {}).get("code", {})
        model = core_config.get("model") or code_config.get("model", "openai/gpt-4o-mini")
        temp = code_config.get("temp", 0.7)
        max_tokens = code_config.get("max_tokens", 8000)

        response, _, _, _, _ = self.query_func(
            system_message="You are a requirements engineering expert.",
            user_message=prompt,
            model=model,
            temperature=temp,
            max_tokens=max_tokens
        )

        return response

    def _parse_response_to_node(
        self,
        response: str,
        node: RequirementNode
    ) -> RequirementNode:
        """Parse LLM response into RequirementNode fields."""
        # Try to parse as JSON first
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
                data = json.loads(json_str)

                node.title = data.get("title", "")
                node.description = data.get("description", "")
                node.type = data.get("type", "functional")
                node.priority = data.get("priority", "should")
                node.rationale = data.get("rationale", "")
                node.acceptance_criteria = data.get("acceptance_criteria", [])

                return node
        except (json.JSONDecodeError, IndexError) as e:
            logger.debug(f"JSON parsing failed, falling back to text extraction: {e}")

        # Fallback: extract from text
        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("Title:"):
                node.title = line.replace("Title:", "").strip()
            elif line.startswith("Description:"):
                node.description = line.replace("Description:", "").strip()
            elif line.startswith("Priority:"):
                priority = line.replace("Priority:", "").strip().lower()
                if priority in ["must", "should", "could", "wont"]:
                    node.priority = priority

        return node

    def select_best_draft(
        self,
        drafts: List[DraftResult],
        criteria: Dict[str, float] = None
    ) -> Optional[RequirementNode]:
        """
        Select the best draft based on quality metrics.

        Args:
            drafts: List of DraftResult objects
            criteria: Optional weights for selection criteria

        Returns:
            Best RequirementNode or None if all failed
        """
        # Filter successful drafts
        successful = [d for d in drafts if d.success and d.node is not None]

        if not successful:
            logger.warning("No successful drafts to select from")
            return None

        # Check quality for each draft
        for draft in successful:
            draft.node.check_quality(self.thresholds)

        # Prefer non-buggy drafts
        non_buggy = [d for d in successful if not d.node.is_buggy]
        candidates = non_buggy if non_buggy else successful

        # Select best by aggregate score
        weights = criteria or self.metric_weights
        best = max(candidates, key=lambda d: d.node.aggregate_score(weights))

        logger.info(f"Selected draft from {best.perspective} perspective "
                   f"(score: {best.node.aggregate_score(weights):.2f})")

        return best.node

    def _get_eval_cache_key(self, node: RequirementNode) -> str:
        """Generate cache key from node content for evaluation caching."""
        content = f"{node.title}|{node.description}|{node.type}|{str(node.acceptance_criteria)}"
        return hashlib.md5(content.encode()).hexdigest()

    def evaluate_draft(
        self,
        node: RequirementNode,
        evaluation_prompt: str = None
    ) -> RequirementNode:
        """
        Evaluate a draft node and populate quality metrics.

        PERFORMANCE: Uses hash-based caching to avoid redundant LLM calls.
        Same content = same scores, ~50-80% LLM call reduction.

        Args:
            node: RequirementNode to evaluate
            evaluation_prompt: Optional custom evaluation prompt

        Returns:
            Node with updated quality metrics
        """
        # PERFORMANCE: Check cache first
        cache_key = self._get_eval_cache_key(node)
        if cache_key in self._eval_cache:
            cached_scores = self._eval_cache[cache_key]
            node.completeness_score = cached_scores.get("completeness", 0.0)
            node.consistency_score = cached_scores.get("consistency", 0.0)
            node.testability_score = cached_scores.get("testability", 0.0)
            node.clarity_score = cached_scores.get("clarity", 0.0)
            node.feasibility_score = cached_scores.get("feasibility", 0.0)
            node.traceability_score = cached_scores.get("traceability", 0.0)
            logger.debug(f"Cache hit for evaluation: {cache_key[:8]}...")
            node.check_quality(self.thresholds)
            return node

        if self.query_func is None:
            # Placeholder scores for testing
            scores = {
                "completeness": 0.7,
                "consistency": 0.8,
                "testability": 0.6,
                "clarity": 0.75,
                "feasibility": 0.7,
                "traceability": 0.5
            }
        else:
            # Use LLM to evaluate
            try:
                scores = self._evaluate_with_llm(node)
            except Exception as e:
                logger.error(f"Evaluation failed: {e}")
                scores = {}

        # Apply scores to node
        node.completeness_score = scores.get("completeness", 0.0)
        node.consistency_score = scores.get("consistency", 0.0)
        node.testability_score = scores.get("testability", 0.0)
        node.clarity_score = scores.get("clarity", 0.0)
        node.feasibility_score = scores.get("feasibility", 0.0)
        node.traceability_score = scores.get("traceability", 0.0)

        # PERFORMANCE: Cache the result
        self._eval_cache[cache_key] = scores
        logger.debug(f"Cached evaluation: {cache_key[:8]}...")

        # Check quality thresholds
        node.check_quality(self.thresholds)

        return node

    def _evaluate_with_llm(self, node: RequirementNode) -> Dict[str, float]:
        """Use LLM to evaluate requirement quality."""
        eval_prompt = f"""Evaluate this requirement on a scale of 0.0 to 1.0:

Title: {node.title}
Description: {node.description}
Type: {node.type}
Priority: {node.priority}
Acceptance Criteria: {node.acceptance_criteria}

Return a JSON object with these scores:
- completeness: Are all necessary details included?
- consistency: Is it free of contradictions?
- testability: Can it be verified/tested?
- clarity: Is the language clear and unambiguous?
- feasibility: Is it technically achievable?
- traceability: Can it be linked to business goals?

```json
{{"completeness": 0.0, "consistency": 0.0, "testability": 0.0, "clarity": 0.0, "feasibility": 0.0, "traceability": 0.0}}
```"""

        # Get model from config - check core.draft_engine first, then agent.feedback
        core_config = self.config.get("core", {}).get("draft_engine", {})
        feedback_config = self.config.get("agent", {}).get("feedback", {})
        model = core_config.get("model") or feedback_config.get("model", "openai/gpt-4o-mini")

        response, _, _, _, _ = self.query_func(
            system_message="You are a requirements quality evaluator.",
            user_message=eval_prompt,
            model=model,
            temperature=0.3,
            max_tokens=500
        )

        # Parse JSON from response
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            else:
                json_str = response
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse evaluation response: {response}")
            return {}
