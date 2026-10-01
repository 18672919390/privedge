import unittest
import numpy as np
from competitive_baselines import context_mixture, trimmed_frequency, rank_frequency
from fusion import ServerRelease

class CompetitiveBaselineTests(unittest.TestCase):
    def setUp(self):
        self.r=[ServerRelease(0,'OLH',(0,1),{0:.8,1:.1},{0:.01,1:.01}),ServerRelease(1,'OLH',(0,2),{0:.7,2:.6},{0:.01,2:.01}),ServerRelease(2,'OLH',(2,3),{2:.7,3:.2},{2:.01,3:.01})]
    def test_all_are_bounded_candidate_only(self):
        c={0,1,2,3}
        for prediction in (context_mixture(self.r,np.ones(4),2),trimmed_frequency(self.r,2),rank_frequency(self.r,2)):
            self.assertEqual(len(prediction),2); self.assertTrue(set(prediction)<=c)
    def test_mixture_and_trim_respond_to_outlier(self):
        self.assertIn(2,context_mixture(self.r,np.array([0.,0.,1.,0.]),2))
        self.assertNotIn(1,trimmed_frequency(self.r,2,1))
        with self.assertRaises(ValueError): trimmed_frequency(self.r,2,2)

if __name__=='__main__': unittest.main()
