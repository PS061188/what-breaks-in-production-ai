"""Run each model at its API default, the setting the book reports.

Every experiment sets the API default: Haiku 4.5 with thinking off, Sonnet 5
with its default adaptive thinking at effort high.

The first recordings (up to the 14 Nov 2026 re-recording) ran Haiku 4.5 with
thinking on and Sonnet 5 at a higher effort. They are kept in the fixture
folders ending in _cli_defaults and replay with CLI_SETTINGS=cli. FINDINGS.md
has the check that found the difference.
"""

import os

CLI_DEFAULTS = os.environ.get("CLI_SETTINGS", "api") == "cli"
SUFFIX = "_cli_defaults" if CLI_DEFAULTS else ""


def api_defaults(model: str, env: dict, cmd: list):
    """The environment and command for one model call at the model's API default."""
    if CLI_DEFAULTS:
        return env, cmd
    if model.startswith("claude-haiku-4-5"):
        return {**env, "MAX_THINKING_TOKENS": "0"}, cmd
    if model.startswith("claude-sonnet-5"):
        return env, cmd + ["--effort", "high"]
    raise ValueError(f"no API default recorded for {model}; add it to shared/cli_defaults.py")
