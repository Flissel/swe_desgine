"""
Completeness Checker — 12 cross-artifact rules for evaluating RE output quality.

Each rule computes a metric, compares against a configurable threshold,
produces a score 0.0–1.0, and emits Gap objects for items below threshold.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from . import (
    ArtifactBundle,
    CompletenessReport,
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    Gap,
    GapFixStrategy,
    GapSeverity,
    RuleResult,
)

logger = logging.getLogger(__name__)

# Stopwords for keyword overlap matching
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "and", "but", "or",
    "nor", "not", "no", "so", "yet", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "about", "up", "down",
    "out", "off", "over", "again", "further", "then", "once", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "than",
    "too", "very", "just", "also", "if", "this", "that", "these", "those",
    "it", "its", "user", "system", "data", "information",
    "der", "die", "das", "ein", "eine", "und", "oder", "nicht", "mit",
    "von", "zu", "auf", "in", "an", "für", "ist", "wird", "werden",
})


def _extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from text (lowercased, stopwords removed).

    Handles CamelCase, snake_case, path segments, and hyphenated names:
      - "PaymentTransaction" → {"payment", "transaction"}
      - "/api/v1/users/{id}" → {"api", "users"}
      - "payment_gateway" → {"payment", "gateway"}
    """
    # Split CamelCase: "PaymentTransaction" → "Payment Transaction"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Split on underscores, hyphens, slashes, braces, dots, colons
    text = re.sub(r'[_/\-{}.:]', ' ', text)
    words = set(re.findall(r"[a-zA-ZäöüÄÖÜß]{3,}", text.lower()))
    return words - _STOPWORDS


class CompletenessChecker:
    """Runs 12 completeness rules against an ArtifactBundle."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.thresholds = {**DEFAULT_THRESHOLDS, **(config.get("thresholds", {}))}
        self.weights = {**DEFAULT_WEIGHTS, **(config.get("weights", {}))}
        self.disabled_rules: Set[str] = set(config.get("disabled_rules", []))
        self._gap_counter = 0

    def _next_gap_id(self) -> str:
        self._gap_counter += 1
        return f"GAP-{self._gap_counter:03d}"

    def check_all(self, bundle: ArtifactBundle) -> CompletenessReport:
        """Run all enabled rules and produce a CompletenessReport."""
        self._gap_counter = 0
        rules = [
            self._check_req_to_story,
            self._check_story_to_test,
            self._check_story_to_screen,
            self._check_api_to_req,
            self._check_entity_to_req,
            self._check_state_machine_density,
            self._check_task_backlinks,
            self._check_task_ratio,
            self._check_component_count,
            self._check_flow_coverage,
            self._check_quality_gates,
            self._check_test_api_linkage,
        ]

        results = []
        for rule_fn in rules:
            result = rule_fn(bundle)
            if result.rule_id not in self.disabled_rules:
                results.append(result)

        # Compute weighted overall score
        total_weight = sum(self.weights.get(r.rule_id, 0) for r in results)
        if total_weight > 0:
            overall = sum(
                r.score * self.weights.get(r.rule_id, 0)
                for r in results
            ) / total_weight
        else:
            overall = 0.0

        return CompletenessReport(
            rule_results=results,
            overall_score=round(overall, 4),
            timestamp=datetime.now().isoformat(),
        )

    # ------------------------------------------------------------------
    # Rule 1: Requirement -> Story coverage
    # ------------------------------------------------------------------

    def _check_req_to_story(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "req_to_story"
        threshold = self.thresholds[rule_id]

        func_reqs = [
            r for r in bundle.requirements
            if getattr(r, "type", "functional") == "functional"
        ]
        if not func_reqs:
            return RuleResult(rule_id=rule_id, rule_name="Requirement -> Story",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Build set of requirement IDs that have stories
        reqs_with_stories: Set[str] = set()
        for story in bundle.user_stories:
            parent = getattr(story, "parent_requirement_id", "")
            if parent:
                reqs_with_stories.add(parent)
            for linked in getattr(story, "linked_requirement_ids", []):
                reqs_with_stories.add(linked)

        gaps = []
        for req in func_reqs:
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            if rid and rid not in reqs_with_stories:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.HIGH,
                    title=f"Requirement {rid} has no user story",
                    affected_ids=[rid],
                    current_value=0.0,
                    target_value=1.0,
                    fix_strategy=GapFixStrategy.GENERATOR,
                    generator_name="user_story",
                ))

        covered = len(func_reqs) - len(gaps)
        ratio = covered / len(func_reqs) if func_reqs else 1.0
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Requirement -> Story",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 2: Story -> Test coverage
    # ------------------------------------------------------------------

    def _check_story_to_test(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "story_to_test"
        threshold = self.thresholds[rule_id]

        if not bundle.user_stories:
            return RuleResult(rule_id=rule_id, rule_name="Story -> Test",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        stories_with_tests: Set[str] = set()
        for tc in bundle.test_cases:
            parent = getattr(tc, "parent_user_story_id", "")
            if parent:
                stories_with_tests.add(parent)

        gaps = []
        for story in bundle.user_stories:
            sid = getattr(story, "id", "")
            if sid and sid not in stories_with_tests:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.HIGH,
                    title=f"Story {sid} has no test case",
                    affected_ids=[sid],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                    generator_name="test_case",
                ))

        covered = len(bundle.user_stories) - len(gaps)
        ratio = covered / len(bundle.user_stories)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Story -> Test",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 3: Story -> Screen coverage
    # ------------------------------------------------------------------

    def _check_story_to_screen(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "story_to_screen"
        threshold = self.thresholds[rule_id]

        if not bundle.user_stories:
            return RuleResult(rule_id=rule_id, rule_name="Story -> Screen",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Build mapping of stories that have screens
        stories_with_screens: Set[str] = set()
        for screen in bundle.screens:
            parent_us = getattr(screen, "parent_user_story", "")
            if parent_us:
                stories_with_screens.add(parent_us)
            for linked in getattr(screen, "linked_user_stories", []):
                stories_with_screens.add(linked)

        # Also check compositions (key varies: "linked_user_stories" or "user_stories")
        for comp in bundle.screen_compositions:
            if isinstance(comp, dict):
                for sid in comp.get("linked_user_stories", comp.get("user_stories", [])):
                    stories_with_screens.add(sid)
            else:
                linked = getattr(comp, "linked_user_stories",
                                 getattr(comp, "user_stories", []))
                for sid in linked:
                    stories_with_screens.add(sid)

        gaps = []
        for story in bundle.user_stories:
            sid = getattr(story, "id", "")
            if sid and sid not in stories_with_screens:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.MEDIUM,
                    title=f"Story {sid} has no screen",
                    affected_ids=[sid],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                    generator_name="screen",
                ))

        covered = len(bundle.user_stories) - len(gaps)
        ratio = covered / len(bundle.user_stories)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Story -> Screen",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 4: API Endpoint -> Requirement linkage
    # ------------------------------------------------------------------

    def _check_api_to_req(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "api_to_req"
        threshold = self.thresholds[rule_id]

        if not bundle.api_endpoints:
            return RuleResult(rule_id=rule_id, rule_name="API -> Requirement",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        gaps = []
        for ep in bundle.api_endpoints:
            parent = getattr(ep, "parent_requirement_id", "")
            if not parent:
                path = getattr(ep, "path", "")
                method = getattr(ep, "method", "")
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.MEDIUM,
                    title=f"API {method} {path} has no linked requirement",
                    affected_ids=[f"{method} {path}"],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                ))

        covered = len(bundle.api_endpoints) - len(gaps)
        ratio = covered / len(bundle.api_endpoints)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="API -> Requirement",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 5: Entity -> Requirement coverage
    # ------------------------------------------------------------------

    def _check_entity_to_req(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "entity_to_req"
        threshold = self.thresholds[rule_id]

        entities = list(bundle.entities.values()) if bundle.entities else []
        if not entities:
            return RuleResult(rule_id=rule_id, rule_name="Entity -> Requirement",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Build entity keywords and match against requirements
        req_keyword_map: Dict[str, Set[str]] = {}
        for req in bundle.requirements:
            rid = getattr(req, "requirement_id", "") or getattr(req, "id", "")
            title = getattr(req, "title", "")
            desc = getattr(req, "description", "")
            req_keyword_map[rid] = _extract_keywords(f"{title} {desc}")

        gaps = []
        for entity in entities:
            name = entity.name if hasattr(entity, "name") else entity.get("name", "")
            entity_kw = _extract_keywords(name)
            linked = False
            for _rid, req_kw in req_keyword_map.items():
                if len(entity_kw & req_kw) >= 1:
                    linked = True
                    break
            if not linked:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.MEDIUM,
                    title=f"Entity '{name}' not linked to any requirement",
                    affected_ids=[name],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.LLM_EXTEND,
                ))

        covered = len(entities) - len(gaps)
        ratio = covered / len(entities)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Entity -> Requirement",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 6: State Machine density
    # ------------------------------------------------------------------

    def _check_state_machine_density(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "state_machine_density"
        threshold = self.thresholds[rule_id]

        entities = list(bundle.entities.values()) if bundle.entities else []
        if not entities:
            return RuleResult(rule_id=rule_id, rule_name="State Machine Density",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Identify lifecycle entities (those likely needing state machines)
        lifecycle_keywords = {
            "status", "state", "phase", "stage", "step", "order", "request",
            "session", "message", "chat", "call", "payment", "subscription",
            "registration", "notification", "task", "job", "workflow",
        }

        lifecycle_entities = []
        for entity in entities:
            name = entity.name if hasattr(entity, "name") else entity.get("name", "")
            fields = getattr(entity, "fields", [])
            if isinstance(entity, dict):
                fields = entity.get("fields", [])

            # Check if entity has status/state field or lifecycle name
            has_lifecycle = name.lower() in lifecycle_keywords
            for f in fields:
                fname = f.name if hasattr(f, "name") else (f.get("name", "") if isinstance(f, dict) else "")
                if fname.lower() in ("status", "state", "phase"):
                    has_lifecycle = True
                    break
            if has_lifecycle:
                lifecycle_entities.append(name)

        if not lifecycle_entities:
            return RuleResult(rule_id=rule_id, rule_name="State Machine Density",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Check which lifecycle entities have state machines
        sm_entities = set()
        for sm in bundle.state_machines:
            ent_name = getattr(sm, "entity", "")
            if ent_name:
                sm_entities.add(ent_name.lower())

        gaps = []
        for name in lifecycle_entities:
            if name.lower() not in sm_entities:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.LOW,
                    title=f"Entity '{name}' has no state machine",
                    affected_ids=[name],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                    generator_name="state_machine",
                ))

        covered = len(lifecycle_entities) - len(gaps)
        ratio = covered / len(lifecycle_entities)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="State Machine Density",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 7: Task backlinks
    # ------------------------------------------------------------------

    def _check_task_backlinks(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "task_backlinks"
        threshold = self.thresholds[rule_id]

        if not bundle.tasks:
            return RuleResult(rule_id=rule_id, rule_name="Task Backlinks",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        gaps = []
        for task in bundle.tasks:
            tid = getattr(task, "id", "")
            parent_req = getattr(task, "parent_requirement_id", "")
            parent_story = getattr(task, "parent_user_story_id", "")
            parent_feature = getattr(task, "parent_feature_id", "")
            if not parent_req and not parent_story and not parent_feature:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.LOW,
                    title=f"Task {tid} has no backlink to requirement/story",
                    affected_ids=[tid],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                ))

        covered = len(bundle.tasks) - len(gaps)
        ratio = covered / len(bundle.tasks)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Task Backlinks",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 8: Task ratio (tasks per requirement)
    # ------------------------------------------------------------------

    def _check_task_ratio(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "task_ratio"
        threshold = self.thresholds[rule_id]  # minimum ratio, e.g. 2.0

        func_reqs = [
            r for r in bundle.requirements
            if getattr(r, "type", "functional") == "functional"
        ]
        if not func_reqs:
            return RuleResult(rule_id=rule_id, rule_name="Task Ratio",
                              current_value=threshold, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        ratio = len(bundle.tasks) / len(func_reqs) if func_reqs else 0

        gaps = []
        if ratio < threshold:
            gaps.append(Gap(
                gap_id=self._next_gap_id(),
                rule_id=rule_id,
                severity=GapSeverity.HIGH,
                title=f"Task ratio {ratio:.1f} below threshold {threshold}",
                description=f"{len(bundle.tasks)} tasks for {len(func_reqs)} requirements",
                affected_ids=[],
                current_value=ratio,
                target_value=threshold,
                fix_strategy=GapFixStrategy.AUTO_LINK,
                generator_name="task",
            ))

        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Task Ratio",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 9: Component count
    # ------------------------------------------------------------------

    def _check_component_count(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "component_count"
        threshold = self.thresholds[rule_id]

        if not bundle.screens:
            return RuleResult(rule_id=rule_id, rule_name="Component Count",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Count unique components from screens and compositions
        components: Set[str] = set()
        for screen in bundle.screens:
            for comp in getattr(screen, "components", []):
                cname = getattr(comp, "name", "") if hasattr(comp, "name") else (
                    comp.get("name", "") if isinstance(comp, dict) else str(comp)
                )
                if cname:
                    components.add(cname)

        target = len(bundle.screens) * 1.5
        if target <= 0:
            return RuleResult(rule_id=rule_id, rule_name="Component Count",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        ratio = len(components) / target

        gaps = []
        if ratio < threshold:
            gaps.append(Gap(
                gap_id=self._next_gap_id(),
                rule_id=rule_id,
                severity=GapSeverity.MEDIUM,
                title=f"Only {len(components)} components for {len(bundle.screens)} screens",
                description=f"Expected ~{int(target)} components (1.5× screens)",
                affected_ids=[],
                current_value=ratio,
                target_value=threshold,
                fix_strategy=GapFixStrategy.GENERATOR,
                generator_name="component",
            ))

        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Component Count",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 10: Flow coverage (epics with user flows)
    # ------------------------------------------------------------------

    def _check_flow_coverage(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "flow_coverage"
        threshold = self.thresholds[rule_id]

        if not bundle.epics:
            return RuleResult(rule_id=rule_id, rule_name="Flow Coverage",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Match flows to epics via keyword overlap
        flow_keywords: List[Set[str]] = []
        for flow in bundle.user_flows:
            name = getattr(flow, "name", "") or getattr(flow, "title", "")
            desc = getattr(flow, "description", "")
            flow_keywords.append(_extract_keywords(f"{name} {desc}"))

        gaps = []
        for epic in bundle.epics:
            eid = getattr(epic, "id", "")
            title = getattr(epic, "title", "")
            desc = getattr(epic, "description", "")
            epic_kw = _extract_keywords(f"{title} {desc}")

            has_flow = False
            for fkw in flow_keywords:
                if len(epic_kw & fkw) >= 2:
                    has_flow = True
                    break

            if not has_flow:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.MEDIUM,
                    title=f"Epic {eid} has no matching user flow",
                    affected_ids=[eid],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.AUTO_LINK,
                    generator_name="user_flow",
                ))

        covered = len(bundle.epics) - len(gaps)
        ratio = covered / len(bundle.epics)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Flow Coverage",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 11: Quality gates checked
    # ------------------------------------------------------------------

    def _check_quality_gates(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "quality_gates"
        threshold = self.thresholds[rule_id]

        # If the bundle has no artifacts at all, there's nothing to gate
        has_any = bundle.requirements or bundle.user_stories or bundle.test_cases
        if not has_any:
            return RuleResult(rule_id=rule_id, rule_name="Quality Gates",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Check how many quality gates we can verify programmatically
        gates_passed = 0
        total_gates = 3  # discovery, analysis, testing

        # Discovery gate: has requirements
        if bundle.requirements:
            gates_passed += 1
        # Analysis gate: has user stories
        if bundle.user_stories:
            gates_passed += 1
        # Testing gate: has test cases
        if bundle.test_cases:
            gates_passed += 1

        ratio = gates_passed / total_gates
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        gaps = []
        if ratio < threshold:
            missing = []
            if not bundle.requirements:
                missing.append("requirements")
            if not bundle.user_stories:
                missing.append("user_stories")
            if not bundle.test_cases:
                missing.append("test_cases")
            gaps.append(Gap(
                gap_id=self._next_gap_id(),
                rule_id=rule_id,
                severity=GapSeverity.CRITICAL,
                title=f"Missing quality gates: {', '.join(missing)}",
                affected_ids=missing,
                current_value=ratio,
                target_value=threshold,
                fix_strategy=GapFixStrategy.MANUAL,
            ))

        return RuleResult(
            rule_id=rule_id, rule_name="Quality Gates",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )

    # ------------------------------------------------------------------
    # Rule 12: Test <-> API endpoint linkage
    # ------------------------------------------------------------------

    def _check_test_api_linkage(self, bundle: ArtifactBundle) -> RuleResult:
        rule_id = "test_api_linkage"
        threshold = self.thresholds[rule_id]

        if not bundle.api_endpoints:
            return RuleResult(rule_id=rule_id, rule_name="Test <-> API Linkage",
                              current_value=1.0, target_value=threshold,
                              score=1.0, weight=self.weights[rule_id], passed=True)

        # Extract keywords from test case titles/descriptions
        test_keywords: List[Set[str]] = []
        for tc in bundle.test_cases:
            title = getattr(tc, "title", "") or getattr(tc, "name", "")
            desc = getattr(tc, "description", "")
            test_keywords.append(_extract_keywords(f"{title} {desc}"))

        gaps = []
        for ep in bundle.api_endpoints:
            path = getattr(ep, "path", "")
            method = getattr(ep, "method", "")
            summary = getattr(ep, "summary", "")
            ep_kw = _extract_keywords(f"{path} {summary}")

            has_test = False
            for tkw in test_keywords:
                if len(ep_kw & tkw) >= 2:
                    has_test = True
                    break

            if not has_test:
                gaps.append(Gap(
                    gap_id=self._next_gap_id(),
                    rule_id=rule_id,
                    severity=GapSeverity.MEDIUM,
                    title=f"API {method} {path} has no matching test",
                    affected_ids=[f"{method} {path}"],
                    current_value=0.0, target_value=1.0,
                    fix_strategy=GapFixStrategy.GENERATOR,
                    generator_name="test_case",
                ))

        covered = len(bundle.api_endpoints) - len(gaps)
        ratio = covered / len(bundle.api_endpoints)
        score = min(ratio / threshold, 1.0) if threshold > 0 else 1.0

        return RuleResult(
            rule_id=rule_id, rule_name="Test <-> API Linkage",
            current_value=round(ratio, 4), target_value=threshold,
            score=round(score, 4), weight=self.weights[rule_id],
            gaps=gaps, passed=ratio >= threshold,
        )
