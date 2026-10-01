import itertools
import unittest
import numpy as np

from adaptive_selection import coverage_features, select_sources
from fusion import ServerRelease


def release(index, items):
    return ServerRelease(index, "OUE", tuple(items), {i: .5/(j+1) for j,i in enumerate(items)}, dict.fromkeys(items, .01))


class AdaptiveSelectionTests(unittest.TestCase):
    def test_complementarity_and_permutation_invariance(self):
        releases = [release(0,[0,1]),release(1,[0,1]),release(2,[2,3])]
        q = np.ones(4)/4
        selected = select_sources(releases,q,2)
        self.assertEqual(selected.source_ids,(0,2))
        self.assertEqual(selected,select_sources(releases[::-1],q,2))
        self.assertGreater(selected.marginal_gains[1],0)

    def test_submodularity_and_greedy_bound_on_small_instance(self):
        releases = [release(0,[0,1]),release(1,[1,2]),release(2,[2,3]),release(3,[0,3])]
        q=np.array([.4,.3,.2,.1])
        _,q,features=coverage_features(releases,q)
        def value(indices):
            return float(np.max(features[list(indices)],axis=0)@q) if indices else 0.
        subsets=[set(c) for size in range(5) for c in itertools.combinations(range(4),size)]
        for a in subsets:
            for b in subsets:
                if a <= b:
                    for s in set(range(4))-b:
                        self.assertGreaterEqual(value(a|{s})-value(a)+1e-12,value(b|{s})-value(b))
        result=select_sources(releases,q,2)
        optimum=max(value(c) for c in itertools.combinations(range(4),2))
        self.assertGreaterEqual(result.coverage_utility,(1-np.exp(-1))*optimum)

    def test_full_budget_and_random_reproducibility(self):
        releases=[release(2,[0,1]),release(5,[2,3]),release(8,[0,2])]
        q=np.ones(4)
        for strategy in ('coverage','relevance','random'):
            result=select_sources(releases,q,3,strategy=strategy,seed=31)
            self.assertEqual(set(result.source_ids),{2,5,8})
            self.assertAlmostEqual(sum(result.marginal_gains),result.coverage_utility)
            self.assertEqual(result,select_sources(releases[::-1],q,3,strategy=strategy,seed=31))

    def test_invalid_inputs(self):
        releases=[release(0,[0,1])]
        for q in (np.zeros(2),np.array([np.nan,1]),np.array([-1,2])):
            with self.assertRaises(ValueError):
                select_sources(releases,q,1)
        with self.assertRaises(ValueError):
            select_sources(releases,np.ones(2),2)


if __name__=='__main__':
    unittest.main()
