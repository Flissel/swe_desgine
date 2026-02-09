"""
Magentic Orchestrator for AI-Scientist.

This module implements the central orchestrator following the Magentic-One
pattern from Microsoft AutoGen. It coordinates specialized agents through
a two-loop architecture:

- Outer Loop: Task Ledger updates with plan revision
- Inner Loop: Progress Ledger updates after each agent action

The orchestrator manages:
- Agent selection and dispatch
- Dynamic replanning on stagnation
- Knowledge accumulation in ledgers
- Stage progression decisions
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, TYPE_CHECKING

from dataclasses_json import DataClassJsonMixin

from .ledger import LedgerManager, TaskLedger, ProgressLedger, ActionRecord
from .journal import Journal, Node
from .agents import (
    BaseResearchAgent,
    AgentContext,
    AgentResult,
    CoderAgent,
    DebuggerAgent,
    AnalystAgent,
    TunerAgent,
    AblationAgent,
    ReviewerAgent,
    TaskType,
)
from .backend import query, FunctionSpec

if TYPE_CHECKING:
    from omegaconf import DictConfig

logger = logging.getLogger(__name__)


@dataclass
class PlannedAction(DataClassJsonMixin):
    """A single planned action in the research plan."""
    agent_name: str
    task_type: str
    description: str
    priority: int = 0
    completed: bool = False
    result: Optional[Dict[str, Any]] = None


@dataclass
class ResearchPlan(DataClassJsonMixin):
    """
    Structured research plan created by the orchestrator.

    Contains the sequence of planned actions and tracks execution progress.
    """
    name: str = ""
    description: str = ""
    actions: List[PlannedAction] = field(default_factory=list)
    current_action_idx: int = 0
    total_iterations: int = 0
    flexibility: float = 0.5  # 0-1, how flexible the plan is to changes

    # Stage information
    stage_number: int = 1
    stage_goals: str = ""

    # Completion tracking
    is_complete: bool = False
    completion_reason: str = ""

    def get_current_action(self) -> Optional[PlannedAction]:
        """Get the current action to execute."""
        if self.current_action_idx < len(self.actions):
            return self.actions[self.current_action_idx]
        return None

    def advance(self) -> bool:
        """Advance to the next action. Returns False if plan is complete."""
        self.current_action_idx += 1
        if self.current_action_idx >= len(self.actions):
            self.is_complete = True
            return False
        return True

    def get_progress(self) -> float:
        """Get completion progress as a ratio."""
        if not self.actions:
            return 0.0
        return self.current_action_idx / len(self.actions)


# FunctionSpec for LLM-based replanning
replan_spec = FunctionSpec(
    name="generate_research_plan",
    description="Generate a revised research plan based on current progress",
    json_schema={
        "type": "object",
        "properties": {
            "plan_name": {
                "type": "string",
                "description": "Name for the revised plan",
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation for why the plan was revised",
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": ["coder", "debugger", "analyst", "tuner", "ablation", "reviewer"]},
                        "task": {"type": "string"},
                        "priority": {"type": "integer"},
                    },
                    "required": ["agent", "task"],
                },
                "description": "List of planned actions",
            },
        },
        "required": ["plan_name", "reasoning", "actions"],
    },
)


class MagenticOrchestrator:
    """
    Magentic-One inspired orchestrator for AI-Scientist.

    This orchestrator implements the two-loop architecture:
    - Outer loop: Plan revision based on Task Ledger
    - Inner loop: Action execution with Progress Ledger updates

    It coordinates specialized agents (Coder, Debugger, Analyst, Tuner,
    Ablation, Reviewer) to conduct research experiments adaptively.
    """

    def __init__(
        self,
        task_desc: Dict[str, Any],
        cfg: "DictConfig",
        workspace_dir: Path,
        journal: Optional[Journal] = None,
    ):
        self.task_desc = task_desc
        self.cfg = cfg
        self.workspace_dir = workspace_dir
        self.journal = journal or Journal()

        # Initialize Ledger System
        self.ledger_manager = LedgerManager()
        self.ledger_manager.initialize_from_task(task_desc)

        # Initialize specialized agents
        self.agents: Dict[str, BaseResearchAgent] = {}
        self._register_agents()

        # Current research plan
        self.current_plan: Optional[ResearchPlan] = None

        # Orchestration state
        self._is_running = False
        self._current_stage = 1
        self._step_count = 0

        logger.info(f"MagenticOrchestrator initialized with {len(self.agents)} agents")

    def _register_agents(self) -> None:
        """Register all specialized agents."""
        agent_config = self.cfg.get("agent", {})

        self.agents = {
            "coder": CoderAgent(config=agent_config),
            "debugger": DebuggerAgent(config=agent_config),
            "analyst": AnalystAgent(config=agent_config),
            "tuner": TunerAgent(config=agent_config),
            "ablation": AblationAgent(config=agent_config),
            "reviewer": ReviewerAgent(config=agent_config),
        }

        logger.info(f"Registered agents: {list(self.agents.keys())}")

    def run(
        self,
        exec_callback: Callable[[str, bool], Any],
        step_callback: Optional[Callable] = None,
        max_iterations: int = 100,
    ) -> Journal:
        """
        Run the research experiment with Magentic-One orchestration.

        This implements the two-loop architecture:
        1. Create initial plan
        2. Execute actions (inner loop)
        3. Update ledgers and check for stagnation
        4. Replan if needed (outer loop)
        5. Repeat until completion or max iterations

        Args:
            exec_callback: Callback for code execution
            step_callback: Optional callback after each step
            max_iterations: Maximum iterations before stopping

        Returns:
            Journal containing all experiment nodes
        """
        self._is_running = True
        logger.info("MagenticOrchestrator starting run")

        try:
            # Phase 1: Initialize
            self._initialize_task_ledger()
            self._create_initial_plan()

            # Main execution loop
            while self._is_running and self._step_count < max_iterations:
                # Inner loop: Execute current action
                action = self.current_plan.get_current_action()
                if action is None:
                    logger.info("Plan completed")
                    break

                # Execute the action
                result = self._execute_action(action, exec_callback)

                # Update Progress Ledger
                self._update_progress_ledger(result)

                # Callback for UI updates
                if step_callback:
                    step_callback(self._current_stage, self.journal)

                # Advance plan
                if not self.current_plan.advance():
                    # Plan complete - check if stage is complete
                    review_result = self._review_stage()
                    if review_result.stage_complete:
                        self._advance_stage()
                    else:
                        # Create new plan for current stage
                        self._create_stage_plan()

                # Outer loop: Check for stagnation and replan
                if self.ledger_manager.should_trigger_replan():
                    logger.info("Stagnation detected - triggering replan")
                    self._revise_plan()

                self._step_count += 1

            # Final review
            final_result = self._review_stage()
            logger.info(f"Orchestration complete after {self._step_count} steps")

            return self.journal

        finally:
            self._is_running = False

    def _initialize_task_ledger(self) -> None:
        """Initialize the Task Ledger with research context."""
        task_ledger = self.ledger_manager.task_ledger

        # Set research goal
        task_ledger.research_goal = self.task_desc.get("Title", "Research Experiment")

        # Add initial hypotheses
        if "Short Hypothesis" in self.task_desc:
            task_ledger.add_hypothesis(self.task_desc["Short Hypothesis"])

        # Add constraints from risk factors
        if "Risk Factors and Limitations" in self.task_desc:
            risks = self.task_desc["Risk Factors and Limitations"]
            if isinstance(risks, list):
                for risk in risks:
                    task_ledger.add_constraint(str(risk))
            else:
                task_ledger.add_constraint(str(risks))

        # Add open questions
        task_ledger.add_question("What is the best model architecture?")
        task_ledger.add_question("Which hyperparameters are most important?")

        logger.info(f"Task Ledger initialized: {task_ledger}")

    def _create_initial_plan(self) -> None:
        """Create the initial research plan for Stage 1."""
        self.current_plan = ResearchPlan(
            name="initial_implementation",
            description="Create and validate initial implementation",
            stage_number=1,
            stage_goals="Get a working baseline implementation",
            actions=[
                PlannedAction(
                    agent_name="coder",
                    task_type="draft",
                    description="Create initial implementation",
                    priority=1
                ),
                PlannedAction(
                    agent_name="analyst",
                    task_type="analyze",
                    description="Analyze initial results",
                    priority=2
                ),
                PlannedAction(
                    agent_name="reviewer",
                    task_type="review",
                    description="Review stage completion",
                    priority=3
                ),
            ],
            flexibility=0.7
        )

        self.ledger_manager.task_ledger.add_fact(
            f"Initial plan created: {self.current_plan.name}"
        )

        logger.info(f"Created initial plan with {len(self.current_plan.actions)} actions")

    def _create_stage_plan(self) -> None:
        """Create a plan for the current stage."""
        stage = self._current_stage
        stage_plans = {
            1: self._create_stage1_plan,
            2: self._create_stage2_plan,
            3: self._create_stage3_plan,
            4: self._create_stage4_plan,
        }

        creator = stage_plans.get(stage, self._create_stage1_plan)
        creator()

    def _create_stage1_plan(self) -> None:
        """Create plan for Stage 1: Initial Implementation."""
        self.current_plan = ResearchPlan(
            name="initial_implementation",
            description="Get working baseline",
            stage_number=1,
            stage_goals="Implement and validate baseline",
            actions=[
                PlannedAction("coder", "draft", "Create baseline", 1),
                PlannedAction("analyst", "analyze", "Analyze results", 2),
                PlannedAction("reviewer", "review", "Check completion", 3),
            ]
        )

    def _create_stage2_plan(self) -> None:
        """Create plan for Stage 2: Baseline Tuning."""
        self.current_plan = ResearchPlan(
            name="baseline_tuning",
            description="Optimize hyperparameters",
            stage_number=2,
            stage_goals="Tune hyperparameters and test on multiple datasets",
            actions=[
                PlannedAction("tuner", "tune", "Tune learning rate", 1),
                PlannedAction("analyst", "analyze", "Analyze tuning results", 2),
                PlannedAction("tuner", "tune", "Tune other parameters", 3),
                PlannedAction("analyst", "analyze", "Analyze final tuning", 4),
                PlannedAction("reviewer", "review", "Check completion", 5),
            ]
        )

    def _create_stage3_plan(self) -> None:
        """Create plan for Stage 3: Creative Research."""
        self.current_plan = ResearchPlan(
            name="creative_research",
            description="Explore novel improvements",
            stage_number=3,
            stage_goals="Discover and implement novel improvements",
            actions=[
                PlannedAction("coder", "improve", "Implement improvement 1", 1),
                PlannedAction("analyst", "analyze", "Analyze improvement", 2),
                PlannedAction("coder", "improve", "Implement improvement 2", 3),
                PlannedAction("analyst", "analyze", "Compare improvements", 4),
                PlannedAction("reviewer", "review", "Check completion", 5),
            ]
        )

    def _create_stage4_plan(self) -> None:
        """Create plan for Stage 4: Ablation Studies."""
        self.current_plan = ResearchPlan(
            name="ablation_studies",
            description="Analyze component contributions",
            stage_number=4,
            stage_goals="Conduct systematic ablation studies",
            actions=[
                PlannedAction("ablation", "ablate", "Ablate component 1", 1),
                PlannedAction("analyst", "analyze", "Analyze ablation 1", 2),
                PlannedAction("ablation", "ablate", "Ablate component 2", 3),
                PlannedAction("analyst", "analyze", "Analyze ablation 2", 4),
                PlannedAction("reviewer", "review", "Check completion", 5),
            ]
        )

    def _execute_action(
        self,
        action: PlannedAction,
        exec_callback: Callable,
    ) -> AgentResult:
        """
        Execute a planned action using the appropriate agent.
        """
        agent = self.agents.get(action.agent_name)
        if not agent:
            logger.error(f"Unknown agent: {action.agent_name}")
            return AgentResult(success=False, error_message=f"Unknown agent: {action.agent_name}")

        # Build context for agent
        context = self._build_agent_context(action)

        # Execute agent
        logger.info(f"Executing {action.agent_name}.{action.task_type}: {action.description}")
        start_time = time.time()

        try:
            result = agent.execute(context)

            # If code was generated, execute it
            if result.code and action.task_type in ["draft", "debug", "improve", "tune", "ablate"]:
                node = Node(
                    plan=result.plan or "",
                    code=result.code,
                    ledger_context=self.ledger_manager.get_combined_context(3)
                )

                # Execute the code
                exec_result = exec_callback(result.code, False)
                node.absorb_exec_result(exec_result)

                # Add to journal
                self.journal.append(node)

                # Update result with execution info
                result.node_id = node.id
                if node.exc_type:
                    result.needs_debugging = True

            action.completed = True
            action.result = result.to_dict() if hasattr(result, 'to_dict') else {"success": result.success}

            return result

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type=action.task_type,
                duration_seconds=time.time() - start_time
            )

    def _build_agent_context(self, action: PlannedAction) -> AgentContext:
        """Build context for agent execution."""
        # Get latest node if available
        current_node = None
        parent_node = None
        if self.journal.nodes:
            current_node = self.journal.nodes[-1].to_dict()
            if self.journal.nodes[-1].parent:
                parent_node = self.journal.nodes[-1].parent.to_dict()

        return AgentContext(
            task_ledger_summary=self.ledger_manager.task_ledger.get_context_summary(5),
            progress_ledger_summary=self.ledger_manager.progress_ledger.get_progress_summary(),
            current_node=current_node,
            parent_node=parent_node,
            journal_summary=self.journal.get_progress_summary() if self.journal.nodes else "",
            stage_name=self.current_plan.name if self.current_plan else "",
            stage_goals=self.current_plan.stage_goals if self.current_plan else "",
            stage_number=self._current_stage,
            task_description=str(self.task_desc),
            config=dict(self.cfg) if hasattr(self.cfg, '__iter__') else {},
            best_node_id=self.ledger_manager.progress_ledger.current_best_node_id,
            best_metric=self.ledger_manager.progress_ledger.current_best_metric,
        )

    def _update_progress_ledger(self, result: AgentResult) -> None:
        """Update the Progress Ledger with action result."""
        self.ledger_manager.record_experiment_result(
            agent_name=result.suggested_next_agent or "unknown",
            action_type=result.action_type,
            node_id=result.node_id or "",
            success=result.success,
            notes=result.notes,
            duration=result.duration_seconds,
            error_info={
                "type": "ExecutionError",
                "message": result.error_message
            } if result.error_message else None
        )

    def _review_stage(self) -> AgentResult:
        """Review current stage for completion."""
        reviewer = self.agents["reviewer"]
        context = self._build_agent_context(PlannedAction("reviewer", "review", "Review stage"))
        return reviewer.execute(context)

    def _advance_stage(self) -> None:
        """Advance to the next stage."""
        if self._current_stage < 4:
            self._current_stage += 1
            self.ledger_manager.task_ledger.add_fact(
                f"Advanced to Stage {self._current_stage}"
            )
            self._create_stage_plan()
            logger.info(f"Advanced to Stage {self._current_stage}")
        else:
            self._is_running = False
            logger.info("All stages complete")

    def _revise_plan(self) -> None:
        """
        Revise the current plan using LLM-based replanning.

        This is triggered when stagnation is detected in the Progress Ledger.
        """
        logger.info("Revising research plan due to stagnation")

        # Build context for replanning
        replan_context = {
            "Current Stage": self._current_stage,
            "Task Ledger": self.ledger_manager.task_ledger.get_context_summary(10),
            "Progress Ledger": self.ledger_manager.progress_ledger.get_progress_summary(),
            "Current Plan": self.current_plan.name if self.current_plan else "None",
            "Completed Actions": [
                a.description for a in (self.current_plan.actions if self.current_plan else [])
                if a.completed
            ],
            "Failed Approaches": self.ledger_manager.task_ledger.failed_approaches[-5:],
        }

        try:
            # Use LLM to generate new plan
            new_plan_data = query(
                system_message="You are a research planning AI. Generate a revised research plan.",
                user_message=f"Current context:\n{replan_context}\n\nGenerate a new plan to make progress.",
                func_spec=replan_spec,
                model=self.cfg.get("agent", {}).get("code", {}).get("model", "gpt-4o"),
                temperature=0.7
            )

            # Create new plan from LLM output
            new_actions = [
                PlannedAction(
                    agent_name=a["agent"],
                    task_type=a.get("task", "draft"),
                    description=a.get("task", "Execute task"),
                    priority=a.get("priority", 0)
                )
                for a in new_plan_data.get("actions", [])
            ]

            self.current_plan = ResearchPlan(
                name=new_plan_data.get("plan_name", "revised_plan"),
                description=new_plan_data.get("reasoning", ""),
                stage_number=self._current_stage,
                stage_goals=self.current_plan.stage_goals if self.current_plan else "",
                actions=new_actions,
                flexibility=0.8  # Higher flexibility after replan
            )

            # Mark replan in Progress Ledger
            self.ledger_manager.progress_ledger.mark_replan()

            # Record in Task Ledger
            self.ledger_manager.task_ledger.add_fact(
                f"Plan revised: {new_plan_data.get('reasoning', 'stagnation recovery')}"
            )

            logger.info(f"Plan revised: {self.current_plan.name} with {len(new_actions)} actions")

        except Exception as e:
            logger.error(f"Replanning failed: {e}")
            # Fallback: create default plan for current stage
            self._create_stage_plan()

    def stop(self) -> None:
        """Stop the orchestration."""
        self._is_running = False
        logger.info("Orchestration stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestration status."""
        return {
            "is_running": self._is_running,
            "current_stage": self._current_stage,
            "step_count": self._step_count,
            "current_plan": self.current_plan.name if self.current_plan else None,
            "plan_progress": self.current_plan.get_progress() if self.current_plan else 0,
            "task_ledger": str(self.ledger_manager.task_ledger),
            "progress_ledger": str(self.ledger_manager.progress_ledger),
            "journal_size": len(self.journal.nodes),
        }
