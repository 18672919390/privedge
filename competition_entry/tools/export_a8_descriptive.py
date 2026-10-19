"""Export all reviewed compare_v1 cells without changing historical run files.

This is a representation conversion, never a new experiment or preregistration.
Use --source for the extracted supplement's 补充 directory and --audit for E28.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2] / "privedge"
sys.path.insert(0, str(PROJECT))
from privedge.server.a8_descriptive import DescriptiveSummary, Registry

MAPPING = {"simple_average": "average", "variance_weighted": "variance_weighted", "trimmed_frequency": "robust_baseline", "privedge": "privedge"}
METHODS = [
    {"id": "average", "name": "简单平均", "definition": "未筛查Top-m摘要的候选并集频率等权平均，缺失补零。", "status": "COMPLETED"},
    {"id": "variance_weighted", "name": "无防御方差加权", "definition": "未筛查摘要，使用1/sqrt(mean variance)权重；不启用筛查、截尾、支持阈值和封顶。", "status": "COMPLETED"},
    {"id": "robust_baseline", "name": "坐标截尾均值（本地适配）", "definition": "候选并集缺失补零，各坐标两端各删1项后平均；不是Yin等论文完整复现。", "status": "COMPLETED"},
    {"id": "privedge", "name": "PrivEdge", "definition": "发布端筛查加留一截尾、多源支持与权重封顶；比较整套统计方案，不是单公式消融。", "status": "COMPLETED"},
]
LIMITS = [
    "原manifest未绑定预注册内容哈希，运行前冻结不能独立确认；101/211/307/401/503为复用种子，不作为新种子独立确认。",
    "区间先在目标内平均5种子，再对目标区域做2000次bootstrap；留一目标共享来源，未作多重比较校正。",
    "实验直接调用统计决策，不覆盖真实签名、网关准入和预算账本；基线与PrivEdge还存在发布端筛查差异。",
    "无攻击时不宣称比简单平均更准；无攻击场景的目标入榜率只是参照，不表示发生了攻击。",
    "双源合谋仍可成功，例如Massive在ε=2双源权重劫持下PrivEdge目标入榜率约0.8476。",
]
def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise ValueError(f"Refusing to overwrite a different archive: {path}")
    else:path.write_bytes(data)

def export(source: Path, audit_path: Path, output: Path):
    audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("all_reaggregations_match") is not True:raise ValueError("An independently checked raw-results audit is required")
    review=source/"完整复核/review-20261014T124507Z-e85059"
    review_bytes=(review/"review_manifest.json").read_bytes();review_manifest=json.loads(review_bytes)
    for name,expected in review_manifest["artifact_sha256"].items():
        p=(review/name).resolve()
        if not p.is_relative_to(review.resolve()) or sha(p.read_bytes())!=expected:raise ValueError("Review artifact mismatch")
    entries=[]
    put(output/"audit.json",audit_path.read_bytes())
    put(output/"exporter.py",Path(__file__).read_bytes())
    for run in sorted((source/"正式运行").iterdir()):
        if not run.is_dir():continue
        mbytes=(run/"manifest.json").read_bytes();m=json.loads(mbytes);dataset=m["config"]["dataset"]
        if dataset not in {"meituan_trd","olist_brazil","massive_steps"}:raise ValueError("Unknown dataset")
        if (not re.fullmatch(rf"compare_v1_{dataset}-\d{{8}}T\d{{6}}Z-[0-9a-f]{{6}}",m.get("run_id",""))
                or run.name!=m["run_id"] or m.get("experiment")!=f"compare_v1_{dataset}"):
            raise ValueError("Source identifiers must match the received directory")
        if audit["runs"][dataset]["manifest_sha256"]!=sha(mbytes):raise ValueError("Audit manifest mismatch")
        for name in ["manifest.json","results.csv","summary.json"]:
            data=(run/name).read_bytes()
            if name in m["outputs"] and sha(data)!=m["outputs"][name]:raise ValueError("Historical output mismatch")
            put(output/"source_runs"/m["run_id"]/name,data)
        cells=[];config=m["config"]
        with (review/dataset/"method_summary.csv").open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                scenario=row["scenario"]
                attackers=0 if scenario=="clean" else 2 if "2src" in scenario else 1
                beta=float(scenario.split("_b")[1]) if "_b" in scenario else 0.0
                cell={"method":MAPPING[row["method"]],"epsilon":float(row["epsilon"]),"top_m":config["top_m"],
                      "scenario":scenario,"attackers":attackers,"beta":beta,"target_scope":"all_leave_one_targets",
                      "seeds":config["seeds"],"sample_count":len(config["targets"])*len(config["seeds"]),
                      "refusal_rate":float(row["refusal_rate"]) if row.get("refusal_rate") else None}
                for metric in ["ndcg","recall","attack_success"]:
                    cell[metric]=float(row[metric]);cell[metric+"_ci95"]=[float(row[metric+"_ci95_low"]),float(row[metric+"_ci95_high"])]
                cells.append(cell)
        summary=DescriptiveSummary.model_validate({"schema_version":1,"dataset":dataset,"interpretation":"DESCRIPTIVE",
             "source_run_id":m["run_id"],"target_count":len(config["targets"]),"source_count":len(config["targets"])-1,
             "users_per_source":config["users_per_source"],"top_k":config["top_k"],"interval_unit":"target_region",
             "limitations":LIMITS,"methods":METHODS,"cells":cells})
        if len(cells)!=72:raise ValueError("Expected all 72 cells per dataset")
        summary_bytes=encoded(summary.model_dump());put(output/"summaries"/f"{dataset}.json",summary_bytes)
        entries.append({"dataset":dataset,"source_run_id":m["run_id"],"review_id":review.name,"evidence_id":"E28",
             "source_manifest_sha256":sha(mbytes),"review_manifest_sha256":sha(review_bytes),"summary_sha256":sha(summary_bytes),
             "audit_sha256":sha(audit_path.read_bytes()),"exporter_sha256":sha(Path(__file__).read_bytes())})
    if len(entries)!=3 or len({e["dataset"] for e in entries})!=3:raise ValueError("All three datasets required")
    for name in ["review_manifest.json",*review_manifest["artifact_sha256"]]:
        put(output/"source_review"/review.name/name,(review/name).read_bytes())
    registry=Registry.model_validate({"schema_version":1,"interpretation":"DESCRIPTIVE","entries":entries})
    put(output/"registry.json",encoded(registry.model_dump()))
    print(json.dumps({"datasets":len(entries),"cells":sum(72 for e in entries),"interpretation":"DESCRIPTIVE"}))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True);parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=PROJECT/"evidence_registry/a8_descriptive")
    args=parser.parse_args();export(args.source.resolve(),args.audit.resolve(),args.output.resolve())
