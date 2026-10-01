"""Information-matched non-oracle baselines for the top-k transfer task."""
from __future__ import annotations
import numpy as np
from fusion import ServerRelease, candidate_set, _top


def _scores(releases, item, values):
    return np.asarray([values.get((r.server_id, item), 0.0) for r in releases], dtype=float)


def context_mixture(releases: list[ServerRelease], context: np.ndarray, k: int, alpha: float = .5) -> list[int]:
    """Fixed shrinkage of source average toward public q; alpha is frozen on dev data."""
    if not 0 <= alpha <= 1 or np.asarray(context).ndim != 1:
        raise ValueError("alpha must be in [0,1] and context one-dimensional")
    q=np.maximum(np.asarray(context,dtype=float),0); q=q/q.sum() if q.sum()>0 else q
    scores={i:(1-alpha)*float(np.mean([r.frequencies.get(i,0.) for r in releases]))+alpha*float(q[i]) for i in candidate_set(releases)}
    return _top(scores,k)


def trimmed_frequency(releases: list[ServerRelease], k: int, trim: int = 1) -> list[int]:
    """Per-item trimmed mean of published values, including explicit absence as zero."""
    if trim < 0 or 2*trim >= len(releases): raise ValueError("invalid trim")
    scores={i:float(np.mean(np.sort([r.frequencies.get(i,0.) for r in releases])[trim:len(releases)-trim])) for i in candidate_set(releases)}
    return _top(scores,k)


def rank_frequency(releases: list[ServerRelease], k: int, frequency_weight: float = 1.) -> list[int]:
    """Public-list rank plus frequency; no context or hidden source quality."""
    if frequency_weight < 0: raise ValueError("frequency_weight must be nonnegative")
    scores={}
    for r in releases:
        for rank,item in enumerate(r.top_items):
            scores[item]=scores.get(item,0.)+1/np.log2(rank+2)+frequency_weight*r.frequencies.get(item,0.)
    return _top(scores,k)


BASELINE_GRID = {
    "context_mixture": (0.25, 0.5, 0.75),
    "trimmed_frequency": (1,),
    "rank_frequency": (0.25, 1.0, 4.0),
}
