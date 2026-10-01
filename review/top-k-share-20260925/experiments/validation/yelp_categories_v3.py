"""Fair Yelp category migration experiment with global one-event users.

The audit cache is built from all Yelp cities and years before this experiment.
This runner uses six predeclared cities in a leave-one-city-out design. It does
not use target review counts to build context; target events are offline truth.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fusion import (ServerRelease, candidate_set, fuse_average,
                    fuse_censor_aware_item_context, fuse_public_context_weighted,
                    fuse_robust_adaptive_context, fuse_variance_weighted)
from ldp_protocols import estimate_frequency
from metrics import (candidate_miss_mass, candidate_recall_upper_bound,
                     evaluate, migration_error, top_items)


DEFAULT_CITIES = [
    'Philadelphia | PA', 'Tucson | AZ', 'Tampa | FL',
    'Indianapolis | IN', 'Nashville | TN', 'New Orleans | LA',
]


def load_audit(path: Path):
    payload = json.loads(path.read_text(encoding='utf8'))
    if payload.get('schema') != 1 or not payload.get('selected_cities'):
        raise ValueError('audit cache is missing schema or selected cities')
    labels = payload['labels']
    index = {label: i for i, label in enumerate(labels)}
    events = {}
    contexts = {}
    for city in payload['selected_cities']:
        counts = payload['events'].get(city, {})
        values = []
        for item, count in counts.items():
            values.extend([int(item)] * int(count))
        if len(values) < 10:
            continue
        events[city] = np.asarray(values, dtype=np.int64)
        vector = np.zeros(len(labels), dtype=float)
        for label, count in payload['catalog'].get(city, {}).items():
            if label in index:
                vector[index[label]] = float(count)
        if vector.sum() <= 0:
            raise ValueError(f'empty public catalog for {city}')
        contexts[city] = vector / vector.sum()
    return payload, labels, events, contexts


def release_for(data, server_id, domain, users, epsilon, report_m, mode, seed):
    if mode == 'ORACLE':
        counts = np.bincount(data, minlength=domain).astype(float)
        ids = np.argsort(-counts, kind='stable')[:report_m]
        return ServerRelease(
            server_id, mode, tuple(map(int, ids)),
            {int(i): float(counts[i]) / users for i in ids},
            {int(i): 1e-8 for i in ids},
        )
    result = estimate_frequency(
        'OLH', data, domain, epsilon,
        np.random.default_rng(np.random.SeedSequence(seed)),
    )
    ids = np.argsort(-result.counts, kind='stable')[:report_m]
    return ServerRelease(
        server_id, mode, tuple(map(int, ids)),
        {int(i): max(0.0, float(result.counts[i])) / users for i in ids},
        {int(i): float(result.variances[i]) / users**2 for i in ids},
    )


def context_only(context, candidates, k):
    items = np.asarray(sorted(candidates), dtype=int)
    return items[np.argsort(-context[items], kind='stable')[:k]].astype(int).tolist()


def run_case(payload, labels, events, contexts, cities, targets, users_list,
             seeds, epsilon, top_k, report_ratio, release_modes):
    domain = len(labels)
    report_m = min(domain, int(np.ceil(report_ratio * top_k)))
    rows = []
    release_cache = {}
    for target_city in targets:
        sources = [city for city in cities if city != target_city]
        target_values = events[target_city]
        target = np.bincount(target_values, minlength=domain).astype(float)
        target /= target.sum()
        truth = top_items(target, top_k)
        source_truth = []
        for source in sources:
            source_vector = np.bincount(events[source], minlength=domain).astype(float)
            source_truth.append(source_vector / source_vector.sum())
        shift = migration_error(target, source_truth)
        context_variants = {
            'uniform': np.ones(domain, dtype=float) / domain,
            'correct_catalog': contexts[target_city],
            'swapped_catalog': contexts[sources[0]],
        }
        for users in users_list:
            if any(len(events[city]) < users for city in [target_city] + sources):
                raise ValueError(f'{target_city}: not enough users for {users}')
            for seed in seeds:
                sampled = {}
                for source_id, source in enumerate(sources):
                    rng = np.random.default_rng(np.random.SeedSequence(
                        [seed, cities.index(source), 17]
                    ))
                    sampled[source] = events[source][rng.permutation(len(events[source]))[:users]]
                for release_mode in release_modes:
                    releases = []
                    for source_id, source in enumerate(sources):
                        key = (source, users, seed, release_mode)
                        if key not in release_cache:
                            release_cache[key] = release_for(
                            sampled[source], cities.index(source), domain, users, epsilon,
                            report_m, release_mode,
                            [seed, cities.index(source), users, 99],
                            )
                        releases.append(release_cache[key])
                    candidates = candidate_set(releases)
                    base_predictions = {
                        'average': fuse_average(releases, top_k),
                        'variance_weighted': fuse_variance_weighted(releases, top_k),
                    }
                    for context_name, context in context_variants.items():
                        predictions = dict(base_predictions)
                        if context_name == 'uniform':
                            # No public target signal: context-aware methods
                            # must fall back to the identifiable average baseline.
                            predictions.update({
                                'context_weighted': base_predictions['average'],
                                'censor_aware': base_predictions['average'],
                                'robust_context': base_predictions['average'],
                            })
                        else:
                            predictions.update({
                                'context_weighted': fuse_public_context_weighted(
                                    releases, context, report_m, top_k
                                ),
                                'censor_aware': fuse_censor_aware_item_context(
                                    releases, context, report_m, top_k
                                ),
                                'robust_context': fuse_robust_adaptive_context(
                                    releases, context, report_m, top_k, min(3, len(releases))
                                ),
                            })
                        predictions.update({
                            'context_only': context_only(context, candidates, top_k),
                            'context_full_domain': top_items(context, top_k),
                        })
                        for method, prediction in predictions.items():
                            support = set(range(domain)) if method == 'context_full_domain' else candidates
                            rows.append(dict(
                                target_city=target_city, source_cities=';'.join(sources),
                                seed=seed, users=users, release=release_mode,
                                context=context_name, method=method, domain=domain,
                                source_count=len(sources), report_m=report_m,
                                candidate_count=len(candidates),
                                candidate_recall_upper_bound=candidate_recall_upper_bound(
                                    truth, support
                                ),
                                candidate_miss_mass=candidate_miss_mass(target, support),
                                target_top10_mass=float(target[truth].sum()),
                                **shift,
                                **evaluate(target, truth, prediction, support),
                            ))
                print(f'{target_city} users={users} seed={seed} complete', flush=True)
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['users'], row['release'], row['context'], row['method'])].append(row)
    summary = []
    metrics = ['recall', 'ndcg', 'candidate_recall_upper_bound', 'candidate_miss_mass',
               'source_target_tv_mean', 'source_mean_bias_l1']
    for key, records in groups.items():
        item = dict(zip(['users', 'release', 'context', 'method'], key))
        item['targets'] = len({r['target_city'] for r in records})
        item['seeds_per_target'] = len({r['seed'] for r in records})
        item['observations'] = len(records)
        for metric in metrics:
            values = np.asarray([float(r[metric]) for r in records])
            item[metric] = float(values.mean())
            item[metric + '_std'] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        summary.append(item)
    return summary


def paired_context(rows):
    grouped = defaultdict(dict)
    for row in rows:
        key = (row['target_city'], row['users'], row['release'], row['seed'], row['method'])
        grouped[key][row['context']] = row
    result = []
    for key, contexts in grouped.items():
        if 'correct_catalog' not in contexts or 'swapped_catalog' not in contexts:
            continue
        target_city, users, release, seed, method = key
        for metric in ['recall', 'ndcg']:
            result.append(dict(target_city=target_city, users=users, release=release,
                               seed=seed, method=method, metric=metric,
                               correct_minus_swapped=float(
                                   contexts['correct_catalog'][metric] - contexts['swapped_catalog'][metric]
                               ),
                               correct_minus_uniform=float(
                                   contexts['correct_catalog'][metric] - contexts['uniform'][metric]
                               )))
    return result


def summarize_paired(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['users'], row['release'], row['method'], row['metric'])].append(row)
    summary = []
    for key, records in groups.items():
        users, release, method, metric = key
        correct_swapped = np.asarray([float(r['correct_minus_swapped']) for r in records])
        correct_uniform = np.asarray([float(r['correct_minus_uniform']) for r in records])
        summary.append(dict(
            users=users, release=release, method=method, metric=metric,
            targets=len({r['target_city'] for r in records}),
            observations=len(records),
            correct_minus_swapped=float(correct_swapped.mean()),
            correct_minus_swapped_std=float(correct_swapped.std(ddof=1)) if len(records) > 1 else 0.0,
            correct_minus_uniform=float(correct_uniform.mean()),
            correct_minus_uniform_std=float(correct_uniform.std(ddof=1)) if len(records) > 1 else 0.0,
            correct_beats_swapped=int((correct_swapped > 1e-12).sum()),
            correct_beats_uniform=int((correct_uniform > 1e-12).sum()),
        ))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path,
                        default=ROOT/'outputs/data_suitability_audit/audit.json')
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT/'outputs/yelp_categories_v3')
    parser.add_argument('--cities', nargs='+', default=DEFAULT_CITIES)
    parser.add_argument('--users', nargs='+', type=int, default=[2000, 10000])
    parser.add_argument('--epsilon', type=float, default=2.0)
    parser.add_argument('--top-k', type=int, default=10)
    parser.add_argument('--report-ratio', type=float, default=2.0)
    parser.add_argument('--seeds', nargs='+', type=int,
                        default=list(range(2026092001, 2026092006)))
    parser.add_argument('--release-modes', nargs='+', choices=['OLH', 'ORACLE'],
                        default=['OLH', 'ORACLE'])
    args = parser.parse_args()
    if len(set(args.cities)) != len(args.cities) or len(args.cities) < 3:
        raise ValueError('Need at least three distinct predeclared cities')
    if args.top_k < 1 or args.report_ratio < 1 or args.epsilon <= 0:
        raise ValueError('invalid top-k, report ratio, or epsilon')
    payload, labels, events, contexts = load_audit(args.audit)
    missing = [city for city in args.cities if city not in events]
    if missing:
        raise ValueError(f'Cities missing from audit: {missing}')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(
        schema=1, audit=str(args.audit), cities=args.cities,
        target_design='leave-one-city-out; each target uses all other predeclared cities as sources',
        users=args.users, epsilon=args.epsilon, top_k=args.top_k,
        report_ratio=args.report_ratio, seeds=args.seeds,
        release_modes=args.release_modes,
        target_truth='full globally-deduplicated retained event distribution; offline evaluation only',
        context_modes=['uniform', 'correct_catalog', 'swapped_catalog'],
        context_note=payload['context_note'],
        no_target_review_counts_in_context=True,
        event_selection=payload['event_selection'],
        interpretation='Exploratory; all audited cities were inspected before this run',
    )
    (args.output_dir/'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8'
    )
    rows = run_case(payload, labels, events, contexts, args.cities, args.cities,
                    args.users, args.seeds, args.epsilon, args.top_k,
                    args.report_ratio, args.release_modes)
    with (args.output_dir/'results.csv').open('w', newline='', encoding='utf8') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir/'summary.json').write_text(
        json.dumps(summarize(rows), indent=2), encoding='utf8'
    )
    paired = paired_context(rows)
    with (args.output_dir/'paired_context.csv').open('w', newline='', encoding='utf8') as handle:
        writer = csv.DictWriter(handle, fieldnames=paired[0])
        writer.writeheader()
        writer.writerows(paired)
    (args.output_dir/'paired_context_summary.json').write_text(
        json.dumps(summarize_paired(paired), indent=2), encoding='utf8'
    )
    print(f'Wrote {len(rows)} rows', flush=True)


if __name__ == '__main__':
    main()
