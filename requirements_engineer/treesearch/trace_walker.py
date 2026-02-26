"""
Trace Walker - Depth-first iterative refinement of epic trace trees.

The main orchestrator that applies the AI-Scientist's BFTS approach to
requirements engineering. For each epic, walks the trace tree
(Epic → Requirement → UserStory → TestCase) depth-first, evaluating
and refining each node relative to its parent.

Algorithm:
1. Build trace tree from existing artifacts
2. DFS walk: for each node:
   a. Evaluate quality (parent-relative)
   b. Refine until threshold met or max iterations reached
   c. Generate children if missing
   d. Recursively walk children
   e. Re-evaluate in light of children
3. Produce audit trail and statistics
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .trace_node import TraceNode, TraceWalkResult
from .trace_evaluator import TraceEvaluator
from .trace_expander import TraceExpander

log = logging.getLogger(__name__)


class TraceWalker:
    """Depth-first iterative refinement of epic trace trees.

    Mirrors the AI-Scientist's approach:
    - Each node is evaluated relative to its parent
    - Low-quality nodes are refined (improve/debug) until threshold
    - Children are generated if missing, then recursively walked
    - Parent is re-evaluated after children are processed
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_call=None):
        """Initialize the trace walker.

        Args:
            config: Configuration dict with thresholds, weights, etc.
            llm_call: Async callable(prompt: str) -> str for LLM operations.
        """
        cfg = config or {}

        # Thresholds
        self.quality_threshold = cfg.get("quality_threshold", 0.80)
        self.debug_threshold = cfg.get("debug_threshold", 0.40)
        self.max_iterations_per_node = cfg.get("max_iterations_per_node", 3)
        self.max_total_llm_calls = cfg.get("max_total_llm_calls", 50)

        # Per-level overrides
        self._level_config = {}
        for level in ("requirement", "user_story", "test_case"):
            level_cfg = cfg.get(level, {})
            self._level_config[level] = {
                "quality_threshold": level_cfg.get("quality_threshold", self.quality_threshold),
                "max_iterations": level_cfg.get("max_iterations", self.max_iterations_per_node),
            }

        # Initialize evaluator and expander
        self.evaluator = TraceEvaluator(config=cfg, llm_call=llm_call)
        self.expander = TraceExpander(config=cfg, llm_call=llm_call)

        # Stats tracking
        self._total_llm_calls = 0
        self._nodes_visited = 0
        self._nodes_refined = 0

    @property
    def total_llm_calls(self) -> int:
        return self.evaluator.llm_calls_used + self.expander.llm_calls_used

    def _budget_remaining(self) -> bool:
        """Check if LLM call budget is not exhausted."""
        return self.total_llm_calls < self.max_total_llm_calls

    # ── Main Entry Point ─────────────────────────────────────

    async def walk_epic(self, epic: Any, artifacts: Dict[str, List]) -> TraceWalkResult:
        """Process one epic's full trace tree.

        Args:
            epic: An Epic dataclass instance.
            artifacts: Dict with keys "requirements", "user_stories", "test_cases"
                       containing lists of the respective dataclass instances.

        Returns:
            TraceWalkResult with statistics and per-node details.
        """
        start_time = time.time()

        # Reset stats
        self._nodes_visited = 0
        self._nodes_refined = 0

        # Build trace tree
        root = self._build_trace_tree(epic, artifacts)

        # Walk the tree (skip the root epic node itself — walk its children)
        for child in root.children_trace:
            await self._walk_node(child)

        # Collect results
        all_nodes = self._collect_all_nodes(root)
        # Exclude the epic root from stats
        artifact_nodes = [n for n in all_nodes if n.node_type != "epic"]

        scores = [n.quality_score for n in artifact_nodes] if artifact_nodes else [0.0]
        complete_count = sum(1 for n in artifact_nodes if n.is_complete)

        result = TraceWalkResult(
            epic_id=getattr(epic, "id", ""),
            epic_title=getattr(epic, "title", ""),
            nodes_total=len(artifact_nodes),
            nodes_refined=self._nodes_refined,
            nodes_complete=complete_count,
            avg_quality=sum(scores) / max(len(scores), 1),
            min_quality=min(scores) if scores else 0.0,
            max_quality=max(scores) if scores else 0.0,
            llm_calls_used=self.total_llm_calls,
            node_summaries=[n.to_summary() for n in artifact_nodes],
            duration_seconds=time.time() - start_time,
        )

        return result

    # ── Tree Building ────────────────────────────────────────

    def _build_trace_tree(self, epic: Any, artifacts: Dict[str, List]) -> TraceNode:
        """Build trace tree from epic and existing artifacts.

        Links:
        - Epic → Requirements via epic.parent_requirements
        - Requirement → Stories via story.parent_requirement_id
        - Story → Tests via tc.parent_user_story_id
        """
        requirements = artifacts.get("requirements", [])
        user_stories = artifacts.get("user_stories", [])
        test_cases = artifacts.get("test_cases", [])

        # Create epic root node
        epic_node = TraceNode(
            node_id=getattr(epic, "id", "EPIC-000"),
            node_type="epic",
            artifact=epic,
            is_complete=True,  # Epics are not refined, they're the root context
        )

        # Map requirement IDs to artifacts
        epic_req_ids = set(getattr(epic, "parent_requirements", []))
        req_map = {}
        for req in requirements:
            req_id = getattr(req, "requirement_id", None) or getattr(req, "id", "")
            if req_id and req_id in epic_req_ids:
                req_map[req_id] = req

        # Build requirement nodes
        for req_id, req in req_map.items():
            req_node = TraceNode(
                node_id=req_id,
                node_type="requirement",
                artifact=req,
                parent_trace=epic_node,
                max_iterations=self._level_config.get("requirement", {}).get("max_iterations", 3),
            )
            epic_node.children_trace.append(req_node)

            # Find stories linked to this requirement
            linked_stories = [
                s for s in user_stories
                if getattr(s, "parent_requirement_id", "") == req_id
            ]
            for story in linked_stories:
                story_id = getattr(story, "id", "")
                story_node = TraceNode(
                    node_id=story_id,
                    node_type="user_story",
                    artifact=story,
                    parent_trace=req_node,
                    max_iterations=self._level_config.get("user_story", {}).get("max_iterations", 3),
                )
                req_node.children_trace.append(story_node)

                # Find test cases linked to this story
                linked_tcs = [
                    tc for tc in test_cases
                    if getattr(tc, "parent_user_story_id", "") == story_id
                ]
                for tc in linked_tcs:
                    tc_id = getattr(tc, "id", "")
                    tc_node = TraceNode(
                        node_id=tc_id,
                        node_type="test_case",
                        artifact=tc,
                        parent_trace=story_node,
                        max_iterations=self._level_config.get("test_case", {}).get("max_iterations", 2),
                    )
                    story_node.children_trace.append(tc_node)

        return epic_node

    # ── DFS Walk ─────────────────────────────────────────────

    async def _walk_node(self, node: TraceNode):
        """Recursive DFS: evaluate → refine → generate children → walk children → re-evaluate."""
        self._nodes_visited += 1
        level_cfg = self._level_config.get(node.node_type, {})
        threshold = level_cfg.get("quality_threshold", self.quality_threshold)
        max_iter = level_cfg.get("max_iterations", self.max_iterations_per_node)
        node.max_iterations = max_iter

        # Step A: Evaluate this node against its parent
        scores = await self.evaluator.evaluate(node)
        node.quality_score = self.evaluator.aggregate_score(scores, node.node_type)

        if node.quality_score >= threshold:
            node.is_complete = True

        # Step B: Refine until quality threshold met (inner loop)
        while not node.is_complete and node.iteration_count < max_iter and self._budget_remaining():
            score_before = node.quality_score

            if node.quality_score < self.debug_threshold:
                improved = await self.expander.debug(node, node.quality_issues)
                stage = "debug"
            else:
                improved = await self.expander.improve(node, node.quality_issues)
                stage = "improve"

            # Record the refinement
            node.record_refinement(improved, stage, score_before, 0.0)
            self._nodes_refined += 1

            # Re-evaluate
            scores = await self.evaluator.evaluate(node)
            score_after = self.evaluator.aggregate_score(scores, node.node_type)
            node.quality_score = score_after

            # Update the refinement log with actual score
            if node.refinement_log:
                node.refinement_log[-1] = (
                    f"v{node.current_version} ({stage}): {score_before:.2f} → {score_after:.2f}"
                )

            if score_after >= threshold:
                node.is_complete = True

            # Stagnation check: if no improvement, stop
            if abs(score_after - score_before) < 0.01:
                log.debug(f"{node.node_id}: Stagnation detected, stopping refinement")
                break

        # Step C: Generate children if missing
        if not node.children_trace and node.node_type != "test_case":
            children_artifacts = await self.expander.draft(node)
            for child_art in children_artifacts:
                child_id = (
                    getattr(child_art, "id", "") or
                    getattr(child_art, "requirement_id", "") or
                    f"child-{len(node.children_trace)}"
                )
                child_type = self._infer_child_type(node.node_type)
                child_node = TraceNode(
                    node_id=child_id,
                    node_type=child_type,
                    artifact=child_art,
                    parent_trace=node,
                    max_iterations=self._level_config.get(child_type, {}).get("max_iterations", 3),
                )
                node.children_trace.append(child_node)

        # Step D: Recursively walk children
        for child in node.children_trace:
            if self._budget_remaining():
                await self._walk_node(child)

        # Step E: Re-evaluate parent in light of children (bottom-up feedback)
        if node.children_trace and self._budget_remaining():
            post_scores = await self.evaluator.evaluate_with_children(node)
            post_overall = post_scores.get("overall", node.quality_score)

            # If children revealed parent needs improvement, refine once more
            if post_overall < node.quality_score - 0.05 and node.iteration_count < max_iter:
                score_before = node.quality_score
                improved = await self.expander.improve(node, [
                    f"Children coverage gap: {post_scores.get('children_coverage', 0):.0%} children complete"
                ])
                node.record_refinement(improved, "improve", score_before, 0.0)
                self._nodes_refined += 1

                scores = await self.evaluator.evaluate(node)
                score_after = self.evaluator.aggregate_score(scores, node.node_type)
                node.quality_score = score_after
                if node.refinement_log:
                    node.refinement_log[-1] = (
                        f"v{node.current_version} (improve/post-children): "
                        f"{score_before:.2f} → {score_after:.2f}"
                    )

    # ── Helpers ───────────────────────────────────────────────

    def _infer_child_type(self, parent_type: str) -> str:
        """Infer child node type from parent type."""
        mapping = {
            "epic": "requirement",
            "requirement": "user_story",
            "user_story": "test_case",
        }
        return mapping.get(parent_type, "test_case")

    def _collect_all_nodes(self, root: TraceNode) -> List[TraceNode]:
        """Collect all nodes in the trace tree (BFS)."""
        result = [root]
        queue = [root]
        while queue:
            node = queue.pop(0)
            for child in node.children_trace:
                result.append(child)
                queue.append(child)
        return result


def write_trace_refinement_report(results: List[TraceWalkResult], output_dir: str):
    """Write markdown report of trace refinement results.

    Args:
        results: List of TraceWalkResult from walking each epic.
        output_dir: Directory to write the report to.
    """
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    md = "# Trace Refinement Report\n\n"

    # Summary
    total_nodes = sum(r.nodes_total for r in results)
    total_refined = sum(r.nodes_refined for r in results)
    total_complete = sum(r.nodes_complete for r in results)
    total_llm = sum(r.llm_calls_used for r in results)
    total_duration = sum(r.duration_seconds for r in results)

    md += f"**Epics processed:** {len(results)}\n"
    md += f"**Total nodes:** {total_nodes}\n"
    md += f"**Refined:** {total_refined}\n"
    md += f"**Complete:** {total_complete}/{total_nodes}\n"
    md += f"**LLM calls:** {total_llm}\n"
    md += f"**Duration:** {total_duration:.1f}s\n\n"
    md += "---\n\n"

    # Per-epic details
    for result in results:
        md += result.to_markdown()
        md += "---\n\n"

    report_path = output_path / "trace_refinement_report.md"
    report_path.write_text(md, encoding="utf-8")
    log.info(f"Trace refinement report written to {report_path}")
