"""Unit tests for the auto-updater (cross-platform; no network, no real swap).

Covers the pure version comparison and the guard logic that must keep the
updater inert in dev / tests and prevent boot-loops.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent import updater
from agent.config import AGENT_VERSION, AgentSettings
from agent.storage import AgentStorage


def test_is_newer_semver():
    assert updater.is_newer("0.1.1", "0.1.0")
    assert updater.is_newer("0.10.0", "0.9.0")  # NOT string comparison
    assert updater.is_newer("1.0.0", "0.9.9")
    assert updater.is_newer("v0.2.0", "0.1.0")  # leading v tolerated
    assert updater.is_newer("0.1.0", "0.1.0-dev")  # real release beats dev
    assert not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("0.1.0", "0.1.1")


def test_noop_when_not_frozen(tmp_path: Path):
    # Running from source (sys.frozen unset) must always be a no-op.
    storage = AgentStorage(tmp_path)
    assert updater.maybe_self_update(AgentSettings(), storage, trigger="startup") is False
    assert updater.maybe_self_update(AgentSettings(), storage, trigger="relay") is False


def test_noop_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    called = False

    def _boom(_repo):
        nonlocal called
        called = True
        return {"version": "9.9.9", "exe_url": "x", "sha_url": "y"}

    monkeypatch.setattr(updater, "check_latest", _boom)
    storage = AgentStorage(tmp_path)
    settings = AgentSettings(disable_autoupdate=True)
    assert updater.maybe_self_update(settings, storage, trigger="startup") is False
    assert called is False  # disabled => never even checks for a release


def test_loop_guard_gives_up_after_max_attempts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(
        updater, "check_latest", lambda _repo: {"version": "9.9.9", "exe_url": "x", "sha_url": "y"}
    )
    # Guard against ever reaching the download/swap path.
    monkeypatch.setattr(updater, "_download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded")))

    storage = AgentStorage(tmp_path)
    settings = AgentSettings()  # update_max_attempts default 3
    (tmp_path / "update_state.json").write_text(
        json.dumps({"target_version": "9.9.9", "attempts": 3, "phase": "swapping"}), encoding="utf-8"
    )
    # Newer version is available but we've already failed 3x → give up, no download.
    assert updater.maybe_self_update(settings, storage, trigger="startup") is False


def test_up_to_date_is_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    # Latest equals what we're running → nothing to do.
    monkeypatch.setattr(
        updater, "check_latest", lambda _repo: {"version": AGENT_VERSION.lstrip("v"), "exe_url": "x", "sha_url": "y"}
    )
    monkeypatch.setattr(updater, "_download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded")))
    storage = AgentStorage(tmp_path)
    assert updater.maybe_self_update(AgentSettings(), storage, trigger="relay") is False
