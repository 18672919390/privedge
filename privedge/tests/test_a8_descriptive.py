"""Real delivered evidence plus isolated tampering; never change source runs."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from privedge.server import a8_descriptive as reader
from privedge.server.a8_evidence import a8_evidence
from privedge.server.app import app

def sha(data):return hashlib.sha256(data).hexdigest()

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    archive=tmp_path/"descriptive"
    shutil.copytree(reader.ARCHIVE,archive)
    monkeypatch.setattr(reader,"ARCHIVE",archive)
    monkeypatch.setattr(reader,"REGISTRY",archive/"registry.json")
    return archive

def test_delivered_raw_results_are_descriptive_and_keep_strict_registration_empty():
    strict_before = a8_evidence()
    with TestClient(app) as client:
        response=client.get("/api/evidence/a8/descriptive")
    assert response.status_code==200
    data=response.json()
    assert data["status"]=="AVAILABLE" and data["interpretation"]=="DESCRIPTIVE"
    assert sum(len(v["cells"]) for v in data["datasets"].values())==216
    for dataset,n in [("meituan_trd",11),("olist_brazil",6),("massive_steps",7)]:
        d=data["datasets"][dataset]
        assert d["status"]=="DESCRIPTIVE" and d["target_count"]==n and d["interval_unit"]=="target_region"
        assert not d["provenance"]["historical_preregistration_bound"]
        assert all(c["sample_count"]==5*n for c in d["cells"])
        assert len(d["limitations"])>=3
    adverse=next(c for c in data["datasets"]["massive_steps"]["cells"] if c["method"]=="privedge" and c["epsilon"]==2 and c["scenario"]=="weight_hijack_2src")
    assert adverse["attack_success"]==pytest.approx(0.8476190476190476)
    assert a8_evidence() == strict_before

@pytest.mark.parametrize("target",["manifest","raw","original_summary","review","snapshot","summary","audit","exporter"])
def test_tampering_hides_descriptive_numbers(isolated,target):
    registry=json.loads((isolated/"registry.json").read_text(encoding="utf-8"));entry=registry["entries"][0]
    source=isolated/"source_runs"/entry["source_run_id"]
    review=isolated/"source_review"/entry["review_id"]
    paths={"manifest":source/"manifest.json","raw":source/"results.csv","original_summary":source/"summary.json",
           "review":review/"review_manifest.json","snapshot":review/entry["dataset"]/"preregistration_snapshot.md",
           "summary":isolated/"summaries"/(entry["dataset"]+".json"),"audit":isolated/"audit.json","exporter":isolated/"exporter.py"}
    paths[target].write_bytes(b"changed")
    data=reader.descriptive_evidence()
    assert data["status"]=="INVALID" and data["datasets"][entry["dataset"]]["cells"]==[]

@pytest.mark.parametrize("fault",["confirmation","nan","unpaired","sample_count","wrong_seeds","missing_scenario","users"])
def test_invalid_exports_rejected_even_when_export_digest_is_updated(isolated,fault):
    p=isolated/"registry.json";registry=json.loads(p.read_text(encoding="utf-8"));entry=registry["entries"][0]
    export=isolated/"summaries"/(entry["dataset"]+".json");summary=json.loads(export.read_text(encoding="utf-8"))
    if fault=="confirmation":summary["interpretation"]="CONFIRMATORY"
    elif fault=="nan":summary["cells"][0]["ndcg"]=float("nan")
    elif fault=="unpaired":summary["cells"].pop()
    elif fault=="sample_count":summary["cells"][0]["sample_count"]+=5
    elif fault=="wrong_seeds":
        for c in summary["cells"]:c["seeds"]=[13,17,19,23,29]
    elif fault=="missing_scenario":summary["cells"]=[c for c in summary["cells"] if c["scenario"]!="clean"]
    else:summary["users_per_source"]+=1
    data=json.dumps(summary).encode();export.write_bytes(data);entry["summary_sha256"]=sha(data);p.write_text(json.dumps(registry),encoding="utf-8")
    assert reader.descriptive_evidence()["datasets"][entry["dataset"]]["cells"]==[]

def test_descriptive_registry_reloads_and_rejects_external_paths(isolated):
    p=isolated/"registry.json";r=json.loads(p.read_text(encoding="utf-8"))
    assert reader.descriptive_evidence()["status"]=="AVAILABLE"
    r["entries"][0]["source_run_id"]="../escape";p.write_text(json.dumps(r),encoding="utf-8")
    assert reader.descriptive_evidence()["status"]=="INVALID"
    r["entries"]=[];p.write_text(json.dumps(r),encoding="utf-8")
    assert reader.descriptive_evidence()["status"]=="NOT_REGISTERED"
