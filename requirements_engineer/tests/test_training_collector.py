"""
Unit Tests for Training Data Collector.

Tests:
- TrainingDataCollector initialization and singleton
- LLM call recording
- Tool call recording
- Error recording
- Training sample creation
- Export functionality
- Timing utilities
"""

import pytest
import json
import time
from pathlib import Path

from requirements_engineer.training.collector import TrainingDataCollector
from requirements_engineer.training.schemas import (
    TrainingSample,
    LLMCallRecord,
    ToolCallRecord,
    ErrorContext,
    TimingInfo,
    RunRecord,
    calculate_cost,
)
from requirements_engineer.training.live_logger import LiveLogger, EventType, reset_live_logger
from requirements_engineer.training.timing import (
    time_stage,
    time_step,
    time_llm_call,
    Timer,
    get_cumulative_timings,
    reset_cumulative_timings,
)


class TestTrainingDataCollector:
    """Tests for TrainingDataCollector."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Setup before each test."""
        TrainingDataCollector.reset()
        reset_live_logger()
        reset_cumulative_timings()
        self.output_dir = tmp_path / "training_data"

    def test_singleton_pattern(self):
        """Test singleton pattern works correctly."""
        collector1 = TrainingDataCollector.get_instance()
        collector2 = TrainingDataCollector.get_instance()
        assert collector1 is collector2

    def test_reset_singleton(self):
        """Test singleton reset."""
        collector1 = TrainingDataCollector.get_instance()
        TrainingDataCollector.reset()
        collector2 = TrainingDataCollector.get_instance()
        assert collector1 is not collector2

    def test_start_run(self):
        """Test starting a run."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        run_id = collector.start_run(
            project_id="test_project",
            project_name="Test Project",
            config={"model": "gpt-4o"}
        )

        assert run_id is not None
        assert collector.run_record is not None
        assert collector.run_record.project_id == "test_project"
        assert collector.run_record.project_name == "Test Project"

    def test_record_llm_call(self):
        """Test recording LLM calls."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        collector.start_run("test", "Test", {})

        record = collector.record_llm_call(
            system_message="You are a helpful assistant",
            user_message="Hello",
            response="Hi there!",
            model="gpt-4o",
            stage="discovery",
            stage_number=1,
            input_tokens=10,
            output_tokens=5,
            latency_ms=500
        )

        assert record is not None
        assert record.system_message == "You are a helpful assistant"
        assert record.model == "gpt-4o"
        assert record.total_tokens == 15
        assert len(collector._llm_calls) == 1

    def test_record_tool_call(self):
        """Test recording tool calls."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        collector.start_run("test", "Test", {})

        record = collector.record_tool_call(
            tool_name="generate_diagram",
            arguments={"type": "flowchart"},
            result="graph TD\n    A-->B",
            success=True,
            duration_ms=100
        )

        assert record is not None
        assert record.tool_name == "generate_diagram"
        assert record.success is True
        assert len(collector._tool_calls) == 1

    def test_record_error(self):
        """Test recording errors."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        collector.start_run("test", "Test", {})

        try:
            raise ValueError("Test error")
        except Exception as e:
            record = collector.record_error(
                error_type="validation",
                exception=e,
                stage="discovery",
                input_text="test input"
            )

        assert record is not None
        assert record.error_type == "validation"
        assert record.exception_class == "ValueError"
        assert len(collector._errors) == 1

    def test_training_sample_creation(self):
        """Test automatic training sample creation."""
        collector = TrainingDataCollector.get_instance({
            "output_dir": str(self.output_dir),
            "auto_create_samples": True
        })
        collector.start_run("test", "Test", {})

        collector.record_llm_call(
            system_message="System prompt",
            user_message="User message",
            response="Assistant response",
            model="gpt-4o",
            stage="discovery",
            stage_number=1
        )

        assert len(collector._samples) == 1
        sample = collector._samples[0]
        assert len(sample.messages) == 3
        assert sample.messages[0]["role"] == "system"
        assert sample.messages[1]["role"] == "user"
        assert sample.messages[2]["role"] == "assistant"

    def test_export_run(self):
        """Test exporting run data."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        run_id = collector.start_run("test", "Test", {"model": "gpt-4o"})

        collector.record_llm_call(
            system_message="Test",
            user_message="Hello",
            response="Hi",
            model="gpt-4o",
            stage="discovery",
            stage_number=1
        )

        collector.end_run(status="completed")

        # Check export files exist
        run_dir = self.output_dir / run_id
        assert (run_dir / "run_record.json").exists()
        assert (run_dir / "llm_calls.jsonl").exists()
        assert (run_dir / "training_samples.jsonl").exists()

    def test_statistics(self):
        """Test statistics collection."""
        collector = TrainingDataCollector.get_instance({"output_dir": str(self.output_dir)})
        collector.start_run("test", "Test", {})

        for i in range(3):
            collector.record_llm_call(
                system_message="Test",
                user_message=f"Message {i}",
                response=f"Response {i}",
                model="gpt-4o",
                input_tokens=10,
                output_tokens=5
            )

        stats = collector.get_statistics()
        assert stats["llm_calls"] == 3
        assert stats["total_tokens"] == 45


class TestTimingUtilities:
    """Tests for timing utilities."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_cumulative_timings()

    def test_time_stage(self):
        """Test stage timing context manager."""
        with time_stage("discovery", 1) as ctx:
            time.sleep(0.01)

        assert ctx.duration_ms > 0
        assert ctx.stage == "discovery"
        timings = get_cumulative_timings()
        assert "discovery" in timings

    def test_time_step(self):
        """Test step timing context manager."""
        with time_step("generate_drafts", "discovery") as ctx:
            time.sleep(0.01)

        assert ctx.duration_ms > 0
        assert ctx.step_name == "generate_drafts"

    def test_timer_class(self):
        """Test Timer class."""
        timer = Timer()
        timer.start()
        time.sleep(0.01)
        timer.stop()

        assert timer.duration_ms > 0
        assert not timer.is_running

    def test_nested_timing(self):
        """Test nested timing contexts."""
        with time_stage("discovery", 1) as stage_ctx:
            with time_step("step1") as step1_ctx:
                time.sleep(0.005)
            with time_step("step2") as step2_ctx:
                time.sleep(0.005)

        assert stage_ctx.duration_ms >= step1_ctx.duration_ms + step2_ctx.duration_ms


class TestSchemas:
    """Tests for data schemas."""

    def test_timing_info_create(self):
        """Test TimingInfo creation."""
        start = time.time()
        end = start + 1.5
        timing = TimingInfo.create(start, end, "discovery", "generate")

        assert timing.duration_ms == 1500
        assert timing.duration_seconds == 1.5

    def test_error_context_from_exception(self):
        """Test ErrorContext creation from exception."""
        try:
            raise ValueError("Test error message")
        except Exception as e:
            error = ErrorContext.from_exception(
                exception=e,
                error_type="validation",
                stage="discovery"
            )

        assert error.exception_class == "ValueError"
        assert error.exception_message == "Test error message"
        assert len(error.stack_trace) > 0

    def test_training_sample_to_openai_format(self):
        """Test TrainingSample OpenAI format conversion."""
        sample = TrainingSample(
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"}
            ]
        )

        openai_format = sample.to_openai_format()
        assert "messages" in openai_format
        assert len(openai_format["messages"]) == 3

    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = calculate_cost("openai/gpt-4o", 1000, 500)
        assert cost > 0
        assert isinstance(cost, float)


class TestLiveLogger:
    """Tests for live logger."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_live_logger()

    def test_emit_event(self):
        """Test event emission."""
        logger = LiveLogger()
        events = []
        logger.add_observer(lambda e: events.append(e))

        logger.emit(EventType.LLM_CALL, {"model": "gpt-4o"})

        assert len(events) == 1
        assert events[0].type == EventType.LLM_CALL

    def test_event_history(self):
        """Test event history."""
        logger = LiveLogger(max_history=10)

        for i in range(5):
            logger.emit(EventType.PROGRESS, {"step": i})

        history = logger.get_history()
        assert len(history) == 5

    def test_event_filtering(self):
        """Test event filtering by type."""
        logger = LiveLogger()

        logger.emit(EventType.LLM_CALL, {"id": 1})
        logger.emit(EventType.TOOL_CALL, {"id": 2})
        logger.emit(EventType.LLM_CALL, {"id": 3})

        history = logger.get_history(event_type=EventType.LLM_CALL)
        assert len(history) == 2

    def test_convenience_methods(self):
        """Test convenience logging methods."""
        logger = LiveLogger()
        events = []
        logger.add_observer(lambda e: events.append(e))

        logger.log_llm_call("gpt-4o", 100, 0.01, 500)
        logger.log_error("validation", "Test error")
        logger.log_progress("Processing", 50)

        assert len(events) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
