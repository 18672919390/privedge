"""Live demo engine: runs the real pipeline (LDP -> signed release -> ledger -> gateway -> decision)
on a dataset and records every step as an event for the console.

Target-region ground truth is used only for the offline evaluation shown next to the answer; it
never reaches admit() or decide()."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import replace
from typing import Callable

import numpy as np

from ..adapters.standard import StandardDataset, load
from ..algorithms import ServerRelease, evaluate, fuse_variance_weighted, top_items
from ..attacks import combine, mga_fake_reports, tamper_frequencies, weight_hijack_items
from ..decision import DecisionPolicy
from ..envelope import ReleaseEnvelope, ReleaseItem, domain_hash, seal
from ..gateway import GatewayPolicy
from ..keys import Identity, KeyRegistry
from ..ldp import HASH_FAMILY
from ..ledger import BudgetPolicy, Ledger, LedgerError
from ..pipeline import ColdStartService, Publisher, summarize_reports
from ..robust import source_scores

DATASETS = {
    "meituan_trd": {"title": "美团外卖（北京 11 商圈）", "role": "主场景：新商圈开站选品",
                    "label": lambda c: f"品类#{c}"},
    "olist_brazil": {"title": "Olist 巴西电商（州×年）", "role": "跨国对照", "label": lambda c: c},
    "massive_steps": {"title": "Massive-STEPS 城市签到", "role": "高异质压力测试",
                      "label": lambda c: c.removeprefix("schema:")},
}

ATTACKS = {
    "none": "无攻击",
    "mga": "伪造用户（MGA 最大增益投毒）",
    "compromised": "被攻破发布者注入目标品类",
    "hijack": "权重劫持（谎报极小方差 + 注入）",
    "demote": "权重劫持 + 扣下真实热门",
    "negative": "负频率删除真实热门",
    "tamper": "中间人篡改摘要（不重新签名）",
    "replay": "重放旧窗口摘要",
    "equivocation": "同一数据源提交两份不同摘要",
    "impostor": "未注册密钥冒充数据源",
    "budget_burn": "第三方冒名登记、耗尽他人预算",
}
POISONING = {"mga", "compromised", "hijack", "demote", "negative"}


def _release_view(items, label) -> list[dict]:
    return [{"category": i.category, "name": label(i.category), "frequency": round(i.frequency, 5)} for i in items]


def _to_release(index: int, items) -> ServerRelease:
    return ServerRelease(index, "OLH", tuple(i.category for i in items),
                         {i.category: i.frequency for i in items}, {i.category: i.variance for i in items})


class DemoEngine:
    def __init__(self, dataset: str):
        self.name = dataset
        self.data: StandardDataset = load(dataset)
        self.label = DATASETS[dataset]["label"]
        self.dhash = domain_hash(self.data.categories, f"{dataset}-v1")
        self.registry = KeyRegistry()
        self.ledger = Ledger(BudgetPolicy(max_epsilon_per_window=4.0, min_users=1000), registry=self.registry)
        self.service = ColdStartService(self.registry, self.ledger)
        self.publishers = {}
        for server in self.data.servers:
            identity = Identity.create(server, "source")
            identity.enroll(self.registry)
            self.publishers[server] = Publisher(identity, self.dhash, self.data.domain)
        self.window_seq = 0
        self.previous: dict[str, ReleaseEnvelope] = {}
        self.lock = threading.Lock()

    def describe(self) -> dict:
        meta = DATASETS[self.name]
        return {
            "name": self.name, "title": meta["title"], "role": meta["role"], "domain": self.data.domain,
            "servers": [{"id": s, "users": int(len(self.data.events[s]))} for s in self.data.servers],
            "attacks": ATTACKS,
        }

    def run(self, target: str, epsilon: float = 2.0, top_m: int = 40, users: int = 5000,
            attack: str = "none", attackers: int = 1, beta: float = 0.10, seed: int | None = None,
            emit: Callable[[dict], None] | None = None) -> dict:
        with self.lock:
            return self._run(target, epsilon, top_m, users, attack, attackers, beta, seed, emit or (lambda e: None))

    def _run(self, target, epsilon, top_m, users, attack, attackers, beta, seed, emit) -> dict:
        if target not in self.data.servers:
            raise ValueError(f"unknown target {target}")
        if attack not in ATTACKS:
            raise ValueError(f"unknown attack {attack}")
        started = time.perf_counter()
        seed = int(seed if seed is not None else np.random.default_rng().integers(0, 2**31 - 1))
        rng = np.random.default_rng(seed)
        self.window_seq += 1
        window = f"W{self.window_seq:03d}"
        policy = GatewayPolicy(self.dhash, self.data.domain, frozenset({window}), target,
                               "2099-01-01", max_epsilon=4.0, min_users=1000)
        sources = [s for s in self.data.servers if s != target]
        bad = [sources[int(i)] for i in rng.permutation(len(sources))[:max(1, attackers)]] if attack != "none" else []
        truth_dist = self.data.distribution(target)
        truth = top_items(truth_dist, 10)
        source_mean = np.mean([self.data.distribution(s) for s in sources], axis=0)
        pool = np.argsort(-source_mean, kind="stable")[30:80]
        targets = sorted(int(x) for x in rng.choice(pool, size=3, replace=False)) if attack in POISONING else []
        events: list[dict] = []

        def log(kind: str, **payload):
            event = {"type": kind, "t_ms": round((time.perf_counter() - started) * 1000, 1), **payload}
            events.append(event)
            emit(event)

        log("start", target=target, window=window, epsilon=epsilon, top_m=top_m, users=users,
            attack=attack, attack_name=ATTACKS[attack], attackers=bad,
            attack_targets=[{"category": t, "name": self.label(t)} for t in targets])

        envelopes: list[ReleaseEnvelope] = []
        naive: list[ServerRelease] = []
        per_source: dict[str, dict] = {}
        for index, source in enumerate(sources):
            publisher = self.publishers[source]
            events_s = self.data.events[source]
            sample = events_s[rng.permutation(len(events_s))[:users]]
            reports = publisher.collect(sample, epsilon, rng)
            n_fake = 0
            if attack == "mga" and source in bad:
                fake = mga_fake_reports(targets, int(round(beta * len(sample))), epsilon, rng)
                reports, n_fake = combine(reports, fake), fake.n
            log("collect", source=source, users=int(len(sample)), fake_users=n_fake, epsilon=epsilon)
            raw_items = summarize_reports(reports, self.data.domain, top_m, False)[0]
            if source in bad and attack in {"compromised", "hijack", "demote", "negative"}:
                env = self._malicious(publisher, reports, top_m, window, attack, targets)
                raw_items = env.items
                log("attack", source=source, detail=f"{ATTACKS[attack]}：以合法密钥签名发布恶意摘要")
            else:
                env = publisher.release(reports, top_m, window, self.ledger, defense=True)
            filt = env.defense or {}
            log("release", source=source, release_id=env.release_id, digest=env.digest()[:16],
                items=len(env.items), removed_reports=filt.get("removed_reports", 0),
                flagged_items=[self.label(i) for i in filt.get("flagged_items", [])],
                preview=_release_view(env.items[:5], self.label))
            log("ledger", source=source, release_id=env.release_id, seq=len(self.ledger.entries) - 1,
                entry_hash=self.ledger.head[:16], spent=self.ledger.spent(source, window))
            envelopes.append(env)
            naive.append(_to_release(index, raw_items))
            per_source[source] = {"source": source, "users": int(len(sample)), "fake_users": n_fake,
                                  "removed_reports": filt.get("removed_reports", 0), "bad": source in bad}

        envelopes, naive = self._network_attack(attack, bad, envelopes, naive, window, log)
        decision, record = self.service.predict(envelopes, None, policy, DecisionPolicy(k=10, report_m=top_m))
        for rej in record["admission"]["rejected"]:
            log("reject", **rej)
        for sid in record["admission"]["accepted"]:
            log("admit", source=sid)
        baseline = fuse_variance_weighted(naive, 10) if naive else []

        def score(prediction):
            if not prediction:
                return {"recall": 0.0, "ndcg": 0.0, "attack_success": None}
            metrics = evaluate(truth_dist, truth, prediction, set(prediction))
            return {"recall": round(metrics["recall"], 4), "ndcg": round(metrics["ndcg"], 4),
                    "attack_success": round(len(set(targets) & set(prediction)) / 3, 4) if targets else None}

        accepted_releases = [_to_release(i, env.items) for i, env in enumerate(envelopes)
                             if env.source_id in record["admission"]["accepted"]]
        scores = {sc.index: sc for sc in source_scores(accepted_releases)} if len(accepted_releases) >= 3 else {}
        for i, sid in enumerate(record["admission"]["accepted"]):
            if sid in per_source and i in scores:
                per_source[sid]["anomaly_score"] = round(scores[i].score, 2)
                per_source[sid]["flagged"] = scores[i].flagged
        for rej in record["admission"]["rejected"]:
            if rej["source_id"] in per_source:
                per_source[rej["source_id"]]["rejected"] = rej["code"]

        result = {
            "run_id": f"run-{uuid.uuid4().hex[:10]}", "dataset": self.name, "target": target, "window": window,
            "seed": seed, "epsilon": epsilon, "top_m": top_m, "users": users,
            "attack": attack, "attack_name": ATTACKS[attack], "attackers": bad,
            "attack_targets": [{"category": t, "name": self.label(t)} for t in targets],
            "decision": {**decision.to_json(),
                         "top_k_named": [{"category": c, "name": self.label(c), "support": decision.support.get(c),
                                          "injected": c in targets, "in_truth": c in set(truth)}
                                         for c in decision.top_k]},
            "baseline": {"method": "无防御基线（不验签、不过滤、不截尾、方差加权）",
                         "top_k_named": [{"category": c, "name": self.label(c), "injected": c in targets,
                                          "in_truth": c in set(truth)} for c in baseline]},
            "evaluation": {"note": "离线评估：目标区域真实分布只用于打分，不进入网关与决策",
                           "privedge": score(decision.top_k), "baseline": score(baseline),
                           "truth_top10": [{"category": c, "name": self.label(c)} for c in truth]},
            "sources": list(per_source.values()),
            "audit": {"request_id": record["request_id"], "record_hash": record["record_hash"],
                      "ledger_head": record["ledger_head"], "ledger_chain_ok": record["ledger_chain_ok"]},
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        log("decision", state=decision.state, top_k=result["decision"]["top_k_named"], reasons=decision.reasons,
            alerts=decision.alerts, evaluation=result["evaluation"]["privedge"])
        accepted_ids = set(record["admission"]["accepted"])
        for env in envelopes:
            if env.source_id in accepted_ids and env.window_id == window:
                self.previous[env.source_id] = env
        result["events"] = events
        return result

    def _malicious(self, publisher: Publisher, reports, top_m, window, attack, targets) -> ReleaseEnvelope:
        items = summarize_reports(reports, self.data.domain, top_m, True)[0]
        if attack == "compromised":
            top_value = max(i.frequency for i in items)
            median_var = float(np.median([i.variance for i in items]))
            injected = [ReleaseItem(t, top_value, median_var) for t in targets]
            items = tuple(injected + [i for i in items if i.category not in targets])[:len(items)]
        elif attack == "hijack":
            items = weight_hijack_items(items, targets, 1e-4)
        elif attack == "demote":
            items = weight_hijack_items(items, targets, 1e-4, demote=7)
        elif attack == "negative":
            median_var = float(np.median([i.variance for i in items]))
            victims = [i.category for i in items[:3]]
            items = tuple(ReleaseItem(v, -1e6, median_var) for v in victims) + items[3:]
        return self._sign_and_log(publisher, reports.epsilon, reports.n, top_m, window, items)

    def _sign_and_log(self, publisher: Publisher, epsilon, n, top_m, window, items, log_it=True) -> ReleaseEnvelope:
        env = ReleaseEnvelope(f"rel-{uuid.uuid4().hex[:12]}", publisher.source_id, window, self.dhash, "OLH",
                              HASH_FAMILY, epsilon, n, top_m, tuple(items), 0.0, {"method": "none"})
        sealed = seal(env, publisher.identity.key_id, publisher.identity.private_key)
        if log_it:
            self.ledger.append(sealed)
        return sealed

    def _network_attack(self, attack, bad, envelopes, naive, window, log):
        if attack in POISONING or attack == "none" or not bad:
            return envelopes, naive
        victim = bad[0]
        if attack == "replay":
            victim = next((s for s in bad + [env.source_id for env in envelopes] if s in self.previous), victim)
        index = next(i for i, env in enumerate(envelopes) if env.source_id == victim)
        env = envelopes[index]
        if attack == "tamper":
            forged = tamper_frequencies(env, [c for c in range(self.data.domain)
                                              if c not in {i.category for i in env.items}][:3], 0.5)
            envelopes[index] = forged
            naive[index] = _to_release(index, forged.items)
            log("attack", source=victim, detail="中间人把 3 个未发布品类改成 0.5，未重新签名")
        elif attack == "replay":
            old = self.previous.get(victim)
            if old is None:
                log("attack", source=victim, detail="该数据源还没有旧窗口摘要可重放（请先运行一次）")
            else:
                envelopes.append(old)
                naive.append(_to_release(len(naive), old.items))
                log("attack", source=victim, detail=f"重放 {old.window_id} 窗口的旧摘要 {old.release_id}")
        elif attack == "equivocation":
            publisher = self.publishers[victim]
            twin_items = tuple(reversed(env.items))
            spent = self.ledger.spent(victim, window)
            if spent + env.epsilon <= self.ledger.policy.max_epsilon_per_window + 1e-12:
                twin = self._sign_and_log(publisher, env.epsilon, env.n_users, env.top_m, window, twin_items)
                envelopes.append(twin)
                naive.append(_to_release(len(naive), twin.items))
                log("attack", source=victim, detail="同一数据源对同一窗口签发第二份内容不同的摘要")
            else:
                log("attack", source=victim, detail="预算不足以签发第二份摘要，账本已阻止")
        elif attack == "impostor":
            impostor = Identity.create(victim, "source-impostor")
            forged = seal(replace(env, release_id=f"rel-{uuid.uuid4().hex[:12]}", nonce="", signature=""),
                          impostor.key_id, impostor.private_key)
            envelopes[index] = forged
            log("attack", source=victim, detail="用未注册的新密钥冒充该数据源签名")
        elif attack == "budget_burn":
            thief = self.publishers[next(s for s in self.publishers if s != victim)].identity
            burn = seal(replace(env, release_id=f"rel-{uuid.uuid4().hex[:12]}", nonce="", signature="", epsilon=4.0),
                        thief.key_id, thief.private_key)
            try:
                self.ledger.append(burn)
                log("attack", source=victim, detail="冒名登记成功（不应发生）")
            except LedgerError as err:
                log("attack", source=victim, detail=f"第三方以 {victim} 名义登记 ε=4 的条目，被账本拒绝：{err.code}")
        return envelopes, naive

    def ledger_view(self, limit: int = 300) -> dict:
        ok, bad = self.ledger.verify_chain()
        return {"entries": self.ledger.entries[-limit:], "total": len(self.ledger.entries),
                "chain_ok": ok, "first_bad": bad, "head": self.ledger.head,
                "budget": self.ledger.budget_table()[-200:], "registry": self.registry.describe()}

    def tamper_drill(self, seq: int) -> dict:
        """Edit a copy of the ledger and show that hash-chain verification pinpoints it."""
        if not self.ledger.entries:
            return {"error": "账本为空，请先运行一次预测"}
        seq = max(0, min(seq, len(self.ledger.entries) - 1))
        copy = Ledger(self.ledger.policy, entries=[dict(e) for e in self.ledger.entries])
        original = copy.entries[seq]["epsilon"]
        copy.entries[seq]["epsilon"] = 0.0 if original else 0.5
        ok, bad = copy.verify_chain()
        return {"edited_seq": seq, "field": "epsilon", "from": original, "to": copy.entries[seq]["epsilon"],
                "chain_ok": ok, "first_bad": bad}


_engines: dict[str, DemoEngine] = {}
_engines_lock = threading.Lock()


def engine(dataset: str) -> DemoEngine:
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset}")
    with _engines_lock:
        if dataset not in _engines:
            _engines[dataset] = DemoEngine(dataset)
        return _engines[dataset]
