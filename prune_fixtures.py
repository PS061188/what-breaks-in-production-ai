"""Delete fixtures no script asks for any more.

Fixtures are content-addressed on the request, so editing a prompt or a
max_tokens value does not overwrite the old recording — it orphans it. This
replays every chapter, notes which fixtures were actually read, and removes the
rest.

    python prune_fixtures.py --dry-run
    python prune_fixtures.py
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from run_all import CHAPTERS, ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list, do not delete")
    args = parser.parse_args()

    audit = Path(tempfile.mkstemp(prefix="fixture-audit-")[1])
    env = dict(os.environ, FIXTURE_AUDIT=str(audit))

    # Every runnable script in every chapter, not just broken/fixed — the
    # fix_*.py scripts have fixtures too, and missing one here would delete them.
    helpers = {"common.py", "normalise.py"}
    for directory, _ in CHAPTERS:
        for script in sorted((ROOT / directory).glob("*.py")):
            if script.name in helpers:
                continue
            result = subprocess.run(
                [sys.executable, str(script)], capture_output=True, text=True, env=env
            )
            if result.returncode != 0:
                print(f"{script.name} in {directory} failed — aborting rather than "
                      f"deleting fixtures on a partial run:\n{result.stderr.strip()[-400:]}")
                return 1

    # A fixture recorded under a model other than the default is NOT an orphan.
    # Replaying with default arguments only ever touches the default model, so
    # every cross-model run — the four-model comparisons this project's headline
    # findings rest on — looks unused and would be deleted. On this repo that was
    # 1,041 fixtures across Opus 5, GPT-5-mini and GPT-4.1-mini, including the
    # evidence for "the stronger model is worse at silent corruption".
    #
    # Deleting evidence because the default code path did not ask for it is
    # exactly the failure this repository documents. They are kept and counted.
    default_model = None
    try:
        sys.path.insert(0, str(ROOT))
        from shared.llm import DEFAULT_MODEL as default_model  # noqa: E402
    except Exception:
        pass

    used = set()
    for line in audit.read_text().splitlines():
        folder, key = line.split("\t")
        used.add((folder, key))
    audit.unlink()

    def is_other_model(path: Path) -> bool:
        if default_model is None:
            return False
        try:
            return json.loads(path.read_text()).get("model") != default_model
        except Exception:
            return True  # unreadable: keep it, do not delete on a guess

    removed = 0
    kept_other_model = 0
    for path in ROOT.glob("ch*/fixtures/*.json"):
        if (str(path.parent), path.stem) in used:
            continue
        if is_other_model(path):
            kept_other_model += 1
            continue
        print(f"{'would remove' if args.dry_run else 'removed'} {path.relative_to(ROOT)}")
        if not args.dry_run:
            path.unlink()
        removed += 1

    print(f"\n{removed} orphaned fixture(s); {len(used)} in use; "
          f"{kept_other_model} kept because they were recorded under a model "
          f"other than {default_model} (cross-model evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
