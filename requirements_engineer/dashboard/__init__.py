"""
Live Dashboard Package for Requirements Engineering System.

Provides real-time visualization of the RE pipeline using an
endless canvas board with WebSocket updates.
"""

from .server import DashboardServer
from .event_emitter import DashboardEventEmitter

__all__ = [
    'DashboardServer',
    'DashboardEventEmitter',
]
