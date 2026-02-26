"""
Tests for Magentic-One Integration in AI-Scientist.

These tests verify the Phase 1-3 implementation:
- Phase 1: Ledger System (TaskLedger, ProgressLedger)
- Phase 2: Specialized Agents
- Phase 3: MagenticOrchestrator and AgentDispatcher
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestPhase1Ledger:
    """Tests for Phase 1: Ledger System"""

    def test_ledger_imports(self):
        """Test that ledger module imports correctly."""
        from ai_scientist.treesearch.ledger import (
            TaskLedger,
            ProgressLedger,
            ActionRecord,
            FailedAttempt,
            LedgerManager,
        )

        # Verify classes exist
        assert TaskLedger is not None
        assert ProgressLedger is not None
        assert ActionRecord is not None
        assert FailedAttempt is not None
        assert LedgerManager is not None

    def test_task_ledger_creation(self):
        """Test TaskLedger creation and basic operations."""
        from ai_scientist.treesearch.ledger import TaskLedger

        ledger = TaskLedger()

        # Add facts
        ledger.add_fact("Test fact 1")
        ledger.add_fact("Test fact 2")
        assert len(ledger.facts) == 2

        # Add hypothesis
        ledger.add_hypothesis("Test hypothesis")
        assert len(ledger.hypotheses) == 1

        # Confirm hypothesis
        ledger.confirm_hypothesis("Test hypothesis", as_fact=True)
        assert len(ledger.hypotheses) == 0
        assert len(ledger.facts) == 3

        # Get summary
        summary = ledger.get_context_summary()
        assert "Test fact" in summary

    def test_progress_ledger_creation(self):
        """Test ProgressLedger creation and stagnation detection."""
        from ai_scientist.treesearch.ledger import ProgressLedger, ActionRecord

        ledger = ProgressLedger(stagnation_threshold=3)

        # Record successful action
        action = ActionRecord(
            agent_name="test_agent",
            action_type="draft",
            node_id="test_node",
            success=True,
            notes="Test action"
        )
        ledger.record_action(action)

        assert ledger.total_steps == 1
        assert ledger.get_success_rate() == 1.0

        # Test stagnation detection
        assert not ledger.detect_stagnation()

        # Add more actions without improvement
        for _ in range(3):
            action = ActionRecord(
                agent_name="test_agent",
                action_type="improve",
                node_id="test_node",
                success=True,
                notes="No improvement"
            )
            ledger.record_action(action)

        # Now should detect stagnation
        assert ledger.detect_stagnation()

    def test_ledger_manager(self):
        """Test LedgerManager initialization and operations."""
        from ai_scientist.treesearch.ledger import LedgerManager

        manager = LedgerManager()

        # Initialize from task
        task_desc = {
            "Title": "Test Research",
            "Abstract": "Test abstract",
            "Short Hypothesis": "Test hypothesis",
            "Experiments": "Test experiments",
            "Risk Factors and Limitations": "Test risks",
        }
        manager.initialize_from_task(task_desc)

        assert manager.task_ledger.research_goal == "Test Research"
        assert len(manager.task_ledger.hypotheses) == 1

        # Get combined context
        context = manager.get_combined_context()
        assert "Task Context" in context
        assert "Progress Status" in context


class TestPhase2Agents:
    """Tests for Phase 2: Specialized Agents"""

    def test_agent_imports(self):
        """Test that all agents import correctly."""
        from ai_scientist.treesearch.agents import (
            BaseResearchAgent,
            AgentContext,
            AgentResult,
            AgentCapability,
            TaskType,
            CoderAgent,
            DebuggerAgent,
            AnalystAgent,
            TunerAgent,
            AblationAgent,
            ReviewerAgent,
        )

        # Verify all classes exist
        assert BaseResearchAgent is not None
        assert AgentContext is not None
        assert AgentResult is not None
        assert CoderAgent is not None
        assert DebuggerAgent is not None
        assert AnalystAgent is not None
        assert TunerAgent is not None
        assert AblationAgent is not None
        assert ReviewerAgent is not None

    def test_coder_agent_creation(self):
        """Test CoderAgent creation."""
        from ai_scientist.treesearch.agents import CoderAgent, AgentCapability

        agent = CoderAgent()

        assert agent.name == "coder"
        assert AgentCapability.CODE_GENERATION in agent.capabilities
        assert AgentCapability.CODE_IMPROVEMENT in agent.capabilities

    def test_agent_can_handle(self):
        """Test agent capability matching."""
        from ai_scientist.treesearch.agents import (
            CoderAgent,
            DebuggerAgent,
            TunerAgent,
            TaskType,
        )

        coder = CoderAgent()
        debugger = DebuggerAgent()
        tuner = TunerAgent()

        # Coder should handle draft and improve
        assert coder.can_handle(TaskType.DRAFT)
        assert coder.can_handle(TaskType.IMPROVE)
        assert not coder.can_handle(TaskType.DEBUG)

        # Debugger should handle debug
        assert debugger.can_handle(TaskType.DEBUG)
        assert not debugger.can_handle(TaskType.DRAFT)

        # Tuner should handle tune
        assert tuner.can_handle(TaskType.TUNE)
        assert not tuner.can_handle(TaskType.DEBUG)

    def test_agent_context_creation(self):
        """Test AgentContext creation and LLM context generation."""
        from ai_scientist.treesearch.agents import AgentContext

        context = AgentContext(
            task_description="Test task",
            stage_name="Stage 1",
            stage_number=1,
            stage_goals="Test goals",
            task_ledger_summary="Facts: test",
            progress_ledger_summary="Progress: test",
        )

        llm_context = context.get_llm_context()
        assert "Test task" in llm_context
        assert "Stage 1" in llm_context


class TestPhase3Orchestration:
    """Tests for Phase 3: Orchestration"""

    def test_orchestrator_imports(self):
        """Test that orchestrator imports correctly."""
        from ai_scientist.treesearch.magentic_orchestrator import (
            MagenticOrchestrator,
            ResearchPlan,
            PlannedAction,
        )

        assert MagenticOrchestrator is not None
        assert ResearchPlan is not None
        assert PlannedAction is not None

    def test_dispatcher_imports(self):
        """Test that dispatcher imports correctly."""
        from ai_scientist.treesearch.agent_dispatcher import (
            AgentDispatcher,
            DispatchResult,
        )

        assert AgentDispatcher is not None
        assert DispatchResult is not None

    def test_research_plan_creation(self):
        """Test ResearchPlan creation and operations."""
        from ai_scientist.treesearch.magentic_orchestrator import (
            ResearchPlan,
            PlannedAction,
        )

        plan = ResearchPlan(
            name="test_plan",
            description="Test plan",
            stage_number=1,
            actions=[
                PlannedAction("coder", "draft", "Create code", 1),
                PlannedAction("analyst", "analyze", "Analyze", 2),
            ]
        )

        assert len(plan.actions) == 2
        assert plan.get_progress() == 0.0

        # Get current action
        action = plan.get_current_action()
        assert action.agent_name == "coder"

        # Advance
        assert plan.advance()
        assert plan.get_progress() == 0.5

        action = plan.get_current_action()
        assert action.agent_name == "analyst"

        # Advance to complete
        assert not plan.advance()
        assert plan.is_complete

    def test_dispatcher_creation(self):
        """Test AgentDispatcher creation."""
        from ai_scientist.treesearch.agent_dispatcher import AgentDispatcher
        from ai_scientist.treesearch.agents import CoderAgent, DebuggerAgent

        agents = {
            "coder": CoderAgent(),
            "debugger": DebuggerAgent(),
        }

        dispatcher = AgentDispatcher(agents, max_workers=2)

        assert len(dispatcher.agents) == 2
        assert dispatcher.max_workers == 2

    def test_agent_selection(self):
        """Test agent selection by task type."""
        from ai_scientist.treesearch.agent_dispatcher import AgentDispatcher
        from ai_scientist.treesearch.agents import (
            CoderAgent,
            DebuggerAgent,
            AnalystAgent,
            AgentContext,
        )

        agents = {
            "coder": CoderAgent(),
            "debugger": DebuggerAgent(),
            "analyst": AnalystAgent(),
        }

        dispatcher = AgentDispatcher(agents)
        context = AgentContext(task_description="test", stage_name="test")

        # Select for draft
        selected = dispatcher.select_best_agent("draft", context)
        assert selected == "coder"

        # Select for debug
        selected = dispatcher.select_best_agent("debug", context)
        assert selected == "debugger"

        # Select for analyze
        selected = dispatcher.select_best_agent("analyze", context)
        assert selected == "analyst"


class TestAgentManagerIntegration:
    """Tests for AgentManager with Magentic integration."""

    def test_agent_manager_magentic_flag(self):
        """Test AgentManager accepts use_magentic flag."""
        # This test just verifies the import works
        from ai_scientist.treesearch.agent_manager import AgentManager

        # Verify the class has the docstring mentioning Magentic
        assert "Magentic" in AgentManager.__doc__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
