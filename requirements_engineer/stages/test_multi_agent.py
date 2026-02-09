"""
Test script for Multi-Agent Presentation System.

This script tests the components of the multi-agent presentation system
without running the full RE pipeline.
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Add parent directories to path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all modules can be imported."""
    log.info("Testing imports...")

    try:
        from requirements_engineer.stages.agents import (
            BasePresentationAgent,
            AgentRole,
            AgentCapability,
            PresentationContext,
            AgentResult,
            ContentAnalyzerAgent,
            HTMLGeneratorAgent,
            HTMLReviewerAgent,
            HTMLImproverAgent,
            KiloIntegrationAgent,
        )
        log.info("  - Agents module: OK")

        from requirements_engineer.stages.orchestrator import (
            PresentationTaskLedger,
            PresentationProgressLedger,
            PresentationLedgerManager,
            PresentationOrchestrator,
            ImprovementType,
            ImprovementPlan,
        )
        log.info("  - Orchestrator module: OK")

        from requirements_engineer.stages.presentation_stage import (
            PresentationStage,
            run_presentation_stage,
        )
        log.info("  - Presentation stage module: OK")

        return True

    except ImportError as e:
        log.error(f"Import error: {e}")
        return False


def test_ledger_system():
    """Test the ledger system."""
    log.info("Testing ledger system...")

    from requirements_engineer.stages.orchestrator import (
        PresentationTaskLedger,
        PresentationProgressLedger,
        PresentationLedgerManager,
        ActionType,
    )

    # Create manager
    manager = PresentationLedgerManager()

    # Initialize
    manager.initialize_from_project(
        project_id="test_project",
        project_name="Test Project",
        artifact_stats={
            "requirements": 10,
            "user_stories": 25,
            "diagrams": 5
        },
        config={
            "max_iterations": 3,
            "target_quality": 0.8
        }
    )

    # Check task ledger
    assert manager.task_ledger.project_id == "test_project"
    assert len(manager.task_ledger.facts) > 0
    log.info(f"  - Task ledger facts: {len(manager.task_ledger.facts)}")

    # Record some actions
    action = manager.record_agent_action(
        agent_name="TestAgent",
        action_type=ActionType.GENERATE_HTML,
        success=True,
        description="Generated test page",
        quality_before=0.5,
        quality_after=0.7
    )

    assert action.success
    log.info(f"  - Recorded action: {action.action_type.name}")

    # Check progress tracking
    manager.record_iteration_complete({"overall": 0.7})
    assert manager.progress_ledger.best_quality_score == 0.7
    log.info(f"  - Best quality: {manager.progress_ledger.best_quality_score}")

    # Test context summary
    context = manager.get_combined_context()
    assert len(context) > 0
    log.info(f"  - Context summary length: {len(context)}")

    log.info("  - Ledger system: OK")
    return True


def test_agents():
    """Test individual agents."""
    log.info("Testing agents...")

    from requirements_engineer.stages.agents import (
        ContentAnalyzerAgent,
        HTMLGeneratorAgent,
        HTMLReviewerAgent,
        HTMLImproverAgent,
        KiloIntegrationAgent,
        AgentRole,
    )

    # Test ContentAnalyzerAgent
    analyzer = ContentAnalyzerAgent()
    assert analyzer.role == AgentRole.CONTENT_ANALYZER
    log.info(f"  - ContentAnalyzerAgent: {analyzer.name}")

    # Test HTMLGeneratorAgent
    generator = HTMLGeneratorAgent()
    assert generator.role == AgentRole.HTML_GENERATOR
    log.info(f"  - HTMLGeneratorAgent: {generator.name}")

    # Test HTMLReviewerAgent
    reviewer = HTMLReviewerAgent()
    assert reviewer.role == AgentRole.HTML_REVIEWER
    log.info(f"  - HTMLReviewerAgent: {reviewer.name}")

    # Test HTMLImproverAgent
    improver = HTMLImproverAgent()
    assert improver.role == AgentRole.HTML_IMPROVER
    log.info(f"  - HTMLImproverAgent: {improver.name}")

    # Test KiloIntegrationAgent
    kilo = KiloIntegrationAgent()
    assert kilo.role == AgentRole.KILO_INTEGRATION
    log.info(f"  - KiloIntegrationAgent: {kilo.name} (available: {kilo.is_available()})")

    log.info("  - All agents: OK")
    return True


def test_orchestrator():
    """Test the orchestrator initialization."""
    log.info("Testing orchestrator...")

    from requirements_engineer.stages.orchestrator import (
        PresentationOrchestrator,
        OrchestratorState,
    )

    config = {
        "max_iterations": 3,
        "stagnation_threshold": 2,
        "target_quality": 0.75
    }

    orchestrator = PresentationOrchestrator(config=config)

    assert orchestrator.state == OrchestratorState.IDLE
    assert len(orchestrator.agents) == 4  # 4 core agents
    log.info(f"  - Orchestrator agents: {list(orchestrator.agents.keys())}")

    status = orchestrator.get_status()
    assert status["state"] == "IDLE"
    log.info(f"  - Orchestrator status: {status['state']}")

    log.info("  - Orchestrator: OK")
    return True


def test_presentation_stage():
    """Test the presentation stage initialization."""
    log.info("Testing presentation stage...")

    from requirements_engineer.stages.presentation_stage import PresentationStage

    config = {
        "stages": {"stage5_max_iters": 3},
        "presentation": {
            "enabled": True,
            "max_pages": 10,
            "multi_agent": {
                "enabled": True,
                "orchestrator": {
                    "max_iterations": 3,
                    "target_quality": 0.75
                }
            }
        }
    }

    stage = PresentationStage(
        project_id="test_project",
        project_dir=Path("."),
        output_dir=Path("./test_output"),
        config=config
    )

    assert stage.project_id == "test_project"
    assert stage.use_multi_agent == True
    log.info(f"  - Multi-agent mode: {stage.use_multi_agent}")

    log.info("  - Presentation stage: OK")
    return True


async def test_full_pipeline_mock():
    """Test a mocked full pipeline run."""
    log.info("Testing mock pipeline...")

    from requirements_engineer.stages.agents import (
        PresentationContext,
        AgentResult,
    )
    from requirements_engineer.stages.orchestrator import (
        PresentationLedgerManager,
        ActionType,
    )

    # Create context
    context = PresentationContext(
        project_id="test_project",
        output_dir="./test_output",
        artifact_stats={
            "requirements": 5,
            "user_stories": 10
        },
        quality_threshold=0.75
    )

    # Create ledger
    ledger = PresentationLedgerManager()
    ledger.initialize_from_project(
        project_id="test_project",
        project_name="Test Project",
        artifact_stats=context.artifact_stats
    )

    # Simulate iterations
    for i in range(3):
        log.info(f"  - Mock iteration {i+1}")

        # Record mock actions
        ledger.record_agent_action(
            agent_name="MockAgent",
            action_type=ActionType.GENERATE_HTML,
            success=True,
            quality_before=0.5 + i * 0.1,
            quality_after=0.6 + i * 0.1
        )

        # Record iteration quality
        quality = 0.6 + i * 0.1
        ledger.record_iteration_complete({"overall": quality})

        # Advance iteration
        if not ledger.progress_ledger.advance_iteration():
            break

    final_quality = ledger.progress_ledger.best_quality_score
    log.info(f"  - Final quality: {final_quality:.1%}")

    assert final_quality >= 0.7
    log.info("  - Mock pipeline: OK")
    return True


def run_all_tests():
    """Run all tests."""
    log.info("=" * 60)
    log.info("Multi-Agent Presentation System Tests")
    log.info("=" * 60)

    results = {
        "imports": test_imports(),
        "ledger": test_ledger_system(),
        "agents": test_agents(),
        "orchestrator": test_orchestrator(),
        "stage": test_presentation_stage(),
    }

    # Run async test
    try:
        results["mock_pipeline"] = asyncio.run(test_full_pipeline_mock())
    except Exception as e:
        log.error(f"Mock pipeline test failed: {e}")
        results["mock_pipeline"] = False

    log.info("=" * 60)
    log.info("Test Results:")
    log.info("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        log.info(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    log.info("=" * 60)
    log.info(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    log.info("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
