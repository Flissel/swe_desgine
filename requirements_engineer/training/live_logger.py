"""
Live Logging System for Training Data Collection.

Provides real-time event emission using Observer pattern:
- Callback-based observers for synchronous handling
- Async observers for WebSocket/Dashboard integration
- Event history for replay
- Event filtering by type

Usage:
    from requirements_engineer.training.live_logger import get_live_logger, EventType

    logger = get_live_logger()

    # Add observer
    logger.add_observer(lambda event: print(event.to_json()))

    # Emit events
    logger.emit(EventType.LLM_CALL, {"model": "gpt-4o", "tokens": 1500})
"""

import json
import threading
import asyncio
from queue import Queue
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Union


class EventType(Enum):
    """Event types for live logging."""
    # Run Events
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"

    # Stage Events
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"

    # Step Events
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"

    # LLM Events
    LLM_CALL = "llm_call"
    LLM_STREAMING = "llm_streaming"  # For streaming responses
    LLM_RETRY = "llm_retry"

    # Tool Events
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    # Error Events
    ERROR = "error"
    WARNING = "warning"

    # Progress Events
    PROGRESS = "progress"

    # Quality Events
    QUALITY_CHECK = "quality_check"
    QUALITY_IMPROVEMENT = "quality_improvement"

    # Training Events
    SAMPLE_CREATED = "sample_created"
    EXPORT_COMPLETED = "export_completed"

    # Custom
    CUSTOM = "custom"


@dataclass
class LiveEvent:
    """A single live event."""
    type: EventType
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_id: str = field(default_factory=lambda: f"evt_{datetime.now().timestamp():.0f}")

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "id": self.event_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp
        }, default=str)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.event_id,
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp
        }


# Type alias for observer callbacks
ObserverCallback = Callable[[LiveEvent], None]
AsyncObserverCallback = Callable[[LiveEvent], Any]


class LiveLogger:
    """
    Observer-based live logging system.

    Supports:
    - Callback-based observers
    - WebSocket integration (via aiohttp)
    - Event queue for async processing
    - Event history for replay
    """

    _instance: Optional['LiveLogger'] = None
    _lock = threading.Lock()

    def __init__(self, max_history: int = 1000):
        """
        Initialize LiveLogger.

        Args:
            max_history: Maximum number of events to keep in history
        """
        self._observers: List[ObserverCallback] = []
        self._async_observers: List[AsyncObserverCallback] = []
        self._history: List[LiveEvent] = []
        self._max_history = max_history
        self._lock = threading.Lock()

        # Event queue for async processing
        self._event_queue: Queue = Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # WebSocket clients (for dashboard)
        self._ws_clients: List[Any] = []

        # Event filters
        self._filters: Dict[str, List[EventType]] = {}

    @classmethod
    def get_instance(cls, max_history: int = 1000) -> 'LiveLogger':
        """Get singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(max_history)
            return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        with cls._lock:
            if cls._instance:
                cls._instance.stop_worker()
            cls._instance = None

    # =========================================================================
    # OBSERVER MANAGEMENT
    # =========================================================================

    def add_observer(
        self,
        callback: ObserverCallback,
        event_types: Optional[List[EventType]] = None,
        name: str = ""
    ) -> str:
        """
        Add a synchronous observer.

        Args:
            callback: Function to call for each event
            event_types: Optional filter for specific event types
            name: Optional name for the observer

        Returns:
            Observer ID for removal
        """
        observer_id = name or f"obs_{len(self._observers)}"

        with self._lock:
            self._observers.append(callback)
            if event_types:
                self._filters[observer_id] = event_types

        return observer_id

    def add_async_observer(
        self,
        callback: AsyncObserverCallback,
        event_types: Optional[List[EventType]] = None,
        name: str = ""
    ) -> str:
        """
        Add an asynchronous observer.

        Args:
            callback: Async function to call for each event
            event_types: Optional filter for specific event types
            name: Optional name for the observer

        Returns:
            Observer ID for removal
        """
        observer_id = name or f"async_obs_{len(self._async_observers)}"

        with self._lock:
            self._async_observers.append(callback)
            if event_types:
                self._filters[observer_id] = event_types

        return observer_id

    def remove_observer(self, callback: Union[ObserverCallback, AsyncObserverCallback]):
        """Remove an observer."""
        with self._lock:
            if callback in self._observers:
                self._observers.remove(callback)
            if callback in self._async_observers:
                self._async_observers.remove(callback)

    def clear_observers(self):
        """Remove all observers."""
        with self._lock:
            self._observers.clear()
            self._async_observers.clear()
            self._filters.clear()

    # =========================================================================
    # WEBSOCKET MANAGEMENT
    # =========================================================================

    def add_ws_client(self, client: Any):
        """Add a WebSocket client."""
        with self._lock:
            self._ws_clients.append(client)

    def remove_ws_client(self, client: Any):
        """Remove a WebSocket client."""
        with self._lock:
            if client in self._ws_clients:
                self._ws_clients.remove(client)

    # =========================================================================
    # EVENT EMISSION
    # =========================================================================

    def emit(self, event_type: EventType, data: Dict[str, Any]) -> LiveEvent:
        """
        Emit an event to all observers.

        Args:
            event_type: Type of event
            data: Event data

        Returns:
            The created LiveEvent
        """
        event = LiveEvent(type=event_type, data=data)

        with self._lock:
            # Add to history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)

            # Call sync observers
            for observer in self._observers:
                try:
                    observer(event)
                except Exception as e:
                    # Don't let observer errors break the system
                    print(f"Observer error: {e}")

            # Send to WebSocket clients
            message = event.to_json()
            disconnected = []
            for client in self._ws_clients:
                try:
                    # Schedule async send
                    asyncio.create_task(self._send_to_ws(client, message))
                except Exception:
                    disconnected.append(client)

            for client in disconnected:
                self._ws_clients.remove(client)

        # Queue for async observers
        if self._async_observers:
            self._event_queue.put(event)

        return event

    async def _send_to_ws(self, client: Any, message: str):
        """Send message to WebSocket client."""
        try:
            await client.send_str(message)
        except Exception as e:
            print(f"WebSocket send error: {e}")

    # =========================================================================
    # ASYNC WORKER
    # =========================================================================

    def start_worker(self):
        """Start worker thread for async events."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self):
        """Stop worker thread."""
        self._running = False
        if self._worker_thread:
            self._event_queue.put(None)  # Poison pill
            self._worker_thread.join(timeout=2)
            self._worker_thread = None

    def _worker_loop(self):
        """Worker loop for async event processing."""
        while self._running:
            try:
                event = self._event_queue.get(timeout=1)
                if event is None:
                    break

                # Call async observers
                for observer in self._async_observers:
                    try:
                        result = observer(event)
                        if asyncio.iscoroutine(result):
                            asyncio.run(result)
                    except Exception as e:
                        print(f"Async observer error: {e}")
            except Exception:
                continue

    # =========================================================================
    # HISTORY ACCESS
    # =========================================================================

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get event history.

        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            since: Optional ISO timestamp to filter events after

        Returns:
            List of event dictionaries
        """
        with self._lock:
            events = self._history

            if event_type:
                events = [e for e in events if e.type == event_type]

            if since:
                events = [e for e in events if e.timestamp >= since]

            return [e.to_dict() for e in events[-limit:]]

    def get_event_counts(self) -> Dict[str, int]:
        """Get counts of events by type."""
        with self._lock:
            counts: Dict[str, int] = {}
            for event in self._history:
                type_name = event.type.value
                counts[type_name] = counts.get(type_name, 0) + 1
            return counts

    def clear_history(self):
        """Clear event history."""
        with self._lock:
            self._history.clear()

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def log_run_started(self, run_id: str, project_name: str):
        """Log run started event."""
        self.emit(EventType.RUN_STARTED, {
            "run_id": run_id,
            "project_name": project_name
        })

    def log_run_completed(self, run_id: str, status: str, total_samples: int = 0):
        """Log run completed event."""
        self.emit(EventType.RUN_COMPLETED, {
            "run_id": run_id,
            "status": status,
            "total_samples": total_samples
        })

    def log_stage_started(self, stage: str, stage_number: int):
        """Log stage started event."""
        self.emit(EventType.STAGE_STARTED, {
            "stage": stage,
            "stage_number": stage_number
        })

    def log_stage_completed(self, stage: str, stage_number: int, duration_ms: int):
        """Log stage completed event."""
        self.emit(EventType.STAGE_COMPLETED, {
            "stage": stage,
            "stage_number": stage_number,
            "duration_ms": duration_ms
        })

    def log_llm_call(
        self,
        model: str,
        tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool = True,
        stage: str = "",
        component: str = ""
    ):
        """Log LLM call event."""
        self.emit(EventType.LLM_CALL, {
            "model": model,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "success": success,
            "stage": stage,
            "component": component
        })

    def log_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: int,
        stage: str = ""
    ):
        """Log tool call event."""
        self.emit(EventType.TOOL_CALL, {
            "tool_name": tool_name,
            "success": success,
            "duration_ms": duration_ms,
            "stage": stage
        })

    def log_error(
        self,
        error_type: str,
        message: str,
        stage: str = "",
        recovered: bool = False
    ):
        """Log error event."""
        self.emit(EventType.ERROR, {
            "error_type": error_type,
            "message": message,
            "stage": stage,
            "recovered": recovered
        })

    def log_warning(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log warning event."""
        self.emit(EventType.WARNING, {
            "message": message,
            "details": details or {}
        })

    def log_progress(self, message: str, percent: int = 0, stage: str = ""):
        """Log progress event."""
        self.emit(EventType.PROGRESS, {
            "message": message,
            "percent": percent,
            "stage": stage
        })

    def log_quality_check(
        self,
        node_id: str,
        score: float,
        verdict: str,
        metrics: Dict[str, float]
    ):
        """Log quality check event."""
        self.emit(EventType.QUALITY_CHECK, {
            "node_id": node_id,
            "score": score,
            "verdict": verdict,
            "metrics": metrics
        })

    def log_sample_created(self, sample_id: str, stage: str, quality_score: float):
        """Log training sample created event."""
        self.emit(EventType.SAMPLE_CREATED, {
            "sample_id": sample_id,
            "stage": stage,
            "quality_score": quality_score
        })


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_global_live_logger: Optional[LiveLogger] = None


def get_live_logger() -> LiveLogger:
    """Get global LiveLogger instance."""
    global _global_live_logger
    if _global_live_logger is None:
        _global_live_logger = LiveLogger.get_instance()
    return _global_live_logger


def reset_live_logger():
    """Reset global LiveLogger instance."""
    global _global_live_logger
    if _global_live_logger:
        _global_live_logger.stop_worker()
    _global_live_logger = None
    LiveLogger.reset()
