"""Frozen one-factor Books diagnosis, with full-target offline evaluation."""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from amazon_books_categories import ROOT, run
import ldp_protocols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT/'outputs/amazon_books_categories_v2/prepared.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'outputs/amazon_books_diagnostic')
    args = parser.parse_args()
    payload = json.loads(args.cache.read_text(encoding='utf8'))
    assert payload['schema'] == 2
    for name, stamp in payload['provenance'].items():
        path = Path(name)
        assert [path.stat().st_size, path.stat().st_mtime_ns] == stamp, 'Stale cache'
    cases = [('base', 1000, 2, 2), ('users_5000', 5000, 2, 2),
             ('users_10000', 10000, 2, 2), ('epsilon_1', 1000, 1, 2),
             ('epsilon_4', 1000, 4, 2), ('report_10', 1000, 2, 1),
             ('report_50', 1000, 2, 5)]
    seeds = list(range(2026091701, 2026091706))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(cases=cases, seeds=seeds, source_years=[2011, 2012], target_year=2013,
                    top_k=10, full_target=True, cache=str(args.cache),
                    hash_backend='xxhash' if ldp_protocols.xxhash else 'universal_hash_fallback',
                    status='Exploratory diagnosis; 2013 already inspected, not held-out confirmation',
                    context_note=payload['context_note'])
    (args.output_dir/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    all_rows = []
    estimates = {}
    for case, users, epsilon, ratio in cases:
        config = SimpleNamespace(users=users, epsilon=epsilon, report_ratio=ratio,
                                 top_k=10, source_years=[2011, 2012], target_year=2013,
                                 seeds=seeds, full_target=True)
        print('CASE', case, flush=True)
        rows = [dict(case=case, **r) for r in run(payload, config, estimates)]
        with (args.output_dir/(case+'.csv')).open('w', newline='', encoding='utf8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        all_rows.extend(rows)
    groups = defaultdict(list)
    for r in all_rows:
        groups[(r['case'], r['release'], r['context'], r['method'])].append(r)
    summary = []
    for key, rows in groups.items():
        entry = dict(zip(['case', 'release', 'context', 'method'], key))
        entry['seeds'] = len(rows)
        for metric in ['recall', 'ndcg', 'candidate_recall_upper_bound', 'candidate_miss_mass',
                       'book_oracle_coverage', 'book_oracle_miss_mass', 'target_topk_mass',
                       'source_target_tv_mean']:
            values = np.array([r[metric] for r in rows])
            entry[metric] = float(values.mean())
            entry[metric+'_std'] = float(values.std(ddof=1))
        summary.append(entry)
    (args.output_dir/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    # Paired comparisons: identical users, noise, candidate sets within each seed.
    paired = []
    for case, *_ in cases:
        subset = [r for r in all_rows if r['case'] == case and r['release'] == 'OLH']
        baseline = {r['seed']: r for r in subset if r['method'] == 'average' and r['context'] == 'uniform'}
        for context, method in [('uniform', 'latest_source'), ('uniform', 'censor_aware'), ('catalog', 'censor_aware')]:
            rows = [r for r in subset if r['method'] == method and r['context'] == context]
            entry = dict(case=case, context=context, method=method)
            for metric in ['recall', 'ndcg']:
                delta = np.array([r[metric]-baseline[r['seed']][metric] for r in rows])
                entry[metric+'_delta'] = float(delta.mean())
                entry[metric+'_delta_std'] = float(delta.std(ddof=1))
                entry[metric+'_wins_ties_losses'] = [int((delta>1e-12).sum()), int((abs(delta)<=1e-12).sum()), int((delta < -1e-12).sum())]
            paired.append(entry)
    (args.output_dir/'paired.json').write_text(json.dumps(paired, indent=2), encoding='utf8')
    print('Wrote', len(all_rows), 'rows', flush=True)


if __name__ == '__main__':
    main()
