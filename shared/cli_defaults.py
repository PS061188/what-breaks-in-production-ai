"""Run `claude -p` at each model's API default, the setting the book reports.

Claude Code's defaults differ from the API's: it lets Claude Haiku 4.5 think
before answering (the API does not, unless asked), and it may run Claude
Sonnet 5 at a higher effort than the API's default. A pipeline calling the API
gets neither unless it asks, so every CLI experiment sets the API default:
Haiku 4.5 with thinking off, Sonnet 5 with its default adaptive thinking at
effort high.

The first recordings (up to the 14 Nov 2026 re-recording) used Claude Code's
own defaults. They are kept in the fixture folders ending in _cli_defaults and
replay with CLI_SETTINGS=cli. FINDINGS.md has the check that found the
difference.
"""

import os

CLI_DEFAULTS = os.environ.get("CLI_SETTINGS", "api") == "cli"
SUFFIX = "_cli_defaults" if CLI_DEFAULTS else ""


def api_defaults(model: str, env: dict, cmd: list):
    """The environment and command for one `claude -p` call at the model's API default."""
    if CLI_DEFAULTS:
        return env, cmd
    if model.startswith("claude-haiku-4-5"):
        return {**env, "MAX_THINKING_TOKENS": "0"}, cmd
    if model.startswith("claude-sonnet-5"):
        return env, cmd + ["--effort", "high"]
    raise ValueError(f"no API default recorded for {model}; add it to shared/cli_defaults.py")
