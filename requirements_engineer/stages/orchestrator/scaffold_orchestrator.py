"""
Scaffold Orchestrator for Project Structure Generation.

Implements the Magentic-One Two-Loop Pattern for scaffold generation:
- Outer Loop: Task Ledger with structural hypotheses, replanning on stagnation
- Inner Loop: Agent execution (Scaffold -> Review -> Improve)

Reuses PresentationLedgerManager from the existing presentation pipeline.
"""

import logging
import asyncio
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
from ..agents.project_scaffold_agent import ProjectScaffoldAgent
from ..agents.scaffold_reviewer_agent import ScaffoldReviewerAgent
from ..agents.scaffold_improver_agent import ScaffoldImproverAgent

log = logging.getLogger(__name__)


class ScaffoldOrchestrator:
    """
    Two-Loop orchestrator for project scaffold generation.

    Outer Loop (Task Ledger):
    - Tracks structural hypotheses (monorepo vs polyrepo, feature vs layer)
    - Records facts from tech stack and epic analysis
    - On stagnation: switches structure strategy

    Inner Loop (Progress Ledger):
    - Iteration 0: ContentAnalyzer (cached) -> ProjectScaffold -> Review -> Improve
    - Iteration 1+: Review -> Improve until quality target met
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        orchestrator_cfg = cfg.get("orchestrator", {})

        self.max_iterations = orchestrator_cfg.get("max_iterations", 4)
        self.stagnation_threshold = orchestrator_cfg.get("stagnation_threshold", 2)
        self.max_replans = orchestrator_cfg.get("max_replans", 2)
        self.target_quality = orchestrator_cfg.get("target_quality", 0.85)

        # Initialize ledger (reuse presentation ledger system)
        self.ledger = PresentationLedgerManager()

        # Initialize agents
        agent_configs = cfg.get("agents", {})
        quality_targets = cfg.get("quality_targets", {})

        scaffold_cfg = {**agent_configs.get("project_scaffold", {})}
        scaffold_cfg["scaffold"] = cfg  # Pass full scaffold config

        reviewer_cfg = {**agent_configs.get("scaffold_reviewer", {})}
        reviewer_cfg["quality_targets"] = quality_targets

        improver_cfg = {**agent_configs.get("scaffold_improver", {})}

        self.agents: Dict[str, BasePresentationAgent] = {
            "project_scaffold": ProjectScaffoldAgent(config=scaffold_cfg),
            "scaffold_reviewer": ScaffoldReviewerAgent(config=reviewer_cfg),
            "scaffold_improver": ScaffoldImproverAgent(config=improver_cfg),
        }

        log.info(
            f"ScaffoldOrchestrator initialized: max_iter={self.max_iterations}, "
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
        Run the scaffold generation process with Two-Loop pattern.

        Args:
            project_id: Unique project identifier
            project_name: Human-readable project name
            output_dir: Directory containing RE artifacts and for scaffold output
            artifact_stats: Statistics about available artifacts

        Returns:
            Dictionary with generation results
        """
        start_time = datetime.now()
        log.info(f"Starting scaffold generation for: {project_name}")

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

        # Add initial hypotheses
        self.ledger.task_ledger.add_fact(
            f"Scaffold generation for {project_name} with {sum(artifact_stats.values())} artifacts"
        )

        # Build context
        context = PresentationContext(
            project_id=project_id,
            output_dir=output_dir,
            artifact_stats=artifact_stats,
            quality_threshold=self.target_quality,
            config={"scaffold": self._get_scaffold_config()},
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
                    f"Scaffold iteration {iteration}: "
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
            scaffold_dir = Path(output_dir) / self._get_scaffold_config().get("output_dir", "project_scaffold")
            ledger_path = scaffold_dir / "scaffold_ledger.json"
            if scaffold_dir.exists():
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
                "scaffold_dir": str(scaffold_dir),
                "ledger_file": str(ledger_path) if scaffold_dir.exists() else None,
            }

        except Exception as e:
            log.error(f"Scaffold orchestrator failed: {e}")
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

        # Iteration 0: Generate scaffold
        if iteration == 0:
            scaffold_result = await self._run_agent("project_scaffold", context)
            self._record_action("project_scaffold", ActionType.GENERATE_SCAFFOLD, scaffold_result)
            actions.append("generate_scaffold")

            if not scaffold_result.success:
                return {
                    "iteration": iteration,
                    "quality_score": 0.0,
                    "actions": actions,
                    "success": False,
                }

        # Review
        review_result = await self._run_agent("scaffold_reviewer", context)
        self._record_action("scaffold_reviewer", ActionType.REVIEW_SCAFFOLD, review_result)
        actions.append("review_scaffold")

        quality_score = review_result.quality_score
        context.current_quality_score = quality_score
        context.quality_issues = review_result.quality_issues

        # Improve if needed
        if review_result.needs_improvement and quality_score < self.target_quality:
            improve_result = await self._run_agent("scaffold_improver", context)
            self._record_action(
                "scaffold_improver", ActionType.IMPROVE_SCAFFOLD, improve_result,
                quality_before=quality_score,
            )
            actions.append("improve_scaffold")

            # Re-review after improvements
            if improve_result.success and improve_result.improvements_applied:
                re_review = await self._run_agent("scaffold_reviewer", context)
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

        log.info(f"Running scaffold agent: {agent_name}")
        try:
            return await agent.execute(context)
        except Exception as e:
            log.error(f"Scaffold agent {agent_name} failed: {e}")
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
        log.info("Scaffold stagnation detected - replanning")
        self.ledger.progress_ledger.mark_replan()

        current_strategy = self.ledger.task_ledger.design_decisions[-1] if self.ledger.task_ledger.design_decisions else ""

        # Switch strategy
        strategies = ["feature_based", "service_based", "layer_based"]
        for s in strategies:
            if s not in current_strategy:
                self.ledger.task_ledger.add_design_decision(
                    f"Replan: switching scaffold strategy to {s}"
                )
                self.ledger.task_ledger.mark_approach_failed(
                    f"Previous strategy did not reach quality target"
                )
                break

    def _get_scaffold_config(self) -> Dict[str, Any]:
        """Get scaffold config for passing to agents."""
        # Reconstruct from what was passed to __init__
        return {
            "output_dir": "project_scaffold",
            "structure_strategy": "auto",
        }
