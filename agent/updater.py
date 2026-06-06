"""Silent auto-update of the frozen ufo-agent.exe from GitHub Releases.

This is the only module that replaces the running binary, so every step is
ordered around one rule: **never leave the device without a working exe.** The
running, known-good exe is never deleted until a verified, self-tested
replacement is in place and has proven it boots.

Triggers (both reuse maybe_self_update):
  * startup    — agent/main.py calls it before binding the local UI
  * relay      — operator pushes RelayMsg.UPDATE_AGENT

Hard guards (no-op unless ALL hold):
  * running as a frozen PyInstaller onefile (sys.frozen)
  * settings.disable_autoupdate is false (env UFO_AGENT_DISABLE_AUTOUPDATE)

So source/editable runs, pytest/e2e subprocesses, and `pip install -e` are
inert automatically; the env var is the kill-switch for the one frozen
context (CI's exe smoke test).

Windows fact this relies on: you cannot overwrite/delete a *running* exe, but
you CAN rename it (Windows tracks the image by handle, not path). So we rename
the running exe aside, drop the new one into the canonical path, relaunch, and
exit.

Integrity is sha256-against-the-published-hash — protection against a corrupt
download, NOT authenticity. Authenticode code-signing is the hardening path
(see docs); not built here.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version
from rich.console import Console

from .config import AGENT_VERSION, AgentSettings
from .storage import AgentStorage

console = Console()

EXE_ASSET = "ufo-agent.exe"
SHA_ASSET = "ufo-agent.exe.sha256"
UPDATE_STATE_FILE = "update_state.json"
HTTP_TIMEOUT = 60.0
SELFTEST_TIMEOUT = 60.0


def _log(msg: str) -> None:
    console.log(f"[magenta]updater[/magenta] {msg}")


def is_frozen() -> bool:
    """True when running as the PyInstaller onefile exe."""
    return bool(getattr(sys, "frozen", False))


def is_newer(remote: str, local: str) -> bool:
    """True if remote version is strictly newer than local (semver-aware).

    Leading 'v' is tolerated on either side. Unparseable versions fall back to
    a conservative string comparison so a bad tag can't silently trigger a loop.
    """
    r, loc = remote.lstrip("vV"), local.lstrip("vV")
    try:
        return Version(r) > Version(loc)
    except InvalidVersion:
        return r != loc and r > loc


# --- persistent update state (anti-boot-loop) --------------------------------


def _state_path(storage: AgentStorage) -> Path:
    return storage.data_dir / UPDATE_STATE_FILE


def _read_update_state(storage: AgentStorage) -> dict[str, Any]:
    path = _state_path(storage)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _write_update_state(storage: AgentStorage, data: dict[str, Any]) -> None:
    try:
        _state_path(storage).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        _log(f"could not persist update state: {exc}")


# --- GitHub release query ----------------------------------------------------


def check_latest(repo: str) -> dict[str, Any] | None:
    """Return {"version", "exe_url", "sha_url"} for the latest release, or None.

    Best-effort: any error (network, rate limit, missing asset) returns None.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        _log(f"latest-release check failed (non-fatal): {exc}")
        return None

    tag = str(data.get("tag_name", "")).lstrip("vV")
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    exe_url, sha_url = assets.get(EXE_ASSET), assets.get(SHA_ASSET)
    if not tag or not exe_url or not sha_url:
        _log(f"release {tag or '?'} is missing {EXE_ASSET}/{SHA_ASSET} assets")
        return None
    return {"version": tag, "exe_url": exe_url, "sha_url": sha_url}


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1 << 16):
                fh.write(chunk)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --- the swap (Windows, frozen only) -----------------------------------------


def _self_test(exe: Path) -> bool:
    """Run the candidate exe's --help and status; require both to exit 0.

    Done while the OLD exe is still canonical, so a broken download (missing
    runtime, AV quarantine) is caught before we touch the live binary.
    """
    for args in (["--help"], ["status"]):
        try:
            proc = subprocess.run(
                [str(exe), *args],
                capture_output=True,
                timeout=SELFTEST_TIMEOUT,
                env={**os.environ, "UFO_AGENT_DISABLE_AUTOUPDATE": "1"},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _log(f"self-test '{' '.join(args)}' failed to run: {exc}")
            return False
        if proc.returncode != 0:
            _log(f"self-test '{' '.join(args)}' exited {proc.returncode}")
            return False
    return True


def _apply_update_and_restart(exe: Path, new_exe: Path) -> None:
    """Rename-first swap, then relaunch with the original argv and exit.

    Raises on failure AFTER restoring the old exe to its canonical path, so the
    caller's state stays "old exe still works".
    """
    old_exe = exe.with_suffix(exe.suffix + ".old")
    if old_exe.exists():
        try:
            old_exe.unlink()
        except OSError:
            pass  # last update's backup; will be retried on next clean boot

    os.replace(exe, old_exe)  # allowed even while running from `exe`
    try:
        os.replace(new_exe, exe)
    except OSError:
        os.replace(old_exe, exe)  # rollback: restore the known-good exe
        raise

    # Relaunch the new exe with the same subcommand/args and environment.
    args = [str(exe), *sys.argv[1:]]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    subprocess.Popen(
        args,
        env={**os.environ, "UFO_AGENT_UPDATED_FROM": AGENT_VERSION},
        close_fds=True,
        creationflags=creationflags,
    )
    _log(f"relaunched {exe.name}; exiting old process")


# --- public entry point ------------------------------------------------------


def maybe_self_update(
    settings: AgentSettings,
    storage: AgentStorage,
    *,
    trigger: str,
    target_version: str | None = None,
    on_shutdown=None,
) -> bool:
    """Check for and apply an update. Returns True if the process is being
    replaced (caller should stop and let the new process take over).

    ``on_shutdown`` (optional callable) is invoked just before relaunch so the
    caller can release port 8766 before the child binds it.
    """
    if not is_frozen():
        if trigger == "relay":
            _log("ignoring update request: not running as a packaged exe")
        return False
    if settings.disable_autoupdate:
        _log("auto-update disabled (UFO_AGENT_DISABLE_AUTOUPDATE)")
        return False

    state = _read_update_state(storage)

    # 1. Boot-success / cleanup: did a prior update reach its target?
    pending = state.get("target_version")
    if pending and not is_newer(pending, AGENT_VERSION):  # AGENT_VERSION >= target
        exe = Path(sys.executable)
        old_exe = exe.with_suffix(exe.suffix + ".old")
        if old_exe.exists():
            try:
                old_exe.unlink()
                _log(f"update to {AGENT_VERSION} confirmed; removed {old_exe.name}")
            except OSError as exc:
                _log(f"could not remove {old_exe.name}: {exc}")
        _write_update_state(storage, {"target_version": AGENT_VERSION, "attempts": 0, "phase": "done"})
        state = {}

    # 2. Find the target version.
    if target_version:
        target = target_version.lstrip("vV")
        exe_url = sha_url = None  # resolved from the matching release below
        latest = check_latest(settings.update_repo)
        if latest and latest["version"] == target:
            exe_url, sha_url = latest["exe_url"], latest["sha_url"]
        if not exe_url:
            _log(f"requested version {target} is not the latest release; skipping")
            return False
    else:
        latest = check_latest(settings.update_repo)
        if latest is None:
            return False
        target, exe_url, sha_url = latest["version"], latest["exe_url"], latest["sha_url"]

    if not is_newer(target, AGENT_VERSION):
        if trigger == "relay":
            _log(f"already up to date (running {AGENT_VERSION}, latest {target})")
        return False

    # 3. Loop guard: don't keep retrying a target that won't take.
    if state.get("target_version") == target and state.get("attempts", 0) >= settings.update_max_attempts:
        _log(f"giving up on {target} after {state['attempts']} attempts; staying on {AGENT_VERSION}")
        return False

    _log(f"update available: {AGENT_VERSION} -> {target} (trigger={trigger})")
    exe = Path(sys.executable)
    new_exe = exe.with_name(f"{exe.name}.new-{target}")

    try:
        # 4. Download + verify.
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            _download(client, exe_url, new_exe)
            expected = client.get(sha_url).text.strip().split()[0].lower()
        actual = _sha256(new_exe)
        if actual != expected:
            _log(f"sha256 mismatch (expected {expected[:12]}…, got {actual[:12]}…); aborting")
            new_exe.unlink(missing_ok=True)
            return False

        # 5. Pre-swap self-test while the old exe is still canonical.
        if not _self_test(new_exe):
            _log("candidate exe failed self-test; keeping current version")
            new_exe.unlink(missing_ok=True)
            return False

        # 6. Record the attempt BEFORE swapping (a mid-swap crash still counts).
        attempts = (state.get("attempts", 0) + 1) if state.get("target_version") == target else 1
        _write_update_state(storage, {"target_version": target, "attempts": attempts, "phase": "swapping"})

        # 7. Swap + spawn the child FIRST (so we never exit mid-swap), THEN ask
        #    the caller to release port 8766. The child has a bind-retry loop, so
        #    it tolerates the old process taking a moment to let go.
        _apply_update_and_restart(exe, new_exe)
        if on_shutdown is not None:
            try:
                on_shutdown()
            except Exception as exc:  # noqa: BLE001
                _log(f"on_shutdown hook error (continuing): {exc}")
        return True

    except Exception as exc:  # noqa: BLE001 — update must never crash the agent
        _log(f"update to {target} failed (staying on {AGENT_VERSION}): {exc}")
        try:
            new_exe.unlink(missing_ok=True)
        except OSError:
            pass
        return False
