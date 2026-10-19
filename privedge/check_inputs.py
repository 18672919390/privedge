"""Check all three datasets and the built frontend before starting the console."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parent


def check(root: Path = ROOT) -> list[str]:
    failures = []
    for name in ("meituan_trd", "olist_brazil", "massive_steps"):
        folder = root / "data" / name
        try:
            metadata = json.loads((folder / "domain.json").read_text(encoding="utf-8"))
            expected = metadata["file_sha256"]
            if "private_events.csv.gz" not in expected:
                raise ValueError("domain.json does not register private_events.csv.gz")
            for filename, sha in expected.items():
                path = (folder / filename).resolve()
                if not path.is_relative_to(folder.resolve()):
                    raise ValueError("Invalid data path")
                if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                    failures.append(f"{name}/{filename}: SHA-256 mismatch")
        except (OSError, KeyError, ValueError) as error:
            failures.append(f"{name}: {error}")
    try:
        dist = root / "web" / "dist"
        html = (dist / "index.html").read_text(encoding="utf-8")
        assets = re.findall(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', html)
        if not assets:
            failures.append("web/dist/index.html has no built assets")
        for asset in assets:
            path = (dist / asset.lstrip("/")).resolve()
            if not path.is_relative_to(dist.resolve()) or not path.is_file():
                failures.append(f"Missing/invalid built asset: {asset}")
    except OSError as error:
        failures.append(f"web/dist: {error}")
    return failures


if __name__ == "__main__":
    errors = check()
    for error in errors:
        print("[error]", error)
    if not errors:
        print("All three datasets and built frontend assets verified.")
    sys.exit(1 if errors else 0)
