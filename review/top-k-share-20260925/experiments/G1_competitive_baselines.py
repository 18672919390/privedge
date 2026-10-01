"""G1: Frozen comparison of competitive baselines and current methods."""
from pathlib import Path
from dataclasses import replace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.validation.desktop_validation import build_cases, execute
import numpy as np

def main():
    root = Path(__file__).resolve().parents[1]
    cases = build_cases("core")
    cases = {name: cases[name] for name in ("desktop_weak", "desktop_strong", "desktop_no_context")}
    cases["desktop_misleading"] = replace(cases["desktop_weak"], context_condition="misleading")
    seeds = [int(s.generate_state(1)[0]) for s in np.random.SeedSequence(2026091505).spawn(20)]
    execute(root / "outputs/formal_baseline_comparison", cases, seeds, 4)

if __name__ == "__main__":
    main()
