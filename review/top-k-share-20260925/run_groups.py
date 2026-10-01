"""List groups, preview commands, or run one group from any working directory."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from experiments.catalog import GROUPS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", nargs="?", choices=list(GROUPS))
    parser.add_argument("--dry-run", action="store_true")
    args, forwarded = parser.parse_known_args()
    if not args.group:
        if forwarded:
            parser.error("Specify a group before its arguments")
        for group, (name, _, output) in GROUPS.items():
            print(f"{group:4} {name:24} outputs/{output}")
        return
    _, filename, _ = GROUPS[args.group]
    command = [sys.executable, str(ROOT / "experiments" / filename), *forwarded]
    if args.dry_run:
        print(subprocess.list2cmdline(command))
        print(f"cwd: {ROOT}")
        return
    raise SystemExit(subprocess.call(command, cwd=ROOT))


if __name__ == "__main__":
    main()
