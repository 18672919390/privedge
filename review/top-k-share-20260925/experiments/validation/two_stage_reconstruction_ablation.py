"""One-change-at-a-time diagnosis of stage-one reconstruction mismatch."""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from experiment import ExperimentConfig, _release
from fusion import ServerRelease, candidate_set
from ldp_protocols import estimate_frequency
from metrics import candidate_miss_mass, evaluate, top_items
from two_stage_synthetic import problem
from two_stage_transfer import (candidate_top_k, equal_mix,
    fit_candidate_target_mixture, fit_target_mixture, reconstruct_candidate_tail,
    reconstruct_sources, zero_filled_sources)


def variants(releases, domain):
    """Ordered ablation: tolerance, reduced domain, then censoring."""
    direct = zero_filled_sources(releases, domain)
    definitions = {
        'direct': direct,
        'full_shift_002': np.asarray([x.probabilities for x in reconstruct_sources(
            releases, domain, prior_strength=.1, shift_tolerance=.02)]),
        'full_shift_0': np.asarray([x.probabilities for x in reconstruct_sources(
            releases, domain, prior_strength=.1, shift_tolerance=0)]),
        'full_shift_0_reported_only': np.asarray([x.probabilities for x in reconstruct_sources(
            releases, domain, prior_strength=.1, shift_tolerance=0, use_censoring=False)]),
        'candidate_tail': np.asarray([x.probabilities for x in reconstruct_candidate_tail(
            releases, domain, prior_strength=.1)]),
        'candidate_tail_reported_only': np.asarray([x.probabilities for x in reconstruct_candidate_tail(
            releases, domain, prior_strength=.1, use_censoring=False)]),
    }
    return definitions


def source_diagnostics(reconstructed, truth, candidates, k=10):
    ids = np.array(sorted(candidates), dtype=int)
    full_l1 = np.mean([np.abs(row-source).sum() for row,source in zip(reconstructed,truth)])
    candidate_l1 = np.mean([np.abs(row[ids]-source[ids]).sum() for row,source in zip(reconstructed,truth)])
    recalls=[]
    for row,source in zip(reconstructed,truth):
        predicted=ids[np.argsort(-row[ids],kind='stable')[:k]]
        actual=np.argsort(-source,kind='stable')[:k]
        recalls.append(len(set(predicted)&set(actual))/k)
    return full_l1, candidate_l1, float(np.mean(recalls))


def summarize(rows, keys):
    groups=defaultdict(list)
    for row in rows:groups[tuple(row[k] for k in keys)].append(row)
    result=[]
    for key,records in groups.items():
        item=dict(zip(keys,key));item['observations']=len(records)
        for metric in ['recall','ndcg','coverage','candidate_miss_mass','source_full_l1',
                       'source_candidate_l1','source_topk_recall']:
            if metric not in records[0]:continue
            values=np.array([r[metric] for r in records],float)
            item[metric]=float(values.mean());item[metric+'_std']=float(values.std(ddof=1)) if len(values)>1 else 0.
        result.append(item)
    return result


def run_synthetic(output):
    seeds=[int(x.generate_state(1)[0]) for x in np.random.SeedSequence(2026091801).spawn(20)]
    config=ExperimentConfig(domain=128,server_count=6,users_per_server=5000,epsilon=2,
                            top_k=10,report_ratio=2,mechanisms=('OLH',),rounds=1)
    rows=[]
    for position,seed in enumerate(seeds,1):
        sources,targets,_,_=problem(seed)
        releases=[_release(i,p,'OLH',config,np.random.default_rng(np.random.SeedSequence([seed,i,41])))
                  for i,p in enumerate(sources)]
        candidates=candidate_set(releases); reconstructed=variants(releases,config.domain)
        diagnostics={name:source_diagnostics(value,sources,candidates) for name,value in reconstructed.items()}
        for concentration in [25,75,250]:
            _,_,contexts,_=problem(seed,context_concentration=concentration)
            for target_id in range(2):
                truth=top_items(targets[target_id],config.top_k)
                for name,value in reconstructed.items():
                    equal=equal_mix(value)
                    fitted=fit_candidate_target_mixture(value,contexts[target_id],releases,ridge=.1)
                    full_fit=fit_target_mixture(value,contexts[target_id],ridge=.1)
                    for stage,distribution in [('equal',equal),('target_mix',fitted.probabilities),
                                               ('target_mix_full_metric',full_fit.probabilities)]:
                        prediction=candidate_top_k(distribution,releases,config.top_k)
                        full_l1,candidate_l1,source_recall=diagnostics[name]
                        rows.append(dict(seed=seed,target=target_id,context_concentration=concentration,
                            variant=name,stage=stage,method=name+'_'+stage,
                            source_full_l1=full_l1,source_candidate_l1=candidate_l1,
                            source_topk_recall=source_recall,
                            candidate_miss_mass=candidate_miss_mass(targets[target_id],candidates),
                            **evaluate(targets[target_id],truth,prediction,candidates)))
        print('synthetic',position,'/',len(seeds),flush=True)
    with (output/'synthetic_results.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    summary=summarize(rows,['context_concentration','variant','stage'])
    (output/'synthetic_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return rows,summary


def run_books(output):
    payload=json.loads((ROOT/'outputs/amazon_books_categories_v2/prepared.json').read_text(encoding='utf8'))
    seeds=list(range(2026091701,2026091706));rows=[];domain=len(payload['labels'])
    target=np.bincount(payload['events']['2013'],minlength=domain).astype(float);target/=target.sum()
    truth=top_items(target,10)
    for users in [1000,10000]:
        for position,seed in enumerate(seeds,1):
            releases=[]
            for server,year in enumerate([2011,2012]):
                order=np.random.default_rng(np.random.SeedSequence([seed,year,17])).permutation(len(payload['events'][str(year)]))[:users]
                data=np.asarray(payload['events'][str(year)])[order]
                z=estimate_frequency('OLH',data,domain,2,np.random.default_rng(np.random.SeedSequence([seed,year,99])))
                ids=np.argsort(-z.counts,kind='stable')[:20]
                releases.append(ServerRelease(server,'OLH',tuple(map(int,ids)),
                    {int(i):max(0.,float(z.counts[i]))/users for i in ids},
                    {int(i):float(z.variances[i])/users**2 for i in ids}))
            candidates=candidate_set(releases)
            for name,value in variants(releases,domain).items():
                prediction=candidate_top_k(equal_mix(value),releases,10)
                rows.append(dict(users=users,seed=seed,variant=name,method=name+'_equal',
                    candidate_miss_mass=candidate_miss_mass(target,candidates),
                    **evaluate(target,truth,prediction,candidates)))
            print('books',users,position,'/',len(seeds),flush=True)
    with (output/'books_results.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    summary=summarize(rows,['users','variant'])
    (output/'books_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return rows,summary


def paired(rows, scope_keys, baseline_variant='direct'):
    units=defaultdict(dict)
    for row in rows:
        key=tuple(row[k] for k in scope_keys)+(row.get('stage','equal'),)
        units[key][row['variant']]=row
    result=[]
    for variant in sorted({r['variant'] for r in rows} - {baseline_variant}):
        for stage in sorted({r.get('stage','equal') for r in rows}):
            deltas=[]
            for key,group in units.items():
                if key[-1]==stage and variant in group and baseline_variant in group:
                    deltas.append(float(group[variant]['recall'])-float(group[baseline_variant]['recall']))
            values=np.asarray(deltas)
            result.append(dict(variant=variant,stage=stage,units=len(values),
                recall_delta=float(values.mean()),wins_ties_losses=[int((values>1e-12).sum()),
                int((abs(values)<=1e-12).sum()),int((values < -1e-12).sum())]))
    return result


def main():
    output=ROOT/'outputs/two_stage_reconstruction_ablation';output.mkdir(parents=True,exist_ok=True)
    manifest=dict(status='Exploratory paired ablation, not held-out confirmation',
        source_seed_root=2026091801,synthetic_seeds=20,books_seeds=list(range(2026091701,2026091706)),
        prior_strength=.1,ridge=.1,contexts=[25,75,250],epsilon=2,k=10,m=20,
        stages=['equal','target_mix (candidate plus tail distance)','target_mix_full_metric'],
        caveat='Reduced coordinates change prior geometry; compression is not by itself a new observation.',
        sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__),ROOT/'two_stage_transfer.py',ROOT/'censor_estimator.py']})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    synthetic,synthetic_summary=run_synthetic(output)
    books,books_summary=run_books(output)
    report=dict(status='Exploratory mismatch diagnosis on previously inspected seeds.',
        variants=['direct','full_shift_002','full_shift_0','full_shift_0_reported_only',
                  'candidate_tail','candidate_tail_reported_only'],
        synthetic_paired=paired(synthetic,['context_concentration','seed','target']),
        books_paired=paired(books,['users','seed']))
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(synthetic_summary=synthetic_summary,books_summary=books_summary,
                          paired=report),indent=2),flush=True)


if __name__=='__main__':main()
