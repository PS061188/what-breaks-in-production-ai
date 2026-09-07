"""Optional dependencies, and a readable message when one is missing.

Most of this repository replays recorded model responses and needs nothing but
the standard library. Four scripts do real work locally — two build a vector
index, two run an embedding model — and those need a package installed.

The point of this module is that the failure says so. A bare `import chromadb`
at the top of a function produces a ModuleNotFoundError traceback pointing into
someone else's code, which is a poor welcome for a reader who has just cloned
the repository to check a number.
"""


class MissingDependency(SystemExit):
    """Exit cleanly with an explanation rather than a traceback."""


def require(module: str, package: str, needed_for: str):
    """Import `module`, or exit with a message naming what to install and why."""
    try:
        return __import__(module)
    except ImportError:
        raise MissingDependency(
            f"\n  This script needs `{package}` for {needed_for}.\n"
            f"      pip install {package}\n"
            f"  Everything else in this repository replays without it — "
            f"`python3 run_all.py` will skip this script and carry on.\n"
        )
