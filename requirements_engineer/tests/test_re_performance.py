"""
Unit tests for Requirements Engineer performance optimizations.
Tests: Parallel drafting, evaluation caching, token management.
"""

import sys
import time
sys.path.insert(0, ".")

from requirements_engineer.core.re_journal import RequirementNode, RequirementJournal
from requirements_engineer.core.re_draft_engine import RequirementDraftEngine, DraftPerspective, DEFAULT_PERSPECTIVES
from requirements_engineer.core.re_improver import IterativeImprover, DiagnosisResult
from requirements_engineer.core.token_manager import TokenBudget, TokenEstimator, RequirementChunker
from requirements_engineer.validators.diagram_validator import DiagramValidator, validate_mermaid


def test_node_tree_structure():
    """Test RequirementNode tree-search fields."""
    print("Test 1: Node Tree Structure...")

    node = RequirementNode(
        requirement_id="REQ-001",
        title="Test Requirement",
        description="A test requirement for validation",
        stage=1,
        stage_name="draft",
        draft_perspective="technical"
    )

    assert node.stage_name == "draft", "stage_name should be 'draft'"
    assert node.draft_perspective == "technical", "draft_perspective should be 'technical'"
    assert node.is_buggy == False, "is_buggy should be False initially"
    assert node.quality_issues == [], "quality_issues should be empty"

    print("  [OK] Node tree fields initialized correctly")
    return True


def test_quality_check():
    """Test quality check with thresholds."""
    print("Test 2: Quality Check...")

    node = RequirementNode(
        requirement_id="REQ-002",
        title="Quality Test",
        description="Testing quality thresholds",
        completeness_score=0.5,  # Below threshold
        consistency_score=0.95,
        testability_score=0.8,
        clarity_score=0.85,
        feasibility_score=0.8,
        traceability_score=0.9
    )

    thresholds = {
        "min_completeness": 0.8,
        "min_consistency": 0.9,
        "min_testability": 0.75,
        "min_clarity": 0.8,
        "min_feasibility": 0.75,
        "min_traceability": 0.8
    }

    result = node.check_quality(thresholds)

    assert result == False, "Should fail quality check (completeness too low)"
    assert node.is_buggy == True, "Node should be marked as buggy"
    assert len(node.quality_issues) > 0, "Should have quality issues"
    assert "completeness" in node.quality_issues[0].lower(), "Issue should mention completeness"

    print(f"  [OK] Quality check detected {len(node.quality_issues)} issue(s)")
    return True


def test_draft_perspectives():
    """Test draft perspectives configuration."""
    print("Test 3: Draft Perspectives...")

    assert len(DEFAULT_PERSPECTIVES) == 3, "Should have 3 default perspectives"

    names = [p.name for p in DEFAULT_PERSPECTIVES]
    assert "technical" in names, "Should have technical perspective"
    assert "business" in names, "Should have business perspective"
    assert "user" in names, "Should have user perspective"

    for p in DEFAULT_PERSPECTIVES:
        assert len(p.focus_areas) > 0, f"{p.name} should have focus areas"
        assert len(p.prompt_modifier) > 0, f"{p.name} should have prompt modifier"

    print(f"  [OK] All 3 perspectives configured: {names}")
    return True


def test_evaluation_caching():
    """Test hash-based evaluation caching."""
    print("Test 4: Evaluation Caching...")

    journal = RequirementJournal()
    config = {
        "agent": {"search": {"num_drafts": 3, "max_debug_depth": 2}},
        "validation": {},
        "metric_weights": {}
    }

    engine = RequirementDraftEngine(config, journal, query_func=None)

    node1 = RequirementNode(
        requirement_id="REQ-003",
        title="Cache Test Node",
        description="Testing evaluation caching",
        acceptance_criteria=["AC-1", "AC-2"]
    )

    # Same content = same cache key
    node2 = RequirementNode(
        requirement_id="REQ-004",
        title="Cache Test Node",
        description="Testing evaluation caching",
        acceptance_criteria=["AC-1", "AC-2"]
    )

    key1 = engine._get_eval_cache_key(node1)
    key2 = engine._get_eval_cache_key(node2)

    assert key1 == key2, "Same content should produce same cache key"

    # Different content = different cache key
    node3 = RequirementNode(
        requirement_id="REQ-005",
        title="Different Node",
        description="Different content",
        acceptance_criteria=["AC-3"]
    )

    key3 = engine._get_eval_cache_key(node3)
    assert key1 != key3, "Different content should produce different cache key"

    print(f"  [OK] Cache key generation working (key sample: {key1[:8]}...)")
    return True


def test_token_budget():
    """Test token budget calculations."""
    print("Test 5: Token Budget...")

    budget = TokenBudget(max_context=100000, max_output=4000, system_prompt_reserve=2000)

    effective = budget.effective_input_budget
    expected = int((100000 - 4000 - 2000) * 0.85)  # 79900

    assert effective == expected, f"Effective budget should be {expected}, got {effective}"
    assert effective < 100000, "Effective budget should be less than max_context"

    print(f"  [OK] Token budget: {effective:,} effective input tokens (from 100k context)")
    return True


def test_token_estimation():
    """Test token count estimation."""
    print("Test 6: Token Estimation...")

    estimator = TokenEstimator()

    # Average ~3.5 chars per token
    text = "A" * 350  # Should be ~100 tokens
    estimated = estimator.estimate_tokens(text)

    assert 90 <= estimated <= 110, f"Should estimate ~100 tokens, got {estimated}"

    # Empty text
    assert estimator.estimate_tokens("") == 0, "Empty string should be 0 tokens"

    print(f"  [OK] Token estimation working (350 chars = {estimated} tokens)")
    return True


def test_requirement_chunking():
    """Test requirement chunking for large sets."""
    print("Test 7: Requirement Chunking...")

    budget = TokenBudget(max_context=10000)  # Smaller budget for testing
    chunker = RequirementChunker(budget)

    # Create requirements with known token sizes
    requirements = []
    for i in range(10):
        req = RequirementNode(
            requirement_id=f"REQ-{i:03d}",
            title=f"Requirement {i}",
            description="A" * 1000,  # ~286 tokens each
        )
        requirements.append(req)

    batches = list(chunker.chunk_requirements(requirements, prompt_template_tokens=500))

    assert len(batches) > 1, "Should split into multiple batches"

    total_reqs = sum(len(b) for b in batches)
    assert total_reqs == 10, "All requirements should be in batches"

    info = chunker.get_batch_info(requirements)
    print(f"  [OK] Chunking: {info['total_requirements']} reqs -> {info['num_batches']} batches")
    print(f"    Batch sizes: {info['batch_sizes']}")
    return True


def test_diagnosis():
    """Test iterative improver diagnosis."""
    print("Test 8: Diagnosis...")

    journal = RequirementJournal()
    config = {
        "agent": {"search": {"max_debug_depth": 2, "debug_prob": 0.5}},
        "validation": {
            "min_completeness": 0.8,
            "min_consistency": 0.9,
            "min_testability": 0.75,
            "min_clarity": 0.8,
            "min_feasibility": 0.75,
            "min_traceability": 0.8
        }
    }

    improver = IterativeImprover(config, journal, query_func=None)

    # Low quality node
    node = RequirementNode(
        requirement_id="REQ-DIAG",
        title="T",  # Too short
        description="D",  # Too short
        completeness_score=0.4,
        consistency_score=0.5,
    )

    diagnosis = improver.diagnose(node)

    assert diagnosis.is_buggy == True, "Should be buggy"
    assert len(diagnosis.quality_issues) > 0, "Should have issues"
    assert len(diagnosis.improvement_hints) > 0, "Should have hints"
    assert diagnosis.severity in ["low", "medium", "high", "critical"], "Should have valid severity"

    print(f"  [OK] Diagnosis: {len(diagnosis.quality_issues)} issues, severity={diagnosis.severity}")
    return True


def test_mermaid_validation():
    """Test Mermaid diagram validation."""
    print("Test 9: Mermaid Validation...")

    validator = DiagramValidator(method="pattern")

    # Valid flowchart
    valid_diagram = """flowchart TD
    A[Start] --> B[Process]
    B --> C[End]"""

    result = validator.validate(valid_diagram)
    assert result.valid == True, "Valid diagram should pass"
    assert result.diagram_type == "flowchart", "Should detect flowchart type"

    # Invalid diagram (no connections)
    invalid_diagram = """flowchart TD
    A[Orphan Node]"""

    result = validator.validate(invalid_diagram)
    assert result.valid == False, "Invalid diagram should fail"
    assert result.errors is not None, "Should have errors"

    print(f"  [OK] Mermaid validation working (pattern-based)")
    return True


def test_journal_tree_methods():
    """Test journal tree-search methods."""
    print("Test 10: Journal Tree Methods...")

    journal = RequirementJournal()

    # Add nodes with different stages
    for i in range(5):
        node = RequirementNode(
            requirement_id=f"REQ-{i:03d}",
            title=f"Req {i}",
            description=f"Description {i}",
            stage=1,
            stage_name="draft" if i < 3 else "debug",
            is_buggy=(i == 4)
        )
        journal.add_node(node)

    draft_nodes = journal.get_draft_nodes()
    assert len(draft_nodes) == 3, f"Should have 3 draft nodes, got {len(draft_nodes)}"

    buggy_nodes = journal.get_buggy_nodes()
    assert len(buggy_nodes) == 1, f"Should have 1 buggy node, got {len(buggy_nodes)}"

    print(f"  [OK] Journal tree methods: {len(draft_nodes)} drafts, {len(buggy_nodes)} buggy")
    return True


def run_all_tests():
    """Run all unit tests."""
    print("\n" + "="*60)
    print("Requirements Engineer Performance Tests")
    print("="*60 + "\n")

    tests = [
        test_node_tree_structure,
        test_quality_check,
        test_draft_perspectives,
        test_evaluation_caching,
        test_token_budget,
        test_token_estimation,
        test_requirement_chunking,
        test_diagnosis,
        test_mermaid_validation,
        test_journal_tree_methods,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] FAILED: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"         {failed} test(s) FAILED")
    print("="*60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
