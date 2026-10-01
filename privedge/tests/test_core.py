import inspect
from dataclasses import replace

import numpy as np
import pytest

from conftest import DOMAIN, DHASH, release_all
from privedge import attacks, ldp
from privedge.algorithms import research_olh, verify_core_integrity
from privedge.decision import DEGRADED, NORMAL, REFUSED, DecisionPolicy, decide
from privedge.envelope import ReleaseEnvelope, ReleaseItem, seal, verify_signature
from privedge.gateway import admit
from privedge.keys import Identity
from privedge.ledger import LedgerError
from privedge.pipeline import ColdStartService, publish_context
from privedge.robust import filter_fake_reports


def test_research_core_is_byte_identical():
    assert all(verify_core_integrity().values())


@pytest.mark.parametrize("epsilon", [0.5, 1.0, 4.0])
def test_olh_matches_research_core_bit_for_bit(epsilon):
    data = np.random.default_rng(1).integers(0, 50, size=1500)
    a = research_olh(data, 50, epsilon, np.random.default_rng(9))
    b = ldp.estimate(data, 50, epsilon, np.random.default_rng(9))
    assert np.array_equal(a.counts, b.counts)
    assert np.allclose(a.variances, b.variances)


def test_olh_is_unbiased_on_average():
    rng = np.random.default_rng(3)
    data = rng.choice(20, size=20000, p=np.linspace(2, 1, 20) / np.linspace(2, 1, 20).sum())
    estimate = ldp.estimate(data, 20, 1.0, rng)
    truth = np.bincount(data, minlength=20)
    assert np.max(np.abs(estimate.counts - truth)) < 5 * np.sqrt(estimate.variances.max())


def test_signature_detects_any_edit(world):
    env = release_all(world)[0]
    public_key = world["registry"].lookup(env.key_id)[0]
    assert verify_signature(env, public_key)
    assert not verify_signature(replace(env, epsilon=0.1), public_key)
    assert not verify_signature(attacks.tamper_frequencies(env, [59], 0.5), public_key)


def test_ledger_chain_and_budget(world):
    release_all(world, epsilon=2.0)
    ledger = world["ledger"]
    assert ledger.verify_chain() == (True, None)
    release_all(world, epsilon=2.0)  # second release on same window: total 4.0 = limit
    with pytest.raises(LedgerError) as err:
        release_all(world, epsilon=0.5)
    assert err.value.code == "BUDGET_EXCEEDED"
    ledger.entries[2]["epsilon"] = 0.0
    ok, bad = ledger.verify_chain()
    assert not ok and bad == 2


def test_ledger_rejects_budget_burning_by_third_parties(world):
    envs = release_all(world, epsilon=1.0)
    victim = envs[0]
    thief = world["publishers"][1].identity
    for rid, key in (("burn-foreign", thief), ("burn-unknown", Identity.create(victim.source_id, "source"))):
        forged = seal(replace(victim, release_id=rid, nonce="", signature="", epsilon=3.0), key.key_id, key.private_key)
        with pytest.raises(LedgerError) as err:
            world["ledger"].append(forged)
        assert err.value.code in {"PRINCIPAL_MISMATCH", "SIGNATURE_INVALID"}
    assert world["ledger"].spent(victim.source_id, "W1") == 1.0


def test_gateway_rejections(world):
    envs = release_all(world)
    policy, registry, ledger = world["policy"], world["registry"], world["ledger"]

    result = admit(envs + [envs[0]], world["target_context"], policy, registry, ledger)
    assert [r["code"] for r in result.rejected] == ["REPLAYED"]
    assert result.context_status == "OK"

    tampered = attacks.tamper_frequencies(envs[1], [59], 0.5)
    assert admit([tampered], None, policy, registry, ledger).rejected[0]["code"] == "SIGNATURE_INVALID"

    impostor = Identity.create("region-1", "source-impostor")
    forged = seal(replace(envs[1], signature=""), impostor.key_id, impostor.private_key)
    assert admit([forged], None, policy, registry, ledger).rejected[0]["code"] == "UNKNOWN_KEY"

    stolen = world["publishers"][2].identity
    wrong_principal = seal(replace(envs[1], signature=""), stolen.key_id, stolen.private_key)
    assert admit([wrong_principal], None, policy, registry, ledger).rejected[0]["code"] == "PRINCIPAL_MISMATCH"

    old = world["publishers"][0].release(
        world["publishers"][0].collect(world["data"]["region-0"], 1.0, np.random.default_rng(5)),
        20, "W0", ledger)
    assert admit([old], None, policy, registry, ledger).rejected[0]["code"] == "STALE_WINDOW"

    unlogged = seal(replace(envs[3], release_id="rel-unlogged", nonce="", signature=""),
                    envs[3].key_id, world["publishers"][3].identity.private_key)
    assert admit([unlogged], None, policy, registry, ledger).rejected[0]["code"] == "NOT_IN_LEDGER"

    wrong_domain = replace(policy, domain_hash="0" * 64)
    assert admit([envs[2]], None, wrong_domain, registry, ledger).rejected[0]["code"] == "DOMAIN_MISMATCH"


def test_context_checks(world):
    envs = release_all(world)
    policy, registry, ledger = world["policy"], world["registry"], world["ledger"]
    other = publish_context(world["other_identity"], "W1", "2016-12-31", np.ones(DOMAIN), "test-osm", DHASH, ledger)
    assert admit(envs, other, policy, registry, ledger).context_status == "CONTEXT_REGION_MISMATCH"
    late = publish_context(world["target_identity"], "W1", "2017-03-01", np.ones(DOMAIN), "test-osm", DHASH, ledger)
    assert admit(envs, late, policy, registry, ledger).context_status == "CONTEXT_NOT_CAUSAL"
    at_start = publish_context(world["target_identity"], "W1", "2017-01-01", np.ones(DOMAIN), "test-osm", DHASH, ledger)
    assert admit(envs, at_start, policy, registry, ledger).context_status == "OK"
    forged = attacks.forge_context_values(world["target_context"], tuple(np.ones(DOMAIN)))
    assert admit(envs, forged, policy, registry, ledger).context_status == "SIGNATURE_INVALID"
    source_key = world["publishers"][0].identity
    with pytest.raises(LedgerError) as err:
        publish_context(source_key, "W1", "2016-12-31", np.ones(DOMAIN), "test-osm", DHASH, ledger)
    assert err.value.code == "PRINCIPAL_MISMATCH"
    wrong_role = seal(replace(world["target_context"], region_id=source_key.principal, nonce="", signature=""),
                      source_key.key_id, source_key.private_key)
    wrong_role_policy = replace(policy, target_region=source_key.principal)
    assert admit(envs, wrong_role, wrong_role_policy, registry, ledger).context_status == "PRINCIPAL_MISMATCH"


def test_mga_attack_and_publisher_filter():
    rng = np.random.default_rng(11)
    honest_values = rng.choice(DOMAIN, size=5000, p=np.linspace(3, 1, DOMAIN) / np.linspace(3, 1, DOMAIN).sum())
    targets = [55, 57, 59]
    honest = ldp.perturb(honest_values, DOMAIN, 1.0, rng)
    fake = attacks.mga_fake_reports(targets, 250, 1.0, rng)
    poisoned = attacks.combine(honest, fake)
    clean_est = ldp.aggregate(honest, DOMAIN).counts / honest.n
    poisoned_est = ldp.aggregate(poisoned, DOMAIN).counts / poisoned.n
    assert np.mean(poisoned_est[targets] - clean_est[targets]) > 0.03

    filtered, report = filter_fake_reports(poisoned, DOMAIN)
    assert set(targets) <= set(report.flagged_items)
    filtered_est = ldp.aggregate(filtered, DOMAIN).counts / filtered.n
    assert np.mean(np.abs(filtered_est[targets] - clean_est[targets])) < 0.4 * np.mean(poisoned_est[targets] - clean_est[targets])

    _, clean_report = filter_fake_reports(honest, DOMAIN)
    assert clean_report.removed_reports == 0


def test_decision_states(world):
    envs = release_all(world)
    service: ColdStartService = world["service"]
    policy = world["policy"]
    decision, record = service.predict(envs, world["target_context"], policy)
    assert decision.state == NORMAL and len(decision.top_k) == 10
    assert record["ledger_chain_ok"]

    decision, _ = service.predict(envs, None, policy)
    assert decision.state == NORMAL and decision.method == "variance_weighted_capped"

    forged = attacks.forge_context_values(world["target_context"], tuple(np.ones(DOMAIN)))
    decision, _ = service.predict(envs, forged, policy)
    assert decision.state == DEGRADED and decision.reasons[0]["code"] == "CONTEXT_UNVERIFIED"

    decision, _ = service.predict(envs[:2], world["target_context"], policy)
    assert decision.state == REFUSED


def test_compromised_publisher_is_excluded(world):
    envs = release_all(world)
    bad = world["publishers"][4]
    items = attacks.compromised_publisher_items(envs[4], [50, 52, 54], 0.2)
    malicious = seal(replace(envs[4], release_id="rel-bad", items=items, nonce="", signature=""),
                     bad.identity.key_id, bad.identity.private_key)
    ledger = world["ledger"]
    ledger._spent[(bad.source_id, "W1")] = 0.0
    ledger.append(malicious)
    targets = {50, 52, 54}
    decision, _ = world["service"].predict(envs[:4] + [malicious], world["target_context"], world["policy"])
    assert decision.state == NORMAL
    assert any(r["code"] == "SOURCE_ANOMALY" for r in decision.alerts)

    admission = admit(envs[:4] + [malicious], world["target_context"], world["policy"],
                      world["registry"], ledger)
    undefended = decide(admission, DecisionPolicy(winsorize=False, min_item_support=1))
    assert len(targets & set(undefended.top_k)) == 3
    assert len(targets & set(decision.top_k)) <= 1


def _signed_variant(world, index, envs, release_id, items):
    publisher = world["publishers"][index]
    env = seal(replace(envs[index], release_id=release_id, items=items, nonce="", signature=""),
               publisher.identity.key_id, publisher.identity.private_key)
    world["ledger"]._spent[(publisher.source_id, "W1")] = 0.0
    world["ledger"].append(env)
    return env


def test_equivocating_source_cannot_count_twice(world):
    envs = release_all(world)
    twin = _signed_variant(world, 4, envs, "rel-twin",
                           attacks.compromised_publisher_items(envs[4], [50, 52, 54], 0.2))
    result = admit(envs + [twin], None, world["policy"], world["registry"], world["ledger"])
    assert [r["code"] for r in result.rejected] == ["EQUIVOCATION", "EQUIVOCATION"]
    assert envs[4].source_id not in {env.source_id for env in result.accepted}


def test_duplicate_categories_are_malformed(world):
    envs = release_all(world)
    doubled = _signed_variant(world, 3, envs, "rel-dup", envs[3].items + envs[3].items[:1])
    assert admit([doubled], None, world["policy"], world["registry"], world["ledger"]).rejected[0]["code"] == "MALFORMED"


@pytest.mark.parametrize("winsorize", [True, False])
def test_support_rule_theorem_under_arbitrary_adversaries(winsorize):
    """Every output item is published by at least t - f honest sources, whatever f < t sources send."""
    from privedge.algorithms import ServerRelease
    from privedge.decision import robust_top_k

    rng = np.random.default_rng(2026)
    for trial in range(400):
        n, m, k = int(rng.integers(3, 11)), int(rng.integers(5, 25)), 10
        t = int(rng.integers(1, min(n, 4) + 1))
        f = int(rng.integers(0, t))
        releases = []
        for s in range(n):
            if s < f:
                items = rng.choice(DOMAIN, size=int(rng.integers(1, DOMAIN)), replace=False)
                freqs = rng.choice([rng.uniform(-1, 10), 1e6, 0.0]) * rng.random(len(items))
                variances = 10.0 ** rng.uniform(-12, 2, size=len(items))
            else:
                items = rng.choice(DOMAIN, size=m, replace=False)
                freqs = np.sort(rng.dirichlet(np.ones(m)))[::-1]
                variances = np.full(m, 1e-4)
            ordered = sorted(zip(items.tolist(), freqs.tolist(), variances.tolist()), key=lambda x: (-x[1], x[0]))
            releases.append(ServerRelease(s, "OLH", tuple(i for i, _, _ in ordered),
                                          {i: v for i, v, _ in ordered}, {i: w for i, _, w in ordered}))
        policy = DecisionPolicy(k=k, report_m=m, min_item_support=t, winsorize=winsorize)
        top, _ = robust_top_k(releases, None, policy)
        honest_support: dict[int, int] = {}
        for release in releases[f:]:
            for item in release.top_items:
                honest_support[item] = honest_support.get(item, 0) + 1
        assert all(honest_support.get(item, 0) >= t - f for item in top), (trial, n, t, f)


def test_weight_cap_limits_variance_underreporting(world):
    envs = release_all(world)
    items = attacks.weight_hijack_items(envs[4].items, [50, 52, 54], variance_scale=1e-4, demote=7)
    hijacker = _signed_variant(world, 4, envs, "rel-hijack", items)
    admission = admit(envs[:4] + [hijacker], None, world["policy"], world["registry"], world["ledger"])
    honest = set(decide(admit(envs[:4], None, world["policy"], world["registry"], world["ledger"])).top_k)
    capped = decide(admission)
    uncapped = decide(admission, DecisionPolicy(weight_cap=None))
    assert len(honest & set(capped.top_k)) > len(honest & set(uncapped.top_k))
    assert len(honest & set(capped.top_k)) >= 8


def test_negative_frequencies_cannot_delete_items(world):
    envs = release_all(world)
    honest = decide(admit(envs[:4], None, world["policy"], world["registry"], world["ledger"])).top_k
    victims = honest[:3]
    median_var = float(np.median([item.variance for item in envs[4].items]))
    poison = tuple(ReleaseItem(v, -1e6, median_var) for v in victims) + tuple(
        item for item in envs[4].items if item.category not in victims)[: len(envs[4].items) - 3]
    deleter = _signed_variant(world, 4, envs, "rel-negative", poison)
    admission = admit(envs[:4] + [deleter], None, world["policy"], world["registry"], world["ledger"])
    assert set(victims) <= set(decide(admission).top_k)
    assert not set(victims) & set(decide(admission, DecisionPolicy(clip_floor=None)).top_k)


def test_legitimate_regional_specialty_is_not_injected_by_one_source(world):
    envs = release_all(world)
    decision, _ = world["service"].predict(envs, world["target_context"], world["policy"])
    assert all(count >= 2 for count in decision.support.values())


def test_inference_interfaces_cannot_receive_target_truth():
    forbidden = {"truth", "target_distribution", "target_events", "target_counts", "ground_truth"}
    for fn in (admit, decide, ColdStartService.predict):
        assert not forbidden & set(inspect.signature(fn).parameters)
