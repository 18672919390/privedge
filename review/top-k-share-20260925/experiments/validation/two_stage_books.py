"""Stage-one source reconstruction on the prepared Amazon Books category data."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fusion import ServerRelease, candidate_set
from ldp_protocols import estimate_frequency
from metrics import candidate_miss_mass, evaluate, top_items
from two_stage_transfer import candidate_top_k, equal_mix, reconstruct_sources, zero_filled_sources


def main():
    cache = ROOT/'outputs/amazon_books_categories_v2/prepared.json'
    output = ROOT/'outputs/two_stage_books'
    output.mkdir(parents=True, exist_ok=True)
    payload = json.loads(cache.read_text(encoding='utf8'))
    seeds = list(range(2026091701, 2026091706))
    cases = [('users_1000',1000), ('users_10000',10000)]
    d, k, m, epsilon = len(payload['labels']), 10, 20, 2
    rows=[]
    for case, users in cases:
        for seed in seeds:
            samples={}
            for year in [2011,2012]:
                ids=np.random.default_rng(np.random.SeedSequence([seed,year,17])).permutation(len(payload['events'][str(year)]))[:users]
                samples[year]=np.asarray(payload['events'][str(year)])[ids]
            target=np.bincount(payload['events']['2013'],minlength=d).astype(float); target/=target.sum()
            truth=top_items(target,k); releases=[]
            for server,year in enumerate([2011,2012]):
                z=estimate_frequency('OLH',samples[year],d,epsilon,np.random.default_rng(np.random.SeedSequence([seed,year,99])))
                ids=np.argsort(-z.counts,kind='stable')[:m]
                releases.append(ServerRelease(server,'OLH',tuple(map(int,ids)),
                    {int(i):max(0.,float(z.counts[i]))/users for i in ids},
                    {int(i):float(z.variances[i])/users**2 for i in ids}))
            candidates=candidate_set(releases)
            direct=equal_mix(zero_filled_sources(releases,d))
            recon_results=reconstruct_sources(releases,d,prior_strength=.1,shift_tolerance=.02)
            reconstructed=equal_mix(np.asarray([x.probabilities for x in recon_results]))
            for method,distribution in [('direct_average',direct),('reconstructed_average',reconstructed)]:
                prediction=candidate_top_k(distribution,releases,k)
                rows.append(dict(case=case,seed=seed,method=method,users=users,domain=d,
                                 candidate_count=len(candidates),candidate_miss_mass=candidate_miss_mass(target,candidates),
                                 all_reconstructions_converged=all(x.converged for x in recon_results),
                                 max_dual_gap=max(x.dual_gap for x in recon_results),
                                 **evaluate(target,truth,prediction,candidates)))
            print(case,seed,flush=True)
    with (output/'results.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    groups=defaultdict(list)
    for r in rows:groups[(r['case'],r['method'])].append(r)
    summary=[]
    for (case,method),records in groups.items():
        item=dict(case=case,method=method,seeds=len(records))
        for metric in ['recall','ndcg','coverage','candidate_miss_mass']:
            values=np.array([r[metric] for r in records]);item[metric]=float(values.mean());item[metric+'_std']=float(values.std(ddof=1))
        summary.append(item)
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    (output/'manifest.json').write_text(json.dumps(dict(cache=str(cache),seeds=seeds,cases=cases,
        epsilon=epsilon,top_k=k,report_m=m,prior_strength=.1,shift_tolerance=.02,
        purpose='Exploratory stage-one preparation; target data used for evaluation only'),indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
