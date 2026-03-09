"""
Tests for wizard suggestion queue and agent teams.

Unit tests use mocked LLM responses / fallback mode.
LLM integration tests are marked with pytest.mark.llm.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ============================================================
# Suggestion Queue Tests
# ============================================================


class TestWizardSuggestion:
    """Tests for WizardSuggestion dataclass."""

    def test_create_suggestion(self):
        from requirements_engineer.wizard.suggestion_queue import (
            WizardSuggestion, SuggestionType, SuggestionStatus,
        )
        s = WizardSuggestion.create(
            suggestion_type=SuggestionType.STAKEHOLDER,
            content={"role": "Product Owner"},
            confidence=0.9,
            reasoning="Identified from domain",
            source_team="StakeholderTeam",
            wizard_step=1,
        )
        assert s.type == SuggestionType.STAKEHOLDER
        assert s.status == SuggestionStatus.PENDING
        assert s.confidence == 0.9
        assert len(s.id) == 8
        assert s.content["role"] == "Product Owner"

    def test_to_dict(self):
        from requirements_engineer.wizard.suggestion_queue import (
            WizardSuggestion, SuggestionType, SuggestionStatus,
        )
        s = WizardSuggestion.create(
            suggestion_type=SuggestionType.REQUIREMENT,
            content={"title": "Auth"},
            confidence=0.7,
            reasoning="Gap found",
            source_team="RequirementGapTeam",
            wizard_step=3,
        )
        d = s.to_dict()
        assert d["type"] == "requirement"
        assert d["status"] == "pending"
        assert d["confidence"] == 0.7
        assert d["content"]["title"] == "Auth"
        assert "id" in d
        assert "created_at" in d


class TestWizardSuggestionQueue:
    """Tests for WizardSuggestionQueue routing logic."""

    def _make_queue(self, thresholds=None):
        from requirements_engineer.wizard.suggestion_queue import WizardSuggestionQueue
        emitter = AsyncMock()
        emitter.emit_raw = AsyncMock()
        config = {}
        if thresholds:
            config["thresholds"] = thresholds
        return WizardSuggestionQueue(emitter=emitter, config=config)

    def _make_suggestion(self, confidence, stype="stakeholder"):
        from requirements_engineer.wizard.suggestion_queue import (
            WizardSuggestion, SuggestionType,
        )
        type_map = {
            "stakeholder": SuggestionType.STAKEHOLDER,
            "requirement": SuggestionType.REQUIREMENT,
            "constraint": SuggestionType.CONSTRAINT,
            "context": SuggestionType.CONTEXT,
        }
        return WizardSuggestion.create(
            suggestion_type=type_map[stype],
            content={"test": True},
            confidence=confidence,
            reasoning="test",
            source_team="TestTeam",
            wizard_step=1,
        )

    @pytest.mark.asyncio
    async def test_auto_apply_high_confidence(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.90)
        result = await queue.submit(s)
        assert result["action"] == "auto_applied"
        assert queue.pending_count == 0
        assert len(queue.get_history()) == 1

    @pytest.mark.asyncio
    async def test_pending_medium_confidence(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.70)
        result = await queue.submit(s)
        assert result["action"] == "pending"
        assert queue.pending_count == 1

    @pytest.mark.asyncio
    async def test_discard_low_confidence(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.30)
        result = await queue.submit(s)
        assert result["action"] == "discarded"
        assert queue.pending_count == 0
        assert len(queue.get_history()) == 1

    @pytest.mark.asyncio
    async def test_approve_pending(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.70)
        await queue.submit(s)
        approved = await queue.approve(s.id)
        assert approved is not None
        assert approved.status.value == "approved"
        assert queue.pending_count == 0

    @pytest.mark.asyncio
    async def test_reject_pending(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.65)
        await queue.submit(s)
        rejected = await queue.reject(s.id, "Not relevant")
        assert rejected is not None
        assert rejected.status.value == "rejected"
        assert queue.pending_count == 0

    @pytest.mark.asyncio
    async def test_approve_nonexistent(self):
        queue = self._make_queue()
        result = await queue.approve("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_reject_nonexistent(self):
        queue = self._make_queue()
        result = await queue.reject("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_thresholds(self):
        queue = self._make_queue(thresholds={"auto_apply": 0.95, "user_review": 0.30})
        # 0.90 is below 0.95 threshold → pending
        s1 = self._make_suggestion(0.90)
        result1 = await queue.submit(s1)
        assert result1["action"] == "pending"
        # 0.25 is below 0.30 → discard
        s2 = self._make_suggestion(0.25)
        result2 = await queue.submit(s2)
        assert result2["action"] == "discarded"

    @pytest.mark.asyncio
    async def test_max_pending_enforced(self):
        from requirements_engineer.wizard.suggestion_queue import WizardSuggestionQueue
        emitter = AsyncMock()
        emitter.emit_raw = AsyncMock()
        queue = WizardSuggestionQueue(
            emitter=emitter,
            config={"queue": {"max_pending": 3}},
        )
        ids = []
        for i in range(5):
            s = self._make_suggestion(0.70)
            await queue.submit(s)
            ids.append(s.id)
        # Max 3 pending, so oldest 2 were evicted
        assert queue.pending_count == 3

    @pytest.mark.asyncio
    async def test_get_pending_filter_by_step(self):
        queue = self._make_queue()
        from requirements_engineer.wizard.suggestion_queue import (
            WizardSuggestion, SuggestionType,
        )
        s1 = WizardSuggestion.create(
            SuggestionType.STAKEHOLDER, {"a": 1}, 0.70, "r", "T", wizard_step=1,
        )
        s2 = WizardSuggestion.create(
            SuggestionType.REQUIREMENT, {"b": 2}, 0.60, "r", "T", wizard_step=3,
        )
        await queue.submit(s1)
        await queue.submit(s2)
        step1 = queue.get_pending(wizard_step=1)
        step3 = queue.get_pending(wizard_step=3)
        assert len(step1) == 1
        assert len(step3) == 1
        assert step1[0]["wizard_step"] == 1

    @pytest.mark.asyncio
    async def test_emitter_called_on_auto_apply(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.90)
        await queue.submit(s)
        queue._emitter.emit_raw.assert_called_once_with(
            "wizard_suggestion_auto_applied", s.to_dict()
        )

    @pytest.mark.asyncio
    async def test_emitter_called_on_pending(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.70)
        await queue.submit(s)
        queue._emitter.emit_raw.assert_called_once_with(
            "wizard_suggestion_pending", s.to_dict()
        )

    @pytest.mark.asyncio
    async def test_boundary_exactly_auto_apply(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.85)  # exactly at threshold
        result = await queue.submit(s)
        assert result["action"] == "auto_applied"

    @pytest.mark.asyncio
    async def test_boundary_exactly_user_review(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.50)  # exactly at threshold
        result = await queue.submit(s)
        assert result["action"] == "pending"

    @pytest.mark.asyncio
    async def test_boundary_just_below_user_review(self):
        queue = self._make_queue()
        s = self._make_suggestion(0.49)
        result = await queue.submit(s)
        assert result["action"] == "discarded"


# ============================================================
# Agent Team Tests (Fallback / Mock Mode)
# ============================================================


class TestStakeholderTeamFallback:
    """Test StakeholderTeam in fallback mode (no AutoGen)."""

    @pytest.mark.asyncio
    async def test_fallback_returns_3_stakeholders(self):
        with patch("requirements_engineer.wizard.wizard_agents._check_autogen", return_value=False):
            from requirements_engineer.wizard.wizard_agents import StakeholderTeam
            team = StakeholderTeam({})
            result = await team.run(
                project_name="TestApp",
                description="A test application",
                domain="web",
                target_users=["Developers"],
            )
            assert result.success is True
            assert result.team_name == "StakeholderTeam"
            assert len(result.suggestions) == 3
            roles = [s["content"]["role"] for s in result.suggestions]
            assert "Product Owner" in roles
            assert "End User" in roles
            assert "Developer" in roles

    @pytest.mark.asyncio
    async def test_fallback_uses_target_user(self):
        with patch("requirements_engineer.wizard.wizard_agents._check_autogen", return_value=False):
            from requirements_engineer.wizard.wizard_agents import StakeholderTeam
            team = StakeholderTeam({})
            result = await team.run(
                project_name="Shop",
                description="Online store",
                domain="e-commerce",
                target_users=["Online Shopper"],
            )
            personas = [s["content"]["persona"] for s in result.suggestions]
            assert "Online Shopper" in personas


class TestContextEnricherFallback:
    """Test ContextEnricher in fallback mode."""

    @pytest.mark.asyncio
    async def test_fallback_returns_context(self):
        with patch("requirements_engineer.wizard.wizard_agents._check_autogen", return_value=False):
            from requirements_engineer.wizard.wizard_agents import ContextEnricher
            team = ContextEnricher({})
            result = await team.run(
                project_name="TestApp",
                description="A great test app",
                domain="web",
            )
            assert result.success is True
            assert result.team_name == "ContextEnricher"
            assert len(result.suggestions) == 1
            ctx = result.suggestions[0]["content"]
            assert "A great test app" in ctx["summary"]
            assert ctx["domain"] == "web"


class TestRequirementGapTeamFallback:
    """Test RequirementGapTeam in fallback mode."""

    @pytest.mark.asyncio
    async def test_fallback_returns_empty(self):
        with patch("requirements_engineer.wizard.wizard_agents._check_autogen", return_value=False):
            from requirements_engineer.wizard.wizard_agents import RequirementGapTeam
            team = RequirementGapTeam({})
            result = await team.run(
                requirements=[{"title": "Login"}],
                stakeholders=[],
                domain="web",
                description="Test",
            )
            assert result.success is True
            assert result.team_name == "RequirementGapTeam"
            assert len(result.suggestions) == 0


class TestConstraintTeamFallback:
    """Test ConstraintTeam in fallback mode."""

    @pytest.mark.asyncio
    async def test_fallback_returns_empty(self):
        with patch("requirements_engineer.wizard.wizard_agents._check_autogen", return_value=False):
            from requirements_engineer.wizard.wizard_agents import ConstraintTeam
            team = ConstraintTeam({})
            result = await team.run(
                requirements=[{"title": "Store user data"}],
                existing_constraints={"technical": ["PostgreSQL"]},
                domain="web",
            )
            assert result.success is True
            assert result.team_name == "ConstraintTeam"
            assert len(result.suggestions) == 0


# ============================================================
# JSON Extraction Tests
# ============================================================


class TestJsonExtraction:
    """Tests for the 4-strategy JSON parser."""

    def test_direct_json(self):
        from requirements_engineer.wizard.wizard_agents import _extract_json
        result = _extract_json('[{"role": "Dev"}]')
        assert result == [{"role": "Dev"}]

    def test_markdown_fence(self):
        from requirements_engineer.wizard.wizard_agents import _extract_json
        text = 'Here are the stakeholders:\n```json\n[{"role": "PO"}]\n```\nDone.'
        result = _extract_json(text)
        assert result == [{"role": "PO"}]

    def test_generic_fence(self):
        from requirements_engineer.wizard.wizard_agents import _extract_json
        text = '```\n{"summary": "Test"}\n```'
        result = _extract_json(text)
        assert result == {"summary": "Test"}

    def test_bracket_match(self):
        from requirements_engineer.wizard.wizard_agents import _extract_json
        text = 'Here is the result: [{"a": 1}] and more text'
        result = _extract_json(text)
        assert result == [{"a": 1}]

    def test_no_json(self):
        from requirements_engineer.wizard.wizard_agents import _extract_json
        result = _extract_json("No JSON here at all")
        assert result is None


# ============================================================
# Event Emitter Tests
# ============================================================


class TestEventEmitterWizardTypes:
    """Test that wizard event types are properly defined."""

    def test_wizard_event_types_exist(self):
        from requirements_engineer.dashboard.event_emitter import EventType
        assert hasattr(EventType, "WIZARD_SUGGESTION_PENDING")
        assert hasattr(EventType, "WIZARD_SUGGESTION_AUTO_APPLIED")
        assert hasattr(EventType, "WIZARD_SUGGESTION_APPROVED")
        assert hasattr(EventType, "WIZARD_SUGGESTION_REJECTED")
        assert hasattr(EventType, "WIZARD_ENRICHMENT_STARTED")
        assert hasattr(EventType, "WIZARD_ENRICHMENT_COMPLETE")

    def test_wizard_event_values(self):
        from requirements_engineer.dashboard.event_emitter import EventType
        assert EventType.WIZARD_SUGGESTION_PENDING.value == "wizard_suggestion_pending"
        assert EventType.WIZARD_ENRICHMENT_COMPLETE.value == "wizard_enrichment_complete"


# ============================================================
# LLM Integration Tests (require OPENROUTER_API_KEY)
# ============================================================


@pytest.mark.llm
class TestStakeholderTeamLLM:
    """Integration test with real LLM. Requires OPENROUTER_API_KEY."""

    @pytest.mark.asyncio
    async def test_generates_stakeholders(self):
        import os
        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set")

        from requirements_engineer.wizard.wizard_agents import StakeholderTeam
        team = StakeholderTeam({
            "agents": {
                "stakeholder_team": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                }
            }
        })
        result = await team.run(
            project_name="E-Commerce Platform",
            description="A multi-vendor online marketplace with real-time inventory",
            domain="e-commerce",
            target_users=["Online Shoppers", "Vendors"],
        )
        assert result.success is True
        assert len(result.suggestions) >= 2
        for s in result.suggestions:
            assert s["type"] == "stakeholder"
            assert "role" in s["content"]
            assert 0 <= s["confidence"] <= 1.0


@pytest.mark.llm
class TestContextEnricherLLM:
    """Integration test with real LLM."""

    @pytest.mark.asyncio
    async def test_enriches_context(self):
        import os
        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set")

        from requirements_engineer.wizard.wizard_agents import ContextEnricher
        team = ContextEnricher({
            "agents": {
                "context_enricher": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                }
            }
        })
        result = await team.run(
            project_name="TaskManager Pro",
            description="Project management tool with Kanban boards",
            domain="productivity",
        )
        assert result.success is True
        assert len(result.suggestions) == 1
        ctx = result.suggestions[0]["content"]
        assert ctx.get("summary")
        assert result.suggestions[0]["type"] == "context"
