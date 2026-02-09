"""
Tests for Quality Gate fixes.

Covers:
- compute_traceability() real metric calculation
- Count metrics display (absolute, not %)
- Ratio capping (coverage <= 100%)
- Integration: markdown output sanity
"""

import pytest
from dataclasses import dataclass
from typing import List

from requirements_engineer.gates.quality_gate import (
    QualityGate,
    GateResult,
    GateStatus,
    COUNT_METRICS,
)


# ================================================================
# Test data helpers
# ================================================================

@dataclass
class FakeReq:
    requirement_id: str = ""
    title: str = ""

@dataclass
class FakeStory:
    id: str = ""
    parent_requirement_id: str = ""

@dataclass
class FakeTC:
    id: str = ""
    parent_user_story_id: str = ""


# ================================================================
# compute_traceability (3 tests)
# ================================================================

class TestComputeTraceability:
    def test_all_linked(self):
        """All reqs → stories → tests gives 1.0."""
        reqs = [FakeReq(requirement_id="REQ-001"), FakeReq(requirement_id="REQ-002")]
        stories = [
            FakeStory(id="US-001", parent_requirement_id="REQ-001"),
            FakeStory(id="US-002", parent_requirement_id="REQ-002"),
        ]
        tcs = [
            FakeTC(id="TC-001", parent_user_story_id="US-001"),
            FakeTC(id="TC-002", parent_user_story_id="US-002"),
        ]
        result = QualityGate.compute_traceability(reqs, stories, tcs)
        assert abs(result["req_to_story"] - 1.0) < 0.001
        assert abs(result["story_to_test"] - 1.0) < 0.001
        assert abs(result["overall"] - 1.0) < 0.001

    def test_partial_coverage(self):
        """Half reqs linked, half stories tested → overall = 0.5."""
        reqs = [FakeReq(requirement_id="REQ-001"), FakeReq(requirement_id="REQ-002")]
        stories = [
            FakeStory(id="US-001", parent_requirement_id="REQ-001"),
            FakeStory(id="US-002", parent_requirement_id=""),  # Orphan
        ]
        tcs = [
            FakeTC(id="TC-001", parent_user_story_id="US-001"),
        ]
        result = QualityGate.compute_traceability(reqs, stories, tcs)
        assert abs(result["req_to_story"] - 0.5) < 0.001  # 1/2 reqs covered
        assert abs(result["story_to_test"] - 0.5) < 0.001  # 1/2 stories tested
        assert abs(result["overall"] - 0.5) < 0.001

    def test_empty_data(self):
        """Empty input gives 0.0 for all."""
        result = QualityGate.compute_traceability([], [], [])
        assert abs(result["req_to_story"] - 0.0) < 0.001
        assert abs(result["story_to_test"] - 0.0) < 0.001
        assert abs(result["overall"] - 0.0) < 0.001

    def test_more_stories_than_reqs(self):
        """Multiple stories per req still caps at 1.0."""
        reqs = [FakeReq(requirement_id="REQ-001")]
        stories = [
            FakeStory(id="US-001", parent_requirement_id="REQ-001"),
            FakeStory(id="US-002", parent_requirement_id="REQ-001"),
        ]
        tcs = [
            FakeTC(id="TC-001", parent_user_story_id="US-001"),
            FakeTC(id="TC-002", parent_user_story_id="US-002"),
        ]
        result = QualityGate.compute_traceability(reqs, stories, tcs)
        assert result["req_to_story"] <= 1.0
        assert result["story_to_test"] <= 1.0


# ================================================================
# Count Metrics Display (3 tests)
# ================================================================

class TestCountMetricsDisplay:
    def test_min_test_cases_not_percentage(self):
        """min_test_cases should display as absolute count, not %."""
        gate = QualityGate()
        result = gate.check_testing_gate(
            test_coverage=0.9,
            traceability=0.95,
            test_cases_count=1130
        )
        md = result.to_markdown()
        # Should show "1130" not "22600.00%"
        assert "1130" in md
        assert "22600" not in md

    def test_min_requirements_display(self):
        """min_requirements should display as absolute count."""
        gate = QualityGate()
        result = gate.check_discovery_gate(
            requirements_count=126,
            stakeholder_coverage=0.9,
            completeness=0.85
        )
        md = result.to_markdown()
        assert "126" in md
        assert "4200" not in md

    def test_count_metric_pass_fail(self):
        """1130 test cases >= 5 threshold → PASS."""
        gate = QualityGate()
        result = gate.check_testing_gate(
            test_coverage=0.9,
            traceability=0.95,
            test_cases_count=1130
        )
        assert result.metrics_met.get("min_test_cases") is True
        assert result.status == GateStatus.PASS

    def test_count_metric_fail_when_below(self):
        """2 test cases < 5 threshold → part of FAIL."""
        gate = QualityGate()
        result = gate.check_testing_gate(
            test_coverage=0.9,
            traceability=0.95,
            test_cases_count=2
        )
        assert result.metrics_met.get("min_test_cases") is False


# ================================================================
# Ratio Capping (3 tests)
# ================================================================

class TestRatioCapping:
    def test_coverage_capped_at_100(self):
        """test_coverage > 1.0 should be capped to 1.0."""
        gate = QualityGate()
        result = gate.check_testing_gate(
            test_coverage=4.48,  # Would be 448% uncapped
            traceability=0.95,
            test_cases_count=1130
        )
        # The metric stored should be capped
        assert result.metrics_evaluated["test_coverage"] <= 1.0
        md = result.to_markdown()
        assert "448" not in md

    def test_traceability_capped(self):
        """traceability > 1.0 should be capped to 1.0."""
        gate = QualityGate()
        result = gate.check_testing_gate(
            test_coverage=0.9,
            traceability=1.5,  # Should be capped
            test_cases_count=100
        )
        assert result.metrics_evaluated["traceability"] <= 1.0

    def test_overall_score_reasonable(self):
        """All percentage values should be between 0-100%."""
        gate = QualityGate()
        gate.check_discovery_gate(126, 0.9, 0.85)
        gate.check_analysis_gate(0.92, 126, 2)
        gate.check_testing_gate(4.48, 0.95, 1130)
        md = gate.get_gate_summary()
        # No value should exceed 100% (except count metrics which are ints)
        lines = md.split("\n")
        for line in lines:
            if "%" in line and "|" in line:
                # Extract percentage values
                parts = line.split("|")
                for part in parts:
                    part = part.strip()
                    if part.endswith("%"):
                        try:
                            val = float(part.rstrip("%"))
                            assert val <= 100.01, f"Percentage too high: {val}% in line: {line}"
                        except ValueError:
                            pass


# ================================================================
# Integration (3 tests)
# ================================================================

class TestIntegration:
    def test_gate_summary_no_absurd_values(self):
        """Full gate summary should have no values like 22600% or 4200%."""
        gate = QualityGate()
        gate.check_discovery_gate(126, 0.9, 0.85)
        gate.check_analysis_gate(0.92, 126, 2)
        gate.check_testing_gate(
            test_coverage=0.9,
            traceability=0.95,
            test_cases_count=1130
        )
        md = gate.get_gate_summary()
        assert "22600" not in md
        assert "4200" not in md
        assert "448" not in md

    def test_gate_history_tracks_all(self):
        """All gate checks should be in history."""
        gate = QualityGate()
        gate.check_discovery_gate(10, 0.9, 0.85)
        gate.check_analysis_gate(0.92, 10, 2)
        gate.check_testing_gate(0.9, 0.95, 100)
        assert len(gate.gate_history) == 3
        assert gate.gate_history[0].gate_name == "pass1_to_pass2"
        assert gate.gate_history[1].gate_name == "pass2_to_pass3"
        assert gate.gate_history[2].gate_name == "pass4_to_pass5"

    def test_post_critique_adds_to_history(self):
        """A second testing gate check (post-critique) should append."""
        gate = QualityGate()
        gate.check_testing_gate(0.8, 0.7, 100)  # Initial
        gate.check_testing_gate(0.9, 0.95, 120)  # Post-fix
        assert len(gate.gate_history) == 2
        # Second should have better traceability
        assert gate.gate_history[1].metrics_evaluated["traceability"] > gate.gate_history[0].metrics_evaluated["traceability"]

    def test_count_thresholds_in_result(self):
        """Count thresholds should be stored in result for display."""
        gate = QualityGate()
        result = gate.check_testing_gate(0.9, 0.95, 1130)
        assert "min_test_cases" in result.count_thresholds
        assert result.count_thresholds["min_test_cases"] == 5
