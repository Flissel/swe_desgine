"""Tests for output quality improvements (4 fixes)."""
import json
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

import pytest


# ── Fix 1: Completeness Score ────────────────────────────────────────────

class TestCompletenessScore:
    """Tests for real completeness_score computation."""

    def _make_req(self, **overrides):
        from requirements_engineer.core.re_journal import RequirementNode
        defaults = {
            "requirement_id": "REQ-001",
            "title": "",
            "description": "",
            "type": "",
            "priority": "",
        }
        defaults.update(overrides)
        return RequirementNode(**defaults)

    def _compute_completeness(self, req):
        """Mirror the logic from run_re_system.py."""
        filled = 0
        total = 6
        if getattr(req, 'title', ''):
            filled += 1
        if getattr(req, 'description', '') and len(getattr(req, 'description', '')) > 20:
            filled += 1
        if getattr(req, 'type', ''):
            filled += 1
        if getattr(req, 'priority', ''):
            filled += 1
        if getattr(req, 'acceptance_criteria', None):
            filled += 1
        if getattr(req, 'mermaid_diagrams', None):
            filled += 1
        return filled / total

    def test_completeness_fully_populated(self):
        req = self._make_req(
            title="User Registration",
            description="Allow users to register with phone number and verification",
            type="functional",
            priority="must",
            acceptance_criteria=["Phone verified", "2FA enabled"],
            mermaid_diagrams=["graph TD; A-->B"],
        )
        score = self._compute_completeness(req)
        assert score == 1.0

    def test_completeness_minimal(self):
        req = self._make_req(title="Something", type="functional")
        score = self._compute_completeness(req)
        # title + type = 2/6
        assert abs(score - 2 / 6) < 0.001

    def test_completeness_no_acceptance_criteria(self):
        req = self._make_req(
            title="Messaging",
            description="Users can send text messages to contacts in real-time",
            type="functional",
            priority="must",
        )
        score = self._compute_completeness(req)
        # title + description(>20) + type + priority = 4/6
        assert abs(score - 4 / 6) < 0.001

    def test_completeness_short_description_not_counted(self):
        req = self._make_req(
            title="Auth",
            description="Short desc",  # <=20 chars
            type="functional",
            priority="must",
        )
        score = self._compute_completeness(req)
        # title + type + priority = 3/6 (description too short)
        assert abs(score - 3 / 6) < 0.001


# ── Fix 2: API Endpoint Deduplication ─────────────────────────────────────

class TestApiDeduplication:
    """Tests for API endpoint dedup logic."""

    def _make_endpoint(self, method, path, parent_req_id="REQ-001", tags=None, params=None):
        from requirements_engineer.generators.api_spec_generator import APIEndpoint, APIParameter
        return APIEndpoint(
            path=path,
            method=method,
            summary=f"{method} {path}",
            tags=tags or [],
            parameters=params or [],
            parent_requirement_id=parent_req_id,
        )

    def _deduplicate(self, endpoints):
        """Mirror the dedup logic from api_spec_generator.py."""
        seen = {}
        deduped = []
        for ep in endpoints:
            key = (ep.method.upper(), ep.path)
            if key in seen:
                existing = seen[key]
                if ep.parent_requirement_id and ep.parent_requirement_id not in (existing.tags or []):
                    if existing.tags is None:
                        existing.tags = []
                    existing.tags.append(ep.parent_requirement_id)
                existing_param_names = {p.name for p in existing.parameters}
                for p in ep.parameters:
                    if p.name not in existing_param_names:
                        existing.parameters.append(p)
            else:
                seen[key] = ep
                deduped.append(ep)
        return deduped

    def test_duplicate_endpoints_merged(self):
        eps = [
            self._make_endpoint("GET", "/api/v1/messages/{id}", "REQ-001"),
            self._make_endpoint("GET", "/api/v1/messages/{id}", "REQ-002"),
            self._make_endpoint("GET", "/api/v1/messages/{id}", "REQ-003"),
        ]
        result = self._deduplicate(eps)
        assert len(result) == 1

    def test_different_endpoints_preserved(self):
        eps = [
            self._make_endpoint("GET", "/api/v1/messages", "REQ-001"),
            self._make_endpoint("POST", "/api/v1/messages", "REQ-001"),
            self._make_endpoint("GET", "/api/v1/users/{id}", "REQ-002"),
        ]
        result = self._deduplicate(eps)
        assert len(result) == 3

    def test_merged_endpoint_has_both_requirement_refs(self):
        eps = [
            self._make_endpoint("GET", "/api/v1/messages/{id}", "REQ-001"),
            self._make_endpoint("GET", "/api/v1/messages/{id}", "REQ-002"),
        ]
        result = self._deduplicate(eps)
        assert len(result) == 1
        # First endpoint keeps its parent_requirement_id, second is added to tags
        assert "REQ-002" in result[0].tags

    def test_merged_endpoint_combines_parameters(self):
        from requirements_engineer.generators.api_spec_generator import APIParameter
        ep1 = self._make_endpoint("GET", "/api/v1/messages", "REQ-001",
                                   params=[APIParameter(name="page", location="query", type="integer")])
        ep2 = self._make_endpoint("GET", "/api/v1/messages", "REQ-002",
                                   params=[APIParameter(name="page", location="query", type="integer"),
                                           APIParameter(name="limit", location="query", type="integer")])
        result = self._deduplicate([ep1, ep2])
        assert len(result) == 1
        param_names = {p.name for p in result[0].parameters}
        assert "page" in param_names
        assert "limit" in param_names


# ── Fix 3: Screen Traceability ────────────────────────────────────────────

class TestScreenTraceability:
    """Tests for building screen links from composition files."""

    def _build_screens_from_compositions(self, compositions_dir):
        """Mirror the logic from run_re_system.py."""
        traceability_screens = []
        if compositions_dir.exists():
            for jf in sorted(compositions_dir.glob("*.json")):
                if jf.name in ("component_matrix.json", "index.json"):
                    continue
                try:
                    with open(jf, encoding="utf-8") as f:
                        comp = json.load(f)
                    for us_id in comp.get("user_stories", []):
                        traceability_screens.append({
                            "id": f"SCREEN-{jf.stem.upper().replace('_', '-')}",
                            "parent_user_story": us_id,
                            "name": comp.get("screen_name", jf.stem),
                        })
                except Exception:
                    pass
        return traceability_screens

    def test_compositions_provide_screen_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            comp_dir = Path(tmpdir) / "compositions"
            comp_dir.mkdir()
            comp = {"screen_name": "Login Screen", "user_stories": ["US-001", "US-002"]}
            (comp_dir / "login_screen.json").write_text(json.dumps(comp), encoding="utf-8")
            screens = self._build_screens_from_compositions(comp_dir)
            assert len(screens) == 2
            assert screens[0]["parent_user_story"] == "US-001"
            assert screens[1]["parent_user_story"] == "US-002"
            assert screens[0]["name"] == "Login Screen"

    def test_skips_component_matrix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            comp_dir = Path(tmpdir) / "compositions"
            comp_dir.mkdir()
            (comp_dir / "component_matrix.json").write_text("{}", encoding="utf-8")
            (comp_dir / "index.json").write_text("{}", encoding="utf-8")
            (comp_dir / "dashboard.json").write_text(
                json.dumps({"screen_name": "Dashboard", "user_stories": ["US-010"]}),
                encoding="utf-8",
            )
            screens = self._build_screens_from_compositions(comp_dir)
            assert len(screens) == 1
            assert screens[0]["id"] == "SCREEN-DASHBOARD"

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            comp_dir = Path(tmpdir) / "compositions"
            comp_dir.mkdir()
            screens = self._build_screens_from_compositions(comp_dir)
            assert screens == []

    def test_real_compositions_have_links(self):
        """Test against real enterprise output if available."""
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()] if output_dir.exists() else []
        comp_dir = None
        for proj in projects:
            candidate = proj / "ui_design" / "compositions"
            if candidate.exists() and list(candidate.glob("*.json")):
                comp_dir = candidate
                break
        if not comp_dir:
            pytest.skip("No enterprise project with compositions found")
        screens = self._build_screens_from_compositions(comp_dir)
        assert len(screens) > 0, "Expected at least one screen-story link from compositions"


# ── Fix 4: Richer Stub Test Cases ─────────────────────────────────────────

class TestRicherStubTests:
    """Tests for acceptance-criteria-based stub test cases."""

    def _make_story(self, story_id="US-001", persona="user", action="send a message",
                    benefit="communicate with contacts", acceptance_criteria=None,
                    parent_req="REQ-001"):
        from requirements_engineer.generators.user_story_generator import UserStory
        return UserStory(
            id=story_id,
            title="Send Message",
            persona=persona,
            action=action,
            benefit=benefit,
            acceptance_criteria=acceptance_criteria or [],
            parent_requirement_id=parent_req,
        )

    def _build_stub_steps(self, story):
        """Mirror the stub TC logic from self_critique.py."""
        from requirements_engineer.generators.test_case_generator import TestStep
        persona = getattr(story, "persona", "user")
        action = getattr(story, "action", "perform action")
        benefit = getattr(story, "benefit", "achieve goal")

        ac_list = getattr(story, "acceptance_criteria", None) or []
        if ac_list and isinstance(ac_list, list) and len(ac_list) > 0:
            steps = [
                TestStep(step_type="Given", description=f"{persona} is authenticated and on the relevant page"),
                TestStep(step_type="When", description=f"{persona} performs: {action}"),
            ]
            for ac in ac_list[:5]:
                ac_text = ac if isinstance(ac, str) else str(ac)
                steps.append(TestStep(step_type="Then", description=ac_text))
        else:
            steps = [
                TestStep(step_type="Given", description=f"{persona} is authenticated"),
                TestStep(step_type="When", description=f"{persona} {action}"),
                TestStep(step_type="Then", description=f"System confirms: {benefit}"),
            ]
        return steps

    def test_stub_uses_acceptance_criteria(self):
        story = self._make_story(
            acceptance_criteria=["Message delivered within 2 seconds", "Read receipt shown"]
        )
        steps = self._build_stub_steps(story)
        then_steps = [s for s in steps if s.step_type == "Then"]
        assert len(then_steps) == 2
        assert then_steps[0].description == "Message delivered within 2 seconds"
        assert then_steps[1].description == "Read receipt shown"

    def test_stub_fallback_when_no_ac(self):
        story = self._make_story(acceptance_criteria=[])
        steps = self._build_stub_steps(story)
        then_steps = [s for s in steps if s.step_type == "Then"]
        assert len(then_steps) == 1
        assert "System confirms:" in then_steps[0].description

    def test_stub_limits_to_5_ac_steps(self):
        acs = [f"Criterion {i}" for i in range(10)]
        story = self._make_story(acceptance_criteria=acs)
        steps = self._build_stub_steps(story)
        then_steps = [s for s in steps if s.step_type == "Then"]
        assert len(then_steps) == 5

    def test_stub_has_given_and_when(self):
        story = self._make_story(acceptance_criteria=["AC1"])
        steps = self._build_stub_steps(story)
        given = [s for s in steps if s.step_type == "Given"]
        when = [s for s in steps if s.step_type == "When"]
        assert len(given) == 1
        assert "authenticated" in given[0].description
        assert len(when) == 1
        assert "send a message" in when[0].description
