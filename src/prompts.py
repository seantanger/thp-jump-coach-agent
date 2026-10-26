"""Load versioned agent prompts from prompts/<agent>.v<N>.md.

Every system prompt is the shared rules in AGENTS.md followed by the agent's
own prompt, so the shared rules cannot be forgotten by any single agent.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
SHARED_RULES = ROOT / "AGENTS.md"

_VERSION_RE = re.compile(r"^(?P<agent>[a-z_]+)\.v(?P<version>\d+)\.md$")


def available_versions(agent: str) -> list[int]:
    versions = []
    for path in PROMPTS_DIR.glob(f"{agent}.v*.md"):
        match = _VERSION_RE.match(path.name)
        if match and match["agent"] == agent:
            versions.append(int(match["version"]))
    return sorted(versions)


def load_prompt(agent: str, version: int | None = None) -> str:
    """Return AGENTS.md + prompts/<agent>.v<version>.md (latest if version is None)."""
    versions = available_versions(agent)
    if not versions:
        raise FileNotFoundError(f"No prompt files for agent {agent!r} in {PROMPTS_DIR}")
    version = versions[-1] if version is None else version
    path = PROMPTS_DIR / f"{agent}.v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found (available: {versions})")
    return f"{SHARED_RULES.read_text().strip()}\n\n---\n\n{path.read_text().strip()}\n"
