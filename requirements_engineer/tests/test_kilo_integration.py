"""Test Kilo Agent Chat Integration."""

import sys
sys.path.insert(0, ".")

from requirements_engineer.dashboard.server import DashboardServer, create_dashboard_server
from requirements_engineer.dashboard.event_emitter import EventType, DashboardEventEmitter


def test_server_creation():
    """Test that the server can be created."""
    print("Test 1: Server Creation...")
    server = create_dashboard_server(port=8099, open_browser=False)
    assert server is not None, "Server should be created"
    print(f"  [OK] Server created: {type(server).__name__}")
    return True


def test_kilo_methods_exist():
    """Test that Kilo Agent methods exist on server."""
    print("Test 2: Kilo Methods Exist...")
    server = create_dashboard_server(port=8098, open_browser=False)

    methods = [
        '_handle_kilo_task',
        '_build_kilo_prompt',
        '_execute_kilo_agent',
        '_extract_mermaid',
        '_save_content'
    ]

    for method in methods:
        assert hasattr(server, method), f"Server should have {method} method"
        print(f"  [OK] {method} exists")

    return True


def test_mermaid_extraction():
    """Test Mermaid code extraction from response."""
    print("Test 3: Mermaid Extraction...")
    server = create_dashboard_server(port=8097, open_browser=False)

    # Test with standard mermaid block
    response1 = """
Here is the updated diagram:

```mermaid
flowchart TD
    A[Start] --> B[Process]
    B --> C[End]
```

This is the updated flow.
"""
    extracted = server._extract_mermaid(response1)
    assert extracted is not None, "Should extract mermaid from standard block"
    assert "flowchart TD" in extracted, "Should contain flowchart definition"
    print("  [OK] Standard mermaid block extracted")

    # Test with fallback pattern (no 'mermaid' keyword)
    response2 = """
```
sequenceDiagram
    Alice->>Bob: Hello
    Bob->>Alice: Hi
```
"""
    extracted2 = server._extract_mermaid(response2)
    assert extracted2 is not None, "Should extract with fallback pattern"
    assert "sequenceDiagram" in extracted2, "Should contain sequence diagram"
    print("  [OK] Fallback pattern extraction works")

    # Test with no mermaid
    response3 = "No diagram here, just text."
    extracted3 = server._extract_mermaid(response3)
    assert extracted3 is None, "Should return None when no mermaid found"
    print("  [OK] Returns None for non-mermaid content")

    return True


def test_kilo_prompt_building():
    """Test Kilo prompt building."""
    print("Test 4: Kilo Prompt Building...")
    server = create_dashboard_server(port=8096, open_browser=False)

    # Test diagram prompt
    content = "flowchart TD\n    A --> B"
    task = "Add an error handler"

    prompt = server._build_kilo_prompt(content, task, "diagram")
    assert "mermaid" in prompt.lower(), "Diagram prompt should mention mermaid"
    assert content in prompt, "Prompt should include original content"
    assert task in prompt, "Prompt should include task"
    print("  [OK] Diagram prompt built correctly")

    # Test generic prompt
    prompt2 = server._build_kilo_prompt("Some content", "Update it", "generic")
    assert "Some content" in prompt2, "Generic prompt should include content"
    assert "Update it" in prompt2, "Generic prompt should include task"
    print("  [OK] Generic prompt built correctly")

    return True


def test_event_types():
    """Test that all Kilo event types are defined."""
    print("Test 5: Kilo Event Types...")

    expected_events = [
        'KILO_TASK_REQUESTED',
        'KILO_TASK_PROCESSING',
        'KILO_TASK_COMPLETE',
        'KILO_TASK_ERROR',
        'DIAGRAM_UPDATED',
        'CONTENT_UPDATED'
    ]

    for event_name in expected_events:
        assert hasattr(EventType, event_name), f"EventType should have {event_name}"
        print(f"  [OK] EventType.{event_name} exists")

    return True


def test_emitter_methods():
    """Test that emitter has Kilo convenience methods."""
    print("Test 6: Emitter Kilo Methods...")

    emitter = DashboardEventEmitter()

    methods = [
        'kilo_task_processing',
        'kilo_task_complete',
        'kilo_task_error',
        'diagram_updated',
        'content_updated'
    ]

    for method in methods:
        assert hasattr(emitter, method), f"Emitter should have {method} method"
        print(f"  [OK] emitter.{method} exists")

    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Kilo Agent Chat Integration Tests")
    print("=" * 60 + "\n")

    tests = [
        test_server_creation,
        test_kilo_methods_exist,
        test_mermaid_extraction,
        test_kilo_prompt_building,
        test_event_types,
        test_emitter_methods,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"         {failed} test(s) FAILED")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
