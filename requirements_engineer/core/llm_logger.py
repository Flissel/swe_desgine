"""
LLM Call Logger for Requirements Engineering System.

Tracks all LLM calls with:
- Token counts (input/output)
- Cost calculation
- Latency measurement
- Component identification

Writes to JSONL file for analysis.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import wraps

log = logging.getLogger(__name__)


@dataclass
class LLMCallLog:
    """Single LLM call log entry."""
    timestamp: str
    component: str          # e.g., "user_story_generator", "html_reviewer"
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentStats:
    """Aggregated stats for a component."""
    component: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    models_used: Dict[str, int] = field(default_factory=dict)


class LLMLogger:
    """
    Central logger for all LLM calls in the RE system.

    Usage:
        logger = LLMLogger(config)

        # Option 1: Manual logging
        start = time.time()
        response = await llm_call(...)
        logger.log_call(
            component="user_story_generator",
            model="openai/gpt-5.2-codex",
            response=response,
            latency_ms=int((time.time() - start) * 1000)
        )

        # Option 2: Decorator
        @logger.track("user_story_generator")
        async def generate_stories(...):
            return await llm_call(...)
    """

    _instance: Optional['LLMLogger'] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM Logger.

        Args:
            config: Configuration dict with cost_tracking section
        """
        self.config = config or {}
        cost_config = self.config.get("cost_tracking", {})

        self.enabled = cost_config.get("enabled", True)
        self.log_file = cost_config.get("log_file", "llm_costs.jsonl")
        self.log_every_call = cost_config.get("log_every_call", True)
        self.summary_at_end = cost_config.get("summary_at_end", True)

        # Pricing: model -> [input_price_per_1M, output_price_per_1M]
        self.pricing = cost_config.get("pricing", {
            "openai/gpt-5.2-codex": [2.50, 10.00],
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "anthropic/claude-sonnet-4": [3.00, 15.00],
            "anthropic/claude-3.5-sonnet": [3.00, 15.00],
            "anthropic/claude-haiku-4.5": [0.25, 1.25],
            "google/gemini-3-flash-preview": [0.10, 0.40],
        })

        # In-memory log for session
        self.calls: List[LLMCallLog] = []
        self.component_stats: Dict[str, ComponentStats] = {}

        # Ensure log directory exists
        if self.enabled:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> 'LLMLogger':
        """Get or create thread-safe singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for an LLM call.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        # Normalize model name - strip openrouter/ prefix since pricing
        # keys use provider/model format (e.g. "openai/gpt-4o")
        normalized_model = model
        if model.startswith("openrouter/"):
            normalized_model = model[len("openrouter/"):]

        prices = self.pricing.get(normalized_model)
        if not prices:
            # Try without prefix
            for key in self.pricing:
                if key.endswith(model.split("/")[-1]):
                    prices = self.pricing[key]
                    break

        if not prices:
            log.warning(f"No pricing found for model: {model}, using default")
            prices = [1.00, 3.00]  # Default fallback

        input_cost = (input_tokens / 1_000_000) * prices[0]
        output_cost = (output_tokens / 1_000_000) * prices[1]

        return round(input_cost + output_cost, 6)

    def extract_tokens_from_response(self, response: Any) -> tuple[int, int]:
        """
        Extract token counts from various LLM response formats.

        Args:
            response: LLM API response object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        input_tokens = 0
        output_tokens = 0

        # OpenAI format
        if hasattr(response, 'usage'):
            usage = response.usage
            if hasattr(usage, 'prompt_tokens'):
                input_tokens = usage.prompt_tokens
            if hasattr(usage, 'completion_tokens'):
                output_tokens = usage.completion_tokens

        # Dict format (from some wrappers)
        elif isinstance(response, dict):
            usage = response.get('usage', {})
            input_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0))
            output_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0))

        return input_tokens, output_tokens

    def log_call(
        self,
        component: str,
        model: str,
        response: Any = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # Prompt context for training data collection
        system_message: str = "",
        user_message: str = "",
        response_text: str = ""
    ) -> LLMCallLog:
        """
        Log an LLM call.

        Args:
            component: Component name (e.g., "user_story_generator")
            model: Model used
            response: Optional LLM response to extract tokens from
            input_tokens: Override input token count
            output_tokens: Override output token count
            latency_ms: Call latency in milliseconds
            success: Whether call succeeded
            error: Error message if failed
            metadata: Additional metadata

        Returns:
            The log entry
        """
        if not self.enabled:
            return None

        # Extract tokens from response if not provided
        if response is not None and (input_tokens is None or output_tokens is None):
            extracted_in, extracted_out = self.extract_tokens_from_response(response)
            input_tokens = input_tokens or extracted_in
            output_tokens = output_tokens or extracted_out

        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        total_tokens = input_tokens + output_tokens

        # Calculate cost
        cost = self.calculate_cost(model, input_tokens, output_tokens)

        # Create log entry
        entry = LLMCallLog(
            timestamp=datetime.now().isoformat(),
            component=component,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            success=success,
            error=error,
            metadata=metadata or {}
        )

        # Add to memory
        self.calls.append(entry)

        # Update component stats
        self._update_component_stats(entry)

        # Write to file
        if self.log_every_call:
            self._write_to_file(entry)

        # Log summary
        log.debug(
            f"[LLM] {component} | {model} | "
            f"{input_tokens}+{output_tokens} tokens | "
            f"${cost:.4f} | {latency_ms}ms"
        )

        # Bridge to TrainingDataCollector (if active)
        self._record_training_data(
            component=component,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            success=success,
            error=error,
            system_message=system_message,
            user_message=user_message,
            response_text=response_text,
        )

        return entry

    def _update_component_stats(self, entry: LLMCallLog):
        """Update aggregated stats for component."""
        if entry.component not in self.component_stats:
            self.component_stats[entry.component] = ComponentStats(
                component=entry.component
            )

        stats = self.component_stats[entry.component]
        stats.total_calls += 1
        if entry.success:
            stats.successful_calls += 1
        else:
            stats.failed_calls += 1
        stats.total_input_tokens += entry.input_tokens
        stats.total_output_tokens += entry.output_tokens
        stats.total_cost_usd += entry.cost_usd
        stats.total_latency_ms += entry.latency_ms

        model_count = stats.models_used.get(entry.model, 0)
        stats.models_used[entry.model] = model_count + 1

    def _record_training_data(
        self,
        component: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        error: Optional[str],
        system_message: str = "",
        user_message: str = "",
        response_text: str = "",
    ):
        """Bridge to TrainingDataCollector for fine-tuning data capture."""
        try:
            from requirements_engineer.training.collector import TrainingDataCollector
            collector = TrainingDataCollector.get_instance()
            if collector and collector.run_record:
                collector.record_llm_call(
                    system_message=system_message,
                    user_message=user_message,
                    response=response_text,
                    model=model,
                    component=component,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    success=success,
                )
        except Exception:
            pass  # Graceful degradation — don't break cost tracking

    def _write_to_file(self, entry: LLMCallLog):
        """Write entry to JSONL file."""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(entry)) + '\n')
        except Exception as e:
            log.warning(f"Failed to write LLM log: {e}")

    def track(self, component: str):
        """
        Decorator to track LLM calls.

        Args:
            component: Component name

        Example:
            @logger.track("user_story_generator")
            async def call_llm(model, prompt):
                return await client.chat.completions.create(...)
        """
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                model = kwargs.get('model', 'unknown')
                start_time = time.time()
                success = True
                error = None
                response = None

                try:
                    response = await func(*args, **kwargs)
                    return response
                except Exception as e:
                    success = False
                    error = str(e)
                    raise
                finally:
                    latency_ms = int((time.time() - start_time) * 1000)
                    self.log_call(
                        component=component,
                        model=model,
                        response=response,
                        latency_ms=latency_ms,
                        success=success,
                        error=error
                    )

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                model = kwargs.get('model', 'unknown')
                start_time = time.time()
                success = True
                error = None
                response = None

                try:
                    response = func(*args, **kwargs)
                    return response
                except Exception as e:
                    success = False
                    error = str(e)
                    raise
                finally:
                    latency_ms = int((time.time() - start_time) * 1000)
                    self.log_call(
                        component=component,
                        model=model,
                        response=response,
                        latency_ms=latency_ms,
                        success=success,
                        error=error
                    )

            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all LLM calls.

        Returns:
            Dict with total stats and per-component breakdown
        """
        total_calls = len(self.calls)
        total_input_tokens = sum(c.input_tokens for c in self.calls)
        total_output_tokens = sum(c.output_tokens for c in self.calls)
        total_cost = sum(c.cost_usd for c in self.calls)
        total_latency = sum(c.latency_ms for c in self.calls)
        successful_calls = sum(1 for c in self.calls if c.success)

        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": total_calls - successful_calls,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "total_cost_usd": round(total_cost, 4),
            "avg_latency_ms": round(total_latency / total_calls, 1) if total_calls > 0 else 0,
            "by_component": {
                name: {
                    "calls": stats.total_calls,
                    "tokens": stats.total_input_tokens + stats.total_output_tokens,
                    "cost_usd": round(stats.total_cost_usd, 4),
                    "models": stats.models_used
                }
                for name, stats in self.component_stats.items()
            }
        }

    def print_summary(self):
        """Print formatted summary to console."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("LLM USAGE SUMMARY")
        print("=" * 70)
        print(f"Total Calls:    {summary['total_calls']} ({summary['successful_calls']} success, {summary['failed_calls']} failed)")
        print(f"Total Tokens:   {summary['total_tokens']:,} ({summary['total_input_tokens']:,} in, {summary['total_output_tokens']:,} out)")
        print(f"Total Cost:     ${summary['total_cost_usd']:.4f} USD")
        print(f"Avg Latency:    {summary['avg_latency_ms']:.0f}ms")
        print("-" * 70)
        print("BY COMPONENT:")
        print("-" * 70)

        for comp, stats in sorted(summary['by_component'].items(), key=lambda x: -x[1]['cost_usd']):
            models = ", ".join(f"{m}({c})" for m, c in stats['models'].items())
            print(f"  {comp}:")
            print(f"    Calls: {stats['calls']} | Tokens: {stats['tokens']:,} | Cost: ${stats['cost_usd']:.4f}")
            print(f"    Models: {models}")

        print("=" * 70)

    def save_summary(self, path: Optional[str] = None):
        """Save summary to JSON file."""
        path = path or self.log_file.replace('.jsonl', '_summary.json')
        summary = self.get_summary()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        log.info(f"LLM usage summary saved to: {path}")


# Global instance for easy access
_global_logger: Optional[LLMLogger] = None


def get_llm_logger(config: Optional[Dict[str, Any]] = None) -> LLMLogger:
    """Get global LLM logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = LLMLogger(config)
    return _global_logger


def log_llm_call(
    component: str,
    model: str,
    response: Any = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: int = 0,
    success: bool = True,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    # Prompt context for training data collection
    system_message: str = "",
    user_message: str = "",
    response_text: str = "",
) -> Optional[LLMCallLog]:
    """
    Convenience function to log an LLM call.

    Example:
        response = await client.chat.completions.create(...)
        log_llm_call("user_story_generator", "openai/gpt-5.2-codex", response,
                     system_message="You are...", user_message=prompt,
                     response_text=response.choices[0].message.content)
    """
    logger = get_llm_logger()
    return logger.log_call(
        component=component,
        model=model,
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        success=success,
        error=error,
        metadata=metadata,
        system_message=system_message,
        user_message=user_message,
        response_text=response_text,
    )
