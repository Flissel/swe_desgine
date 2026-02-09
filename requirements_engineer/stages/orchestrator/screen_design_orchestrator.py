"""
Screen Design Orchestrator for Multi-Agent Screen Generation.

Implements the Magentic-One Two-Loop Pattern for screen design:
- Outer Loop: Task Ledger with wireframe strategy, replanning on stagnation
- Inner Loop: Agent execution (Generate -> Review -> Improve)

Reuses PresentationLedgerManager from the existing presentation pipeline.
"""

import logging
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .presentation_ledger import (
    PresentationLedgerManager,
    ActionType,
)
from ..agents.base_presentation_agent import (
    BasePresentationAgent,
    PresentationContext,
    AgentResult,
)
from ..agents.screen_generator_agent import ScreenGeneratorAgent
from ..agents.screen_reviewer_agent import ScreenReviewerAgent
from ..agents.screen_improver_agent import ScreenImproverAgent

log = logging.getLogger(__name__)


class ScreenDesignOrchestrator:
    """
    Two-Loop orchestrator for screen design generation.

    Outer Loop (Task Ledger):
    - Tracks wireframe strategy (detailed_wireframe, simplified_wireframe, text_only)
    - Records facts from component library and user stories
    - On stagnation: switches wireframe strategy

    Inner Loop (Progress Ledger):
    - Iteration 0: ScreenGenerator -> ScreenReviewer -> ScreenImprover -> ScreenReviewer
    - Iteration 1+: ScreenReviewer -> ScreenImprover -> ScreenReviewer (until quality target)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        orchestrator_cfg = cfg.get("orchestrator", {})

        self.max_iterations = orchestrator_cfg.get("max_iterations", 3)
        self.stagnation_threshold = orchestrator_cfg.get("stagnation_threshold", 2)
        self.max_replans = orchestrator_cfg.get("max_replans", 2)
        self.target_quality = orchestrator_cfg.get("target_quality", 0.80)

        # Initialize ledger
        self.ledger = PresentationLedgerManager()

        # Initialize agents
        agent_configs = cfg.get("agents", {})
        quality_targets = cfg.get("quality_targets", {})

        gen_cfg = {**agent_configs.get("screen_generator", {})}
        gen_cfg["max_screens"] = cfg.get("max_screens", 8)

        reviewer_cfg = {**agent_configs.get("screen_reviewer", {})}
        reviewer_cfg["quality_targets"] = quality_targets

        improver_cfg = {**agent_configs.get("screen_improver", {})}

        self.agents: Dict[str, BasePresentationAgent] = {
            "screen_generator": ScreenGeneratorAgent(config=gen_cfg),
            "screen_reviewer": ScreenReviewerAgent(config=reviewer_cfg),
            "screen_improver": ScreenImproverAgent(config=improver_cfg),
        }

        log.info(
            f"ScreenDesignOrchestrator initialized: max_iter={self.max_iterations}, "
            f"target={self.target_quality}, agents={list(self.agents.keys())}"
        )

    async def run(
        self,
        project_id: str,
        project_name: str,
        output_dir: str,
        artifact_stats: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Run the screen design process with Two-Loop pattern.

        Args:
            project_id: Unique project identifier
            project_name: Human-readable project name
            output_dir: Directory containing UI artifacts
            artifact_stats: Statistics about available artifacts

        Returns:
            Dictionary with generation results
        """
        start_time = datetime.now()
        log.info(f"Starting screen design for: {project_name}")

        # Initialize ledgers
        self.ledger.initialize_from_project(
            project_id=project_id,
            project_name=project_name,
            artifact_stats=artifact_stats,
            config={
                "max_iterations": self.max_iterations,
                "stagnation_threshold": self.stagnation_threshold,
                "max_replans": self.max_replans,
                "target_quality": self.target_quality,
            },
        )

        self.ledger.task_ledger.add_fact(
            f"Screen design for {project_name} with {sum(artifact_stats.values())} artifacts"
        )
        self.ledger.task_ledger.add_design_decision(
            "Initial strategy: detailed_wireframe with coordinate grid"
        )

        # Build context
        context = PresentationContext(
            project_id=project_id,
            output_dir=output_dir,
            artifact_stats=artifact_stats,
            quality_threshold=self.target_quality,
        )

        iteration_results = []

        try:
            # ==============================
            # OUTER LOOP: Task Ledger
            # ==============================
            while self.ledger.should_continue():
                iteration = self.ledger.progress_ledger.current_iteration

                # Update context with ledger info
                context.task_ledger_summary = self.ledger.task_ledger.get_context_summary()
                context.progress_ledger_summary = self.ledger.progress_ledger.get_progress_summary()

                # ==============================
                # INNER LOOP: Agent Execution
                # ==============================
                iter_result = await self._execute_iteration(context, iteration)
                iteration_results.append(iter_result)

                # Record iteration completion
                self.ledger.record_iteration_complete({
                    "overall": iter_result["quality_score"],
                    "iteration": iteration,
                })

                log.info(
                    f"Screen design iteration {iteration}: "
                    f"quality={iter_result['quality_score']:.1%}, "
                    f"actions={iter_result['actions']}"
                )

                # Check stagnation -> replan
                if self.ledger.should_trigger_replan():
                    self._replan(context)

                # Advance
                if not self.ledger.progress_ledger.advance_iteration():
                    break

            # Save ledger state
            ui_design_dir = Path(output_dir) / "ui_design"
            ledger_path = ui_design_dir / "screen_design_ledger.json"
            if ui_design_dir.exists():
                self.ledger.save_to_file(str(ledger_path))

            total_duration = (datetime.now() - start_time).total_seconds()
            final_quality = self.ledger.progress_ledger.best_quality_score

            return {
                "success": True,
                "project_id": project_id,
                "final_quality_score": final_quality,
                "target_quality": self.target_quality,
                "quality_achieved": final_quality >= self.target_quality,
                "iterations_completed": len(iteration_results),
                "total_duration_seconds": total_duration,
                "replans": self.ledger.progress_ledger.replan_count,
                "ledger_file": str(ledger_path) if ui_design_dir.exists() else None,
            }

        except Exception as e:
            log.error(f"Screen design orchestrator failed: {e}")
            return {
                "success": False,
                "project_id": project_id,
                "error": str(e),
                "iterations_completed": len(iteration_results),
            }

    async def _execute_iteration(
        self, context: PresentationContext, iteration: int
    ) -> Dict[str, Any]:
        """Execute a single iteration of the inner loop."""
        actions = []
        quality_score = 0.0

        # Iteration 0: Generate screens
        if iteration == 0:
            gen_result = await self._run_agent("screen_generator", context)
            self._record_action("screen_generator", ActionType.GENERATE_SCREEN, gen_result)
            actions.append("generate_screens")

            if not gen_result.success:
                return {
                    "iteration": iteration,
                    "quality_score": 0.0,
                    "actions": actions,
                    "success": False,
                }

        # Review
        review_result = await self._run_agent("screen_reviewer", context)
        self._record_action("screen_reviewer", ActionType.REVIEW_SCREEN, review_result)
        actions.append("review_screens")

        quality_score = review_result.quality_score
        context.current_quality_score = quality_score
        context.quality_issues = review_result.quality_issues

        # Improve if needed
        if review_result.needs_improvement and quality_score < self.target_quality:
            improve_result = await self._run_agent("screen_improver", context)
            self._record_action(
                "screen_improver", ActionType.IMPROVE_SCREEN, improve_result,
                quality_before=quality_score,
            )
            actions.append("improve_screens")

            # Re-review after improvements
            if improve_result.success and improve_result.improvements_applied:
                re_review = await self._run_agent("screen_reviewer", context)
                quality_score = re_review.quality_score
                context.current_quality_score = quality_score
                actions.append("re_review")

        return {
            "iteration": iteration,
            "quality_score": quality_score,
            "actions": actions,
            "success": True,
        }

    async def _run_agent(self, agent_name: str, context: PresentationContext) -> AgentResult:
        """Run a specific agent."""
        agent = self.agents.get(agent_name)
        if not agent:
            log.error(f"Agent not found: {agent_name}")
            return AgentResult(success=False, error_message=f"Agent not found: {agent_name}")

        log.info(f"Running screen agent: {agent_name}")
        try:
            return await agent.execute(context)
        except Exception as e:
            log.error(f"Screen agent {agent_name} failed: {e}")
            return AgentResult(success=False, error_message=str(e))

    def _record_action(
        self,
        agent_name: str,
        action_type: ActionType,
        result: AgentResult,
        quality_before: Optional[float] = None,
    ) -> None:
        """Record an agent action in the ledger."""
        self.ledger.record_agent_action(
            agent_name=agent_name,
            action_type=action_type,
            success=result.success,
            description=result.notes,
            quality_before=quality_before,
            quality_after=result.quality_score if result.quality_score > 0 else None,
            duration=result.duration_seconds,
            error_message=result.error_message if not result.success else None,
        )

    def _replan(self, context: PresentationContext) -> None:
        """Trigger replanning when stagnation detected."""
        log.info("Screen design stagnation detected - replanning")
        self.ledger.progress_ledger.mark_replan()

        current_decisions = self.ledger.task_ledger.design_decisions

        # Switch wireframe strategy
        strategies = ["detailed_wireframe", "simplified_wireframe", "text_only"]
        for s in strategies:
            if not any(s in d for d in current_decisions):
                self.ledger.task_ledger.add_design_decision(
                    f"Replan: switching wireframe strategy to {s}"
                )
                self.ledger.task_ledger.mark_approach_failed(
                    "Previous wireframe strategy did not reach quality target"
                )
                break
