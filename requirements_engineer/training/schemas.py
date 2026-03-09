"""
Training Data Schemas for AI-Scientist-v2.

All dataclasses for structured training data collection:
- TimingInfo: Time measurements for each step
- ToolCallRecord: Tool/function call records
- ErrorContext: Detailed error context for debugging
- LLMCallRecord: Full LLM call records with conversation
- TrainingSample: OpenAI Fine-Tuning format
- RunRecord: Complete pipeline run record
- StageEvaluationResult: Test result per stage
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import uuid

try:
    from dataclasses_json import DataClassJsonMixin
except ImportError:
    # Fallback if dataclasses_json not installed
    class DataClassJsonMixin:
        def to_dict(self):
            from dataclasses import asdict
            return asdict(self)

        @classmethod
        def from_dict(cls, d):
            return cls(**d)


# =============================================================================
# TIMING SCHEMAS - Zeit ist MUST HAVE
# =============================================================================

@dataclass
class TimingInfo(DataClassJsonMixin):
    """Time measurement for a single step."""
    start_time: float                      # Unix timestamp
    end_time: float                        # Unix timestamp
    duration_ms: int                       # Milliseconds
    stage: str = ""                        # e.g., "discovery", "analysis"
    step_name: str = ""                    # e.g., "generate_drafts", "evaluate"

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000.0

    @classmethod
    def create(cls, start: float, end: float, stage: str = "", step_name: str = "") -> "TimingInfo":
        return cls(
            start_time=start,
            end_time=end,
            duration_ms=int((end - start) * 1000),
            stage=stage,
            step_name=step_name
        )


@dataclass
class CumulativeTiming(DataClassJsonMixin):
    """Aggregated timing per stage/component."""
    total_ms: int = 0
    llm_call_ms: int = 0
    tool_execution_ms: int = 0
    parsing_ms: int = 0
    validation_ms: int = 0
    call_count: int = 0

    def add_timing(self, timing_type: str, duration_ms: int):
        """Add timing to appropriate category."""
        self.total_ms += duration_ms
        self.call_count += 1

        if timing_type == "llm_call":
            self.llm_call_ms += duration_ms
        elif timing_type == "tool_execution":
            self.tool_execution_ms += duration_ms
        elif timing_type == "parsing":
            self.parsing_ms += duration_ms
        elif timing_type == "validation":
            self.validation_ms += duration_ms


# =============================================================================
# TOOL CALL SCHEMA
# =============================================================================

@dataclass
class ToolCallRecord(DataClassJsonMixin):
    """Records a single tool/function call."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Tool Info
    tool_name: str = ""                    # e.g., "generate_diagram", "python_exec"
    tool_type: Literal["function", "code_interpreter", "retrieval", "custom"] = "function"

    # Arguments (Input)
    arguments: Dict[str, Any] = field(default_factory=dict)
    arguments_raw: str = ""                # Original JSON string

    # Result (Output)
    result: Any = None
    result_raw: str = ""                   # Original response string
    success: bool = True
    error: Optional[str] = None

    # Timing
    duration_ms: int = 0

    # Context
    parent_llm_call_id: str = ""           # Link to parent LLM call
    stage: str = ""
    component: str = ""


# =============================================================================
# ERROR CONTEXT SCHEMA
# =============================================================================

@dataclass
class ErrorContext(DataClassJsonMixin):
    """Detailed error context for debugging and training."""
    error_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Error Type
    error_type: Literal["parsing", "validation", "llm_call", "tool_call",
                        "timeout", "rate_limit", "unknown"] = "unknown"
    exception_class: str = ""              # e.g., "JSONDecodeError"
    exception_message: str = ""

    # Stack Trace
    stack_trace: List[str] = field(default_factory=list)

    # Input that caused error
    input_text: str = ""
    input_tokens: int = 0

    # Recovery Info
    retry_count: int = 0
    was_recovered: bool = False
    recovery_strategy: str = ""            # e.g., "retry", "fallback", "skip"

    # Stage Context
    stage: str = ""
    step: str = ""
    component: str = ""

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        error_type: str = "unknown",
        input_text: str = "",
        stage: str = "",
        step: str = "",
        component: str = ""
    ) -> "ErrorContext":
        """Create ErrorContext from an exception."""
        import traceback

        return cls(
            error_type=error_type,
            exception_class=type(exception).__name__,
            exception_message=str(exception),
            stack_trace=traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ),
            input_text=input_text[:10000] if input_text else "",  # Truncate
            stage=stage,
            step=step,
            component=component
        )


# =============================================================================
# LLM CALL SCHEMA
# =============================================================================

@dataclass
class LLMCallRecord(DataClassJsonMixin):
    """Complete record of an LLM call for training."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # === CONVERSATION FORMAT ===
    system_message: str = ""
    user_message: str = ""
    assistant_response: str = ""

    # Multi-Turn (optional)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    # Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    # === MODEL INFO ===
    model: str = ""
    model_provider: str = ""               # "openai", "anthropic", "openrouter"
    temperature: float = 0.7
    max_tokens: int = 0

    # === TOKEN COUNTS ===
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0              # For o1 models
    cached_tokens: int = 0

    # === COST ===
    cost_usd: float = 0.0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0

    # === TIMING ===
    latency_ms: int = 0
    time_to_first_token_ms: Optional[int] = None

    # === TOOL CALLS ===
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    has_tool_calls: bool = False

    # === FUNCTION CALLING (OpenAI Format) ===
    function_spec: Optional[Dict[str, Any]] = None
    function_result: Optional[Dict[str, Any]] = None

    # === METADATA ===
    stage: str = ""                        # "discovery", "analysis", etc.
    stage_number: int = 0                  # 1-5
    iteration: int = 0
    component: str = ""                    # "draft_engine", "improver", etc.
    node_id: str = ""                      # Link to RequirementNode

    # === STATUS ===
    success: bool = True
    error: Optional[ErrorContext] = None

    # === QUALITY METRICS (added post-hoc) ===
    quality_score: Optional[float] = None
    quality_verdict: Optional[str] = None  # "pass", "fail", "needs_improvement"

    def __post_init__(self):
        """Calculate derived fields."""
        if self.total_tokens == 0 and (self.input_tokens or self.output_tokens):
            self.total_tokens = self.input_tokens + self.output_tokens
        if self.tool_calls and not self.has_tool_calls:
            self.has_tool_calls = True


# =============================================================================
# TRAINING SAMPLE SCHEMA (Main Export Format)
# =============================================================================

@dataclass
class TrainingSample(DataClassJsonMixin):
    """
    Single training sample in OpenAI Fine-Tuning format.

    Optimized for OpenAI/Anthropic Fine-Tuning APIs.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # === CONVERSATION (Standard Format) ===
    messages: List[Dict[str, Any]] = field(default_factory=list)
    # Format: [{"role": "system", "content": "..."},
    #          {"role": "user", "content": "..."},
    #          {"role": "assistant", "content": "..."}]

    # === TOOL CALLS (Function Calling Format) ===
    tools: List[Dict[str, Any]] = field(default_factory=list)
    # OpenAI Tools Format
    tool_choice: Optional[str] = None      # "auto", "none", "required"

    # === METADATA ===
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Contains: stage, iteration, component, quality_score, etc.

    # === QUALITY ===
    quality_score: float = 0.0             # 0.0 - 1.0
    quality_tags: List[str] = field(default_factory=list)
    # e.g., ["high_quality", "includes_tool_calls", "stage_1_discovery"]

    # === TIMING ===
    total_duration_ms: int = 0

    # === COST ===
    total_cost_usd: float = 0.0

    # === FILTERING ===
    is_valid: bool = True
    exclusion_reason: Optional[str] = None

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI Fine-Tuning format."""
        result = {"messages": self.messages}
        if self.tools:
            result["tools"] = self.tools
        return result

    def to_full_format(self) -> Dict[str, Any]:
        """Convert to full format with metadata."""
        from dataclasses import asdict
        return asdict(self)


# =============================================================================
# RUN RECORD SCHEMA
# =============================================================================

@dataclass
class RunRecord(DataClassJsonMixin):
    """Records a complete pipeline run."""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: str = ""

    # === PROJECT INFO ===
    project_id: str = ""
    project_name: str = ""

    # === CONFIGURATION ===
    config_hash: str = ""                  # Hash of configuration
    config_snapshot: Dict[str, Any] = field(default_factory=dict)

    # === STAGE PROGRESS ===
    stages_completed: List[int] = field(default_factory=list)
    current_stage: int = 0

    # === AGGREGATED METRICS ===
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_errors: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0

    # === TIMING PER STAGE ===
    stage_timings: Dict[str, CumulativeTiming] = field(default_factory=dict)

    # === QUALITY METRICS ===
    final_quality_score: float = 0.0
    requirements_generated: int = 0
    requirements_validated: int = 0

    # === SAMPLES ===
    training_samples: List[str] = field(default_factory=list)  # Sample IDs
    sample_count: int = 0

    # === STATUS ===
    status: Literal["running", "completed", "failed", "cancelled"] = "running"
    error: Optional[ErrorContext] = None

    def calculate_duration(self) -> int:
        """Calculate total duration from timestamps."""
        if self.started_at and self.ended_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            return int((end - start).total_seconds() * 1000)
        return 0


# =============================================================================
# STAGE EVALUATION RESULT
# =============================================================================

@dataclass
class StageEvaluationResult(DataClassJsonMixin):
    """Result of evaluating a stage."""
    stage_number: int
    stage_name: str

    # Timing
    duration_ms: int = 0

    # Metrics
    metrics: Dict[str, float] = field(default_factory=dict)
    # e.g., {"completeness": 0.85, "consistency": 0.92, ...}

    # Quality
    passed: bool = False
    quality_score: float = 0.0

    # Details
    issues_found: List[str] = field(default_factory=list)
    improvements_suggested: List[str] = field(default_factory=list)

    # Artifacts
    artifacts_generated: List[str] = field(default_factory=list)
    # e.g., ["REQ-001", "diagram_flowchart", ...]

    # LLM Stats
    llm_calls: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0

    # Errors
    errors: List[ErrorContext] = field(default_factory=list)

    def __post_init__(self):
        """Calculate quality score from metrics if not set."""
        if self.quality_score == 0.0 and self.metrics:
            self.quality_score = sum(self.metrics.values()) / len(self.metrics)


# =============================================================================
# MODEL PRICING
# =============================================================================

# Pricing database: model -> [input_price_per_1M, output_price_per_1M]
MODEL_PRICING: Dict[str, List[float]] = {
    # OpenAI
    "openai/gpt-5.2-codex": [2.50, 10.00],
    "openai/gpt-4o": [2.50, 10.00],
    "openai/gpt-4o-2024-11-20": [2.50, 10.00],
    "openai/gpt-4o-mini": [0.15, 0.60],
    "openai/gpt-4o-mini-2024-07-18": [0.15, 0.60],
    "openai/o1": [15.00, 60.00],
    "openai/o1-2024-12-17": [15.00, 60.00],
    "openai/o3-mini": [1.10, 4.40],
    "openai/o3-mini-2025-01-31": [1.10, 4.40],

    # Anthropic
    "anthropic/claude-opus-4.5": [15.00, 75.00],
    "anthropic/claude-sonnet-4": [3.00, 15.00],
    "anthropic/claude-3.5-sonnet": [3.00, 15.00],
    "anthropic/claude-haiku-4.5": [0.25, 1.25],

    # Google
    "google/gemini-3-flash-preview": [0.10, 0.40],
    "google/gemini-2.0-flash": [0.10, 0.40],

    # OpenRouter prefixes
    "openrouter/anthropic/claude-3.5-sonnet": [3.00, 15.00],
    "openrouter/anthropic/claude-3.5-haiku": [0.25, 1.25],
    "openrouter/openai/gpt-4o": [2.50, 10.00],
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost for an LLM call.

    Args:
        model: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Cost in USD
    """
    # Try direct match
    prices = MODEL_PRICING.get(model)

    if not prices:
        # Try without provider prefix
        for key in MODEL_PRICING:
            if key.endswith(model.split("/")[-1]):
                prices = MODEL_PRICING[key]
                break

    if not prices:
        # Default fallback
        prices = [1.00, 3.00]

    input_cost = (input_tokens / 1_000_000) * prices[0]
    output_cost = (output_tokens / 1_000_000) * prices[1]

    return round(input_cost + output_cost, 6)
