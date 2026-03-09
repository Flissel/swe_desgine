"""
Training Data Collection Module for AI-Scientist-v2.

Provides structured collection of:
- LLM calls with full conversation context
- Tool calls with arguments and results
- Error contexts with stack traces
- Timing information for all operations
- Export to OpenAI Fine-Tuning format (JSONL)

Usage:
    from requirements_engineer.training import TrainingDataCollector, get_live_logger

    collector = TrainingDataCollector.get_instance()
    collector.start_run(project_id, project_name, config)

    with collector.time_stage("discovery", 1):
        # Stage code...
        collector.record_llm_call(...)

    collector.end_run()
"""

from .schemas import (
    TimingInfo,
    CumulativeTiming,
    ToolCallRecord,
    ErrorContext,
    LLMCallRecord,
    TrainingSample,
    RunRecord,
    StageEvaluationResult,
)
from .collector import TrainingDataCollector
from .live_logger import LiveLogger, EventType, get_live_logger
from .timing import time_stage, time_step, time_llm_call, TimingContext

__all__ = [
    # Schemas
    "TimingInfo",
    "CumulativeTiming",
    "ToolCallRecord",
    "ErrorContext",
    "LLMCallRecord",
    "TrainingSample",
    "RunRecord",
    "StageEvaluationResult",
    # Collector
    "TrainingDataCollector",
    # Live Logger
    "LiveLogger",
    "EventType",
    "get_live_logger",
    # Timing
    "time_stage",
    "time_step",
    "time_llm_call",
    "TimingContext",
]
