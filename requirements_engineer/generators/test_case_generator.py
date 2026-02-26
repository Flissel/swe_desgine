"""
Test Case Generator - Generates Gherkin/BDD test scenarios from User Stories.

Generates:
- Gherkin feature files with scenarios
- Test case documentation
- Test coverage matrix
"""

import os
import json
import re
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from datetime import datetime

# Try to import OpenAI, fall back gracefully
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Import LLM logger
import time
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call

# Import local types if available
try:
    from .user_story_generator import UserStory, AcceptanceCriterion
except ImportError:
    UserStory = Any
    AcceptanceCriterion = Any


@dataclass_json
@dataclass
class TestStep:
    """A single step in a test case."""
    step_type: str  # Given, When, Then, And, But
    description: str
    expected_result: str = ""


@dataclass_json
@dataclass
class GherkinScenario:
    """A Gherkin scenario with steps."""
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)  # For scenario outlines

    def to_gherkin(self) -> str:
        """Convert to Gherkin format."""
        lines = []

        if self.tags:
            lines.append("  " + " ".join(f"@{tag}" for tag in self.tags))

        if self.examples:
            lines.append(f"  Scenario Outline: {self.name}")
        else:
            lines.append(f"  Scenario: {self.name}")

        if self.description:
            lines.append(f"    # {self.description}")

        for step in self.steps:
            lines.append(f"    {step.step_type} {step.description}")

        if self.examples:
            lines.append("")
            lines.append("    Examples:")
            # Get headers from first example
            if self.examples:
                headers = list(self.examples[0].keys())
                lines.append("      | " + " | ".join(headers) + " |")
                for example in self.examples:
                    values = [str(example.get(h, "")) for h in headers]
                    lines.append("      | " + " | ".join(values) + " |")

        return "\n".join(lines)


@dataclass_json
@dataclass
class GherkinFeature:
    """A complete Gherkin feature file."""
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    background: List[TestStep] = field(default_factory=list)
    scenarios: List[GherkinScenario] = field(default_factory=list)
    parent_user_story_id: str = ""
    parent_requirement_id: str = ""
    # Gap #18: Test framework and mock strategy
    test_framework: str = ""  # e.g. "vitest", "jest", "jest+supertest"
    mock_strategy: Dict[str, str] = field(default_factory=dict)  # e.g. {"sms_service": "mock"}

    def to_gherkin(self) -> str:
        """Convert to complete Gherkin feature file."""
        lines = []

        if self.tags:
            lines.append(" ".join(f"@{tag}" for tag in self.tags))

        lines.append(f"Feature: {self.name}")

        if self.description:
            for line in self.description.split("\n"):
                lines.append(f"  {line}")

        lines.append("")

        if self.background:
            lines.append("  Background:")
            for step in self.background:
                lines.append(f"    {step.step_type} {step.description}")
            lines.append("")

        for scenario in self.scenarios:
            lines.append(scenario.to_gherkin())
            lines.append("")

        return "\n".join(lines)


@dataclass_json
@dataclass
class TestCase:
    """A test case with steps and expected results."""
    id: str  # TC-001, TC-002, etc.
    title: str
    description: str = ""
    preconditions: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    expected_result: str = ""
    priority: str = "medium"  # high, medium, low
    test_type: str = "functional"  # functional, integration, e2e, performance
    parent_user_story_id: str = ""
    parent_requirement_id: str = ""
    automation_status: str = "manual"  # manual, automated, pending

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        md = f"### {self.id}: {self.title}\n\n"
        md += f"**Type:** {self.test_type}\n"
        md += f"**Priority:** {self.priority}\n"
        md += f"**Status:** {self.automation_status}\n"

        if self.parent_user_story_id:
            md += f"**User Story:** {self.parent_user_story_id}\n"
        if self.parent_requirement_id:
            md += f"**Requirement:** {self.parent_requirement_id}\n"

        md += "\n"

        if self.description:
            md += f"**Description:** {self.description}\n\n"

        if self.preconditions:
            md += "**Preconditions:**\n"
            for pre in self.preconditions:
                md += f"- {pre}\n"
            md += "\n"

        if self.steps:
            md += "**Steps:**\n\n"
            md += "| # | Action | Expected Result |\n"
            md += "|---|--------|------------------|\n"
            for i, step in enumerate(self.steps, 1):
                md += f"| {i} | {step.description} | {step.expected_result} |\n"
            md += "\n"

        if self.expected_result:
            md += f"**Final Expected Result:** {self.expected_result}\n\n"

        return md


class TestCaseGenerator:
    """
    Generates Gherkin feature files and test cases from User Stories.

    The generator:
    1. Analyzes User Stories and their acceptance criteria
    2. Generates Gherkin scenarios (happy path, edge cases, errors)
    3. Creates test case documentation
    4. Builds test coverage matrix
    """

    GHERKIN_PROMPT = """You are a QA Engineer expert in BDD/Gherkin test design.

Given this User Story:
- ID: {us_id}
- Title: {title}
- As a: {persona}
- I want to: {action}
- So that: {benefit}

Acceptance Criteria:
{acceptance_criteria}

Generate Gherkin scenarios covering:
1. Happy path (success scenarios)
2. Edge cases
3. Error scenarios
4. Boundary conditions

Return JSON format:
{{
    "feature_name": "Feature name",
    "feature_description": "As a {persona}\\nI want to {action}\\nSo that {benefit}",
    "tags": ["smoke", "regression"],
    "background": [
        {{"step_type": "Given", "description": "common precondition"}}
    ],
    "scenarios": [
        {{
            "name": "Scenario name",
            "description": "What this scenario tests",
            "tags": ["happy-path"],
            "steps": [
                {{"step_type": "Given", "description": "precondition"}},
                {{"step_type": "When", "description": "action"}},
                {{"step_type": "Then", "description": "expected result"}},
                {{"step_type": "And", "description": "additional check"}}
            ],
            "examples": []
        }}
    ]
}}

Guidelines:
- Use clear, business-readable language
- Include at least 3 scenarios (happy path, edge case, error)
- Use scenario outlines with examples for data-driven tests
- Tag scenarios appropriately (@smoke, @regression, @negative)
- Keep steps atomic and independent
- Include a "test_strategy" section:
  - "test_framework": recommended framework (e.g., "vitest", "jest", "jest+supertest", "pytest")
  - "mock_strategy": object mapping external services to mock approach (e.g., {{"sms_service": "mock", "biometric": "stub", "webauthn": "emulated"}})

Return ONLY valid JSON, no other text."""

    TEST_CASE_PROMPT = """You are a QA Engineer expert in test case design.

Given this User Story:
- ID: {us_id}
- Title: {title}
- Description: As a {persona}, I want to {action}, so that {benefit}

Acceptance Criteria:
{acceptance_criteria}

Generate detailed test cases covering this functionality.

Return JSON format:
{{
    "test_cases": [
        {{
            "title": "Test case title",
            "description": "What is being tested",
            "test_type": "functional|integration|e2e|performance",
            "priority": "high|medium|low",
            "preconditions": ["User is logged in", "Product exists"],
            "steps": [
                {{
                    "description": "Click on login button",
                    "expected_result": "Login modal appears"
                }}
            ],
            "expected_result": "Final expected outcome"
        }}
    ]
}}

Guidelines:
- Include clear, numbered steps
- Each step should have an expected result
- Include both positive and negative test cases
- Consider boundary conditions
- Prioritize based on business impact

Return ONLY valid JSON, no other text."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Test Case Generator.

        Args:
            model_name: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.test_case section
        """
        # Load from config if available
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("test_case", {})

        self.model_name = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None

        # Counters
        self._tc_counter = 0

        # Storage
        self.features: Dict[str, GherkinFeature] = {}
        self.test_cases: Dict[str, TestCase] = {}

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _generate_tc_id(self) -> str:
        """Generate a new test case ID."""
        self._tc_counter += 1
        return f"TC-{str(self._tc_counter).zfill(3)}"

    async def _call_llm(self, prompt: str, timeout: int = 60, retries: int = 2) -> str:
        """Call the LLM and return the response with timeout and retry logic."""
        if not self.client:
            await self.initialize()

        last_error = None
        for attempt in range(retries + 1):
            try:
                start_time = time.time()
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": "You are an expert QA Engineer. Always respond with valid JSON only."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    ),
                    timeout=timeout
                )
                latency_ms = int((time.time() - start_time) * 1000)

                response_text = response.choices[0].message.content.strip()

                # Log the LLM call
                log_llm_call(
                    component="test_case_generator",
                    model=self.model_name,
                    response=response,
                    latency_ms=latency_ms,
                    system_message="You are an expert QA Engineer. Always respond with valid JSON only.",
                    user_message=prompt,
                    response_text=response_text,
                )

                return response_text
            except asyncio.TimeoutError:
                last_error = f"Timeout after {timeout}s"
                print(f"    Warning: LLM call timed out (attempt {attempt + 1}/{retries + 1})")
                # Log the failed call
                log_llm_call(
                    component="test_case_generator",
                    model=self.model_name,
                    latency_ms=timeout * 1000,
                    success=False,
                    error=last_error,
                    user_message=prompt,
                )
                if attempt < retries:
                    await asyncio.sleep(2)  # Brief pause before retry
            except Exception as e:
                last_error = str(e)
                print(f"    Warning: LLM call failed: {e} (attempt {attempt + 1}/{retries + 1})")
                # Log the failed call
                log_llm_call(
                    component="test_case_generator",
                    model=self.model_name,
                    latency_ms=int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0,
                    success=False,
                    error=last_error,
                    user_message=prompt,
                )
                if attempt < retries:
                    await asyncio.sleep(2)

        # All retries failed, return empty JSON structure
        print(f"    Error: All LLM attempts failed. Last error: {last_error}")
        return '{"test_cases": [], "scenarios": []}'

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        # Try to parse directly
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                # Try to fix truncated JSON by closing brackets
                json_text = json_match.group(0)
                # Count open/close brackets
                open_braces = json_text.count('{') - json_text.count('}')
                open_brackets = json_text.count('[') - json_text.count(']')
                # Add missing closing brackets
                json_text = json_text + ']' * open_brackets + '}' * open_braces
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    pass

        # Return empty structure if all parsing fails
        print(f"    Warning: Could not parse JSON, returning empty test_cases")
        return {"test_cases": []}

    async def generate_gherkin(self, user_story: UserStory) -> GherkinFeature:
        """
        Generate Gherkin feature from a User Story.

        Args:
            user_story: UserStory instance

        Returns:
            GherkinFeature instance
        """
        # Format acceptance criteria
        ac_text = ""
        for i, ac in enumerate(user_story.acceptance_criteria, 1):
            ac_text += f"{i}. Given {ac.given}, When {ac.when}, Then {ac.then}\n"

        prompt = self.GHERKIN_PROMPT.format(
            us_id=user_story.id,
            title=user_story.title,
            persona=user_story.persona,
            action=user_story.action,
            benefit=user_story.benefit,
            acceptance_criteria=ac_text or "Not specified"
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        # Parse background steps
        background = []
        for step_data in data.get("background", []):
            background.append(TestStep(
                step_type=step_data.get("step_type", "Given"),
                description=step_data.get("description", "")
            ))

        # Parse scenarios
        scenarios = []
        for sc_data in data.get("scenarios", []):
            steps = []
            for step_data in sc_data.get("steps", []):
                steps.append(TestStep(
                    step_type=step_data.get("step_type", "Given"),
                    description=step_data.get("description", "")
                ))

            scenario = GherkinScenario(
                name=sc_data.get("name", "Unnamed Scenario"),
                description=sc_data.get("description", ""),
                tags=sc_data.get("tags", []),
                steps=steps,
                examples=sc_data.get("examples", [])
            )
            scenarios.append(scenario)

        # Gap #18: Parse test strategy
        test_strategy = data.get("test_strategy", {})

        feature = GherkinFeature(
            name=data.get("feature_name", user_story.title),
            description=data.get("feature_description", ""),
            tags=data.get("tags", []),
            background=background,
            scenarios=scenarios,
            parent_user_story_id=user_story.id,
            parent_requirement_id=user_story.parent_requirement_id,
            test_framework=test_strategy.get("test_framework", ""),
            mock_strategy=test_strategy.get("mock_strategy", {}),
        )

        self.features[user_story.id] = feature
        return feature

    async def generate_test_cases(self, user_story: UserStory) -> List[TestCase]:
        """
        Generate detailed test cases from a User Story.

        Args:
            user_story: UserStory instance

        Returns:
            List of TestCase instances
        """
        # Format acceptance criteria
        ac_text = ""
        for i, ac in enumerate(user_story.acceptance_criteria, 1):
            ac_text += f"{i}. Given {ac.given}, When {ac.when}, Then {ac.then}\n"

        prompt = self.TEST_CASE_PROMPT.format(
            us_id=user_story.id,
            title=user_story.title,
            persona=user_story.persona,
            action=user_story.action,
            benefit=user_story.benefit,
            acceptance_criteria=ac_text or "Not specified"
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        test_cases = []
        for tc_data in data.get("test_cases", []):
            steps = []
            for step_data in tc_data.get("steps", []):
                steps.append(TestStep(
                    step_type="When",
                    description=step_data.get("description", ""),
                    expected_result=step_data.get("expected_result", "")
                ))

            tc_id = self._generate_tc_id()
            test_case = TestCase(
                id=tc_id,
                title=tc_data.get("title", "Unnamed Test"),
                description=tc_data.get("description", ""),
                test_type=tc_data.get("test_type", "functional"),
                priority=tc_data.get("priority", "medium"),
                preconditions=tc_data.get("preconditions", []),
                steps=steps,
                expected_result=tc_data.get("expected_result", ""),
                parent_user_story_id=user_story.id,
                parent_requirement_id=user_story.parent_requirement_id
            )

            self.test_cases[tc_id] = test_case
            test_cases.append(test_case)

        return test_cases

    async def generate_all_gherkin(self, user_stories: List[UserStory]) -> List[GherkinFeature]:
        """Generate Gherkin features for all user stories with error handling."""
        features = []
        total = len(user_stories)
        for i, story in enumerate(user_stories, 1):
            try:
                print(f"  [{i}/{total}] Generating Gherkin for {story.id}: {story.title}...")
                feature = await self.generate_gherkin(story)
                features.append(feature)
                print(f"    [OK] Generated {len(feature.scenarios)} scenarios")
            except Exception as e:
                print(f"    [FAIL] Failed to generate Gherkin for {story.id}: {e}")
                # Create minimal feature on failure
                features.append(GherkinFeature(
                    name=story.title,
                    description=f"As a {story.persona}, I want to {story.action}, so that {story.benefit}",
                    parent_user_story_id=story.id,
                    parent_requirement_id=story.parent_requirement_id
                ))
        return features

    async def generate_all_test_cases(self, user_stories: List[UserStory]) -> List[TestCase]:
        """Generate test cases for all user stories with error handling."""
        all_cases = []
        total = len(user_stories)
        for i, story in enumerate(user_stories, 1):
            try:
                print(f"  [{i}/{total}] Generating test cases for {story.id}...")
                cases = await self.generate_test_cases(story)
                all_cases.extend(cases)
                print(f"    [OK] Generated {len(cases)} test cases")
            except Exception as e:
                print(f"    [WARN] First attempt failed for {story.id}: {e}, retrying...")
                try:
                    cases = await self.generate_test_cases(story)
                    all_cases.extend(cases)
                    print(f"    [OK] Retry succeeded: {len(cases)} test cases")
                except Exception as e2:
                    print(f"    [FAIL] Retry also failed for {story.id}: {e2}")
                    # Create stub with acceptance criteria as test steps
                    tc_id = self._generate_tc_id()
                    steps = []
                    if story.acceptance_criteria:
                        for ac in story.acceptance_criteria:
                            steps.append(TestStep(
                                step_type="When",
                                description=f"Given {ac.given}, When {ac.when}",
                                expected_result=f"Then {ac.then}"
                            ))
                    all_cases.append(TestCase(
                        id=tc_id,
                        title=f"Test {story.title}",
                        description=f"Verify: {story.action}",
                        steps=steps,
                        parent_user_story_id=story.id,
                        parent_requirement_id=story.parent_requirement_id
                    ))
        return all_cases

    def get_coverage_matrix(self) -> Dict[str, Any]:
        """Generate test coverage matrix."""
        matrix = {
            "user_stories": {},
            "requirements": {},
            "summary": {
                "total_features": len(self.features),
                "total_test_cases": len(self.test_cases),
                "total_scenarios": sum(len(f.scenarios) for f in self.features.values())
            }
        }

        # Map user stories to test coverage
        for tc in self.test_cases.values():
            us_id = tc.parent_user_story_id
            if us_id not in matrix["user_stories"]:
                matrix["user_stories"][us_id] = {"test_cases": [], "scenarios": 0}
            matrix["user_stories"][us_id]["test_cases"].append(tc.id)

        for feature in self.features.values():
            us_id = feature.parent_user_story_id
            if us_id in matrix["user_stories"]:
                matrix["user_stories"][us_id]["scenarios"] = len(feature.scenarios)

        return matrix

    def to_markdown(self) -> str:
        """Export all test artifacts to markdown."""
        md = "# Test Documentation\n\n"
        md += f"**Generated:** {datetime.now().isoformat()}\n\n"

        md += "## Summary\n\n"
        md += f"- Gherkin Features: {len(self.features)}\n"
        md += f"- Total Scenarios: {sum(len(f.scenarios) for f in self.features.values())}\n"
        md += f"- Test Cases: {len(self.test_cases)}\n\n"

        # Gherkin Features
        md += "---\n\n## Gherkin Features\n\n"
        for feature in sorted(self.features.values(), key=lambda x: x.parent_user_story_id):
            md += f"### {feature.name}\n\n"
            md += f"*User Story:* {feature.parent_user_story_id}\n\n"
            md += "```gherkin\n"
            md += feature.to_gherkin()
            md += "\n```\n\n"

        # Test Cases
        md += "---\n\n## Test Cases\n\n"
        for tc in sorted(self.test_cases.values(), key=lambda x: x.id):
            md += tc.to_markdown()
            md += "---\n\n"

        return md

    def to_step_definitions(self) -> Dict[str, str]:
        """Generate step definition stubs for all Gherkin features.

        Dispatches by detected test_framework to generate language-appropriate stubs:
        - pytest-bdd (default for Python)
        - @cucumber/cucumber (for JS/TS)
        - io.cucumber (for Java)

        Returns:
            Dict mapping filename -> source code
        """
        framework = self._detect_step_framework()

        if framework in ("jest", "vitest", "cucumber-js", "mocha"):
            return self._generate_js_step_defs()
        elif framework in ("junit", "cucumber-java", "testng"):
            return self._generate_java_step_defs()
        else:
            return self._generate_pytest_step_defs()

    def _detect_step_framework(self) -> str:
        """Detect step definition framework from features or config."""
        # Check features for test_framework set by LLM
        for feature in self.features.values():
            if feature.test_framework:
                return feature.test_framework.lower().strip()
        # Check config
        gen_config = self.config.get("generators", {}).get("test_case", {})
        return gen_config.get("step_framework", "pytest-bdd").lower().strip()

    # ── Python / pytest-bdd ───────────────────────────────────────────────────

    def _generate_pytest_step_defs(self) -> Dict[str, str]:
        """Generate pytest-bdd step definition stubs."""
        files = {}
        files["conftest.py"] = self._generate_conftest_python()

        all_steps = {}
        for story_id, feature in self.features.items():
            feature_slug = story_id.replace('-', '_').lower()
            feature_steps = []

            for scenario in feature.scenarios:
                current_context = "given"
                for step in scenario.steps:
                    st = step.step_type.strip().lower()
                    if st in ("given", "when", "then"):
                        current_context = st
                        decorator = st
                    elif st in ("and", "but"):
                        decorator = current_context
                    else:
                        decorator = "given"

                    func_name = self._step_to_func_name(decorator, step.description)
                    if func_name not in all_steps:
                        all_steps[func_name] = (decorator, step.description)
                        feature_steps.append((decorator, step.description, func_name))

            if feature_steps:
                content = self._generate_step_file_python(
                    feature_slug, feature.name, feature_steps
                )
                files[f"test_{feature_slug}_steps.py"] = content

        return files

    def _step_to_func_name(self, step_type: str, description: str) -> str:
        """Convert step description to a valid Python function name."""
        slug = re.sub(r'[^a-z0-9]+', '_', description.lower()).strip('_')
        slug = slug[:60].rstrip('_')
        prefix = step_type.lower()
        if prefix in ("and", "but"):
            prefix = "step"
        return f"{prefix}_{slug}"

    def _generate_step_file_python(self, feature_slug: str, feature_name: str,
                                   steps: list) -> str:
        """Generate a pytest-bdd step definition file for one feature."""
        lines = [
            f'"""Step definitions for: {feature_name}',
            f'',
            f'Auto-generated by requirements_engineer pipeline.',
            f'Each step raises NotImplementedError until implemented.',
            f'"""',
            f'from pytest_bdd import given, when, then, scenario',
            f'',
            f'',
            f'FEATURE_FILE = "{feature_slug}.feature"',
            f'',
        ]

        seen = set()
        for decorator, description, func_name in steps:
            if func_name in seen:
                continue
            seen.add(func_name)
            desc_escaped = description.replace('"', '\\"')
            lines.append(f'')
            lines.append(f'@{decorator}("{desc_escaped}")')
            lines.append(f'def {func_name}():')
            lines.append(f'    """TODO: Implement - {desc_escaped}"""')
            lines.append(f'    raise NotImplementedError("Step not implemented")')

        lines.append('')
        return '\n'.join(lines)

    def _generate_conftest_python(self) -> str:
        """Generate shared conftest.py with common fixtures."""
        return '''"""Shared fixtures for BDD test step definitions.

Auto-generated by requirements_engineer pipeline.
"""
import pytest


@pytest.fixture
def app_context():
    """TODO: Set up application context for testing."""
    pass


@pytest.fixture
def authenticated_user():
    """TODO: Set up an authenticated user session."""
    pass


@pytest.fixture
def database():
    """TODO: Set up test database connection with rollback."""
    pass


@pytest.fixture
def api_client():
    """TODO: Set up HTTP test client."""
    pass


@pytest.fixture
def websocket_client():
    """TODO: Set up WebSocket test client."""
    pass
'''

    # ── JavaScript / @cucumber/cucumber ───────────────────────────────────────

    def _generate_js_step_defs(self) -> Dict[str, str]:
        """Generate @cucumber/cucumber step definition stubs (JS/TS)."""
        files = {}
        files["support/world.js"] = self._generate_js_world()

        all_steps = {}
        for story_id, feature in self.features.items():
            feature_slug = story_id.replace('-', '_').lower()
            feature_steps = []

            for scenario in feature.scenarios:
                current_context = "Given"
                for step in scenario.steps:
                    st = step.step_type.strip()
                    cap = st.capitalize()
                    if cap in ("Given", "When", "Then"):
                        current_context = cap
                        kw = cap
                    elif cap in ("And", "But"):
                        kw = current_context
                    else:
                        kw = "Given"

                    key = f"{kw}:{step.description}"
                    if key not in all_steps:
                        all_steps[key] = True
                        feature_steps.append((kw, step.description))

            if feature_steps:
                content = self._generate_step_file_js(
                    feature_slug, feature.name, feature_steps
                )
                files[f"steps/{feature_slug}.steps.js"] = content

        return files

    def _generate_step_file_js(self, feature_slug: str, feature_name: str,
                                steps: list) -> str:
        """Generate a @cucumber/cucumber step file for one feature."""
        # Collect unique keywords used
        keywords = sorted(set(kw for kw, _ in steps))
        imports = ", ".join(keywords)

        lines = [
            f"// Step definitions for: {feature_name}",
            f"//",
            f"// Auto-generated by requirements_engineer pipeline.",
            f"// Each step throws until implemented.",
            f"const {{ {imports} }} = require('@cucumber/cucumber');",
            "",
        ]

        seen = set()
        for kw, description in steps:
            key = f"{kw}:{description}"
            if key in seen:
                continue
            seen.add(key)
            desc_escaped = description.replace("'", "\\'")
            lines.append("")
            lines.append(f"{kw}('{desc_escaped}', function () {{")
            lines.append(f"  // TODO: Implement")
            lines.append(f"  throw new Error('Not implemented');")
            lines.append("});")

        lines.append("")
        return "\n".join(lines)

    def _generate_js_world(self) -> str:
        """Generate Cucumber.js World class with shared context."""
        return """// Cucumber.js World — shared test context
//
// Auto-generated by requirements_engineer pipeline.
const { setWorldConstructor, Before, After } = require('@cucumber/cucumber');

class CustomWorld {
  constructor({ attach, parameters }) {
    this.attach = attach;
    this.parameters = parameters;
    this.context = {};
  }
}

setWorldConstructor(CustomWorld);

Before(function () {
  // TODO: Set up test context (DB, auth, etc.)
});

After(function () {
  // TODO: Tear down test context
});
"""

    # ── Java / io.cucumber ────────────────────────────────────────────────────

    def _generate_java_step_defs(self) -> Dict[str, str]:
        """Generate io.cucumber step definition stubs (Java)."""
        files = {}

        all_steps = {}
        for story_id, feature in self.features.items():
            feature_slug = story_id.replace('-', '_').lower()
            feature_steps = []

            for scenario in feature.scenarios:
                current_context = "Given"
                for step in scenario.steps:
                    st = step.step_type.strip()
                    cap = st.capitalize()
                    if cap in ("Given", "When", "Then"):
                        current_context = cap
                        kw = cap
                    elif cap in ("And", "But"):
                        kw = current_context
                    else:
                        kw = "Given"

                    key = f"{kw}:{step.description}"
                    if key not in all_steps:
                        all_steps[key] = True
                        feature_steps.append((kw, step.description))

            if feature_steps:
                class_name = self._slug_to_java_class(feature_slug)
                content = self._generate_step_file_java(
                    class_name, feature.name, feature_steps
                )
                files[f"{class_name}Steps.java"] = content

        # Runner class
        files["CucumberTestRunner.java"] = self._generate_java_runner()

        return files

    def _slug_to_java_class(self, slug: str) -> str:
        """Convert slug to Java class name (PascalCase)."""
        return ''.join(w.capitalize() for w in slug.split('_'))

    def _generate_step_file_java(self, class_name: str, feature_name: str,
                                  steps: list) -> str:
        """Generate a Java step definition class."""
        # Collect unique annotations
        annotations = sorted(set(kw for kw, _ in steps))
        imports = "\n".join(f"import io.cucumber.java.en.{a};" for a in annotations)

        lines = [
            f"/**",
            f" * Step definitions for: {feature_name}",
            f" *",
            f" * Auto-generated by requirements_engineer pipeline.",
            f" * Each step throws until implemented.",
            f" */",
            f"package stepdefs;",
            f"",
            imports,
            f"",
            f"public class {class_name}Steps {{",
        ]

        seen = set()
        for kw, description in steps:
            key = f"{kw}:{description}"
            if key in seen:
                continue
            seen.add(key)
            desc_escaped = description.replace('"', '\\"')
            method = self._desc_to_java_method(kw, description)
            lines.append(f"")
            lines.append(f'    @{kw}("{desc_escaped}")')
            lines.append(f"    public void {method}() {{")
            lines.append(f'        // TODO: Implement')
            lines.append(f'        throw new UnsupportedOperationException("Not implemented");')
            lines.append(f"    }}")

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _desc_to_java_method(self, kw: str, description: str) -> str:
        """Convert step description to a Java method name (camelCase)."""
        slug = re.sub(r'[^a-zA-Z0-9]+', ' ', description).strip()
        words = slug.split()[:8]  # Limit length
        if not words:
            return f"{kw.lower()}Step"
        return words[0].lower() + ''.join(w.capitalize() for w in words[1:])

    def _generate_java_runner(self) -> str:
        """Generate Cucumber JUnit runner class."""
        return """/**
 * Cucumber test runner — entry point for BDD tests.
 *
 * Auto-generated by requirements_engineer pipeline.
 */
package stepdefs;

import org.junit.runner.RunWith;
import io.cucumber.junit.Cucumber;
import io.cucumber.junit.CucumberOptions;

@RunWith(Cucumber.class)
@CucumberOptions(
    features = "src/test/resources/features",
    glue = "stepdefs",
    plugin = {"pretty", "json:target/cucumber-report.json"}
)
public class CucumberTestRunner {
}
"""


# Test function
async def test_test_case_generator():
    """Test the TestCaseGenerator with sample data."""
    from .user_story_generator import UserStory, AcceptanceCriterion

    # Create sample user story
    user_story = UserStory(
        id="US-001",
        title="User Login",
        persona="registered customer",
        action="login with my email and password",
        benefit="I can access my account and order history",
        acceptance_criteria=[
            AcceptanceCriterion(
                given="I am on the login page",
                when="I enter valid credentials and click login",
                then="I am redirected to my dashboard"
            ),
            AcceptanceCriterion(
                given="I am on the login page",
                when="I enter invalid credentials",
                then="I see an error message"
            )
        ],
        priority="must",
        parent_requirement_id="REQ-001"
    )

    generator = TestCaseGenerator()
    await generator.initialize()

    print("=== Generating Gherkin Feature ===\n")
    feature = await generator.generate_gherkin(user_story)
    print(feature.to_gherkin())

    print("\n=== Generating Test Cases ===\n")
    test_cases = await generator.generate_test_cases(user_story)
    for tc in test_cases:
        print(tc.to_markdown())

    return generator


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_test_case_generator())
