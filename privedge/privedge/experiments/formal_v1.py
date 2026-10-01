"""Run the ProVerif model and its negative controls (each removes one check the code performs)."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

from .runner import PACKAGE, Run

MODEL = PACKAGE.parent / "formal" / "privedge_release.pv"
DEFAULT_PROVERIF = PACKAGE.parent.parent / "tools" / "proverif" / "proverif2.05" / "proverif.exe"

# name -> (what the variant drops, [(exact old text, new text)], query expected to break)
CONTROLS = {
    "nc1_window_unsigned": (
        "窗口号不在签名内（网关只检查未签名的窗口字段）",
        [("  let body = (TAG_REL, sid, w, rid, summary) in\n  event Publish(sid, w, rid, summary);\n  out(c, (body, sign(body, sk))).",
          "  let body = (TAG_REL, sid, W1, rid, summary) in\n  event Publish(sid, w, rid, summary);\n  out(c, (w, body, sign(body, sk)))."),
         ("let Gateway(wok: window) =\n  in(c, (body: bitstring, s: bitstring));\n  let (=TAG_REL, sid: principal, w: window, rid: bitstring, summary: bitstring) = body in\n  if w = wok then",
          "let Gateway(wok: window) =\n  in(c, (w: window, body: bitstring, s: bitstring));\n  let (=TAG_REL, sid: principal, w0: window, rid: bitstring, summary: bitstring) = body in\n  if w = wok then")],
        ["Q1", "Q2"],
    ),
    "nc2_no_role_binding": (
        "注册表查询不区分密钥角色",
        [("  get registry(=r, =CTX, pkr) in\n  if checksign(s, pkr) = body then\n  get ledger(",
          "  get registry(=r, anyrole: role, pkr) in\n  if checksign(s, pkr) = body then\n  get ledger("),
         ("  get registry(=r, =CTX, pkr) in\n  if checksign(s, pkr) = body then\n  event LoggedCtx",
          "  get registry(=r, anyrole: role, pkr) in\n  if checksign(s, pkr) = body then\n  event LoggedCtx")],
        ["Q3"],
    ),
    "nc3_gateway_skips_ledger": (
        "网关不核对账本登记",
        [("  get ledger(=rid, =h((body, s))) in\n  event Accept(sid, w, rid, summary).",
          "  event Accept(sid, w, rid, summary).")],
        ["Q2"],
    ),
    "nc4_ledger_skips_signature": (
        "账本登记不验签（修复前的 ledger.append）",
        [("  let (=TAG_REL, sid: principal, w: window, rid: bitstring, summary: bitstring) = body in\n  get registry(=sid, =SRC, pks) in\n  if checksign(s, pks) = body then\n  event LoggedRel",
          "  let (=TAG_REL, sid: principal, w: window, rid: bitstring, summary: bitstring) = body in\n  event LoggedRel")],
        ["Q5"],
    ),
}

QUERY_ORDER = ["Q1", "Q2", "Q5", "Q3", "Q4", "S1", "S2"]


def run_proverif(exe: Path, path: Path) -> list[dict]:
    out = subprocess.run([str(exe), str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    results = [line for line in out.splitlines() if line.startswith("RESULT")]
    return [{"query": q, "result": line.removeprefix("RESULT ").strip(),
             "holds": line.rstrip(".").endswith("is true")} for q, line in zip(QUERY_ORDER, results)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proverif", type=Path, default=DEFAULT_PROVERIF)
    args = parser.parse_args()
    source = MODEL.read_text(encoding="utf-8")
    version = subprocess.run([str(args.proverif), "--help"], capture_output=True, text=True).stdout.splitlines()[0]
    run = Run("formal_v1", {"model": str(MODEL.name), "proverif": version, "controls": list(CONTROLS)},
              {MODEL.name: hashlib.sha256(source.encode("utf-8")).hexdigest()})
    (run.dir / MODEL.name).write_text(source, encoding="utf-8")
    report = {"main": run_proverif(args.proverif, run.dir / MODEL.name), "controls": {}}
    outputs = [MODEL.name]
    for name, (dropped, edits, expected) in CONTROLS.items():
        variant = source
        for old, new in edits:
            if variant.count(old) != 1:
                raise ValueError(f"{name}: edit anchor not unique")
            variant = variant.replace(old, new)
        variant = re.sub(r"^\(\* PrivEdge", f"(* NEGATIVE CONTROL {name}: {dropped}\n   PrivEdge", variant, count=1, flags=re.M)
        path = run.dir / f"{name}.pv"
        path.write_text(variant, encoding="utf-8")
        results = run_proverif(args.proverif, path)
        broken = [r["query"] for r in results if r["query"].startswith("Q") and not r["holds"]]
        report["controls"][name] = {"dropped_check": dropped, "expected_broken": expected,
                                    "broken": broken, "as_expected": broken == expected, "results": results}
        outputs.append(path.name)
    report["main_ok"] = all(r["holds"] != r["query"].startswith("S") for r in report["main"])
    run.write_json("results.json", report)
    run.finish(outputs + ["results.json"])
    for r in report["main"]:
        if r["query"].startswith("S"):
            print("main", r["query"], "reachable" if not r["holds"] else "UNREACHABLE", sep="\t")
        else:
            print("main", r["query"], "holds" if r["holds"] else "FAILS", sep="\t")
    for name, entry in report["controls"].items():
        print(name, "broken:", entry["broken"], "as expected" if entry["as_expected"] else "UNEXPECTED", sep="\t")
    print(run.dir)


if __name__ == "__main__":
    main()
