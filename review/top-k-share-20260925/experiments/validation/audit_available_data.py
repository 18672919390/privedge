"""Data suitability audit, not algorithm selection or a deployment replay."""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from metrics import top_items, evaluate, candidate_miss_mass


def lines(path):
    with path.open(encoding='utf8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    data = ROOT/'data/Yelp Dataset'
    out = ROOT/'outputs/data_suitability_audit'
    out.mkdir(parents=True, exist_ok=True)
    businesses = {}
    labels = set()
    catalogs = defaultdict(Counter)
    city_counts = Counter()
    audit = Counter()
    for row in lines(data/'yelp_academic_dataset_business.json'):
        audit['business_rows'] += 1
        cats = sorted({c.strip() for c in (row.get('categories') or '').split(',') if c.strip()})
        city, state = row.get('city', '').strip(), row.get('state', '').strip()
        if not city or not state or not cats:
            continue
        # Geography uses city AND state to avoid merging homonymous cities.
        key = city+' | '+state
        book = row['business_id']
        category = cats[int.from_bytes(hashlib.sha256(('category-v2:'+book).encode()).digest(), 'big') % len(cats)]
        businesses[book] = (key, category)
        labels.update(cats)
        catalogs[key][category] += 1
        city_counts[key] += 1
    labels = sorted(labels)
    index = {label: i for i, label in enumerate(labels)}
    # Choose audit cities before reading any review or assessing outcomes.
    audit_cities = sorted(city_counts, key=lambda c: (-city_counts[c], c))[:12]
    chosen = {}
    dates = Counter()
    for row in lines(data/'yelp_academic_dataset_review.json'):
        audit['review_rows'] += 1
        if audit['review_rows'] % 1000000 == 0:
            print('Scanned', audit['review_rows'], flush=True)
        dates[str(row.get('date', ''))[:4]] += 1
        if not 4 <= float(row.get('stars', 0)) <= 5:
            continue
        audit['positive_reviews'] += 1
        meta = businesses.get(row.get('business_id'))
        user, review = row.get('user_id'), row.get('review_id')
        if not meta or not user or not review:
            continue
        audit['eligible_reviews'] += 1
        city, category = meta
        priority = hashlib.sha256(('review-v2:'+review).encode()).digest()
        previous = chosen.get(user)
        first_city = city if previous is None else previous[3]
        multiple = False if previous is None else previous[4]
        if not multiple and first_city != city:
            audit['users_with_positive_reviews_in_multiple_cities'] += 1
            multiple = True
        event = (priority, city, index[category])
        if previous is None or event < previous[:3]:
            chosen[user] = (*event, first_city, multiple)
        elif multiple != previous[4]:
            chosen[user] = (*previous[:4], multiple)
    events = defaultdict(Counter)
    for _, city, category, _, _ in chosen.values():
        events[city][category] += 1
    audit['retained_users_all_cities'] = len(chosen)
    del chosen
    domain = len(labels)
    context = {}
    target = {}
    city_rows = []
    for city in sorted(city_counts, key=lambda c: (-city_counts[c], c)):
        users = sum(events[city].values())
        city_rows.append(dict(city=city, catalog_businesses=city_counts[city], retained_users=users))
        if city not in audit_cities:
            continue
        context[city] = np.array([catalogs[city][x] for x in labels], dtype=float)
        context[city] /= context[city].sum()
        target[city] = np.array([events[city][i] for i in range(domain)], dtype=float)
        target[city] /= target[city].sum()
    results = []
    swap_rows = []
    for city in audit_cities:
        truth = top_items(target[city], 10)
        sources = [c for c in audit_cities if c != city]
        candidates = set().union(*(set(top_items(target[c], 20)) for c in sources))
        average = np.mean([target[c] for c in sources], axis=0)
        prediction = sorted(candidates, key=lambda i: (-average[i], i))[:10]
        oracle_eval = evaluate(target[city], truth, prediction, candidates)
        own = evaluate(target[city], truth, top_items(context[city], 10), set(range(domain)))
        own_tv = .5*abs(context[city]-target[city]).sum()
        foreign = []
        for other in sources:
            metrics = evaluate(target[city], truth, top_items(context[other], 10), set(range(domain)))
            tv = .5*abs(context[other]-target[city]).sum()
            foreign.append((metrics['recall'], metrics['ndcg'], float(tv)))
            swap_rows.append(dict(target_city=city, context_city=other, **metrics, tv=float(tv)))
        results.append(dict(city=city, users=sum(events[city].values()), businesses=city_counts[city],
            own_context_recall=own['recall'], swapped_context_recall_mean=float(np.mean([x[0] for x in foreign])),
            own_context_ndcg=own['ndcg'], swapped_context_ndcg_mean=float(np.mean([x[1] for x in foreign])),
            own_context_tv=float(own_tv), swapped_context_tv_mean=float(np.mean([x[2] for x in foreign])),
            oracle_source_union_coverage=oracle_eval['coverage'], oracle_average_recall=oracle_eval['recall'],
            oracle_average_ndcg=oracle_eval['ndcg'], oracle_miss_mass=candidate_miss_mass(target[city], candidates),
            top10_mass=float(target[city][truth].sum())))
    for name, records in [('cities.csv',city_rows),('context_diagnostics.csv',results),('swapped_contexts.csv',swap_rows)]:
        with (out/name).open('w', encoding='utf8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=records[0]); w.writeheader(); w.writerows(records)
    payload = dict(schema=1, labels=labels, audit=dict(audit), review_years=dict(sorted(dates.items())),
        selected_cities=audit_cities, selection='12 largest categorized business catalogs before reading reviews',
        events={c:dict(events[c]) for c in events}, catalog={c:dict(catalogs[c]) for c in catalogs},
        context_note='Present metadata snapshot; no historical availability established',
        event_selection='Minimum SHA256(review-v2:review_id) positive matched review across ALL cities and years per user',
        interpretation='Offline suitability diagnostics, not private releases or held-out model confirmation',
        provenance={str(p.resolve()):[p.stat().st_size,p.stat().st_mtime_ns] for p in
                    [data/'yelp_academic_dataset_business.json',data/'yelp_academic_dataset_review.json']})
    (out/'audit.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf8')
    print(json.dumps(dict(audit=dict(audit),domain=domain,selected_cities=audit_cities,
        cities_with_10000_users=sum(r['retained_users']>=10000 for r in city_rows),results=results),indent=2),flush=True)


if __name__ == '__main__':
    main()
