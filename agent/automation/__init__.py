"""Automation backends: the only layer that touches the GUI.

basic — real native Windows actions (open app, type, screenshot), no planning.
ufo   — Microsoft UFO² (milestone 2; fails loudly until wired).
"""

from .base import DeviceAutomationBackend
from .basic_backend import BasicAutomationBackend
from .ufo_backend import UfoAutomationBackend

__all__ = ["BasicAutomationBackend", "DeviceAutomationBackend", "UfoAutomationBackend"]
