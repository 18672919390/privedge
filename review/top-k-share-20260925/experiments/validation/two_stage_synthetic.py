"""Two-target simulation for the target-aware second transfer stage."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiment import ExperimentConfig, _release
from fusion import candidate_set
from metrics import candidate_miss_mass, evaluate, top_items
from two_stage_transfer import (candidate_top_k, equal_mix, fit_target_mixture,
                                reconstruct_sources, zero_filled_sources)


def problem(seed, domain=128, server_count=6, context_concentration=250):
    """Two targets share sources; target and context are independent latent draws."""
    root = np.random.SeedSequence(seed)
    source_rng, target_rng, context_rng = map(np.random.default_rng, root.spawn(3))
    sources = []
    for server in range(server_count):
        center = np.full(domain, 0.15)
        block = np.arange(server * 16, server * 16 + 32) % domain
        center[block[:8]] = 8.0
        center[block[8:]] = 1.5
        sources.append(source_rng.dirichlet(center * 3.0))
    source_weights = np.array([
        [.55, .25, .10, .05, .03, .02],
        [.03, .05, .10, .22, .25, .35],
    ])
    centers = source_weights @ np.asarray(sources)
    targets = [target_rng.dirichlet(500 * center) for center in centers]
    contexts = [context_rng.dirichlet(context_concentration * center) for center in centers]
    return sources, targets, contexts, source_weights


def main():
    output = ROOT/'outputs/two_stage_synthetic'
    output.mkdir(parents=True, exist_ok=True)
    seeds = [int(x.generate_state(1)[0]) for x in np.random.SeedSequence(2026091801).spawn(20)]
    config = ExperimentConfig(domain=128, server_count=6, users_per_server=5000,
                              epsilon=2, top_k=10, report_ratio=2,
                              mechanisms=('OLH',), rounds=1)
    manifest = dict(seeds=seeds, domain=128, servers=6, users_per_server=5000,
                    epsilon=2, top_k=10, report_m=20, prior_strength=.1,
                    shift_tolerance=.02, mixture_ridge=.1,
                    context_concentrations=[25,75,250],
                    target_generation='Independent Dirichlet(500*latent mixture)',
                    context_generation='Independent Dirichlet(c*same latent mixture)',
                    information_boundary='Methods receive releases and public context only')
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    rows = []
    pair_rows = []
    for run_index, seed in enumerate(seeds, 1):
        sources, targets, _, true_weights = problem(seed)
        releases = [_release(i, p, 'OLH', config,
                             np.random.default_rng(np.random.SeedSequence([seed, i, 41])))
                    for i, p in enumerate(sources)]
        candidates = candidate_set(releases)
        direct = zero_filled_sources(releases, config.domain)
        rebuilt_result = reconstruct_sources(releases, config.domain,
                                             prior_strength=.1, shift_tolerance=.02)
        rebuilt = np.asarray([r.probabilities for r in rebuilt_result])
        shared = dict(direct_equal=equal_mix(direct), reconstructed_equal=equal_mix(rebuilt))
        for concentration in manifest['context_concentrations']:
            _, _, contexts, _ = problem(seed, context_concentration=concentration)
            predictions = [dict(), dict()]
            learned_weights = []
            for target_id in range(2):
                direct_fit = fit_target_mixture(direct, contexts[target_id], ridge=.1)
                rebuilt_fit = fit_target_mixture(rebuilt, contexts[target_id], ridge=.1)
                swapped = fit_target_mixture(rebuilt, contexts[1-target_id], ridge=.1)
                oracle_fit = fit_target_mixture(np.asarray(sources), contexts[target_id], ridge=.1)
                learned_weights.append(rebuilt_fit.weights)
                distributions = {**shared, 'direct_target_mix': direct_fit.probabilities,
                                 'reconstructed_target_mix': rebuilt_fit.probabilities,
                                 'reconstructed_swapped_context': swapped.probabilities,
                                 'oracle_source_target_mix': oracle_fit.probabilities,
                                 'context_only': contexts[target_id]}
                truth = top_items(targets[target_id], config.top_k)
                for method, distribution in distributions.items():
                    prediction = candidate_top_k(distribution, releases, config.top_k)
                    predictions[target_id][method] = prediction
                    result = evaluate(targets[target_id], truth, prediction, candidates)
                    rows.append(dict(seed=seed, target=target_id, context_concentration=concentration,
                                 method=method,
                                 candidate_miss_mass=candidate_miss_mass(targets[target_id], candidates),
                                 source_reconstruction_l1=float(np.mean([
                                     np.abs(rebuilt[i]-sources[i]).sum() for i in range(config.server_count)])),
                                 zero_fill_source_l1=float(np.mean([
                                     np.abs(equal_mix(direct[i:i+1])-sources[i]).sum()
                                     for i in range(config.server_count)])),
                                 weight_l1=float(np.abs(rebuilt_fit.weights-true_weights[target_id]).sum()),
                                 all_reconstructions_converged=all(r.converged for r in rebuilt_result),
                                 **result))
            for method in predictions[0]:
                a, b = set(predictions[0][method]), set(predictions[1][method])
                pair_rows.append(dict(seed=seed, context_concentration=concentration, method=method,
                                      target_topk_overlap=len(a & b)/config.top_k,
                                      weight_distance_l1=float(np.abs(learned_weights[0]-learned_weights[1]).sum())))
        print(f'seed {run_index}/{len(seeds)}', flush=True)
    with (output/'results.csv').open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    groups = defaultdict(list)
    for r in rows: groups[(r['context_concentration'],r['method'])].append(r)
    pair_groups = defaultdict(list)
    for r in pair_rows: pair_groups[(r['context_concentration'],r['method'])].append(r)
    summary = []
    for (concentration,method), records in groups.items():
        item = dict(context_concentration=concentration,method=method, observations=len(records))
        for metric in ['recall','ndcg','candidate_miss_mass','source_reconstruction_l1',
                       'zero_fill_source_l1','weight_l1']:
            values=np.array([r[metric] for r in records]); item[metric]=float(values.mean()); item[metric+'_std']=float(values.std(ddof=1))
        item['target_topk_overlap'] = float(np.mean([r['target_topk_overlap'] for r in pair_groups[(concentration,method)]]))
        item['weight_distance_l1'] = float(np.mean([r['weight_distance_l1'] for r in pair_groups[(concentration,method)]]))
        summary.append(item)
    (output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
