"""Task-level safety policy.

MVP enforcement is deliberately simple: case-insensitive keyword matching
against the task instruction. This is NOT a security boundary — it is a
seatbelt for the happy path. Real enforcement must eventually happen at the
*action* level inside the automation backend (UFO² step callbacks: "about to
click Submit on a payment form"), not just at task intake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

DEFAULT_POLICY_YAML = """\
# UFO Device Agent safety policy (MVP).
# mode: allow_all | ask_before_risky | always_ask
mode: ask_before_risky

# Apps the agent may be asked to use. (MVP: informational; matching only.)
allowed_apps:
  - Chrome
  - Notepad
  - Bambu Studio
  - Excel

# If an instruction mentions any of these, the task is denied outright.
blocked_apps:
  - Banking
  - Password Manager

# Risk categories that force a human approval before the task runs.
require_approval:
  - install_software
  - delete_files
  - submit_form
  - purchase
  - send_email
"""

# Keyword heuristics per risk category (MVP — coarse on purpose).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "install_software": ["install", "uninstall", "setup.exe", ".msi", "download and run"],
    "delete_files": ["delete", "erase", "remove file", "format ", "rm -"],
    "submit_form": ["submit"],
    "purchase": ["purchase", "buy ", "checkout", "place order", "payment"],
    "send_email": ["send email", "send an email", "send the email", "email to"],
}


class PolicyDecision(BaseModel):
    action: Literal["allow", "deny", "require_approval"]
    reason: str = ""


class Policy(BaseModel):
    mode: Literal["allow_all", "ask_before_risky", "always_ask"] = "ask_before_risky"
    allowed_apps: list[str] = Field(default_factory=list)
    blocked_apps: list[str] = Field(default_factory=list)
    require_approval: list[str] = Field(default_factory=list)

    def evaluate(self, instruction: str) -> PolicyDecision:
        text = instruction.lower()

        for app in self.blocked_apps:
            if app.lower() in text:
                return PolicyDecision(action="deny", reason=f"instruction mentions blocked app '{app}'")

        if self.mode == "always_ask":
            return PolicyDecision(action="require_approval", reason="policy mode is always_ask")

        if self.mode == "ask_before_risky":
            for category in self.require_approval:
                keywords = CATEGORY_KEYWORDS.get(category, [category.replace("_", " ")])
                for kw in keywords:
                    if kw in text:
                        return PolicyDecision(
                            action="require_approval",
                            reason=f"matched risk category '{category}' (keyword: '{kw.strip()}')",
                        )

        return PolicyDecision(action="allow", reason="no policy rule matched")


def load_policy(path: Path) -> Policy:
    """Load policy from YAML, falling back to the built-in default."""
    if not path.exists():
        return Policy.model_validate(yaml.safe_load(DEFAULT_POLICY_YAML))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Policy.model_validate(data)
