"""Automation backends: the only layer that touches the GUI (or pretends to)."""

from .base import DeviceAutomationBackend
from .mock_backend import MockAutomationBackend
from .ufo_backend import UfoAutomationBackend

__all__ = ["DeviceAutomationBackend", "MockAutomationBackend", "UfoAutomationBackend"]
