"""
File Watcher - Monitors project directories for file changes.

Uses watchdog library for cross-platform file system event monitoring.
"""

import asyncio
import threading
from pathlib import Path
from typing import Callable, Optional, Set
from datetime import datetime
import time

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("[FileWatcher] watchdog not installed. Install with: pip install watchdog")


class ChangeHandler(FileSystemEventHandler):
    """
    Handles file system events with debouncing.
    """

    def __init__(self, callback: Callable, debounce_delay: float = 0.5, watched_patterns: Optional[Set[str]] = None):
        """
        Initialize the change handler.

        Args:
            callback: Function to call with (event_type, file_path)
            debounce_delay: Delay in seconds to debounce rapid changes
            watched_patterns: Set of file patterns to watch (e.g., {"*.json", "*.md"})
        """
        super().__init__()
        self.callback = callback
        self.debounce_delay = debounce_delay
        self.watched_patterns = watched_patterns or {
            "journal.json",
            "user_stories.md",
            "task_list.json",
            "*.mmd",
            "*.feature",
            "data_dictionary.md",
            "feature_breakdown.md",
            "api_documentation.md",
        }

        self._pending_events = {}  # file_path -> (event_type, timestamp)
        self._lock = threading.Lock()
        self._debounce_thread = None
        self._running = True

    def start_debounce_thread(self):
        """Start the debounce processing thread."""
        self._running = True
        self._debounce_thread = threading.Thread(target=self._process_debounced_events, daemon=True)
        self._debounce_thread.start()

    def stop(self):
        """Stop the debounce thread."""
        self._running = False
        if self._debounce_thread:
            self._debounce_thread.join(timeout=1.0)

    def _should_watch(self, file_path: str) -> bool:
        """Check if this file should be watched."""
        path = Path(file_path)

        # Skip hidden files and directories
        if any(part.startswith('.') for part in path.parts):
            return False

        # Skip backup files
        if path.suffix == '.bak':
            return False

        # Check against patterns
        for pattern in self.watched_patterns:
            if '*' in pattern:
                # Glob pattern
                if path.match(pattern):
                    return True
            else:
                # Exact filename
                if path.name == pattern:
                    return True

        return False

    def on_modified(self, event):
        """Handle file modification event."""
        if event.is_directory:
            return

        if self._should_watch(event.src_path):
            self._add_pending_event(event.src_path, "modified")

    def on_created(self, event):
        """Handle file creation event."""
        if event.is_directory:
            return

        if self._should_watch(event.src_path):
            self._add_pending_event(event.src_path, "created")

    def on_deleted(self, event):
        """Handle file deletion event."""
        if event.is_directory:
            return

        if self._should_watch(event.src_path):
            self._add_pending_event(event.src_path, "deleted")

    def _add_pending_event(self, file_path: str, event_type: str):
        """Add an event to the pending queue with debouncing."""
        with self._lock:
            self._pending_events[file_path] = (event_type, time.time())

    def _process_debounced_events(self):
        """Process pending events after debounce delay."""
        while self._running:
            time.sleep(0.1)  # Check every 100ms

            events_to_process = []
            current_time = time.time()

            with self._lock:
                for file_path, (event_type, timestamp) in list(self._pending_events.items()):
                    if current_time - timestamp >= self.debounce_delay:
                        events_to_process.append((event_type, file_path))
                        del self._pending_events[file_path]

            # Process events outside the lock
            for event_type, file_path in events_to_process:
                try:
                    self.callback(event_type, file_path)
                except Exception as e:
                    print(f"[FileWatcher] Error in callback: {e}")


class FileWatcher:
    """
    Monitors enterprise_output/{project}/ for file changes.

    Uses watchdog library for cross-platform file system events.
    """

    def __init__(self, project_path: Path, on_change: Callable[[str, str], None]):
        """
        Initialize the file watcher.

        Args:
            project_path: Path to the project directory to watch
            on_change: Callback function with signature (event_type, file_path)
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog library is required. Install with: pip install watchdog")

        self.project_path = Path(project_path)
        self.on_change = on_change
        self.observer: Optional[Observer] = None
        self.handler: Optional[ChangeHandler] = None
        self._is_running = False

        # Async callback wrapper
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_callback: Optional[Callable] = None

    def start(self, async_callback: Optional[Callable] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        Start watching for changes.

        Args:
            async_callback: Optional async callback to use instead of sync callback
            loop: Event loop to use for async callbacks
        """
        if self._is_running:
            return

        self._loop = loop
        self._async_callback = async_callback

        # Create handler with appropriate callback
        if async_callback and loop:
            def sync_wrapper(event_type: str, file_path: str):
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    async_callback(event_type, file_path)
                )
            callback = sync_wrapper
        else:
            callback = self.on_change

        self.handler = ChangeHandler(callback, debounce_delay=0.5)
        self.handler.start_debounce_thread()

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.project_path), recursive=True)
        self.observer.start()

        self._is_running = True
        print(f"[FileWatcher] Started watching: {self.project_path}")

    def stop(self):
        """Stop watching for changes."""
        if not self._is_running:
            return

        if self.handler:
            self.handler.stop()

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2.0)

        self._is_running = False
        print(f"[FileWatcher] Stopped watching: {self.project_path}")

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._is_running

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class AsyncFileWatcher:
    """
    Async wrapper for FileWatcher that integrates with asyncio event loops.
    """

    def __init__(self, project_path: Path):
        """
        Initialize the async file watcher.

        Args:
            project_path: Path to the project directory to watch
        """
        self.project_path = Path(project_path)
        self._watcher: Optional[FileWatcher] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._callbacks: list = []

    def add_callback(self, callback: Callable[[str, str], None]):
        """Add a callback for file change events."""
        self._callbacks.append(callback)

    async def start(self):
        """Start watching for changes."""
        def sync_callback(event_type: str, file_path: str):
            # Put event in queue for async processing
            try:
                self._queue.put_nowait((event_type, file_path))
            except asyncio.QueueFull:
                pass

        self._watcher = FileWatcher(self.project_path, sync_callback)
        self._watcher.start()

        # Start event processor
        asyncio.create_task(self._process_events())

    async def _process_events(self):
        """Process events from the queue."""
        while True:
            try:
                event_type, file_path = await self._queue.get()

                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event_type, file_path)
                        else:
                            callback(event_type, file_path)
                    except Exception as e:
                        print(f"[AsyncFileWatcher] Callback error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AsyncFileWatcher] Event processing error: {e}")

    async def stop(self):
        """Stop watching for changes."""
        if self._watcher:
            self._watcher.stop()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
