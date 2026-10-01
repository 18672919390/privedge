"""Books category benchmark; metadata-only domain, globally disjoint users."""
import argparse
import ast
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ldp_protocols import estimate_frequency
from fusion import (ServerRelease, candidate_set, fuse_average,
                    fuse_censor_aware_item_context, fuse_variance_weighted)
from competitive_baselines import trimmed_frequency, rank_frequency
from metrics import (top_items, evaluate, candidate_miss_mass,
                     candidate_recall_upper_bound, migration_error)


def digest(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def prepare(ratings, metadata, years):
    csv.field_size_limit(100_000_000)
    titles = {}
    ambiguous = set()
    stats = Counter()
    with metadata.open(encoding='utf8', newline='') as handle:
        for row in csv.DictReader(handle):
            stats['metadata_rows'] += 1
            try:
                cats = ast.literal_eval(row.get('categories') or '[]')
            except (ValueError, SyntaxError):
                continue
            if not isinstance(cats, list):
                continue
            cats = tuple(sorted({c.strip() for c in cats if isinstance(c, str) and c.strip()}))
            title = row.get('Title')
            if not title or not cats:
                continue
            if title in titles and titles[title] != cats:
                ambiguous.add(title)
            titles[title] = cats
    for title in ambiguous:
        titles.pop(title, None)
    stats['ambiguous_titles_excluded'] = len(ambiguous)
    # Identical coding for public catalog and private single-category events.
    mapping = {t: cs[int(digest('category-v1:'+t), 16) % len(cs)] for t, cs in titles.items()}
    labels = sorted({c for cs in titles.values() for c in cs})
    index = {v: i for i, v in enumerate(labels)}
    catalog = Counter(mapping.values())
    chosen = {}
    with ratings.open(encoding='utf8', newline='') as handle:
        for row in csv.DictReader(handle):
            stats['rating_rows'] += 1
            if stats['rating_rows'] % 500000 == 0:
                print('Scanned', stats['rating_rows'], flush=True)
            try:
                year = datetime.fromtimestamp(int(row['review/time']), timezone.utc).year
                score = float(row['review/score'])
            except (ValueError, KeyError, OverflowError, OSError):
                stats['invalid_rating_rows'] += 1
                continue
            if not math.isfinite(score) or score < 4 or score > 5:
                continue
            stats['positive_rows_all_years'] += 1
            label = mapping.get(row.get('Title'))
            if label is None:
                continue
            stats['matched_positive_rows'] += 1
            user = row.get('User_id', '').strip()
            if not user:
                stats['missing_user_rows'] += 1
                continue
            book = row.get('Id', '').strip()
            if not book:
                stats['missing_book_rows'] += 1
                continue
            priority = digest(json.dumps(['event-v2', user, book, row['review/time'],
                                         row['review/score'], row.get('Title')], ensure_ascii=False))
            event = (priority, year, index[label], book)
            if user not in chosen or event < chosen[user]:
                chosen[user] = event
    events = {str(y): [] for y in years}
    book_events = {str(y): [] for y in years}
    selected_years = Counter()
    for user in sorted(chosen):
        _, year, item, book = chosen[user]
        selected_years[str(year)] += 1
        if year in years:
            events[str(year)].append(item)
            book_events[str(year)].append(book)
    stats['distinct_users'] = len(chosen)
    stats['selected_users_in_windows'] = sum(map(len, events.values()))
    stats['cross_server_duplicate_users'] = 0
    return dict(schema=2, years=years, labels=labels, events=events, book_events=book_events,
                catalog=[catalog[c] for c in labels], audit=dict(stats),
                selected_users_by_year=dict(sorted(selected_years.items())),
                provenance={str(p.resolve()): [p.stat().st_size, p.stat().st_mtime_ns]
                            for p in (ratings, metadata)},
                context_note='Present metadata snapshot; historical availability is NOT established.',
                selection='SHA256 minimum eligible positive event per user over ALL years; title category-v1')


def book_oracle(payload, positions, args):
    counts = {y: Counter(payload['book_events'][y][int(i)] for i in ids)
              for y, ids in positions.items()}
    # Fixed hash tie ordering avoids dependence on file order or ID lexicography.
    rank = lambda c, k: sorted(c, key=lambda x: (-c[x], digest('book-tie-v1:'+x)))[:k]
    candidates = set().union(*(set(rank(counts[str(y)], math.ceil(args.report_ratio*args.top_k)))
                              for y in args.source_years))
    target = counts[str(args.target_year)]
    truth = rank(target, args.top_k)
    return dict(book_oracle_coverage=candidate_recall_upper_bound(truth, candidates),
                book_oracle_miss_mass=sum(v for b, v in target.items() if b not in candidates)/sum(target.values()),
                book_target_topk_mass=sum(target[b] for b in truth)/sum(target.values()),
                book_target_boundary_ties=sum(v == target[truth[-1]] for v in target.values()))


def run(payload, args, estimate_cache=None):
    d = len(payload['labels'])
    m = min(d, math.ceil(args.report_ratio * args.top_k))
    if not 0 < args.top_k <= d or args.epsilon <= 0 or args.report_ratio < 1:
        raise ValueError('Invalid domain/k/epsilon/report ratio')
    for year in map(str, args.source_years + [args.target_year]):
        events = payload['events'][year]
        if len(events) < args.users:
            raise ValueError(f'{year}: only {len(events)} eligible users, need {args.users}')
    rows = []
    for seed in args.seeds:
        # Independent year streams and permutation prefixes give nested source samples.
        # Full target evaluation is offline only; it is never passed to fusion.
        positions = {str(y): np.random.default_rng(np.random.SeedSequence([seed, y, 17])).permutation(
                         len(payload['events'][str(y)]))[:args.users]
                     for y in args.source_years}
        target_size = len(payload['events'][str(args.target_year)]) if getattr(args, 'full_target', False) else args.users
        positions[str(args.target_year)] = np.random.default_rng(
            np.random.SeedSequence([seed, args.target_year, 17])).permutation(
                len(payload['events'][str(args.target_year)]))[:target_size]
        samples = {y: np.asarray(payload['events'][y])[ids] for y, ids in positions.items()}
        book_metrics = book_oracle(payload, positions, args)
        target = np.bincount(samples[str(args.target_year)], minlength=d) / target_size
        truth = top_items(target, args.top_k)
        shift = migration_error(target, [np.bincount(samples[str(y)], minlength=d)/args.users
                                        for y in args.source_years])
        releases = {'OLH': [], 'ORACLE': []}
        for server, year in enumerate(args.source_years):
            data = samples[str(year)]
            cache_key = (seed, year, args.users, args.epsilon)
            z = estimate_cache.get(cache_key) if estimate_cache is not None else None
            if z is None:
                z = estimate_frequency('OLH', data, d, args.epsilon,
                                       np.random.default_rng(np.random.SeedSequence([seed, year, 99])))
                if estimate_cache is not None:
                    estimate_cache[cache_key] = z
            for mode in releases:
                counts = z.counts if mode == 'OLH' else np.bincount(data, minlength=d)
                ids = np.argsort(-counts, kind='stable')[:m]
                variances = z.variances / args.users**2 if mode == 'OLH' else np.full(d, 1e-8)
                releases[mode].append(ServerRelease(server, mode, tuple(map(int, ids)),
                    {int(i): max(0., float(counts[i]))/args.users for i in ids},
                    {int(i): float(variances[i]) for i in ids}))
        for mode, rel in releases.items():
            candidates = candidate_set(rel)
            for context_mode in ['uniform', 'catalog']:
                q = np.ones(d) if context_mode == 'uniform' else np.array(payload['catalog'], dtype=float)
                q /= q.sum()
                predictions = dict(average=fuse_average(rel, args.top_k),
                    variance_weighted=fuse_variance_weighted(rel, args.top_k),
                    latest_source=fuse_average(rel[-1:], args.top_k),
                    trimmed=trimmed_frequency(rel, args.top_k, trim=0 if len(rel) < 3 else 1),
                    rank_frequency=rank_frequency(rel, args.top_k),
                    censor_aware=fuse_censor_aware_item_context(rel, q, m, args.top_k))
                for method, prediction in predictions.items():
                    rows.append(dict(seed=seed, release=mode, context=context_mode, method=method,
                        domain=d, users=args.users, epsilon=args.epsilon, report_m=m,
                        target_users=target_size,
                        candidate_count=len(candidates),
                        candidate_recall_upper_bound=candidate_recall_upper_bound(truth, candidates),
                        candidate_miss_mass=candidate_miss_mass(target, candidates),
                        target_topk_mass=float(target[truth].sum()),
                        **book_metrics, **shift,
                        **evaluate(target, truth, prediction, candidates)))
        print('Finished seed', seed, flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    data = ROOT / 'data/Amazon/Amazon Books Reviews'
    parser.add_argument('--ratings', type=Path, default=data/'Books_rating.csv')
    parser.add_argument('--metadata', type=Path, default=data/'books_data.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'outputs/amazon_books_categories')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--source-years', nargs='+', type=int, default=[2011, 2012])
    parser.add_argument('--target-year', type=int, default=2013)
    parser.add_argument('--users', '--users-per-server', type=int, default=1000)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--full-target', action='store_true', help='Evaluate on all retained target events, offline only')
    parser.add_argument('--epsilon', type=float, default=2)
    parser.add_argument('--top-k', type=int, default=10)
    parser.add_argument('--report-ratio', type=float, default=2)
    parser.add_argument('--seeds', nargs='+', type=int, default=list(range(2026091601, 2026091621)))
    args = parser.parse_args()
    years = args.source_years + [args.target_year]
    if len(set(years)) != len(years) or args.users <= 0 or not args.seeds:
        raise ValueError('Years must be distinct')
    if args.source_years != sorted(args.source_years) or max(args.source_years) >= args.target_year:
        raise ValueError('Source years must be ascending and precede target year')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache = args.cache or args.output_dir/'prepared.json'
    if args.prepare or not cache.exists():
        payload = prepare(args.ratings, args.metadata, years)
        cache.write_text(json.dumps(payload), encoding='utf8')
    else:
        payload = json.loads(cache.read_text(encoding='utf8'))
    if not set(years).issubset(payload['years']) or payload['schema'] != 2:
        raise ValueError('Cache mismatch: use --prepare')
    provenance = {str(p.resolve()): [p.stat().st_size, p.stat().st_mtime_ns]
                  for p in (args.ratings, args.metadata)}
    if payload['provenance'] != provenance:
        raise ValueError('Input file mismatch: use --prepare')
    print('Domain', len(payload['labels']), 'users', {y: len(v) for y,v in payload['events'].items()}, flush=True)
    rows = run(payload, args)
    with (args.output_dir/'results.csv').open('w', encoding='utf8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir/'config.json').write_text(json.dumps(vars(args), default=str, indent=2), encoding='utf8')
    groups = defaultdict(list)
    for row in rows:
        groups[(row['release'], row['context'], row['method'])].append(row)
    summary = []
    for key, group in groups.items():
        entry = dict(zip(['release', 'context', 'method'], key))
        entry['seeds'] = len(group)
        for metric in ['recall', 'ndcg', 'candidate_recall_upper_bound', 'candidate_miss_mass',
                       'book_oracle_coverage', 'book_oracle_miss_mass', 'target_topk_mass',
                       'book_target_topk_mass', 'book_target_boundary_ties', 'source_target_tv_mean']:
            values = [r[metric] for r in group]
            entry[metric] = float(np.mean(values))
            entry[metric+'_std'] = float(np.std(values, ddof=1)) if len(values)>1 else 0.
        summary.append(entry)
    (args.output_dir/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    print('Wrote', len(rows), 'rows', flush=True)


if __name__ == '__main__':
    main()
