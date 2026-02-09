"""
Agent Dispatcher for Magentic-One inspired AI-Scientist architecture.

This module provides coordination and dispatch capabilities for the
specialized research agents. It handles:

- Sequential and parallel agent execution
- Resource management (GPU allocation)
- Error handling and retry logic
- Progress monitoring across agents
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable, TYPE_CHECKING

from .agents import (
    BaseResearchAgent,
    AgentContext,
    AgentResult,
    ProgressUpdate,
)

if TYPE_CHECKING:
    from .ledger import LedgerManager

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result from dispatching an agent or batch of agents."""
    success: bool
    results: List[AgentResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    total_duration: float = 0.0


class AgentDispatcher:
    """
    Coordinates agent execution with monitoring and error handling.

    The dispatcher provides a unified interface for executing agents
    either sequentially or in parallel, with built-in retry logic
    and progress tracking.
    """

    def __init__(
        self,
        agents: Dict[str, BaseResearchAgent],
        ledger_manager: Optional["LedgerManager"] = None,
        max_workers: int = 4,
        max_retries: int = 2,
    ):
        """
        Initialize the agent dispatcher.

        Args:
            agents: Dictionary of registered agents by name
            ledger_manager: Optional ledger manager for recording results
            max_workers: Maximum parallel workers for concurrent execution
            max_retries: Maximum retry attempts for failed agents
        """
        self.agents = agents
        self.ledger_manager = ledger_manager
        self.max_workers = max_workers
        self.max_retries = max_retries

        # Execution tracking
        self._running_agents: Dict[str, Future] = {}
        self._completed_results: List[AgentResult] = []

        logger.info(f"AgentDispatcher initialized with {len(agents)} agents, {max_workers} workers")

    def dispatch(
        self,
        agent_name: str,
        context: AgentContext,
        retry_on_failure: bool = True,
    ) -> AgentResult:
        """
        Dispatch a single agent for execution.

        Args:
            agent_name: Name of the agent to dispatch
            context: Context for the agent
            retry_on_failure: Whether to retry on failure

        Returns:
            AgentResult from the agent execution
        """
        agent = self.agents.get(agent_name)
        if not agent:
            logger.error(f"Unknown agent: {agent_name}")
            return AgentResult(
                success=False,
                error_message=f"Unknown agent: {agent_name}"
            )

        start_time = time.time()
        last_error = None
        attempts = 0

        while attempts <= (self.max_retries if retry_on_failure else 0):
            try:
                logger.info(f"Dispatching {agent_name} (attempt {attempts + 1})")

                result = agent.execute(context)

                # Record in ledger if available
                if self.ledger_manager and result.node_id:
                    self.ledger_manager.record_experiment_result(
                        agent_name=agent_name,
                        action_type=result.action_type,
                        node_id=result.node_id,
                        success=result.success,
                        notes=result.notes,
                        duration=time.time() - start_time,
                    )

                if result.success:
                    logger.info(f"Agent {agent_name} completed successfully")
                    return result

                last_error = result.error_message
                logger.warning(f"Agent {agent_name} failed: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"Agent {agent_name} raised exception: {e}")

            attempts += 1

        # All retries exhausted
        return AgentResult(
            success=False,
            error_message=f"Agent {agent_name} failed after {attempts} attempts: {last_error}",
            duration_seconds=time.time() - start_time
        )

    def dispatch_parallel(
        self,
        agent_contexts: List[tuple[str, AgentContext]],
        timeout: Optional[float] = None,
    ) -> DispatchResult:
        """
        Dispatch multiple agents in parallel.

        Args:
            agent_contexts: List of (agent_name, context) tuples
            timeout: Optional timeout in seconds for all agents

        Returns:
            DispatchResult with all agent results
        """
        start_time = time.time()
        results: List[AgentResult] = []
        errors: List[str] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all agents
            futures: Dict[Future, str] = {}
            for agent_name, context in agent_contexts:
                future = executor.submit(self.dispatch, agent_name, context, retry_on_failure=True)
                futures[future] = agent_name

            # Collect results
            for future in as_completed(futures, timeout=timeout):
                agent_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if not result.success:
                        errors.append(f"{agent_name}: {result.error_message}")
                except Exception as e:
                    error_msg = f"{agent_name}: {str(e)}"
                    errors.append(error_msg)
                    results.append(AgentResult(
                        success=False,
                        error_message=error_msg
                    ))

        return DispatchResult(
            success=len(errors) == 0,
            results=results,
            errors=errors,
            total_duration=time.time() - start_time
        )

    def dispatch_sequence(
        self,
        agent_sequence: List[tuple[str, AgentContext]],
        stop_on_failure: bool = True,
    ) -> DispatchResult:
        """
        Dispatch agents in sequence, optionally stopping on failure.

        Args:
            agent_sequence: List of (agent_name, context) tuples in order
            stop_on_failure: Whether to stop on first failure

        Returns:
            DispatchResult with all agent results
        """
        start_time = time.time()
        results: List[AgentResult] = []
        errors: List[str] = []

        for agent_name, context in agent_sequence:
            result = self.dispatch(agent_name, context)
            results.append(result)

            if not result.success:
                errors.append(f"{agent_name}: {result.error_message}")
                if stop_on_failure:
                    logger.warning(f"Stopping sequence due to failure in {agent_name}")
                    break

            # Update context for next agent if needed
            if result.recommendations:
                context.previous_agent_feedback.extend(result.recommendations)

        return DispatchResult(
            success=len(errors) == 0,
            results=results,
            errors=errors,
            total_duration=time.time() - start_time
        )

    def dispatch_conditional(
        self,
        agent_name: str,
        context: AgentContext,
        condition: Callable[[AgentResult], bool],
        fallback_agent: Optional[str] = None,
    ) -> AgentResult:
        """
        Dispatch an agent with conditional fallback.

        If the condition is not met after execution, dispatch the fallback agent.

        Args:
            agent_name: Primary agent to dispatch
            context: Context for agents
            condition: Function that takes AgentResult and returns True if satisfied
            fallback_agent: Agent to dispatch if condition not met

        Returns:
            AgentResult from primary or fallback agent
        """
        result = self.dispatch(agent_name, context)

        if condition(result):
            return result

        if fallback_agent:
            logger.info(f"Condition not met, dispatching fallback: {fallback_agent}")
            # Update context with primary agent's feedback
            context.previous_agent_feedback.append(
                f"Previous agent ({agent_name}) result: {result.notes}"
            )
            return self.dispatch(fallback_agent, context)

        return result

    def get_agent_status(self, agent_name: str) -> Optional[ProgressUpdate]:
        """
        Get the current status of an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            ProgressUpdate if agent exists and is running, None otherwise
        """
        agent = self.agents.get(agent_name)
        if agent and agent.is_running:
            return agent.report_progress()
        return None

    def get_all_status(self) -> Dict[str, ProgressUpdate]:
        """
        Get status of all agents.

        Returns:
            Dictionary mapping agent names to their status
        """
        status = {}
        for name, agent in self.agents.items():
            if agent.is_running:
                status[name] = agent.report_progress()
        return status

    def select_best_agent(
        self,
        task_type: str,
        context: AgentContext,
    ) -> Optional[str]:
        """
        Select the best agent for a given task type.

        Args:
            task_type: Type of task to perform
            context: Context that may influence selection

        Returns:
            Name of the best agent, or None if no suitable agent
        """
        from .agents import TaskType

        try:
            task = TaskType(task_type)
        except ValueError:
            logger.warning(f"Unknown task type: {task_type}")
            return None

        # Find agents that can handle this task
        candidates = [
            (name, agent) for name, agent in self.agents.items()
            if agent.can_handle(task)
        ]

        if not candidates:
            return None

        # For now, return the first capable agent
        # Future: Could use context to make smarter selection
        return candidates[0][0]

    def create_pipeline(
        self,
        stages: List[Dict[str, Any]],
    ) -> Callable[[AgentContext], DispatchResult]:
        """
        Create a reusable pipeline of agent executions.

        Args:
            stages: List of stage definitions with 'agent', 'parallel' keys

        Returns:
            Callable that executes the pipeline given a context
        """
        def run_pipeline(context: AgentContext) -> DispatchResult:
            all_results = []
            all_errors = []
            start_time = time.time()

            for stage in stages:
                if stage.get("parallel", False):
                    # Execute agents in parallel
                    agent_contexts = [
                        (name, context) for name in stage.get("agents", [])
                    ]
                    result = self.dispatch_parallel(agent_contexts)
                else:
                    # Execute single agent
                    agent_name = stage.get("agent")
                    if agent_name:
                        result = DispatchResult(
                            success=True,
                            results=[self.dispatch(agent_name, context)]
                        )
                    else:
                        continue

                all_results.extend(result.results)
                all_errors.extend(result.errors)

                # Update context for next stage
                for r in result.results:
                    if r.recommendations:
                        context.previous_agent_feedback.extend(r.recommendations)

                # Stop if stage failed and stop_on_failure is set
                if stage.get("stop_on_failure", True) and not result.success:
                    break

            return DispatchResult(
                success=len(all_errors) == 0,
                results=all_results,
                errors=all_errors,
                total_duration=time.time() - start_time
            )

        return run_pipeline
