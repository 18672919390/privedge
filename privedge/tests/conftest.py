import numpy as np
import pytest

from privedge.envelope import domain_hash
from privedge.gateway import GatewayPolicy
from privedge.keys import Identity, KeyRegistry
from privedge.ledger import BudgetPolicy, Ledger
from privedge.pipeline import ColdStartService, Publisher, publish_context

DOMAIN = 60
CATEGORIES = [f"c{i}" for i in range(DOMAIN)]
DHASH = domain_hash(CATEGORIES, "test-v1")


def zipf_distribution(rng: np.random.Generator, shift: int) -> np.ndarray:
    ranks = (np.arange(DOMAIN) + shift) % DOMAIN
    weights = 1.0 / (ranks + 1.0) ** 1.1
    weights *= rng.uniform(0.8, 1.2, size=DOMAIN)
    return weights / weights.sum()


@pytest.fixture
def world():
    return build_world()


def build_world():
    rng = np.random.default_rng(7)
    registry = KeyRegistry()
    ledger = Ledger(BudgetPolicy(max_epsilon_per_window=4.0, min_users=500), registry=registry)
    publishers, data = [], {}
    for index in range(5):
        identity = Identity.create(f"region-{index}", "source")
        identity.enroll(registry)
        publishers.append(Publisher(identity, DHASH, DOMAIN))
        dist = zipf_distribution(rng, shift=0)
        data[identity.principal] = rng.choice(DOMAIN, size=4000, p=dist)
    target_identity = Identity.create("target", "context")
    target_identity.enroll(registry)
    other_identity = Identity.create("region-0", "context")
    other_identity.enroll(registry)
    target_context = publish_context(target_identity, "W1", "2016-12-31", zipf_distribution(rng, 0),
                                     "test-osm", DHASH, ledger)
    policy = GatewayPolicy(DHASH, DOMAIN, frozenset({"W1"}), "target", "2017-01-01",
                           max_epsilon=4.0, min_users=500)
    service = ColdStartService(registry, ledger)
    return {
        "rng": rng, "registry": registry, "ledger": ledger, "publishers": publishers, "data": data,
        "target_identity": target_identity, "other_identity": other_identity,
        "target_context": target_context, "policy": policy, "service": service,
    }


def release_all(world, epsilon=2.0, window="W1", defense=True):
    envelopes = []
    for index, publisher in enumerate(world["publishers"]):
        rng = np.random.default_rng(100 + index)
        reports = publisher.collect(world["data"][publisher.source_id], epsilon, rng)
        envelopes.append(publisher.release(reports, 20, window, world["ledger"], defense=defense))
    return envelopes
