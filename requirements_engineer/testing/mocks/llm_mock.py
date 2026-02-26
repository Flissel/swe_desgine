"""
LLM Mock utilities for testing.

Provides mock responses for LLM calls to enable testing
without real API calls.

Usage:
    from requirements_engineer.testing.mocks import setup_llm_mock

    setup_llm_mock("path/to/mock_responses")

    # LLM calls will now return mock responses
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock
import logging

logger = logging.getLogger(__name__)

# Global mock state
_mock_responses: Dict[str, Any] = {}
_mock_enabled: bool = False
_call_history: List[Dict[str, Any]] = []


@dataclass
class MockLLMResponse:
    """Mock LLM response structure."""
    content: str = ""
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Token counts
    prompt_tokens: int = 100
    completion_tokens: int = 50
    total_tokens: int = 150

    # Timing
    latency_ms: int = 500

    def to_openai_format(self) -> MagicMock:
        """Convert to OpenAI API response format."""
        message = MagicMock()
        message.content = self.content
        message.tool_calls = [
            self._create_tool_call(tc) for tc in self.tool_calls
        ] if self.tool_calls else None

        choice = MagicMock()
        choice.message = message

        usage = MagicMock()
        usage.prompt_tokens = self.prompt_tokens
        usage.completion_tokens = self.completion_tokens
        usage.total_tokens = self.total_tokens

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage

        return response

    def _create_tool_call(self, tc: Dict[str, Any]) -> MagicMock:
        """Create mock tool call object."""
        function = MagicMock()
        function.name = tc.get("name", "")
        function.arguments = json.dumps(tc.get("arguments", {}))

        tool_call = MagicMock()
        tool_call.id = tc.get("id", "call_mock123")
        tool_call.type = "function"
        tool_call.function = function

        return tool_call


def setup_llm_mock(responses_path: Optional[str] = None):
    """
    Setup LLM mocking.

    Args:
        responses_path: Path to directory with mock response JSON files
    """
    global _mock_enabled, _mock_responses

    _mock_enabled = True
    _mock_responses.clear()
    _call_history.clear()

    if responses_path:
        load_mock_responses(responses_path)

    # Patch the query function
    _apply_patches()


def load_mock_responses(path: str):
    """Load mock responses from JSON files."""
    global _mock_responses

    path = Path(path)
    if not path.exists():
        logger.warning(f"Mock responses path does not exist: {path}")
        return

    for file in path.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = file.stem
                _mock_responses[key] = data
                logger.debug(f"Loaded mock response: {key}")
        except Exception as e:
            logger.error(f"Failed to load mock response {file}: {e}")


def get_mock_response(
    prompt_key: Optional[str] = None,
    stage: str = "",
    component: str = ""
) -> MockLLMResponse:
    """
    Get a mock response for a given context.

    Args:
        prompt_key: Specific key to look up
        stage: Stage name for context-based lookup
        component: Component name for context-based lookup

    Returns:
        MockLLMResponse
    """
    # Try specific key first
    if prompt_key and prompt_key in _mock_responses:
        data = _mock_responses[prompt_key]
        return MockLLMResponse(**data)

    # Try stage-based key
    stage_key = f"{stage}_{component}" if component else stage
    if stage_key in _mock_responses:
        data = _mock_responses[stage_key]
        return MockLLMResponse(**data)

    # Default response
    return _get_default_response(stage, component)


def _get_default_response(stage: str, component: str) -> MockLLMResponse:
    """Get default mock response based on stage."""
    defaults = {
        "discovery": MockLLMResponse(
            content=json.dumps([
                {
                    "title": "Mock Requirement 1",
                    "description": "This is a mock requirement",
                    "type": "functional",
                    "priority": "must"
                }
            ]),
            prompt_tokens=200,
            completion_tokens=100
        ),
        "analysis": MockLLMResponse(
            content=json.dumps({
                "classification": "functional",
                "priority": "must",
                "dependencies": [],
                "confidence": 0.9
            }),
            prompt_tokens=250,
            completion_tokens=80
        ),
        "specification": MockLLMResponse(
            content=json.dumps({
                "acceptance_criteria": ["Given X, when Y, then Z"],
                "diagrams": {"flowchart": "graph TD\n    A-->B"},
                "work_package": "Feature"
            }),
            prompt_tokens=300,
            completion_tokens=150
        ),
        "validation": MockLLMResponse(
            content=json.dumps({
                "is_valid": True,
                "quality_scores": {
                    "completeness": 0.85,
                    "consistency": 0.90
                },
                "issues": []
            }),
            prompt_tokens=350,
            completion_tokens=100
        ),
        "presentation": MockLLMResponse(
            content="<html><head><title>Mock Page</title></head><body><h1>Requirements</h1></body></html>",
            prompt_tokens=400,
            completion_tokens=200
        )
    }

    return defaults.get(stage, MockLLMResponse(content="Mock response"))


def _apply_patches():
    """Apply mock patches to LLM query functions."""
    # This is called during test setup
    # Actual patching is done via pytest fixtures
    pass


def record_call(
    system_message: str,
    user_message: str,
    model: str,
    stage: str = "",
    component: str = ""
):
    """Record a mock LLM call for inspection."""
    _call_history.append({
        "system_message": system_message[:200],  # Truncate
        "user_message": user_message[:200],
        "model": model,
        "stage": stage,
        "component": component
    })


def get_call_history() -> List[Dict[str, Any]]:
    """Get the call history."""
    return _call_history.copy()


def clear_call_history():
    """Clear the call history."""
    _call_history.clear()


def is_mock_enabled() -> bool:
    """Check if mocking is enabled."""
    return _mock_enabled


def disable_mock():
    """Disable mocking."""
    global _mock_enabled
    _mock_enabled = False


# Context manager for temporary mocking
class mock_llm:
    """Context manager for LLM mocking."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self.responses = responses or {}
        self._original_enabled = False

    def __enter__(self):
        global _mock_enabled, _mock_responses
        self._original_enabled = _mock_enabled
        _mock_enabled = True
        if self.responses:
            _mock_responses.update(self.responses)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _mock_enabled
        _mock_enabled = self._original_enabled
        clear_call_history()
        return False
