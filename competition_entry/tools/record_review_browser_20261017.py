"""Record observed E34 browser checks; never manufacture experimental output."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "competition_entry/docs/v4/backend_validation/20261017_review_delivery"
BROWSER = OUT / "browser"

checks = [
    ("overview_presets", "Four guided steps populate parameters and do not start a run", "overview_full.png"),
    ("seed_validation", "Negative seed disables execution and displays an error", "normal_state.txt"),
    ("normal", "TRD target 商圈3, epsilon=1, m=20, users=5000, seed=20260929; DEGRADED, 10 categories, Recall=.7, NDCG=.8968", "final_normal_state.txt"),
    ("seed_replay", "Replay retains parameters and numerical outcome, with a new run/window/audit identity", "normal_replay_state.txt"),
    ("changed_parameters", "Editing seed marks displayed result as an older completed snapshot", "normal_replay_state.txt"),
    ("parameter_carry", "Normal-to-attack action carries the completed request and seed without execution", "final_hijack_state.txt"),
    ("hijack", "Signed malicious values may pass gateway; baseline AS 3/3, PrivEdge AS 1/3; DEGRADED remains explicit", "final_hijack_expanded_state.txt"),
    ("as_rounding_correction", "1/3 and rounded API .3333 no longer produce a false mismatch warning", "attack_metrics.png"),
    ("tamper", "One invalid signature rejected; remaining nine sources accepted; single-source rejection differs from whole-request refusal", "tamper_state.txt"),
    ("ledger_copy", "Corrupted copy returns REFUSED / LEDGER_CORRUPTED; original 60 entries and chain head stay unchanged", "final_ledger_state.txt"),
    ("experiments", "Descriptive four-method evidence displayed; strict A8 NOT_RUN; historical evidence distinguished from rerunning", "final_experiments_state.txt"),
    ("massive", "Petaling Jaya@2018, epsilon=2, m=40, users=5000, seed=1; named categories, NORMAL, Recall=.5, NDCG=.806", "final_massive_state.txt"),
    ("dataset_isolation", "Switch during Massive execution leaves Olist waiting with no late Massive result", "dataset_switch_no_late_result.txt"),
    ("completed_result_retention", "Returning to TRD prediction restores run-e5146d3c82 without rerunning", "prediction.png"),
    ("sweep_complete", "All ten attack types finish and retain per-row run IDs", "final_sweep_state.txt"),
    ("sweep_interrupted", "Leaving an active sweep stops subsequent client requests; return shows incomplete 0/10 and does not resume automatically", "sweep_cancel_state.txt"),
    ("download", "Actual browser JSON downloaded from the fresh final package contains request, seed, result and exact final E34 source/data identity", "normal_export_final.json"),
]
export = json.loads((BROWSER / "normal_export_final.json").read_text(encoding="utf-8-sig"))
live = json.loads((OUT / "fresh_live_launcher.json").read_text(encoding="utf-8"))
assert export["program_identity"] == live["checks"]["version"]
record = {
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Observed local browser engineering acceptance; not new statistical evidence or a second physical computer",
    "checks": [{"name": n, "passed": True, "observation": o, "evidence": f} for n, o, f in checks],
    "passed_count": len(checks),
    "browser_console_errors_at_final_check": [],
    "export_top_level_keys": sorted(export),
    "final_export_identity_matches_fresh_package_api": True,
    "final_export_source_fingerprint": export["program_identity"]["source_fingerprint_sha256"],
    "final_export_sha256": hashlib.sha256((BROWSER / "normal_export_final.json").read_bytes()).hexdigest(),
    "screenshots": {},
    "limitations": [
        "Only normal-run JSON exports were downloaded through the real browser; other export types have automated checks.",
        "normal_export.json preserves the earlier pre-AS-fix download. normal_export_final.json was downloaded from the final fresh package and its exact identity matches that package API. Final screenshots and AS checks use the frozen final assets.",
        "The first seed validation/change-state observations are summarized here; not every intermediate state has a dedicated screenshot.",
        "An initial AS-rounding warning was a product display defect and was fixed, rebuilt and rechecked.",
        "Initial automation attempts using an incorrect option value or locator failed without indicating product defects.",
        "Page result history and ledger are in memory; browser refresh and service restart have different effects.",
        "Client cancellation does not guarantee termination of already-started server computation.",
    ],
}
for name in ("overview.png", "overview_full.png", "prediction.png", "attack.png", "attack_metrics.png", "ledger.png", "experiments.png", "sweep.png", "final_package_guide.png"):
    p = BROWSER / name
    record["screenshots"][name] = {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
(OUT / "browser_validation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": len(checks), "output": str(OUT / "browser_validation.json")}, ensure_ascii=False))
