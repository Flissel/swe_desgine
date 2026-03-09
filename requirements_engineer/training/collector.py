"""
Training Data Collector for AI-Scientist-v2.

Unified collector for all training data:
- LLM calls with full conversation context
- Tool calls with arguments and results
- Error contexts with stack traces
- Timing information
- Export to OpenAI Fine-Tuning format

Usage:
    from requirements_engineer.training import TrainingDataCollector

    collector = TrainingDataCollector.get_instance()
    run_id = collector.start_run(project_id, project_name, config)

    with collector.time_stage("discovery", 1):
        collector.record_llm_call(...)

    collector.end_run(status="completed")
"""

import json
import time
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from dataclasses import asdict
from typing import Optional, Dict, Any, List, Generator

from .schemas import (
    TrainingSample,
    LLMCallRecord,
    ToolCallRecord,
    ErrorContext,
    CumulativeTiming,
    RunRecord,
    calculate_cost,
)
from .live_logger import LiveLogger, EventType, get_live_logger


class TrainingDataCollector:
    """
    Unified collector for ALL training data.

    Singleton pattern - one instance per run.
    Thread-safe for parallel processing.
    """

    _instance: Optional['TrainingDataCollector'] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize TrainingDataCollector.

        Args:
            config: Configuration dict with output_dir, etc.
        """
        self.config = config or {}
        self.run_record: Optional[RunRecord] = None

        # Storage
        self._llm_calls: List[LLMCallRecord] = []
        self._tool_calls: List[ToolCallRecord] = []
        self._errors: List[ErrorContext] = []
        self._samples: List[TrainingSample] = []

        # Timing
        self._stage_timings: Dict[str, CumulativeTiming] = {}
        self._active_timers: Dict[str, float] = {}
        self._last_llm_duration_ms: int = 0

        # Live Logger
        self.live_logger = get_live_logger()

        # Output
        self.output_dir = Path(self.config.get("output_dir", "training_data"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._data_lock = threading.Lock()

        # Auto-create samples
        self.auto_create_samples = self.config.get("auto_create_samples", True)

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> 'TrainingDataCollector':
        """Get singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
            return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # =========================================================================
    # RUN MANAGEMENT
    # =========================================================================

    def start_run(
        self,
        project_id: str,
        project_name: str,
        config: Dict[str, Any]
    ) -> str:
        """
        Start a new run.

        Args:
            project_id: Project identifier
            project_name: Project name
            config: Configuration dict

        Returns:
            Run ID
        """
        config_hash = hashlib.md5(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]

        self.run_record = RunRecord(
            project_id=project_id,
            project_name=project_name,
            config_hash=config_hash,
            config_snapshot=config
        )

        # Clear previous data
        self._llm_calls.clear()
        self._tool_calls.clear()
        self._errors.clear()
        self._samples.clear()
        self._stage_timings.clear()

        self.live_logger.log_run_started(
            self.run_record.run_id,
            project_name
        )

        return self.run_record.run_id

    def end_run(
        self,
        status: str = "completed",
        error: Optional[ErrorContext] = None
    ):
        """
        End the current run and export data.

        Args:
            status: Run status ("completed", "failed", "cancelled")
            error: Optional error context if failed
        """
        if not self.run_record:
            return

        self.run_record.ended_at = datetime.now().isoformat()
        self.run_record.status = status
        self.run_record.error = error

        # Aggregate metrics
        self._aggregate_run_metrics()

        # Export data
        self._export_run()

        self.live_logger.log_run_completed(
            self.run_record.run_id,
            status,
            len(self._samples)
        )

    # =========================================================================
    # TIMING CONTEXT MANAGERS
    # =========================================================================

    @contextmanager
    def time_stage(
        self,
        stage: str,
        stage_number: int
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Context manager for stage timing.

        Args:
            stage: Stage name
            stage_number: Stage number (1-5)

        Yields:
            Dict with timing info
        """
        start = time.time()
        timer_key = f"stage_{stage_number}_{stage}"
        self._active_timers[timer_key] = start

        context = {
            "stage": stage,
            "stage_number": stage_number,
            "start_time": start
        }

        self.live_logger.log_stage_started(stage, stage_number)

        if self.run_record:
            self.run_record.current_stage = stage_number

        try:
            yield context
        finally:
            duration_ms = int((time.time() - start) * 1000)
            context["duration_ms"] = duration_ms

            if stage not in self._stage_timings:
                self._stage_timings[stage] = CumulativeTiming()
            self._stage_timings[stage].total_ms += duration_ms

            if self.run_record:
                self.run_record.stage_timings[stage] = self._stage_timings[stage]
                if stage_number not in self.run_record.stages_completed:
                    self.run_record.stages_completed.append(stage_number)

            self.live_logger.log_stage_completed(stage, stage_number, duration_ms)

            del self._active_timers[timer_key]

    @contextmanager
    def time_step(
        self,
        step_name: str,
        stage: str = ""
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Context manager for step timing.

        Args:
            step_name: Step name
            stage: Stage name (optional)

        Yields:
            Dict with timing info
        """
        start = time.time()
        context = {
            "step_name": step_name,
            "stage": stage,
            "start_time": start
        }

        try:
            yield context
        finally:
            duration_ms = int((time.time() - start) * 1000)
            context["duration_ms"] = duration_ms

    @contextmanager
    def time_llm_call(self) -> Generator[Dict[str, Any], None, None]:
        """
        Context manager for LLM call timing.

        Yields:
            Dict with timing info
        """
        start = time.time()
        context = {"start_time": start}

        try:
            yield context
        finally:
            duration_ms = int((time.time() - start) * 1000)
            context["duration_ms"] = duration_ms
            self._last_llm_duration_ms = duration_ms

    # =========================================================================
    # LLM CALL RECORDING
    # =========================================================================

    def record_llm_call(
        self,
        system_message: str = "",
        user_message: str = "",
        response: str = "",
        model: str = "",
        stage: str = "",
        stage_number: int = 0,
        iteration: int = 0,
        component: str = "",
        node_id: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        temperature: float = 0.7,
        max_tokens: int = 0,
        tool_calls: Optional[List[ToolCallRecord]] = None,
        function_spec: Optional[Dict[str, Any]] = None,
        function_result: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error: Optional[ErrorContext] = None,
        quality_score: Optional[float] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> LLMCallRecord:
        """
        Record an LLM call with all details.

        Returns:
            The created LLMCallRecord
        """
        # Use timing from context manager if not provided
        if latency_ms == 0 and self._last_llm_duration_ms > 0:
            latency_ms = self._last_llm_duration_ms
            self._last_llm_duration_ms = 0

        # Calculate cost if not provided
        if cost_usd == 0.0 and model and (input_tokens or output_tokens):
            cost_usd = calculate_cost(model, input_tokens, output_tokens)

        record = LLMCallRecord(
            system_message=system_message,
            user_message=user_message,
            assistant_response=response,
            model=model,
            model_provider=self._detect_provider(model),
            temperature=temperature,
            max_tokens=max_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            stage=stage,
            stage_number=stage_number,
            iteration=iteration,
            component=component,
            node_id=node_id,
            tool_calls=tool_calls or [],
            has_tool_calls=bool(tool_calls),
            function_spec=function_spec,
            function_result=function_result,
            success=success,
            error=error,
            quality_score=quality_score,
            conversation_history=conversation_history or []
        )

        with self._data_lock:
            self._llm_calls.append(record)

            # Update run record
            if self.run_record:
                self.run_record.total_llm_calls += 1
                self.run_record.total_tokens += record.total_tokens
                self.run_record.total_cost_usd += record.cost_usd

            # Update stage timing
            if stage and stage in self._stage_timings:
                self._stage_timings[stage].add_timing("llm_call", latency_ms)

        # Live log
        self.live_logger.log_llm_call(
            model=model,
            tokens=record.total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            stage=stage,
            component=component
        )

        # Auto-create training sample
        if self.auto_create_samples and success:
            self._create_training_sample(record)

        return record

    # =========================================================================
    # TOOL CALL RECORDING
    # =========================================================================

    def record_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any = None,
        success: bool = True,
        error: Optional[str] = None,
        duration_ms: int = 0,
        parent_llm_call_id: str = "",
        tool_type: str = "function",
        stage: str = "",
        component: str = ""
    ) -> ToolCallRecord:
        """
        Record a tool/function call.

        Returns:
            The created ToolCallRecord
        """
        record = ToolCallRecord(
            tool_name=tool_name,
            tool_type=tool_type,
            arguments=arguments,
            arguments_raw=json.dumps(arguments, default=str),
            result=result,
            result_raw=json.dumps(result, default=str) if result else "",
            success=success,
            error=error,
            duration_ms=duration_ms,
            parent_llm_call_id=parent_llm_call_id,
            stage=stage,
            component=component
        )

        with self._data_lock:
            self._tool_calls.append(record)

            if self.run_record:
                self.run_record.total_tool_calls += 1

            # Update stage timing
            if stage and stage in self._stage_timings:
                self._stage_timings[stage].add_timing("tool_execution", duration_ms)

        self.live_logger.log_tool_call(
            tool_name=tool_name,
            success=success,
            duration_ms=duration_ms,
            stage=stage
        )

        return record

    # =========================================================================
    # ERROR RECORDING
    # =========================================================================

    def record_error(
        self,
        error_type: str,
        exception: Exception,
        input_text: str = "",
        stage: str = "",
        step: str = "",
        component: str = "",
        retry_count: int = 0,
        was_recovered: bool = False,
        recovery_strategy: str = ""
    ) -> ErrorContext:
        """
        Record an error with full context.

        Returns:
            The created ErrorContext
        """
        record = ErrorContext.from_exception(
            exception=exception,
            error_type=error_type,
            input_text=input_text,
            stage=stage,
            step=step,
            component=component
        )
        record.retry_count = retry_count
        record.was_recovered = was_recovered
        record.recovery_strategy = recovery_strategy

        with self._data_lock:
            self._errors.append(record)

            if self.run_record:
                self.run_record.total_errors += 1

        self.live_logger.log_error(
            error_type=error_type,
            message=str(exception),
            stage=stage,
            recovered=was_recovered
        )

        return record

    # =========================================================================
    # TRAINING SAMPLE CREATION
    # =========================================================================

    def _create_training_sample(self, llm_call: LLMCallRecord) -> TrainingSample:
        """Create a training sample from an LLM call."""
        messages = []

        # System message
        if llm_call.system_message:
            messages.append({
                "role": "system",
                "content": llm_call.system_message
            })

        # Conversation history
        for msg in llm_call.conversation_history:
            messages.append(msg)

        # User message
        if llm_call.user_message:
            messages.append({
                "role": "user",
                "content": llm_call.user_message
            })

        # Assistant response
        if llm_call.assistant_response:
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": llm_call.assistant_response
            }

            # Add tool calls if present
            if llm_call.has_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": tc.arguments_raw
                        }
                    }
                    for tc in llm_call.tool_calls
                ]

            messages.append(assistant_msg)

        # Tool responses
        for tc in llm_call.tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tc.result_raw
            })

        # Tools definition
        tools = []
        if llm_call.function_spec:
            tools.append({
                "type": "function",
                "function": llm_call.function_spec
            })

        # Quality tags
        quality_tags = [f"stage_{llm_call.stage_number}_{llm_call.stage}"]
        if llm_call.has_tool_calls:
            quality_tags.append("includes_tool_calls")
        if llm_call.quality_score and llm_call.quality_score >= 0.8:
            quality_tags.append("high_quality")

        sample = TrainingSample(
            messages=messages,
            tools=tools if tools else [],
            metadata={
                "stage": llm_call.stage,
                "stage_number": llm_call.stage_number,
                "iteration": llm_call.iteration,
                "component": llm_call.component,
                "model": llm_call.model,
                "node_id": llm_call.node_id,
                "llm_call_id": llm_call.id
            },
            quality_score=llm_call.quality_score or 0.0,
            quality_tags=quality_tags,
            total_duration_ms=llm_call.latency_ms,
            total_cost_usd=llm_call.cost_usd
        )

        with self._data_lock:
            self._samples.append(sample)
            if self.run_record:
                self.run_record.training_samples.append(sample.id)
                self.run_record.sample_count = len(self._samples)

        self.live_logger.log_sample_created(
            sample.id,
            llm_call.stage,
            sample.quality_score
        )

        return sample

    def create_sample_manually(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        quality_score: float = 0.0,
        quality_tags: Optional[List[str]] = None
    ) -> TrainingSample:
        """Create a training sample manually."""
        sample = TrainingSample(
            messages=messages,
            tools=tools or [],
            metadata=metadata or {},
            quality_score=quality_score,
            quality_tags=quality_tags or []
        )

        with self._data_lock:
            self._samples.append(sample)
            if self.run_record:
                self.run_record.training_samples.append(sample.id)
                self.run_record.sample_count = len(self._samples)

        return sample

    # =========================================================================
    # EXPORT
    # =========================================================================

    def _export_run(self):
        """Export all data for the current run."""
        if not self.run_record:
            return

        run_dir = self.output_dir / self.run_record.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Run record
        with open(run_dir / "run_record.json", "w", encoding="utf-8") as f:
            json.dump(asdict(self.run_record), f, indent=2, default=str)

        # LLM calls (JSONL)
        with open(run_dir / "llm_calls.jsonl", "w", encoding="utf-8") as f:
            for call in self._llm_calls:
                f.write(json.dumps(asdict(call), default=str) + "\n")

        # Tool calls (JSONL)
        with open(run_dir / "tool_calls.jsonl", "w", encoding="utf-8") as f:
            for call in self._tool_calls:
                f.write(json.dumps(asdict(call), default=str) + "\n")

        # Errors (JSONL)
        with open(run_dir / "errors.jsonl", "w", encoding="utf-8") as f:
            for error in self._errors:
                f.write(json.dumps(asdict(error), default=str) + "\n")

        # Training samples - OpenAI format (JSONL)
        with open(run_dir / "training_samples.jsonl", "w", encoding="utf-8") as f:
            for sample in self._samples:
                if sample.is_valid:
                    f.write(json.dumps(sample.to_openai_format(), default=str) + "\n")

        # Training samples - Full format with metadata (JSONL)
        with open(run_dir / "training_samples_full.jsonl", "w", encoding="utf-8") as f:
            for sample in self._samples:
                f.write(json.dumps(sample.to_full_format(), default=str) + "\n")

        self.live_logger.emit(EventType.EXPORT_COMPLETED, {
            "run_id": self.run_record.run_id,
            "output_dir": str(run_dir),
            "sample_count": len(self._samples),
            "llm_call_count": len(self._llm_calls)
        })

    def export_filtered_samples(
        self,
        output_path: str,
        min_quality: float = 0.0,
        stages: Optional[List[int]] = None,
        include_tool_calls: Optional[bool] = None,
        max_samples: Optional[int] = None,
        format: str = "openai"
    ) -> int:
        """
        Export filtered samples to a file.

        Args:
            output_path: Output file path
            min_quality: Minimum quality score filter
            stages: Stage number filter
            include_tool_calls: Filter for tool calls presence
            max_samples: Maximum samples to export
            format: Export format ("openai" or "full")

        Returns:
            Number of samples exported
        """
        filtered = self._samples.copy()

        if min_quality > 0:
            filtered = [s for s in filtered if s.quality_score >= min_quality]

        if stages:
            filtered = [
                s for s in filtered
                if s.metadata.get("stage_number") in stages
            ]

        if include_tool_calls is not None:
            if include_tool_calls:
                filtered = [s for s in filtered if "includes_tool_calls" in s.quality_tags]
            else:
                filtered = [s for s in filtered if "includes_tool_calls" not in s.quality_tags]

        if max_samples:
            filtered = filtered[:max_samples]

        with open(output_path, "w", encoding="utf-8") as f:
            for sample in filtered:
                if format == "openai":
                    f.write(json.dumps(sample.to_openai_format(), default=str) + "\n")
                else:
                    f.write(json.dumps(sample.to_full_format(), default=str) + "\n")

        return len(filtered)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _detect_provider(self, model: str) -> str:
        """Detect provider from model string."""
        if model.startswith("openrouter/"):
            return "openrouter"
        elif model.startswith("ollama/"):
            return "ollama"
        elif "claude" in model.lower():
            return "anthropic"
        elif "gpt" in model.lower() or "o1" in model.lower() or "o3" in model.lower():
            return "openai"
        elif "gemini" in model.lower():
            return "google"
        return "unknown"

    def _aggregate_run_metrics(self):
        """Aggregate metrics for the run."""
        if not self.run_record:
            return

        # Total duration
        self.run_record.total_duration_ms = self.run_record.calculate_duration()

        # Sample count
        self.run_record.sample_count = len(self._samples)

        # Average quality
        if self._samples:
            valid_scores = [s.quality_score for s in self._samples if s.quality_score > 0]
            if valid_scores:
                self.run_record.final_quality_score = sum(valid_scores) / len(valid_scores)

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics for the current session."""
        return {
            "llm_calls": len(self._llm_calls),
            "tool_calls": len(self._tool_calls),
            "errors": len(self._errors),
            "samples": len(self._samples),
            "total_tokens": sum(c.total_tokens for c in self._llm_calls),
            "total_cost_usd": sum(c.cost_usd for c in self._llm_calls),
            "avg_latency_ms": (
                sum(c.latency_ms for c in self._llm_calls) / len(self._llm_calls)
                if self._llm_calls else 0
            ),
            "stage_timings": {
                stage: asdict(timing)
                for stage, timing in self._stage_timings.items()
            },
            "samples_by_stage": self._get_samples_by_stage(),
            "errors_by_type": self._get_errors_by_type()
        }

    def _get_samples_by_stage(self) -> Dict[str, int]:
        """Get sample counts by stage."""
        counts: Dict[str, int] = {}
        for sample in self._samples:
            stage = sample.metadata.get("stage", "unknown")
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def _get_errors_by_type(self) -> Dict[str, int]:
        """Get error counts by type."""
        counts: Dict[str, int] = {}
        for error in self._errors:
            counts[error.error_type] = counts.get(error.error_type, 0) + 1
        return counts

    def print_summary(self):
        """Print a summary of the current session."""
        stats = self.get_statistics()

        print("\n" + "=" * 70)
        print("TRAINING DATA COLLECTION SUMMARY")
        print("=" * 70)
        print(f"LLM Calls:      {stats['llm_calls']}")
        print(f"Tool Calls:     {stats['tool_calls']}")
        print(f"Errors:         {stats['errors']}")
        print(f"Samples:        {stats['samples']}")
        print(f"Total Tokens:   {stats['total_tokens']:,}")
        print(f"Total Cost:     ${stats['total_cost_usd']:.4f} USD")
        print(f"Avg Latency:    {stats['avg_latency_ms']:.0f}ms")
        print("-" * 70)
        print("SAMPLES BY STAGE:")
        for stage, count in stats["samples_by_stage"].items():
            print(f"  {stage}: {count}")
        if stats["errors_by_type"]:
            print("-" * 70)
            print("ERRORS BY TYPE:")
            for error_type, count in stats["errors_by_type"].items():
                print(f"  {error_type}: {count}")
        print("=" * 70)
