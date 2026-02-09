"""
Presentation Orchestrator for Multi-Agent HTML Generation.

Implements the Magentic-One Two-Loop Pattern:
- Outer Loop: Updates Task Ledger, decides on replanning
- Inner Loop: Executes agent actions, tracks progress

Coordinates all presentation agents to iteratively generate and improve
HTML documentation pages.
"""

import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from .presentation_ledger import (
    PresentationTaskLedger,
    PresentationProgressLedger,
    PresentationLedgerManager,
    PresentationActionRecord,
    ActionType,
)
from ..agents.base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    PresentationContext,
    AgentResult,
)
from ..agents.content_analyzer_agent import ContentAnalyzerAgent
from ..agents.html_generator_agent import HTMLGeneratorAgent
from ..agents.html_reviewer_agent import HTMLReviewerAgent
from ..agents.html_improver_agent import HTMLImproverAgent

log = logging.getLogger(__name__)


class OrchestratorState(Enum):
    """Orchestrator execution states."""
    IDLE = auto()
    ANALYZING = auto()
    GENERATING = auto()
    REVIEWING = auto()
    IMPROVING = auto()
    REPLANNING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    max_iterations: int = 5
    stagnation_threshold: int = 2
    max_replans: int = 3
    target_quality: float = 0.8
    min_quality_threshold: float = 0.6
    max_improvements_per_iteration: int = 5
    enable_kilo_integration: bool = True


@dataclass
class IterationResult:
    """Result of a single iteration."""
    iteration: int
    state: OrchestratorState
    quality_score: float
    actions_taken: List[str]
    improvements_applied: int
    duration_seconds: float
    success: bool


class PresentationOrchestrator:
    """
    Orchestrator for multi-agent HTML presentation generation.

    Implements the Two-Loop Pattern:
    - Outer Loop: Task management and replanning
    - Inner Loop: Agent execution and progress tracking
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the orchestrator.

        Args:
            config: Configuration dictionary
        """
        # Parse configuration
        cfg = config or {}
        self.config = OrchestratorConfig(
            max_iterations=cfg.get("max_iterations", 5),
            stagnation_threshold=cfg.get("stagnation_threshold", 2),
            max_replans=cfg.get("max_replans", 3),
            target_quality=cfg.get("target_quality", 0.8),
            min_quality_threshold=cfg.get("min_quality_threshold", 0.6),
            max_improvements_per_iteration=cfg.get("max_improvements_per_iteration", 5),
            enable_kilo_integration=cfg.get("enable_kilo_integration", True)
        )

        # Initialize ledger manager
        self.ledger = PresentationLedgerManager()

        # Store default LLM config for agents
        self.default_llm_config = cfg.get("llm", {})

        # Initialize agents
        self.agents: Dict[str, BasePresentationAgent] = {}
        self._init_agents(cfg.get("agents", {}))

        # State
        self.state = OrchestratorState.IDLE
        self.iteration_results: List[IterationResult] = []

        log.info(f"Initialized PresentationOrchestrator with config: {self.config}")

    def _init_agents(self, agent_configs: Dict[str, Dict[str, Any]]) -> None:
        """Initialize all presentation agents."""
        # Merge default LLM config with agent-specific config
        # Agent-specific values override defaults
        def merge_config(agent_name: str) -> Dict[str, Any]:
            agent_cfg = agent_configs.get(agent_name, {})
            # Start with default LLM config, then overlay agent-specific
            merged = {**self.default_llm_config}
            merged.update(agent_cfg)
            return merged

        self.agents = {
            "content_analyzer": ContentAnalyzerAgent(
                config=merge_config("content_analyzer")
            ),
            "html_generator": HTMLGeneratorAgent(
                config=merge_config("html_generator")
            ),
            "html_reviewer": HTMLReviewerAgent(
                config=merge_config("html_reviewer")
            ),
            "html_improver": HTMLImproverAgent(
                config=merge_config("html_improver")
            ),
        }

        log.info(f"Initialized {len(self.agents)} agents with LLM config from: {self.default_llm_config.get('model', 'default')}")

    async def run(
        self,
        project_id: str,
        project_name: str,
        output_dir: str,
        artifact_stats: Dict[str, int],
        artifact_paths: Optional[Dict[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Run the complete presentation generation process.

        This is the main entry point that implements the Two-Loop pattern.

        Args:
            project_id: Unique project identifier
            project_name: Human-readable project name
            output_dir: Directory for output files
            artifact_stats: Statistics of available artifacts
            artifact_paths: Paths to artifact files

        Returns:
            Dictionary with generation results and metrics
        """
        start_time = datetime.now()
        log.info(f"Starting presentation generation for project: {project_name}")

        # Initialize ledgers
        self.ledger.initialize_from_project(
            project_id=project_id,
            project_name=project_name,
            artifact_stats=artifact_stats,
            config={
                "max_iterations": self.config.max_iterations,
                "stagnation_threshold": self.config.stagnation_threshold,
                "max_replans": self.config.max_replans,
                "target_quality": self.config.target_quality
            }
        )

        # Build initial context
        context = PresentationContext(
            project_id=project_id,
            output_dir=output_dir,
            artifact_stats=artifact_stats,
            artifact_paths=artifact_paths or {},
            quality_threshold=self.config.target_quality,
            config={"max_improvements": self.config.max_improvements_per_iteration}
        )

        try:
            # ========================================
            # OUTER LOOP: Task Ledger Management
            # ========================================
            while self.ledger.should_continue():
                iteration_start = datetime.now()

                # Update task ledger context
                context.task_ledger_summary = self.ledger.task_ledger.get_context_summary()
                context.progress_ledger_summary = self.ledger.progress_ledger.get_progress_summary()

                # ========================================
                # INNER LOOP: Agent Execution
                # ========================================
                iteration_result = await self._execute_iteration(context)
                self.iteration_results.append(iteration_result)

                # Record iteration completion
                self.ledger.record_iteration_complete({
                    "overall": iteration_result.quality_score,
                    "iteration": iteration_result.iteration
                })

                # Check for stagnation and replan if needed
                if self.ledger.should_trigger_replan():
                    await self._replan(context)

                # Advance iteration counter
                if not self.ledger.progress_ledger.advance_iteration():
                    break

                log.info(
                    f"Iteration {iteration_result.iteration} complete: "
                    f"quality={iteration_result.quality_score:.1%}, "
                    f"duration={iteration_result.duration_seconds:.1f}s"
                )

            # Final state
            self.state = OrchestratorState.COMPLETED
            final_quality = self.ledger.progress_ledger.best_quality_score

            # Save ledger state
            ledger_path = Path(output_dir) / "presentation_ledger.json"
            self.ledger.save_to_file(str(ledger_path))

            end_time = datetime.now()
            total_duration = (end_time - start_time).total_seconds()

            return {
                "success": True,
                "project_id": project_id,
                "final_quality_score": final_quality,
                "target_quality": self.config.target_quality,
                "quality_achieved": final_quality >= self.config.target_quality,
                "iterations_completed": len(self.iteration_results),
                "total_duration_seconds": total_duration,
                "replans": self.ledger.progress_ledger.replan_count,
                "generated_files": self._collect_generated_files(output_dir),
                "ledger_file": str(ledger_path)
            }

        except Exception as e:
            log.error(f"Orchestrator failed: {e}")
            self.state = OrchestratorState.FAILED

            return {
                "success": False,
                "project_id": project_id,
                "error": str(e),
                "iterations_completed": len(self.iteration_results),
                "last_quality_score": self.ledger.progress_ledger.best_quality_score
            }

    async def _execute_iteration(self, context: PresentationContext) -> IterationResult:
        """
        Execute a single iteration of the inner loop.

        This runs through the agent pipeline:
        1. Analyze (first iteration only)
        2. Generate (first iteration only)
        3. Review
        4. Improve (if needed)
        """
        iteration = self.ledger.progress_ledger.current_iteration
        iteration_start = datetime.now()
        actions_taken = []
        quality_score = 0.0

        log.info(f"Starting iteration {iteration}")

        # First iteration: Analyze and Generate
        if iteration == 0:
            # Step 1: Content Analysis
            self.state = OrchestratorState.ANALYZING
            analyze_result = await self._run_agent("content_analyzer", context)
            actions_taken.append("content_analysis")

            self._record_agent_action("content_analyzer", ActionType.ANALYZE_CONTENT, analyze_result)

            if not analyze_result.success:
                return IterationResult(
                    iteration=iteration,
                    state=OrchestratorState.FAILED,
                    quality_score=0.0,
                    actions_taken=actions_taken,
                    improvements_applied=0,
                    duration_seconds=(datetime.now() - iteration_start).total_seconds(),
                    success=False
                )

            # Step 2: HTML Generation
            self.state = OrchestratorState.GENERATING
            generate_result = await self._run_agent("html_generator", context)
            actions_taken.append("html_generation")

            self._record_agent_action("html_generator", ActionType.GENERATE_HTML, generate_result)

            if not generate_result.success:
                return IterationResult(
                    iteration=iteration,
                    state=OrchestratorState.FAILED,
                    quality_score=0.0,
                    actions_taken=actions_taken,
                    improvements_applied=0,
                    duration_seconds=(datetime.now() - iteration_start).total_seconds(),
                    success=False
                )

        # Step 3: Review
        self.state = OrchestratorState.REVIEWING
        review_result = await self._run_agent("html_reviewer", context)
        actions_taken.append("html_review")

        self._record_agent_action("html_reviewer", ActionType.REVIEW_HTML, review_result)

        quality_score = review_result.quality_score
        context.current_quality_score = quality_score
        context.quality_issues = review_result.quality_issues

        # Step 4: Improve (if needed)
        improvements_applied = 0
        if review_result.needs_improvement and quality_score < self.config.target_quality:
            self.state = OrchestratorState.IMPROVING
            improve_result = await self._run_agent("html_improver", context)
            actions_taken.append("html_improvement")

            self._record_agent_action(
                "html_improver",
                ActionType.IMPROVE_HTML,
                improve_result,
                quality_before=quality_score
            )

            improvements_applied = len(improve_result.improvements_applied)

            # Re-review after improvements
            if improvements_applied > 0:
                re_review_result = await self._run_agent("html_reviewer", context)
                quality_score = re_review_result.quality_score
                context.current_quality_score = quality_score
                actions_taken.append("re_review")

        iteration_duration = (datetime.now() - iteration_start).total_seconds()

        return IterationResult(
            iteration=iteration,
            state=self.state,
            quality_score=quality_score,
            actions_taken=actions_taken,
            improvements_applied=improvements_applied,
            duration_seconds=iteration_duration,
            success=True
        )

    async def _run_agent(
        self,
        agent_name: str,
        context: PresentationContext
    ) -> AgentResult:
        """Run a specific agent."""
        agent = self.agents.get(agent_name)

        if not agent:
            log.error(f"Agent not found: {agent_name}")
            return AgentResult(
                success=False,
                error_message=f"Agent not found: {agent_name}"
            )

        log.info(f"Running agent: {agent_name}")

        try:
            result = await agent.execute(context)
            log.info(f"Agent {agent_name} completed: success={result.success}")
            return result

        except Exception as e:
            log.error(f"Agent {agent_name} failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e)
            )

    def _record_agent_action(
        self,
        agent_name: str,
        action_type: ActionType,
        result: AgentResult,
        quality_before: Optional[float] = None
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
            metadata={"recommendations": result.recommendations}
        )

    async def _replan(self, context: PresentationContext) -> None:
        """
        Trigger replanning when stagnation is detected.

        This is part of the Outer Loop - revising the approach when
        progress stalls.
        """
        self.state = OrchestratorState.REPLANNING
        log.info("Triggering replan due to stagnation")

        # Mark replan in ledger
        self.ledger.progress_ledger.mark_replan()

        # Update task ledger with new insights
        self.ledger.task_ledger.add_design_decision(
            f"Replan #{self.ledger.progress_ledger.replan_count}: "
            f"Adjusting approach after stagnation at {self.ledger.progress_ledger.best_quality_score:.1%} quality"
        )

        # Could add more sophisticated replanning logic here:
        # - Try different improvement strategies
        # - Adjust quality targets
        # - Enable additional agents (e.g., Kilo)

    def _collect_generated_files(self, output_dir: str) -> List[str]:
        """Collect list of generated files."""
        output_path = Path(output_dir)
        presentation_dir = output_path / "presentation"

        files = []

        if presentation_dir.exists():
            files.extend([str(f) for f in presentation_dir.glob("*.html")])

        # Add analysis and report files
        for pattern in ["content_analysis.json", "html_review_report.json", "presentation_ledger.json"]:
            for f in output_path.glob(pattern):
                files.append(str(f))

        return files

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "state": self.state.name,
            "current_iteration": self.ledger.progress_ledger.current_iteration,
            "max_iterations": self.config.max_iterations,
            "best_quality_score": self.ledger.progress_ledger.best_quality_score,
            "target_quality": self.config.target_quality,
            "stagnation_counter": self.ledger.progress_ledger.stagnation_counter,
            "replan_count": self.ledger.progress_ledger.replan_count,
            "agents_available": list(self.agents.keys())
        }


# Convenience function for running the orchestrator
async def run_presentation_orchestrator(
    project_id: str,
    project_name: str,
    output_dir: str,
    artifact_stats: Dict[str, int],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the presentation orchestrator.

    Args:
        project_id: Unique project identifier
        project_name: Human-readable project name
        output_dir: Directory for output files
        artifact_stats: Statistics of available artifacts
        config: Optional configuration

    Returns:
        Generation results
    """
    orchestrator = PresentationOrchestrator(config=config)
    return await orchestrator.run(
        project_id=project_id,
        project_name=project_name,
        output_dir=output_dir,
        artifact_stats=artifact_stats
    )
