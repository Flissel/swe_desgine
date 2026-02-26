"""
Timing Utilities for Training Data Collection.

Provides context managers for precise timing of:
- Stages (discovery, analysis, specification, validation, presentation)
- Steps within stages
- LLM calls
- Tool executions

Usage:
    from requirements_engineer.training.timing import time_stage, time_step, time_llm_call

    with time_stage("discovery", 1) as timing:
        # Stage code...
        with time_step("generate_drafts") as step_timing:
            # Step code...
    print(f"Stage took {timing.duration_ms}ms")
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, Generator, Callable, Any
from datetime import datetime

from .schemas import TimingInfo, CumulativeTiming


@dataclass
class TimingContext:
    """Context for tracking timing within a context manager."""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    stage: str = ""
    stage_number: int = 0
    step_name: str = ""
    timing_type: str = ""  # "stage", "step", "llm_call", "tool"

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000.0

    def to_timing_info(self) -> TimingInfo:
        """Convert to TimingInfo schema."""
        return TimingInfo(
            start_time=self.start_time,
            end_time=self.end_time,
            duration_ms=self.duration_ms,
            stage=self.stage,
            step_name=self.step_name
        )


# Global timing state for nested contexts
_timing_stack: list[TimingContext] = []
_cumulative_timings: dict[str, CumulativeTiming] = {}


def get_cumulative_timings() -> dict[str, CumulativeTiming]:
    """Get cumulative timing stats per stage."""
    return _cumulative_timings.copy()


def reset_cumulative_timings():
    """Reset cumulative timings (for testing)."""
    global _cumulative_timings
    _cumulative_timings = {}


@contextmanager
def time_stage(stage: str, stage_number: int) -> Generator[TimingContext, None, None]:
    """
    Context manager for timing a complete stage.

    Args:
        stage: Stage name (e.g., "discovery", "analysis")
        stage_number: Stage number (1-5)

    Yields:
        TimingContext with timing information

    Example:
        with time_stage("discovery", 1) as timing:
            run_discovery_stage()
        print(f"Discovery took {timing.duration_ms}ms")
    """
    ctx = TimingContext(
        start_time=time.time(),
        stage=stage,
        stage_number=stage_number,
        timing_type="stage"
    )
    _timing_stack.append(ctx)

    try:
        yield ctx
    finally:
        ctx.end_time = time.time()
        ctx.duration_ms = int((ctx.end_time - ctx.start_time) * 1000)
        _timing_stack.pop()

        # Update cumulative timings
        if stage not in _cumulative_timings:
            _cumulative_timings[stage] = CumulativeTiming()
        _cumulative_timings[stage].add_timing("stage", ctx.duration_ms)


@contextmanager
def time_step(step_name: str, stage: str = "") -> Generator[TimingContext, None, None]:
    """
    Context manager for timing a step within a stage.

    Args:
        step_name: Step name (e.g., "generate_drafts", "evaluate")
        stage: Optional stage name (inherits from parent if not provided)

    Yields:
        TimingContext with timing information

    Example:
        with time_step("generate_drafts", "discovery") as timing:
            generate_drafts()
        print(f"Step took {timing.duration_ms}ms")
    """
    # Inherit stage from parent context if not provided
    if not stage and _timing_stack:
        stage = _timing_stack[-1].stage

    ctx = TimingContext(
        start_time=time.time(),
        stage=stage,
        step_name=step_name,
        timing_type="step"
    )
    _timing_stack.append(ctx)

    try:
        yield ctx
    finally:
        ctx.end_time = time.time()
        ctx.duration_ms = int((ctx.end_time - ctx.start_time) * 1000)
        _timing_stack.pop()


@contextmanager
def time_llm_call(stage: str = "", component: str = "") -> Generator[TimingContext, None, None]:
    """
    Context manager for timing an LLM call.

    Args:
        stage: Stage name
        component: Component name (e.g., "draft_engine", "improver")

    Yields:
        TimingContext with timing information

    Example:
        with time_llm_call("discovery", "draft_engine") as timing:
            response = await llm.query(...)
        collector.record_llm_call(..., latency_ms=timing.duration_ms)
    """
    # Inherit from parent context if not provided
    if not stage and _timing_stack:
        stage = _timing_stack[-1].stage

    ctx = TimingContext(
        start_time=time.time(),
        stage=stage,
        step_name=component,
        timing_type="llm_call"
    )
    _timing_stack.append(ctx)

    try:
        yield ctx
    finally:
        ctx.end_time = time.time()
        ctx.duration_ms = int((ctx.end_time - ctx.start_time) * 1000)
        _timing_stack.pop()

        # Update cumulative timings
        if stage:
            if stage not in _cumulative_timings:
                _cumulative_timings[stage] = CumulativeTiming()
            _cumulative_timings[stage].add_timing("llm_call", ctx.duration_ms)


@contextmanager
def time_tool_execution(tool_name: str, stage: str = "") -> Generator[TimingContext, None, None]:
    """
    Context manager for timing a tool execution.

    Args:
        tool_name: Tool name (e.g., "generate_diagram", "python_exec")
        stage: Stage name

    Yields:
        TimingContext with timing information
    """
    if not stage and _timing_stack:
        stage = _timing_stack[-1].stage

    ctx = TimingContext(
        start_time=time.time(),
        stage=stage,
        step_name=tool_name,
        timing_type="tool"
    )
    _timing_stack.append(ctx)

    try:
        yield ctx
    finally:
        ctx.end_time = time.time()
        ctx.duration_ms = int((ctx.end_time - ctx.start_time) * 1000)
        _timing_stack.pop()

        # Update cumulative timings
        if stage:
            if stage not in _cumulative_timings:
                _cumulative_timings[stage] = CumulativeTiming()
            _cumulative_timings[stage].add_timing("tool_execution", ctx.duration_ms)


class Timer:
    """
    Reusable timer class for manual timing.

    Example:
        timer = Timer()
        timer.start()
        # do work
        timer.stop()
        print(f"Took {timer.duration_ms}ms")
    """

    def __init__(self):
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._running: bool = False

    def start(self) -> "Timer":
        """Start the timer."""
        self._start_time = time.time()
        self._running = True
        return self

    def stop(self) -> "Timer":
        """Stop the timer."""
        self._end_time = time.time()
        self._running = False
        return self

    def reset(self) -> "Timer":
        """Reset the timer."""
        self._start_time = 0.0
        self._end_time = 0.0
        self._running = False
        return self

    @property
    def duration_ms(self) -> int:
        """Get duration in milliseconds."""
        if self._running:
            return int((time.time() - self._start_time) * 1000)
        return int((self._end_time - self._start_time) * 1000)

    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return self.duration_ms / 1000.0

    @property
    def is_running(self) -> bool:
        """Check if timer is running."""
        return self._running

    def to_timing_info(self, stage: str = "", step_name: str = "") -> TimingInfo:
        """Convert to TimingInfo schema."""
        return TimingInfo(
            start_time=self._start_time,
            end_time=self._end_time,
            duration_ms=self.duration_ms,
            stage=stage,
            step_name=step_name
        )


def timed(stage: str = "", step_name: str = ""):
    """
    Decorator for timing function execution.

    Args:
        stage: Stage name
        step_name: Step name (defaults to function name)

    Example:
        @timed("discovery", "generate_drafts")
        def generate_drafts():
            # function code
            pass
    """
    def decorator(func: Callable) -> Callable:
        import functools

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = step_name or func.__name__
            with time_step(name, stage):
                return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = step_name or func.__name__
            with time_step(name, stage):
                return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_current_stage() -> Optional[str]:
    """Get the current stage from the timing stack."""
    for ctx in reversed(_timing_stack):
        if ctx.stage:
            return ctx.stage
    return None


def get_current_timing_context() -> Optional[TimingContext]:
    """Get the current timing context."""
    return _timing_stack[-1] if _timing_stack else None
